import datetime as dt

from pydantic import Field, field_validator

from app.models.enums import CategoryKind, CategorySource, PaymentMethod, TransactionType
from app.schemas.common import InModel, OutModel

MAX_AMOUNT = 1e11


def _not_future(v: dt.date | None) -> dt.date | None:
    if v is not None and v > dt.date.today():
        raise ValueError("date cannot be in the future")
    return v


class TransactionIn(InModel):
    date: dt.date
    amount: float = Field(gt=0, le=MAX_AMOUNT)
    type: TransactionType
    description: str = Field(min_length=1, max_length=255)
    category_id: int | None = None  # omitted -> automatic categorization
    merchant: str | None = Field(default=None, max_length=120)
    payment_method: PaymentMethod = PaymentMethod.OTHER
    is_recurring: bool = False

    _date = field_validator("date")(_not_future)


class TransactionUpdate(InModel):
    date: dt.date | None = None
    amount: float | None = Field(default=None, gt=0, le=MAX_AMOUNT)
    type: TransactionType | None = None
    description: str | None = Field(default=None, min_length=1, max_length=255)
    category_id: int | None = None
    merchant: str | None = Field(default=None, max_length=120)
    payment_method: PaymentMethod | None = None
    is_recurring: bool | None = None

    _date = field_validator("date")(_not_future)


class ImportRow(TransactionIn):
    """A row confirmed by the user in the import preview (re-validated server-side)."""

    category_id: int
    category_source: CategorySource = CategorySource.IMPORT
    category_confidence: float | None = Field(default=None, ge=0, le=1)


class ImportCommit(InModel):
    transactions: list[ImportRow] = Field(min_length=1, max_length=5000)


class CategoryOut(OutModel):
    id: int
    name: str
    kind: CategoryKind
    color: str
    icon: str


class TransactionOut(OutModel):
    id: int
    date: dt.date
    amount: float
    type: TransactionType
    description: str
    merchant: str | None
    payment_method: PaymentMethod
    is_recurring: bool
    category: CategoryOut
    category_source: CategorySource
    category_confidence: float | None
