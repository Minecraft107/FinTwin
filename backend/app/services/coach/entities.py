"""Extract money amounts, percentages, durations and goal references from a question.

Understands Indian conventions: "₹1,30,000", "1.3 lakh", "5L", "2 crore", "15k", "Rs. 50,000".
"""

import re
from dataclasses import dataclass, field

_NUMBER = r"\d[\d,]*(?:\.\d+)?"
_MONEY = re.compile(
    rf"(?P<cur>₹|rs\.?|inr)?\s*(?P<num>{_NUMBER})\s*"
    r"(?P<unit>lakhs?|lacs?|l\b|crores?|cr\b|k\b|thousand)?",
    re.IGNORECASE,
)
_PERCENT = re.compile(rf"(?P<num>{_NUMBER})\s*(?:%|percent|per cent)", re.IGNORECASE)
_DURATION = re.compile(rf"(?P<num>{_NUMBER})\s*(?P<unit>months?|mos?|years?|yrs?)\b", re.IGNORECASE)
_UNITS = {
    "l": 1e5,
    "lakh": 1e5,
    "lakhs": 1e5,
    "lac": 1e5,
    "lacs": 1e5,
    "cr": 1e7,
    "crore": 1e7,
    "crores": 1e7,
    "k": 1e3,
    "thousand": 1e3,
}
_YEAR = re.compile(r"\b(19|20)\d{2}\b")


@dataclass
class Entities:
    amounts: list[float] = field(default_factory=list)  # rupees, in order of appearance
    percents: list[float] = field(default_factory=list)
    months: list[int] = field(default_factory=list)  # durations converted to months
    goal_ids: list[int] = field(default_factory=list)

    @property
    def amount(self) -> float | None:
        return self.amounts[0] if self.amounts else None


def _to_float(raw: str) -> float:
    return float(raw.replace(",", ""))


def parse_amounts(text: str) -> list[float]:
    """Money mentions. A bare number counts only with a currency marker or unit, or if it is
    at least 1,000 (so "3 months" or "2027" are not treated as rupees)."""
    spans_to_skip = [m.span() for m in _PERCENT.finditer(text)]
    spans_to_skip += [m.span() for m in _DURATION.finditer(text)]
    spans_to_skip += [m.span() for m in _YEAR.finditer(text)]
    amounts = []
    for m in _MONEY.finditer(text):
        start = m.start("num")
        if any(a <= start < b for a, b in spans_to_skip):
            continue
        value = _to_float(m.group("num"))
        unit = (m.group("unit") or "").lower()
        if unit:
            value *= _UNITS[unit]
        elif not m.group("cur") and value < 1_000:
            continue
        amounts.append(value)
    return amounts


def parse_percents(text: str) -> list[float]:
    return [_to_float(m.group("num")) for m in _PERCENT.finditer(text)]


def parse_months(text: str) -> list[int]:
    out = []
    for m in _DURATION.finditer(text):
        value = _to_float(m.group("num"))
        out.append(
            round(value * 12) if m.group("unit").lower().startswith(("y",)) else round(value)
        )
    return out


def match_goals(text: str, goals) -> list[int]:
    """Goals whose name shares a meaningful word with the question ("car" -> "Buy a car")."""
    words = set(re.findall(r"[a-z]{3,}", text.lower())) - {
        "goal",
        "goals",
        "the",
        "for",
        "and",
        "buy",
    }
    return [g.id for g in goals if words & set(re.findall(r"[a-z]{3,}", g.name.lower()))]


def extract(text: str, goals=()) -> Entities:
    return Entities(
        parse_amounts(text), parse_percents(text), parse_months(text), match_goals(text, goals)
    )
