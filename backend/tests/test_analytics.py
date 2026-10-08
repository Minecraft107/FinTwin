from datetime import date

import pytest

from app.services.analytics import aggregations as agg
from app.services.financial.formulas import future_value, value_months_ago
from app.utils.dates import add_months, last_complete_month_end, months_between
from tests.test_twin_builder import frame

TODAY = date(2026, 10, 8)

ROWS = [
    ("2026-08-01", 100_000, "Salary"),
    ("2026-08-05", 30_000, "Housing"),
    ("2026-08-20", 10_000, "Shopping"),
    ("2026-09-01", 100_000, "Salary"),
    ("2026-09-05", 30_000, "Housing"),
    ("2026-09-10", 5_000, "Investment"),
    ("2026-09-12", 2_000, "Groceries"),
    ("2026-09-20", 15_000, "Shopping"),
]
TXNS = frame(ROWS)


# ---------------- dates & formulas ----------------


def test_date_helpers():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2026, 3, 15), -3) == date(2025, 12, 15)
    assert months_between(date(2025, 11, 30), date(2026, 2, 1)) == 3
    assert last_complete_month_end(date(2026, 10, 8)) == date(2026, 9, 30)
    assert last_complete_month_end(date(2026, 9, 30)) == date(2026, 9, 30)
    assert last_complete_month_end(date(2026, 1, 1)) == date(2025, 12, 31)


@pytest.mark.parametrize("rate", [0.0, 0.11])
def test_value_months_ago_inverts_future_value(rate):
    past = value_months_ago(250_000, 5_000, rate, 12)
    assert future_value(past, 5_000, rate, 12) == pytest.approx(250_000)


def test_value_months_ago_floors_at_zero():
    assert value_months_ago(10_000, 5_000, 0.0, 12) == 0


# ---------------- ranges ----------------


@pytest.mark.parametrize(
    "key,start",
    [
        ("7d", date(2026, 10, 2)),
        ("30d", date(2026, 9, 9)),
        ("3m", date(2026, 7, 9)),
        ("12m", date(2025, 10, 9)),
        (None, date(2026, 7, 9)),  # default 3m
    ],
)
def test_resolve_presets(key, start):
    assert agg.resolve_range(key, None, None, TODAY) == (start, TODAY)


def test_resolve_custom():
    assert agg.resolve_range(None, date(2026, 1, 1), date(2026, 1, 31), TODAY) == (
        date(2026, 1, 1),
        date(2026, 1, 31),
    )


@pytest.mark.parametrize(
    "key,start,end",
    [
        ("2w", None, None),
        (None, date(2026, 2, 1), None),
        (None, date(2026, 2, 1), date(2026, 1, 1)),
        (None, date(2015, 1, 1), date(2026, 1, 1)),
    ],
)
def test_resolve_invalid(key, start, end):
    with pytest.raises(ValueError):
        agg.resolve_range(key, start, end, TODAY)


# ---------------- aggregations ----------------


def test_summarize_september():
    s = agg.summarize(TXNS, date(2026, 9, 1), date(2026, 9, 30))
    assert s["income"] == 100_000
    assert s["expenses"] == 47_000  # 30k + 2k essential + 15k discretionary
    assert s["investments"] == 5_000
    assert s["net_cash_flow"] == 48_000
    assert s["savings_ratio"] == pytest.approx(0.53)
    assert s["avg_daily_spend"] == pytest.approx(47_000 / 30)
    assert s["transaction_count"] == 5


def test_overview_compares_with_previous_equal_period():
    out = agg.overview(TXNS, date(2026, 9, 1), date(2026, 9, 30))
    assert out["previous_period"] == {"from": "2026-08-02", "to": "2026-08-31"}
    # previous period excludes 1 Aug salary: 0 income -> change undefined
    assert out["change"]["income"] == {"abs": 100_000, "pct": None}
    assert out["change"]["expenses"]["pct"] == pytest.approx((47_000 - 40_000) / 40_000 * 100)
    # previous net = -40k, current = +48k: an improvement must read as positive
    assert out["change"]["net_cash_flow"] == {"abs": 88_000, "pct": pytest.approx(220.0)}
    assert out["essential_share"] == pytest.approx(32_000 / 47_000)


def test_categories_share_and_change():
    rows = agg.categories(TXNS, date(2026, 9, 1), date(2026, 9, 30))
    assert [r["category"] for r in rows] == ["Housing", "Shopping", "Investment", "Groceries"]
    shopping = rows[1]
    assert shopping["share"] == pytest.approx(15_000 / 52_000)
    assert shopping["previous_total"] == 10_000
    assert shopping["change_pct"] == pytest.approx(50.0)
    assert rows[3]["change_pct"] is None  # no groceries in the previous period


def test_monthly_trends_fill_empty_months_and_track_cash():
    rows = agg.trends(TXNS, date(2026, 7, 1), date(2026, 9, 30), "month", opening_cash=1_000)
    assert [r["period"] for r in rows] == ["2026-07", "2026-08", "2026-09"]
    assert rows[0]["net_cash_flow"] == 0 and rows[0]["savings_ratio"] is None
    assert rows[1]["net_cash_flow"] == 60_000
    assert [r["cash_balance"] for r in rows] == [1_000, 61_000, 109_000]


def test_daily_trends():
    rows = agg.trends(TXNS, date(2026, 9, 1), date(2026, 9, 5), "day", opening_cash=0)
    assert len(rows) == 5
    assert rows[0]["income"] == 100_000 and rows[4]["essential"] == 30_000
    assert agg.granularity_for(date(2026, 9, 1), date(2026, 9, 30)) == "day"
    assert agg.granularity_for(date(2026, 1, 1), date(2026, 9, 30)) == "month"


def test_trends_on_empty_range():
    rows = agg.trends(TXNS.iloc[0:0], date(2026, 1, 1), date(2026, 2, 28), "month", 500)
    assert [r["cash_balance"] for r in rows] == [500, 500]


def test_top_merchants_falls_back_to_description():
    txns = TXNS.copy()
    txns.loc[txns["category"] == "Shopping", "merchant"] = "Amazon"
    rows = agg.top_merchants(txns, date(2026, 8, 1), date(2026, 9, 30), limit=2)
    assert rows[0] == {"merchant": "x", "total": 67_000, "count": 4, "category": "Housing"}
    assert rows[1]["merchant"] == "Amazon" and rows[1]["total"] == 25_000


@pytest.mark.parametrize(
    "narration,label",
    [
        ("UPI/40212/RENT - UPI/LANDLORD", "UPI/RENT - UPI/LANDLORD"),
        ("UPI/40234/DMART ORDER", "UPI/DMART ORDER"),
        ("AMAZON ORDER 402-1234567", "AMAZON ORDER"),
        ("1MG PHARMACY", "1MG PHARMACY"),
        ("12345", "12345"),
    ],
)
def test_merchant_label_drops_reference_numbers(narration, label):
    assert agg.merchant_label(narration) == label


def test_monthly_buckets_start_on_the_first():
    assert agg.bucket_start(date(2025, 10, 9), "month") == date(2025, 10, 1)
    assert agg.bucket_start(date(2025, 10, 9), "day") == date(2025, 10, 9)
