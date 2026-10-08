"""Transaction categorization cascade: user memory -> keyword rules -> (ML, Phase 7) -> fallback.

Works fully offline; no external API is used for categorization.
"""

import re
from dataclasses import dataclass

from app.models.enums import CategorySource, TransactionType
from app.seed.categories import FALLBACK_EXPENSE_CATEGORY, FALLBACK_INCOME_CATEGORY

RULE_CONFIDENCE = 0.9

# Ordered: the first match wins, so specific patterns precede generic ones
# (e.g. "swiggy instamart" -> Groceries before "swiggy" -> Food & Dining,
#  "uber trip" -> Transport before "trip" -> Travel, "amazon prime" before "amazon").
INCOME_RULES: list[tuple[str, str]] = [
    ("Salary", r"salary|payroll|\bsal\b|stipend"),
    ("Bonus", r"bonus|incentive"),
    ("Interest", r"interest|\bint\b|dividend"),
    ("Freelance", r"freelance|upwork|fiverr|toptal|consult|invoice"),
    ("Other Income", r"refund|cashback|reversal|reimburse"),
]

EXPENSE_RULES: list[tuple[str, str]] = [
    ("EMI/Debt", r"\bemi\b|\bloan\b|credit card (bill|payment)|\bcc (bill|payment)"),
    (
        "Investment",
        r"\bsip\b|mutual fund|zerodha|groww|upstox|kuvera|\bppf\b|\bnps\b|"
        r"fixed deposit|\bfd\b|smallcase|\betf\b|\bsgb\b|gold bond",
    ),
    ("Insurance", r"insurance|\blic\b|policy|star health|hdfc ergo|icici lombard|acko"),
    ("Housing", r"\brent\b|landlord|nobroker|society maintenance|maintenance charge"),
    (
        "Groceries",
        r"instamart|bigbasket|dmart|blinkit|zepto|grofers|jiomart|reliance fresh|"
        r"more supermarket|spencer|nature s basket|kirana|grocer|supermarket",
    ),
    (
        "Transport",
        r"uber|\bola\b|rapido|metro|namma yatri|petrol|diesel|\bfuel\b|hpcl|iocl|"
        r"indian oil|bpcl|fastag|parking|\bcab\b|auto rickshaw",
    ),
    (
        "Utilities",
        r"electricity|bescom|tata power|adani electricity|msedcl|water bill|"
        r"indane|bharat gas|hp gas|\bgas\b|broadband|fiber|fibernet|airtel|\bjio\b|"
        r"vodafone|\bvi\b|bsnl|\bdth\b|tata play|postpaid|prepaid|recharge",
    ),
    (
        "Subscriptions",
        r"netflix|spotify|prime|hotstar|disney|youtube premium|apple com|icloud|"
        r"google one|cult fit|cultfit|\bgym\b|membership|subscription|sonyliv|zee5",
    ),
    (
        "Food & Dining",
        r"swiggy|zomato|restaurant|\bcafe\b|starbucks|domino|pizza|mcdonald|"
        r"\bkfc\b|burger|haldiram|chaayos|eatsure|\bdine\b|bakery",
    ),
    ("Entertainment", r"bookmyshow|\bpvr\b|inox|cinema|steam|playstation|xbox|concert|movie"),
    (
        "Shopping",
        r"amazon|flipkart|myntra|ajio|meesho|nykaa|decathlon|croma|reliance digital|"
        r"ikea|lifestyle|shoppers stop|tata cliq|\bmall\b",
    ),
    (
        "Healthcare",
        r"pharmacy|apollo|medplus|1mg|pharmeasy|netmeds|hospital|clinic|doctor|"
        r"diagnostic|\blab\b|dental|practo",
    ),
    (
        "Education",
        r"udemy|coursera|course|tuition|school|college|university|\bfees?\b|byju|"
        r"unacademy|\bbooks?\b",
    ),
    (
        "Travel",
        r"makemytrip|goibibo|cleartrip|irctc|indigo|air india|vistara|spicejet|akasa|"
        r"hotel|\boyo\b|airbnb|\btaj\b|redbus|flight|\btrip\b|holiday",
    ),
    ("Personal Care", r"salon|\bspa\b|urban company|barber|grooming|parlour"),
    ("Family Support", r"parents|family|\bmom\b|\bdad\b|mother|father"),
]

_COMPILED = {
    TransactionType.INCOME: [(c, re.compile(p)) for c, p in INCOME_RULES],
    TransactionType.EXPENSE: [(c, re.compile(p)) for c, p in EXPENSE_RULES],
}


@dataclass(frozen=True)
class Categorization:
    category: str
    source: CategorySource
    confidence: float | None


def _clean(text: str, keep_digits: bool) -> str:
    text = re.sub(r"[^a-z0-9 ]+" if keep_digits else r"[^a-z ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def normalize_description(text: str) -> str:
    """Category-memory key: no digits/punctuation, since UPI refs and order ids vary per
    payment to the same merchant."""
    return _clean(text, keep_digits=False)


def duplicate_text(text: str) -> str:
    """Duplicate-detection key: keeps digits, so 'ORDER 1234' and 'ORDER 5678' stay distinct."""
    return _clean(text, keep_digits=True)


def categorize(
    description: str,
    merchant: str | None,
    txn_type: TransactionType | str,
    memory: dict[str, str] | None = None,
) -> Categorization:
    """`memory` maps normalized description -> category name from the user's manual fixes."""
    txn_type = TransactionType(txn_type)
    key = normalize_description(description)
    if memory and key in memory:
        return Categorization(memory[key], CategorySource.MEMORY, 1.0)

    text = _clean(f"{description} {merchant or ''}", keep_digits=True)  # keeps "1mg"
    for category, pattern in _COMPILED[txn_type]:
        if pattern.search(text):
            return Categorization(category, CategorySource.RULE, RULE_CONFIDENCE)

    fallback = (
        FALLBACK_INCOME_CATEGORY
        if txn_type == TransactionType.INCOME
        else FALLBACK_EXPENSE_CATEGORY
    )
    return Categorization(fallback, CategorySource.RULE, 0.0)
