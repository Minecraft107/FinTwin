"""Spending analytics over a date range. Pure pandas over the transactions DataFrame."""

import re
from datetime import date, timedelta

import pandas as pd

from app.services.digital_twin.builder import KINDS
from app.utils.dates import add_months

RANGES = {"7d": ("days", 7), "30d": ("days", 30), "3m": ("months", 3), "6m": ("months", 6),
          "12m": ("months", 12)}  # fmt: skip
DEFAULT_RANGE = "3m"
MAX_CUSTOM_DAYS = 5 * 366
DAILY_GRANULARITY_MAX_DAYS = 62


def resolve_range(
    key: str | None, start: date | None, end: date | None, today: date
) -> tuple[date, date]:
    """Preset (`7d`, `30d`, `3m`, `6m`, `12m`) or custom `from`/`to`. Raises ValueError."""
    if start or end:
        if not (start and end):
            raise ValueError("Custom ranges need both 'from' and 'to'.")
        if start > end:
            raise ValueError("'from' must be on or before 'to'.")
        if (end - start).days > MAX_CUSTOM_DAYS:
            raise ValueError("Custom ranges are limited to 5 years.")
        return start, end
    key = key or DEFAULT_RANGE
    if key not in RANGES:
        raise ValueError(f"'range' must be one of {', '.join(RANGES)} (or use from/to).")
    unit, amount = RANGES[key]
    if unit == "days":
        return today - timedelta(days=amount - 1), today
    return add_months(today, -amount) + timedelta(days=1), today


def _slice(txns: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    dates = txns["date"].dt.date
    return txns[(dates >= start) & (dates <= end)]


def _pct_change(current: float, previous: float) -> float | None:
    """Relative to the size of the previous value, so a move from -10k to +5k reads as +150%
    (an improvement), not a sign-flipped -150%. Undefined when previous is 0."""
    return (current - previous) / abs(previous) * 100 if previous else None


def summarize(txns: pd.DataFrame, start: date, end: date) -> dict:
    window = _slice(txns, start, end)
    by_kind = window.groupby("kind")["amount"].sum()
    totals = {k: float(by_kind.get(k, 0.0)) for k in KINDS}
    expenses = totals["essential"] + totals["discretionary"]
    income = totals["income"]
    days = (end - start).days + 1
    return {
        "income": income,
        "expenses": expenses,
        "essential": totals["essential"],
        "discretionary": totals["discretionary"],
        "debt_payments": totals["debt"],
        "investments": totals["investment"],
        "net_cash_flow": income - expenses - totals["debt"] - totals["investment"],
        "savings_ratio": (income - expenses - totals["debt"]) / income if income else None,
        "avg_daily_spend": expenses / days,
        "transaction_count": int(len(window)),
    }


def _previous_period(start: date, end: date) -> tuple[date, date]:
    days = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    return prev_end - timedelta(days=days - 1), prev_end


def overview(txns: pd.DataFrame, start: date, end: date) -> dict:
    current = summarize(txns, start, end)
    prev_start, prev_end = _previous_period(start, end)
    previous = summarize(txns, prev_start, prev_end)
    spend = current["expenses"]
    return {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "previous_period": {"from": prev_start.isoformat(), "to": prev_end.isoformat()},
        "current": current,
        "previous": previous,
        "change": {
            k: {"abs": current[k] - previous[k], "pct": _pct_change(current[k], previous[k])}
            for k in ("income", "expenses", "essential", "discretionary", "net_cash_flow")
        },
        "essential_share": current["essential"] / spend if spend else None,
        "discretionary_share": current["discretionary"] / spend if spend else None,
    }


def categories(txns: pd.DataFrame, start: date, end: date) -> list[dict]:
    """Expense outflows by category, with the previous equal-length period for comparison."""

    def grouped(s: date, e: date) -> pd.DataFrame:
        window = _slice(txns, s, e)
        window = window[window["type"] == "expense"]
        return window.groupby(["category", "kind"])["amount"].agg(["sum", "count"])

    current = grouped(start, end)
    previous = grouped(*_previous_period(start, end))
    total = float(current["sum"].sum())
    rows = []
    for (category, kind), row in current.sort_values("sum", ascending=False).iterrows():
        prev = float(previous["sum"].get((category, kind), 0.0))
        rows.append(
            {
                "category": category,
                "kind": kind,
                "total": float(row["sum"]),
                "count": int(row["count"]),
                "share": float(row["sum"]) / total if total else 0.0,
                "previous_total": prev,
                "change_pct": _pct_change(float(row["sum"]), prev),
            }
        )
    return rows


def granularity_for(start: date, end: date) -> str:
    return "day" if (end - start).days < DAILY_GRANULARITY_MAX_DAYS else "month"


def bucket_start(start: date, granularity: str) -> date:
    """Monthly charts start on the 1st: a partial first month (e.g. 10-31 Oct) would miss
    that month's salary and plot a misleading dip."""
    return start.replace(day=1) if granularity == "month" else start


def trends(
    txns: pd.DataFrame, start: date, end: date, granularity: str, opening_cash: float
) -> list[dict]:
    """Per-bucket flows plus the running cash balance (the savings trend)."""
    freq = "D" if granularity == "day" else "M"
    window = _slice(txns, start, end)
    buckets = pd.period_range(start=start, end=end, freq=freq)
    if window.empty:
        table = pd.DataFrame(0.0, index=buckets, columns=KINDS)
    else:
        table = (
            window.assign(bucket=window["date"].dt.to_period(freq))
            .pivot_table(index="bucket", columns="kind", values="amount", aggfunc="sum")
            .reindex(index=buckets, columns=KINDS)
            .fillna(0.0)
        )
    rows, balance = [], opening_cash
    for period, r in table.iterrows():
        expenses = r["essential"] + r["discretionary"]
        net = r["income"] - expenses - r["debt"] - r["investment"]
        balance += net
        rows.append(
            {
                "period": str(period),
                "income": float(r["income"]),
                "expenses": float(expenses),
                "essential": float(r["essential"]),
                "discretionary": float(r["discretionary"]),
                "debt_payments": float(r["debt"]),
                "investments": float(r["investment"]),
                "net_cash_flow": float(net),
                "savings_ratio": float((r["income"] - expenses - r["debt"]) / r["income"])
                if r["income"]
                else None,
                "cash_balance": float(balance),
            }
        )
    return rows


def merchant_label(description: str) -> str:
    """Narration without reference numbers (UPI refs, order ids vary per payment), so repeat
    payments to one merchant group together: 'UPI/40212/DMART' -> 'UPI/DMART'."""
    text = re.sub(r"[\d-]*\d{4,}[\d-]*", "", description)
    return re.sub(r"\s*([/-])(\s*[/-])+\s*", r"\1", text).strip(" /-") or description


def top_merchants(txns: pd.DataFrame, start: date, end: date, limit: int) -> list[dict]:
    window = _slice(txns, start, end)
    window = window[window["type"] == "expense"]
    if window.empty:
        return []
    name = window["merchant"].fillna(window["description"].map(merchant_label))
    grouped = (
        window.assign(name=name)
        .groupby("name")
        .agg(total=("amount", "sum"), count=("amount", "size"), category=("category", "first"))
    )
    top = grouped.sort_values("total", ascending=False).head(limit)
    return [
        {
            "merchant": n,
            "total": float(r["total"]),
            "count": int(r["count"]),
            "category": r["category"],
        }  # fmt: skip
        for n, r in top.iterrows()
    ]
