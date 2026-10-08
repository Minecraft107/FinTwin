"""Transaction categorization cascade: user memory -> keyword rules -> ML -> fallback.

Works fully offline; no external API is used for categorization.
"""

import re
from dataclasses import dataclass

from app.models.enums import CategorySource, TransactionType
from app.seed.categories import FALLBACK_EXPENSE_CATEGORY, FALLBACK_INCOME_CATEGORY
from app.services.ml.artifacts import load_artifact

RULE_CONFIDENCE = 0.9
ML_CONFIDENCE_THRESHOLD = 0.55  # below this the ML guess is not trusted -> fallback category

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


def match_rules(
    description: str, merchant: str | None, txn_type: TransactionType | str
) -> str | None:
    """Keyword rules only (also used by the offline evaluation as the rules-only baseline)."""
    text = _clean(f"{description} {merchant or ''}", keep_digits=True)  # keeps "1mg"
    for category, pattern in _COMPILED[TransactionType(txn_type)]:
        if pattern.search(text):
            return category
    return None


def _ml_guess(description: str, merchant: str | None) -> tuple[str, float] | None:
    model = load_artifact("categorizer")
    if model is None:
        return None
    proba = model.predict_proba([f"{description} {merchant or ''}"])[0]
    best = int(proba.argmax())
    return str(model.classes_[best]), float(proba[best])


def categorize(
    description: str,
    merchant: str | None,
    txn_type: TransactionType | str,
    memory: dict[str, str] | None = None,
) -> Categorization:
    """Cascade: user memory -> keyword rules -> ML classifier (expenses, if confident) ->
    fallback. `memory` maps normalized description -> category from the user's manual fixes."""
    txn_type = TransactionType(txn_type)
    key = normalize_description(description)
    if memory and key in memory:
        return Categorization(memory[key], CategorySource.MEMORY, 1.0)

    rule = match_rules(description, merchant, txn_type)
    if rule:
        return Categorization(rule, CategorySource.RULE, RULE_CONFIDENCE)

    if txn_type == TransactionType.EXPENSE:
        guess = _ml_guess(description, merchant)
        if guess and guess[1] >= ML_CONFIDENCE_THRESHOLD:
            return Categorization(guess[0], CategorySource.ML, round(guess[1], 4))

    fallback = (
        FALLBACK_INCOME_CATEGORY
        if txn_type == TransactionType.INCOME
        else FALLBACK_EXPENSE_CATEGORY
    )
    return Categorization(fallback, CategorySource.RULE, 0.0)
