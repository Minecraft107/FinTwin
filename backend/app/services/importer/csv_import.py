"""CSV import preview: parse -> validate -> clean -> categorize -> flag duplicates.

Pure: takes file bytes plus lookups, returns per-row results. Nothing is written here;
the user confirms rows in the UI and they are committed by a separate endpoint.

Accepted columns (case-insensitive, common bank aliases mapped):
  date, description, amount, type, category, merchant, payment_method, is_recurring
  or bank style: date, description, debit, credit
Real bank exports are tolerated: account-info lines above the header, `;` / tab / `|`
delimiters, `0.00` or `-` in the unused debit/credit column, `Cr`/`Dr` amount suffixes and
dates with a time part. Dates are read day-first (Indian format).
"""

import csv
import io
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime

from app.models.enums import CategoryKind, PaymentMethod, TransactionType
from app.schemas.transactions import MAX_AMOUNT
from app.services.ml.categorizer import Categorization

MAX_ROWS = 5000
HEADER_SEARCH_LINES = 30
DELIMITERS = (",", ";", "\t", "|")

HEADER_ALIASES = {
    "narration": "description",
    "details": "description",
    "particulars": "description",
    "remarks": "description",
    "transaction date": "date",
    "txn date": "date",
    "withdrawal": "debit",
    "withdrawal amt": "debit",
    "deposit": "credit",
    "deposit amt": "credit",
    "mode": "payment_method",
    "payment method": "payment_method",
    "recurring": "is_recurring",
}

DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y",
                "%d-%b-%Y", "%d-%b-%y", "%d %b %Y", "%d %b %y", "%Y/%m/%d")  # fmt: skip

TYPE_ALIASES = {
    "income": TransactionType.INCOME,
    "credit": TransactionType.INCOME,
    "cr": TransactionType.INCOME,
    "deposit": TransactionType.INCOME,
    "expense": TransactionType.EXPENSE,
    "debit": TransactionType.EXPENSE,
    "dr": TransactionType.EXPENSE,
    "withdrawal": TransactionType.EXPENSE,
}


class CsvFormatError(ValueError):
    """The file as a whole is unusable (empty, wrong columns, too many rows)."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


@dataclass(frozen=True)
class CategoryRef:
    id: int
    name: str
    kind: CategoryKind


@dataclass
class PreviewRow:
    row: int  # line number in the file (header = 1)
    status: str = "ok"  # ok | warning | duplicate | error
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    duplicate_of: str | None = None  # "existing" | "file"
    category_name: str | None = None
    transaction: dict | None = None  # ready to send back to the commit endpoint


def parse_date(raw: str) -> date | None:
    raw = raw.strip()
    # A time part ("2026-01-05 10:22", "2026-01-05T10:22:00") is ignored.
    for candidate in (raw, raw.replace("T", " ").split(" ")[0]):
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def parse_amount(raw: str) -> float | None:
    """'₹1,23,456.50', '(500)' and '500 Dr' are negative-aware; NaN / infinity are rejected."""
    s = raw.strip().lower()
    for token in ("₹", "inr", "rs.", "rs", ",", " "):
        s = s.replace(token, "")
    negative = (s.startswith("(") and s.endswith(")")) or s.endswith("dr")
    s = s.strip("()").removesuffix("dr").removesuffix("cr")
    try:
        value = float(s)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return -value if negative else value


def _blank(value: str) -> bool:
    """Banks fill the unused debit/credit column with '', '-', or 0.00."""
    return value.strip(" -–") == "" or parse_amount(value) == 0


def _find_header(lines: list[str]) -> tuple[int, str]:
    """(line index, delimiter) of the header row; statements often start with account info."""
    for i, line in enumerate(lines[:HEADER_SEARCH_LINES]):
        for delimiter in DELIMITERS:
            if delimiter not in line:
                continue
            names = next(csv.reader([line], delimiter=delimiter))
            columns = {HEADER_ALIASES.get(n.strip().lower(), n.strip().lower()) for n in names}
            if {"date", "description"} <= columns and columns & {"amount", "debit", "credit"}:
                return i, delimiter
    return 0, ","


def _read_rows(content: bytes) -> tuple[list[str], list[dict[str, str]], int]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    if not text.strip():
        raise CsvFormatError("The file is empty.")
    lines = text.splitlines(keepends=True)
    start, delimiter = _find_header(lines)
    reader = csv.DictReader(io.StringIO("".join(lines[start:])), delimiter=delimiter)
    if not reader.fieldnames:
        raise CsvFormatError("The file has no header row.")
    mapping = {}
    for name in reader.fieldnames:
        key = (name or "").strip().lower()
        mapping[name] = HEADER_ALIASES.get(key, key)
    columns = list(mapping.values())
    has_amount = "amount" in columns or "debit" in columns or "credit" in columns
    missing = [c for c in ("date", "description") if c not in columns]
    if not has_amount:
        missing.append("amount (or debit/credit)")
    if missing:
        raise CsvFormatError(
            "Required columns are missing.", {"missing": missing, "found": reader.fieldnames}
        )
    rows = []
    for raw in reader:
        rows.append({mapping[k]: (v or "").strip() for k, v in raw.items() if k in mapping})
        if len(rows) > MAX_ROWS:
            raise CsvFormatError(f"Too many rows (max {MAX_ROWS}).")
    if not rows:
        raise CsvFormatError("The file has a header but no data rows.")
    return columns, rows, start


def _amount_and_type(
    data: dict[str, str], columns: list[str], out: PreviewRow
) -> tuple[float | None, TransactionType | None]:
    if "debit" in columns or "credit" in columns:
        debit, credit = data.get("debit", ""), data.get("credit", "")
        debit, credit = ("" if _blank(debit) else debit), ("" if _blank(credit) else credit)
        if debit and credit:
            out.errors.append("Both debit and credit are filled.")
            return None, None
        if not debit and not credit:
            out.errors.append("Missing amount (debit/credit both empty).")
            return None, None
        raw, txn_type = (
            (debit, TransactionType.EXPENSE) if debit else (credit, TransactionType.INCOME)
        )
        amount = parse_amount(raw)
        if amount is None:
            out.errors.append(f"Invalid amount '{raw}'.")
            return None, None
        return abs(amount), txn_type

    raw = data.get("amount", "")
    amount = parse_amount(raw) if raw else None
    if amount is None:
        out.errors.append(f"Invalid amount '{raw}'." if raw else "Missing amount.")
        return None, None
    raw_type = data.get("type", "").lower()
    if raw_type:
        txn_type = TYPE_ALIASES.get(raw_type)
        if txn_type is None:
            out.errors.append(f"Unknown type '{data['type']}' (use income/expense).")
            return None, None
    else:
        txn_type = TransactionType.EXPENSE if amount < 0 else TransactionType.INCOME
        out.warnings.append(f"Type inferred as {txn_type.value} from the amount's sign.")
    return abs(amount), txn_type


def preview_csv(
    content: bytes,
    categories: list[CategoryRef],
    categorize_fn: Callable[[str, str | None, TransactionType], Categorization],
    existing_keys: set,
    key_fn: Callable[[date, float, str, str], tuple],
    today: date | None = None,
) -> dict:
    today = today or date.today()
    columns, rows, header_index = _read_rows(content)
    by_name = {c.name.lower(): c for c in categories}
    seen: set = set()
    results: list[PreviewRow] = []

    for index, data in enumerate(rows):
        out = PreviewRow(row=header_index + index + 2)  # file line number
        results.append(out)

        raw_date = data.get("date", "")
        txn_date = parse_date(raw_date) if raw_date else None
        if txn_date is None:
            out.errors.append(f"Invalid date '{raw_date}'." if raw_date else "Missing date.")
        elif txn_date > today:
            out.errors.append(f"Date {txn_date.isoformat()} is in the future.")

        description = data.get("description", "")
        if not description:
            out.errors.append("Missing description.")
        elif len(description) > 255:
            description = description[:255]
            out.warnings.append("Description truncated to 255 characters.")

        amount, txn_type = _amount_and_type(data, columns, out)
        if amount == 0:
            out.errors.append("Amount cannot be zero.")
        elif amount is not None and amount > MAX_AMOUNT:
            out.errors.append("Amount is too large.")

        if out.errors:
            out.status = "error"
            continue

        merchant = data.get("merchant") or None
        if merchant and len(merchant) > 120:
            merchant = merchant[:120]

        # Category: the file's value if valid for this type, else automatic.
        source, confidence = "import", None
        category = by_name.get(data.get("category", "").lower())
        income_type = txn_type == TransactionType.INCOME
        if category and (category.kind == CategoryKind.INCOME) != income_type:
            out.warnings.append(f"Category '{category.name}' does not fit a {txn_type.value}.")
            category = None
        elif data.get("category") and category is None:
            out.warnings.append(f"Unknown category '{data['category']}'.")
        if category is None:
            result = categorize_fn(description, merchant, txn_type)
            category = by_name[result.category.lower()]
            source, confidence = result.source.value, result.confidence
            if data.get("category"):
                out.warnings[-1] += f" Auto-categorized as {category.name}."

        method = data.get("payment_method", "").lower().replace(" ", "_")
        payment_method = method if method in PaymentMethod._value2member_map_ else "other"

        key = key_fn(txn_date, amount, txn_type.value, description)
        if key in existing_keys:
            out.duplicate_of = "existing"
        elif key in seen:
            out.duplicate_of = "file"
        seen.add(key)

        out.category_name = category.name
        out.transaction = {
            "date": txn_date.isoformat(),
            "amount": round(amount, 2),
            "type": txn_type.value,
            "description": description,
            "merchant": merchant,
            "category_id": category.id,
            "category_source": source,
            "category_confidence": confidence,
            "payment_method": payment_method,
            "is_recurring": data.get("is_recurring", "").lower() in ("true", "yes", "y", "1"),
        }
        out.status = "duplicate" if out.duplicate_of else "warning" if out.warnings else "ok"

    counts = {
        s: sum(r.status == s for r in results) for s in ("ok", "warning", "duplicate", "error")
    }
    return {
        "rows": [r.__dict__ for r in results],
        "summary": {
            "total": len(results),
            **counts,
            "importable": counts["ok"] + counts["warning"],
        },
    }
