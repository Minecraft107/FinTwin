from datetime import date

from flask import Blueprint, Response, request

from app.extensions import db
from app.models import Transaction
from app.models.enums import CategorySource, TransactionType
from app.repositories import transactions as repo
from app.repositories.base import get_owned
from app.schemas.common import dump, parse_body
from app.schemas.transactions import (
    CategoryOut,
    ImportCommit,
    TransactionIn,
    TransactionOut,
    TransactionUpdate,
)
from app.services.digital_twin.service import recalculate_after_writes
from app.services.importer.csv_import import CategoryRef, CsvFormatError, preview_csv
from app.services.ml.categorizer import categorize
from app.utils.auth import current_user_id, protect
from app.utils.http import ApiError, ok

bp = recalculate_after_writes(
    protect(Blueprint("transactions", __name__)), skip=("import_preview",)
)

MAX_PER_PAGE = 200


def _query_date(name: str) -> date | None:
    raw = request.args.get(name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise ApiError(400, "VALIDATION_ERROR", f"'{name}' must be YYYY-MM-DD.") from None


def _query_int(name: str, default: int | None, minimum: int = 1) -> int | None:
    raw = request.args.get(name)
    if raw is None or raw == "":
        return default
    if not raw.isdigit() or int(raw) < minimum:
        raise ApiError(400, "VALIDATION_ERROR", f"'{name}' must be an integer >= {minimum}.")
    return int(raw)


def _checked_category(category_id: int, txn_type: TransactionType | str) -> int:
    category = repo.category_or_none(category_id)
    if category is None:
        raise ApiError(400, "VALIDATION_ERROR", f"Category {category_id} does not exist.")
    if not repo.kind_matches_type(category.kind, txn_type):
        raise ApiError(
            400, "VALIDATION_ERROR", f"Category '{category.name}' cannot be used for {txn_type}."
        )
    return category_id


@bp.get("/categories")
def list_categories():
    return ok([dump(CategoryOut, c) for c in repo.all_categories()])


@bp.get("/transactions")
def list_transactions():
    raw_type = request.args.get("type")
    if raw_type and raw_type not in TransactionType._value2member_map_:
        raise ApiError(400, "VALIDATION_ERROR", "'type' must be income or expense.")
    filters = repo.TransactionFilters(
        date_from=_query_date("from"),
        date_to=_query_date("to"),
        category_id=_query_int("category_id", None),
        type=TransactionType(raw_type) if raw_type else None,
        q=(request.args.get("q") or "").strip() or None,
    )
    page = _query_int("page", 1)
    per_page = min(_query_int("per_page", 50), MAX_PER_PAGE)
    items, total = repo.list_transactions(current_user_id(), filters, page, per_page)
    return ok(
        [dump(TransactionOut, t) for t in items],
        meta={"page": page, "per_page": per_page, "total": total},
    )


@bp.post("/transactions")
def create_transaction():
    body = parse_body(TransactionIn)
    user_id = current_user_id()
    fields = body.model_dump(exclude={"category_id"})
    if body.category_id is not None:
        category_id = _checked_category(body.category_id, body.type)
        source, confidence = CategorySource.MANUAL, None
    else:
        result = categorize(
            body.description, body.merchant, body.type, repo.category_memory(user_id)
        )
        category_id = repo.category_id_by_name(result.category)
        source, confidence = result.source, result.confidence
    txn = Transaction(
        user_id=user_id,
        category_id=category_id,
        category_source=source,
        category_confidence=confidence,
        **fields,
    )
    db.session.add(txn)
    db.session.commit()
    return ok(dump(TransactionOut, txn), status=201)


@bp.put("/transactions/<int:txn_id>")
def update_transaction(txn_id: int):
    body = parse_body(TransactionUpdate)
    txn = get_owned(Transaction, txn_id, current_user_id())
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    new_type = changes.get("type", txn.type)
    if "category_id" in changes:
        _checked_category(changes["category_id"], new_type)
        # A user correction: remembered for future imports of the same description.
        txn.category_source, txn.category_confidence = CategorySource.MANUAL, None
    elif "type" in changes and not repo.kind_matches_type(txn.category.kind, new_type):
        raise ApiError(
            400, "VALIDATION_ERROR", "Changing the type requires a matching category_id."
        )
    for name, value in changes.items():
        setattr(txn, name, value)
    db.session.commit()
    db.session.refresh(txn)
    return ok(dump(TransactionOut, txn))


@bp.delete("/transactions/<int:txn_id>")
def delete_transaction(txn_id: int):
    db.session.delete(get_owned(Transaction, txn_id, current_user_id()))
    db.session.commit()
    return "", 204


@bp.get("/transactions/import/sample")
def import_sample():
    """A fresh bank-statement CSV (6 months ending last month) to try the import with."""
    from app.seed.sample_csv import sample_statement

    return Response(
        sample_statement(6),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=fintwin-sample-statement.csv"},
    )


@bp.post("/transactions/import/preview")
def import_preview():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        raise ApiError(400, "VALIDATION_ERROR", "Attach a CSV file in the 'file' field.")
    if not upload.filename.lower().endswith(".csv"):
        raise ApiError(400, "VALIDATION_ERROR", "Only .csv files are supported.")
    user_id = current_user_id()
    memory = repo.category_memory(user_id)
    categories = [CategoryRef(c.id, c.name, c.kind) for c in repo.all_categories()]
    try:
        preview = preview_csv(
            upload.read(),
            categories,
            lambda desc, merchant, txn_type: categorize(desc, merchant, txn_type, memory),
            repo.existing_duplicate_keys(user_id, date.min, date.today()),
            repo.duplicate_key,
        )
    except CsvFormatError as e:
        raise ApiError(422, "INVALID_CSV", str(e), e.details) from None
    return ok(preview)


@bp.post("/transactions/import")
def import_commit():
    body = parse_body(ImportCommit)
    user_id = current_user_id()
    categories = {c.id: c for c in repo.all_categories()}
    for i, row in enumerate(body.transactions):
        category = categories.get(row.category_id)
        if category is None or not repo.kind_matches_type(category.kind, row.type):
            raise ApiError(
                400,
                "VALIDATION_ERROR",
                f"Row {i}: category {row.category_id} is not valid for {row.type}.",
            )
    db.session.add_all(
        Transaction(user_id=user_id, **row.model_dump()) for row in body.transactions
    )
    db.session.commit()
    return ok({"imported": len(body.transactions)}, status=201)
