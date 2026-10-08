"""Synthetic transaction generator.

Produces a realistic ledger for one persona with *deliberate* patterns so forecasting,
anomaly detection and simulation have something real to find:

- salary raise after N months, annual bonus, occasional freelance income
- seasonal electricity (summer AC peak), festive (Oct/Nov) shopping spike, annual
  insurance premium, December travel
- food-delivery "creep" over the final months (category drift + score decrease story)
- injected anomalies with ground-truth labels in the `anomaly` field (used by ML evaluation,
  never written to the database)

Deterministic for a given (persona, end date, months, seed). Pure: no DB access.
"""

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

SUMMER, MONSOON, WINTER = (4, 5, 6), (7, 8, 9), (12, 1, 2)
FESTIVE_MONTHS = (10, 11)


@dataclass(frozen=True)
class Persona:
    employer: str = "ACME TECHNOLOGIES PVT LTD"
    salary: float = 95_000
    raise_pct: float = 0.08
    raise_after_months: int = 12
    bonus_month: int = 3
    bonus_multiple: float = 0.6
    freelance_prob: float = 0.2
    rent: float = 26_000
    family_support: float = 8_000  # monthly transfer to parents
    electricity_base: float = 1_800
    groceries_weekly: float = 2_400
    dining_orders_per_month: float = 14
    dining_median: float = 420
    # Multipliers for the final months (last entry = current month): food-delivery creep.
    dining_creep: tuple[float, ...] = (1.3, 1.6, 1.9, 2.2)
    rides_per_month: float = 8
    shopping_per_month: float = 3
    shopping_median: float = 1_400
    festive_multiplier: float = 2.5
    health_premium: float = 16_000  # paid every June
    travel_budget: float = 12_000  # December trip
    sips: tuple[tuple[str, float, int], ...] = (("SIP - AXIS BLUECHIP FUND", 10_000, 10),)
    emi: float = 0.0
    emi_label: str = "EMI - HDFC EDUCATION LOAN"
    emi_start: date | None = None  # first EMI month; None = before the window
    anomalies: dict[int, str] = field(default_factory=dict)  # months-from-end -> anomaly kind


class _Ledger:
    def __init__(self, end: date):
        self.end = end
        self.rows: list[dict] = []

    def add(
        self,
        day: date,
        amount: float,
        category: str,
        merchant: str,
        description: str,
        method: str,
        *,
        income: bool = False,
        recurring: bool = False,
        anomaly: str | None = None,
    ) -> None:
        if day > self.end or amount <= 0:
            return
        self.rows.append(
            {
                "date": day,
                "amount": round(float(amount), 2),
                "type": "income" if income else "expense",
                "category": category,
                "merchant": merchant,
                "description": description,
                "payment_method": method,
                "is_recurring": recurring,
                "anomaly": anomaly,
            }
        )


def month_starts(end: date, months: int) -> list[date]:
    starts = []
    y, m = end.year, end.month
    for _ in range(months):
        starts.append(date(y, m, 1))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    return starts[::-1]


def _day(month_start: date, day: int) -> date:
    last = calendar.monthrange(month_start.year, month_start.month)[1]
    return month_start.replace(day=min(max(day, 1), last))


def _lognormal(rng: np.random.Generator, median: float, sigma: float) -> float:
    return median * float(np.exp(sigma * rng.standard_normal()))


def generate_transactions(persona: Persona, end: date, months: int, seed: int = 42) -> list[dict]:
    """Generate `months` calendar months of transactions ending on `end` (inclusive)."""
    rng = np.random.default_rng(seed)
    ledger = _Ledger(end)
    starts = month_starts(end, months)

    def random_days(ms: date, count: int) -> list[date]:
        last = calendar.monthrange(ms.year, ms.month)[1]
        return [_day(ms, int(d)) for d in rng.integers(1, last + 1, size=count)]

    def pick(options: list[str]) -> str:
        return options[int(rng.integers(len(options)))]

    for i, ms in enumerate(starts):
        from_end = months - 1 - i
        month = ms.month

        # ---------------- income ----------------
        salary = persona.salary * (
            (1 + persona.raise_pct) if i >= persona.raise_after_months else 1
        )
        ledger.add(
            _day(ms, 1),
            salary,
            "Salary",
            persona.employer,
            f"SALARY CREDIT - {persona.employer}",
            "netbanking",
            income=True,
            recurring=True,
        )
        if month == persona.bonus_month:
            ledger.add(
                _day(ms, 15),
                salary * persona.bonus_multiple,
                "Bonus",
                persona.employer,
                f"ANNUAL BONUS - {persona.employer}",
                "netbanking",
                income=True,
            )
        if rng.random() < persona.freelance_prob:
            ledger.add(
                _day(ms, int(rng.integers(8, 26))),
                round(rng.uniform(5_000, 20_000), -2),
                "Freelance",
                "Upwork",
                "FREELANCE PAYMENT - UPWORK",
                "netbanking",
                income=True,
            )
        if month in (3, 6, 9, 12):
            ledger.add(
                _day(ms, 28),
                round(rng.uniform(600, 1_500)),
                "Interest",
                "Bank",
                "SAVINGS ACCOUNT INTEREST",
                "netbanking",
                income=True,
                recurring=True,
            )

        # ---------------- fixed obligations ----------------
        ledger.add(
            _day(ms, 5),
            persona.rent,
            "Housing",
            "Landlord",
            "RENT - UPI/LANDLORD",
            "upi",
            recurring=True,
        )
        if persona.family_support:
            ledger.add(
                _day(ms, 7),
                persona.family_support,
                "Family Support",
                "Family",
                "UPI TRANSFER - PARENTS",
                "upi",
                recurring=True,
            )
        if persona.emi and (persona.emi_start is None or ms >= persona.emi_start):
            ledger.add(
                _day(ms, 5),
                persona.emi,
                "EMI/Debt",
                "HDFC Bank",
                persona.emi_label,
                "auto_debit",
                recurring=True,
            )
        for label, amount, day in persona.sips:
            ledger.add(
                _day(ms, day),
                amount,
                "Investment",
                label.split(" - ")[-1].title(),
                label,
                "auto_debit",
                recurring=True,
            )

        # ---------------- utilities (seasonal electricity) ----------------
        season = (
            1.6
            if month in SUMMER
            else 1.2
            if month in MONSOON
            else 0.85
            if month in WINTER
            else 1.0
        )
        ledger.add(
            _day(ms, 12),
            _lognormal(rng, persona.electricity_base * season, 0.08),
            "Utilities",
            "BESCOM",
            "ELECTRICITY BILL - BESCOM",
            "upi",
            recurring=True,
        )
        ledger.add(
            _day(ms, 15),
            999,
            "Utilities",
            "Airtel",
            "AIRTEL XSTREAM FIBER",
            "auto_debit",
            recurring=True,
        )
        ledger.add(
            _day(ms, 20), 599, "Utilities", "Jio", "JIO POSTPAID", "auto_debit", recurring=True
        )
        if i % 2 == 0:
            ledger.add(_day(ms, 18), 1_105, "Utilities", "Indane", "INDANE GAS CYLINDER", "upi")

        # ---------------- subscriptions ----------------
        ledger.add(
            _day(ms, 3),
            1_500,
            "Subscriptions",
            "Cult.fit",
            "CULT.FIT MEMBERSHIP",
            "card",
            recurring=True,
        )
        ledger.add(
            _day(ms, 8), 649, "Subscriptions", "Netflix", "NETFLIX.COM", "card", recurring=True
        )
        ledger.add(
            _day(ms, 14), 119, "Subscriptions", "Spotify", "SPOTIFY INDIA", "card", recurring=True
        )
        if month == 1:
            ledger.add(
                _day(ms, 9),
                1_499,
                "Subscriptions",
                "Amazon",
                "AMAZON PRIME ANNUAL",
                "card",
                recurring=True,
            )

        # ---------------- groceries: every Saturday ----------------
        d = ms + timedelta(days=(5 - ms.weekday()) % 7)
        while d.month == month:
            store = pick(["BigBasket", "DMart", "Blinkit", "Zepto", "Reliance Fresh"])
            ledger.add(
                d,
                _lognormal(rng, persona.groceries_weekly, 0.2),
                "Groceries",
                store,
                f"{store.upper()} ORDER",
                "upi",
            )
            d += timedelta(days=7)

        # ---------------- discretionary ----------------
        creep_index = len(persona.dining_creep) - 1 - from_end
        creep = (
            persona.dining_creep[creep_index]
            if 0 <= creep_index < len(persona.dining_creep)
            else 1.0
        )
        for day in random_days(ms, int(rng.poisson(persona.dining_orders_per_month * creep))):
            place = pick(["Swiggy", "Zomato", "Swiggy", "Zomato", "Starbucks", "Haldiram's"])
            ledger.add(
                day,
                _lognormal(rng, persona.dining_median, 0.45),
                "Food & Dining",
                place,
                f"{place.upper()} ORDER",
                "upi",
            )

        for day in random_days(ms, int(rng.poisson(persona.rides_per_month))):
            app = pick(["Uber", "Ola", "Rapido"])
            ledger.add(
                day, _lognormal(rng, 230, 0.4), "Transport", app, f"{app.upper()} TRIP", "upi"
            )
        ledger.add(
            _day(ms, 2),
            500,
            "Transport",
            "Namma Metro",
            "METRO CARD RECHARGE",
            "upi",
            recurring=True,
        )

        festive = persona.festive_multiplier if month in FESTIVE_MONTHS else 1.0
        for day in random_days(ms, int(rng.poisson(persona.shopping_per_month * festive))):
            shop = pick(["Amazon", "Flipkart", "Myntra", "Decathlon", "Nykaa"])
            ledger.add(
                day,
                _lognormal(rng, persona.shopping_median * (1.3 if festive > 1 else 1), 0.6),
                "Shopping",
                shop,
                f"{shop.upper()} PURCHASE",
                "card",
            )

        for day in random_days(ms, int(rng.poisson(1.5))):
            venue = pick(["BookMyShow", "PVR Cinemas", "Steam"])
            ledger.add(
                day, _lognormal(rng, 550, 0.35), "Entertainment", venue, f"{venue.upper()}", "card"
            )
        for day in random_days(ms, int(rng.poisson(1.0))):
            ledger.add(
                day,
                _lognormal(rng, 450, 0.4),
                "Healthcare",
                "Apollo Pharmacy",
                "APOLLO PHARMACY",
                "upi",
            )
        for day in random_days(ms, int(rng.poisson(0.8))):
            ledger.add(
                day,
                _lognormal(rng, 700, 0.4),
                "Personal Care",
                "Urban Company",
                "URBAN COMPANY SERVICE",
                "upi",
            )
        if rng.random() < 0.15:
            ledger.add(
                random_days(ms, 1)[0],
                round(rng.uniform(499, 3_999), -1),
                "Education",
                "Udemy",
                "UDEMY COURSE",
                "card",
            )

        # ---------------- annual events ----------------
        if month == 6:
            ledger.add(
                _day(ms, 10),
                persona.health_premium,
                "Insurance",
                "Star Health",
                "STAR HEALTH INSURANCE PREMIUM",
                "netbanking",
                recurring=True,
            )
        if month == 12:
            ledger.add(
                _day(ms, 20),
                _lognormal(rng, persona.travel_budget, 0.15),
                "Travel",
                "MakeMyTrip",
                "MAKEMYTRIP BOOKING",
                "card",
            )

        # ---------------- injected anomalies (ground truth labels) ----------------
        kind = persona.anomalies.get(from_end)
        if kind == "large_electronics":
            ledger.add(
                _day(ms, 17),
                48_000,
                "Shopping",
                "Croma",
                "CROMA ELECTRONICS - LAPTOP",
                "card",
                anomaly="large_purchase",
            )
        elif kind == "hospital":
            ledger.add(
                _day(ms, 22),
                18_500,
                "Healthcare",
                "Apollo Hospitals",
                "APOLLO HOSPITALS - INPATIENT BILL",
                "card",
                anomaly="large_purchase",
            )
        elif kind == "duplicate":
            ledger.add(_day(ms, 11), 3_499, "Shopping", "Amazon", "AMAZON PURCHASE", "card")
            ledger.add(
                _day(ms, 11),
                3_499,
                "Shopping",
                "Amazon",
                "AMAZON PURCHASE",
                "card",
                anomaly="duplicate",
            )
        elif kind == "travel_month":
            ledger.add(
                _day(ms, 6),
                14_200,
                "Travel",
                "IndiGo",
                "INDIGO AIRLINES - GOA",
                "card",
                anomaly="abnormal_month",
            )
            ledger.add(
                _day(ms, 8),
                16_800,
                "Travel",
                "Taj Hotels",
                "TAJ HOLIDAY VILLAGE GOA",
                "card",
                anomaly="abnormal_month",
            )
            for d in (8, 9, 10, 11):
                ledger.add(
                    _day(ms, d),
                    _lognormal(rng, 1_400, 0.2),
                    "Food & Dining",
                    "Goa Restaurant",
                    "RESTAURANT GOA",
                    "card",
                    anomaly="abnormal_month",
                )

    ledger.rows.sort(key=lambda r: (r["date"], r["type"] != "income"))
    return ledger.rows
