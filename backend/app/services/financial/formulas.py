"""Core time-value-of-money formulas. Pure functions, monthly compounding, rates as fractions."""


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
