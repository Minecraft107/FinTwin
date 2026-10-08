"""Core time-value-of-money formulas. Pure functions, monthly compounding, rates as fractions."""

import math


def emi(principal: float, annual_rate: float, months: int) -> float:
    """Equated monthly instalment: P·r·(1+r)^n / ((1+r)^n − 1)."""
    if months <= 0:
        raise ValueError("months must be positive")
    r = annual_rate / 12
    if r == 0:
        return principal / months
    growth = (1 + r) ** months
    return principal * r * growth / (growth - 1)


def outstanding_after(
    principal: float, annual_rate: float, months: int, payments_made: int
) -> float:
    """Remaining loan balance after `payments_made` EMIs."""
    k = min(max(payments_made, 0), months)
    r = annual_rate / 12
    if r == 0:
        return principal * (1 - k / months)
    growth = (1 + r) ** k
    balance = principal * growth - emi(principal, annual_rate, months) * (growth - 1) / r
    return max(balance, 0.0)


def future_value(
    present: float, monthly_contribution: float, annual_rate: float, months: int
) -> float:
    """Value after `months` of a lump sum plus end-of-month contributions."""
    r = annual_rate / 12
    if r == 0:
        return present + monthly_contribution * months
    growth = (1 + r) ** months
    return present * growth + monthly_contribution * (growth - 1) / r


def required_payment(target: float, present: float, annual_rate: float, months: int) -> float:
    """Monthly saving needed to grow `present` into `target` in `months`:
    P = (FV − PV·(1+i)ⁿ)·i / ((1+i)ⁿ − 1), or (FV − PV)/n at zero return. Never negative."""
    if months <= 0:
        raise ValueError("months must be positive")
    i = annual_rate / 12
    if i == 0:
        return max((target - present) / months, 0.0)
    growth = (1 + i) ** months
    return max((target - present * growth) * i / (growth - 1), 0.0)


def months_to_target(
    target: float, present: float, payment: float, annual_rate: float
) -> int | None:
    """Whole months until `present` plus monthly `payment` reaches `target`
    (n = ln((FV·i + P)/(PV·i + P)) / ln(1+i)). None if it never does."""
    if present >= target:
        return 0
    i = annual_rate / 12
    if i == 0:
        return math.ceil((target - present) / payment - 1e-9) if payment > 0 else None
    if payment <= 0 and present <= 0:
        return None
    n = math.log((target * i + payment) / (present * i + payment)) / math.log(1 + i)
    return math.ceil(n - 1e-9)


def value_months_ago(
    current: float, monthly_contribution: float, annual_rate: float, months: int
) -> float:
    """Inverse of future_value: estimated value `months` ago, given today's value and the
    contributions made since. Floored at 0 (the holding may not have existed then)."""
    if months <= 0:
        return current
    r = annual_rate / 12
    if r == 0:
        return max(current - monthly_contribution * months, 0.0)
    growth = (1 + r) ** months
    return max((current - monthly_contribution * (growth - 1) / r) / growth, 0.0)
