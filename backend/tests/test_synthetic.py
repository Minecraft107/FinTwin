from collections import Counter
from datetime import date

from app.seed.categories import CATEGORIES
from app.seed.demo import demo_persona
from app.seed.synthetic import Persona, generate_transactions, month_starts

END = date(2026, 10, 8)
CATEGORY_NAMES = {name for name, *_ in CATEGORIES}


def _rows(**kwargs):
    return generate_transactions(demo_persona(), END, 24, seed=7, **kwargs)


def test_month_starts_cross_year_boundary():
    assert month_starts(date(2026, 2, 15), 3) == [
        date(2025, 12, 1),
        date(2026, 1, 1),
        date(2026, 2, 1),
    ]


def test_deterministic_for_same_seed():
    assert _rows() == _rows()
    assert generate_transactions(Persona(), END, 6, seed=1) != generate_transactions(
        Persona(), END, 6, seed=2
    )


def test_covers_window_and_never_future():
    rows = _rows()
    assert min(r["date"] for r in rows) == date(2024, 11, 1)
    assert max(r["date"] for r in rows) <= END


def test_rows_are_valid():
    for r in _rows():
        assert r["amount"] > 0
        assert r["category"] in CATEGORY_NAMES
        assert r["type"] in ("income", "expense")


def test_salary_every_month_and_raise_applied():
    salaries = [r for r in _rows() if r["category"] == "Salary"]
    assert len(salaries) == 24
    assert salaries[0]["amount"] == 95_000
    assert salaries[-1]["amount"] == 95_000 * 1.08


def test_injected_anomalies_are_labelled():
    labels = Counter(r["anomaly"] for r in _rows() if r["anomaly"])
    assert labels == {"large_purchase": 2, "duplicate": 1, "abnormal_month": 6}


def test_festive_months_have_more_shopping():
    rows = _rows()
    by_month = Counter(
        r["date"].month for r in rows if r["category"] == "Shopping" and not r["anomaly"]
    )
    festive = by_month[10] + by_month[11]
    others = sum(v for m, v in by_month.items() if m not in (10, 11)) / 10
    assert festive / 2 > others  # festive months average more purchases


def test_dining_creep_in_final_months():
    rows = _rows()

    def dining(ym):
        return sum(
            r["amount"] for r in rows
            if r["category"] == "Food & Dining" and not r["anomaly"]
            and (r["date"].year, r["date"].month) == ym
        )  # fmt: skip

    before = sum(dining(ym) for ym in [(2026, 1), (2026, 2), (2026, 3)]) / 3
    after = sum(dining(ym) for ym in [(2026, 7), (2026, 8), (2026, 9)]) / 3
    assert after > before * 1.3
