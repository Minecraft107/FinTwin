from datetime import date

import pytest

from app.models.enums import CategorySource
from app.seed.demo import demo_persona
from app.seed.synthetic import generate_transactions
from app.services.ml.categorizer import categorize, normalize_description


@pytest.mark.parametrize(
    "description,merchant,txn_type,expected",
    [
        ("UPI/4567812/SWIGGY INSTAMART", None, "expense", "Groceries"),
        ("UPI/4567812/SWIGGY", None, "expense", "Food & Dining"),
        ("UBER TRIP 23 OCT", None, "expense", "Transport"),
        ("Weekend trip to Coorg", None, "expense", "Travel"),
        ("AMAZON PRIME MEMBERSHIP", None, "expense", "Subscriptions"),
        ("AMAZON PAY - order 403-112", None, "expense", "Shopping"),
        ("POS 1MG HEALTHCARE", None, "expense", "Healthcare"),
        ("LIC POLICY PREMIUM", None, "expense", "Insurance"),
        ("NACH HDFC HOME LOAN EMI", None, "expense", "EMI/Debt"),
        ("ZERODHA COIN SIP", None, "expense", "Investment"),
        ("METRO CARD RECHARGE", None, "expense", "Transport"),
        ("JIO PREPAID RECHARGE", None, "expense", "Utilities"),
        ("NEFT SAL OCT ACME", None, "income", "Salary"),
        ("CREDIT INTEREST", None, "income", "Interest"),
        ("FLIPKART REFUND", None, "income", "Other Income"),
        ("Payment", "Croma", "expense", "Shopping"),  # merchant field is used too
    ],
)
def test_rules(description, merchant, txn_type, expected):
    result = categorize(description, merchant, txn_type)
    assert result.category == expected
    assert result.source == CategorySource.RULE
    assert result.confidence == 0.9


def test_unmatched_falls_back_by_type():
    assert categorize("XYZ 123", None, "expense").category == "Other"
    assert categorize("XYZ 123", None, "income").category == "Other Income"
    assert categorize("XYZ 123", None, "income").confidence == 0.0


def test_user_memory_overrides_rules():
    memory = {normalize_description("SWIGGY ORDER 991"): "Groceries"}
    result = categorize("SWIGGY ORDER 12", None, "expense", memory)
    assert result.category == "Groceries"
    assert result.source == CategorySource.MEMORY


def test_normalization_strips_reference_numbers():
    assert normalize_description("UPI/123456/Swiggy-Order") == normalize_description(
        "upi 98 swiggy order"
    )


def test_rules_cover_every_synthetic_description():
    # Sanity check, not a performance claim: the ML evaluation in Phase 7 uses held-out data.
    rows = generate_transactions(demo_persona(), date(2026, 10, 8), 24, seed=3)
    predicted = {
        (r["description"], r["category"]): categorize(
            r["description"], r["merchant"], r["type"]
        ).category
        for r in rows
    }
    wrong = {key: got for key, got in predicted.items() if got != key[1]}
    assert not wrong
