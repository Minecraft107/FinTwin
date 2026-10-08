"""Grounding check: every number in an answer must come from the provided context.

The LLM is only allowed to *explain* backend results. If its answer contains a rupee amount,
percentage or count that does not appear (within rounding) in the structured context, the
retrieved knowledge or the question, the answer is rejected and the deterministic local
answer is used instead. This is what stops the model inventing or calculating figures.
"""

import json
import re
from dataclasses import dataclass

_NUM = re.compile(
    r"(?P<cur>₹\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>%|lakhs?|crores?|cr\b|k\b)?",
    re.IGNORECASE,
)
_UNITS = {"lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7, "k": 1e3}
_DATE = re.compile(r"\b\d{4}-\d{2}(?:-\d{2})?\b")
SMALL_COUNT = 12  # bare whole numbers up to 12 (e.g. "3 months", "2 goals") are not checked
REL_TOL = 0.01  # 1%: allows rounding such as ₹7,719.81 -> ₹7,720
ABS_TOL = 0.05  # for small values, e.g. 1.48 months shown as 1.5


@dataclass(frozen=True)
class GroundingResult:
    passed: bool
    checked: int
    unverified: list[str]


def numbers(text: str) -> list[tuple[float, str, str]]:
    """(value, kind, raw) for each number; kind is 'pct', 'money' or 'plain'. Dates are skipped."""
    text = _DATE.sub(" ", text)
    out = []
    for m in _NUM.finditer(text):
        try:
            value = float(m.group("num").replace(",", ""))
        except ValueError:
            continue
        unit = (m.group("unit") or "").lower()
        kind = "pct" if unit == "%" else "money" if (m.group("cur") or unit) else "plain"
        if unit in _UNITS:
            value *= _UNITS[unit]
        out.append((value, kind, m.group(0).strip()))
    return out


def allowed_numbers(*sources) -> list[float]:
    values = []
    for source in sources:
        text = source if isinstance(source, str) else json.dumps(source, ensure_ascii=False)
        values.extend(v for v, _, _ in numbers(text))
    return values


def check(answer_text: str, allowed: list[float]) -> GroundingResult:
    unverified, checked = [], 0
    for value, kind, raw in numbers(answer_text):
        # Whole small counts ("3 months") and years are skipped; decimals ("1.8 months") are
        # measurements and always checked.
        if (
            kind == "plain"
            and value.is_integer()
            and (value <= SMALL_COUNT or 1900 <= value <= 2100)
        ):
            continue
        checked += 1
        if not any(abs(value - a) <= max(REL_TOL * abs(a), ABS_TOL) for a in allowed):
            unverified.append(raw)
    return GroundingResult(not unverified, checked, unverified)
