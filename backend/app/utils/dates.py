import calendar
from datetime import date, timedelta


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def add_months(d: date, months: int) -> date:
    """Same day-of-month `months` later (clamped, e.g. 31 Jan + 1 -> 28/29 Feb)."""
    y, m = divmod(d.year * 12 + d.month - 1 + months, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def months_between(start: date, end: date) -> int:
    """Whole calendar months from start's month to end's month (can be negative)."""
    return (end.year - start.year) * 12 + end.month - start.month


def last_complete_month_end(as_of: date) -> date:
    """End of the latest calendar month that has fully elapsed by `as_of`."""
    return as_of if as_of == month_end(as_of) else as_of.replace(day=1) - timedelta(days=1)
