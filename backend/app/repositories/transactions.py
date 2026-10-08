from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_

from app.extensions import db
from app.models import ExpenseCategory, Transaction
from app.models.enums import CategoryKind, CategorySource, TransactionType
from app.services.ml.categorizer import duplicate_text, normalize_description

DuplicateKey = tuple[date, float, str, str]


def duplicate_key(d: date, amount: float, txn_type: str, description: str) -> DuplicateKey:
    return d, round(float(amount), 2), str(txn_type), duplicate_text(description)


@dataclass
class TransactionFilters:
    date_from: date | None = None
    date_to: date | None = None
    category_id: int | None = None
    type: TransactionType | None = None
    q: str | None = None


def list_transactions(
    user_id: int, f: TransactionFilters, page: int, per_page: int
) -> tuple[list[Transaction], int]:
    query = db.select(Transaction).where(Transaction.user_id == user_id)
    if f.date_from:
        query = query.where(Transaction.date >= f.date_from)
    if f.date_to:
        query = query.where(Transaction.date <= f.date_to)
    if f.category_id:
        query = query.where(Transaction.category_id == f.category_id)
    if f.type:
        query = query.where(Transaction.type == f.type)
    if f.q:
        like = f"%{f.q}%"
        query = query.where(
            or_(Transaction.description.ilike(like), Transaction.merchant.ilike(like))
        )
    total = db.session.scalar(db.select(db.func.count()).select_from(query.subquery()))
    items = db.session.scalars(
        query.order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
    ).all()
    return list(items), total


def all_categories() -> list[ExpenseCategory]:
    return list(db.session.scalars(db.select(ExpenseCategory).order_by(ExpenseCategory.id)))


def category_or_none(category_id: int) -> ExpenseCategory | None:
    return db.session.get(ExpenseCategory, category_id)


def category_id_by_name(name: str) -> int:
    return db.session.scalar(db.select(ExpenseCategory.id).where(ExpenseCategory.name == name))


def kind_matches_type(kind: CategoryKind, txn_type: TransactionType | str) -> bool:
    return (kind == CategoryKind.INCOME) == (TransactionType(txn_type) == TransactionType.INCOME)


def category_memory(user_id: int) -> dict[str, str]:
    """normalized description -> category name, learned from the user's manual corrections
    (latest correction wins)."""
    rows = db.session.execute(
        db.select(Transaction.description, ExpenseCategory.name)
        .join(ExpenseCategory)
        .where(
            Transaction.user_id == user_id,
            Transaction.category_source == CategorySource.MANUAL,
        )
        .order_by(Transaction.updated_at, Transaction.id)
    )
    return {normalize_description(desc): name for desc, name in rows}


def existing_duplicate_keys(user_id: int, start: date, end: date) -> set[DuplicateKey]:
    rows = db.session.execute(
        db.select(
            Transaction.date, Transaction.amount, Transaction.type, Transaction.description
        ).where(Transaction.user_id == user_id, Transaction.date.between(start, end))
    )
    return {duplicate_key(d, a, t, desc) for d, a, t, desc in rows}
