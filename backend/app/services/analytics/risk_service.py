"""Risk scan: turns anomaly detections and Digital Twin ratio rules into persisted alerts.

Alerts are keyed by a stable fingerprint, so rescanning updates rather than duplicates them,
a dismissed alert stays dismissed while its condition persists, and alerts whose condition
has disappeared are removed (resolved).
"""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import pandas as pd

from app.extensions import db
from app.models import RiskAlert
from app.models.enums import AlertStatus, Severity
from app.services.analytics.anomalies import (
    SEVERITY_RANK,
    TransactionFlag,
    abnormal_months,
    category_drift,
    describe_flag,
    detect_transaction_anomalies,
    monthly_spending,
)
from app.services.digital_twin.builder import build_twin
from app.services.digital_twin.state import TwinState, UserData
from app.utils.dates import last_complete_month_end
from app.utils.money import inr, pct

TRANSACTION_ALERT_DAYS = 90  # older one-off anomalies are history, not actionable risks


@dataclass(frozen=True)
class Alert:
    type: str
    severity: Severity
    title: str
    explanation: str
    affected_metric: str
    metric_value: float | None
    recommended_action: str
    key: str  # stable identity of the condition
    transaction_id: int | None = None

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(f"{self.type}:{self.key}".encode()).hexdigest()[:64]


def ratio_alerts(t: TwinState) -> list[Alert]:
    alerts = []
    if t.savings_ratio is not None and t.savings_ratio < 0.10:
        negative = t.savings_ratio < 0
        alerts.append(Alert(
            "low_savings", Severity.HIGH if negative else Severity.MEDIUM,
            "Spending exceeds income" if negative else "Low savings rate",
            f"You keep {pct(t.savings_ratio)} of your income after expenses and EMIs "
            f"(income {inr(t.monthly_income)}, spending + EMIs "
            f"{inr(t.monthly_expenses + t.debt_payments)} per month).",
            "savings_ratio", t.savings_ratio,
            "Aim for at least 10–20%: review discretionary categories and set monthly limits.",
            "savings",
        ))  # fmt: skip
    if t.debt_to_income is not None and t.debt_to_income > 0.36:
        critical = t.debt_to_income > 0.50
        alerts.append(Alert(
            "high_debt", Severity.CRITICAL if critical else Severity.HIGH,
            "Dangerous debt-to-income ratio" if critical else "High debt burden",
            f"EMIs take {pct(t.debt_to_income)} of your income ({inr(t.debt_payments)}/month); "
            "lenders commonly treat over 36% as high and over 50% as critical.",
            "debt_to_income", t.debt_to_income,
            "Avoid new loans; prepaying the highest-interest loan reduces the burden fastest.",
            "debt",
        ))  # fmt: skip
    if t.emergency_months is not None and t.emergency_months < 3:
        severe = t.emergency_months < 1
        alerts.append(Alert(
            "emergency_fund_shortage", Severity.HIGH if severe else Severity.MEDIUM,
            "Emergency fund shortage",
            f"Your emergency fund covers {t.emergency_months:.1f} months of essential expenses "
            f"and EMIs; 3–6 months is recommended.",
            "emergency_months", t.emergency_months,
            f"Build it to at least {inr(3 * (t.essential_expenses + t.debt_payments))} "
            "(3 months of essentials and EMIs).",
            "emergency",
        ))  # fmt: skip
    recent = t.recent_months[-3:]
    negative_months = [m.month for m in recent if m.net < 0]
    if len(recent) == 3 and len(negative_months) >= 2:
        alerts.append(Alert(
            "negative_cash_flow", Severity.HIGH, "Repeated negative cash flow",
            f"Cash flow was negative in {', '.join(negative_months)}: more money left your "
            "account than came in.",
            "net_cash_flow", t.net_cash_flow,
            "Identify the months' largest expenses and plan big purchases ahead.",
            "cash_flow",
        ))  # fmt: skip
    monthly_outflow = t.monthly_expenses + t.debt_payments
    if monthly_outflow > 0 and t.cash_balance < monthly_outflow:
        alerts.append(Alert(
            "low_cash_buffer", Severity.CRITICAL if t.cash_balance < 0 else Severity.HIGH,
            "Low cash balance",
            f"Your account balance ({inr(t.cash_balance)}) is below one month of spending "
            f"and EMIs ({inr(monthly_outflow)}).",
            "cash_balance", t.cash_balance,
            "Keep at least one month of outgoings in your account to avoid missed payments.",
            "cash",
        ))  # fmt: skip
    return alerts


def anomaly_alerts(flags: list[TransactionFlag], today: date) -> list[Alert]:
    cutoff = today - timedelta(days=TRANSACTION_ALERT_DAYS)
    alerts = []
    for f in flags:
        if f.date <= cutoff or f.severity == Severity.LOW:
            continue
        title, explanation, action = describe_flag(f)
        alerts.append(Alert(
            "duplicate_charge" if f.duplicate and not f.by_rule else "unusual_transaction",
            f.severity, title, explanation, "transaction_amount", f.amount, action,
            str(f.transaction_id), transaction_id=f.transaction_id,
        ))  # fmt: skip
    return alerts


def monthly_alerts(data: UserData, last_month: pd.Period) -> list[Alert]:
    monthly = monthly_spending(data.transactions, last_month)
    if monthly.empty:
        return []
    alerts = []
    for month, z in abnormal_months(monthly):
        if month != last_month:
            continue
        total = float(monthly.loc[month].sum())
        baseline = float(monthly.iloc[-7:-1].sum(axis=1).mean())
        alerts.append(Alert(
            "abnormal_monthly_spending", Severity.HIGH if z >= 3 else Severity.MEDIUM,
            f"Unusually high spending in {month}",
            f"You spent {inr(total)} in {month}, versus {inr(baseline)} on average over the "
            f"previous 6 months ({z:.1f} standard deviations above normal).",
            "monthly_spending", total,
            "Review that month's largest transactions to see whether they were one-offs.",
            str(month),
        ))  # fmt: skip
    for d in category_drift(monthly):
        window = "over the last 3 months" if d.kind == "trend" else f"in {last_month}"
        compared = "the 3 months before" if d.kind == "trend" else "your previous 3-month average"
        alerts.append(Alert(
            "category_spending_increase", d.severity,
            f"{d.category} spending up {d.change * 100:.0f}%",
            f"You spent {inr(d.recent)}/month on {d.category} {window}, versus {inr(d.baseline)} "
            f"in {compared}.",
            "category_spending", d.recent,
            f"Set a monthly limit for {d.category}; bringing it back to {inr(d.baseline)} would "
            f"free {inr(d.recent - d.baseline)} a month.",
            f"{d.category}:{last_month}",
        ))  # fmt: skip
    return alerts


def detect_risks(
    data: UserData, flags: list[TransactionFlag] | None = None
) -> tuple[list[Alert], list[TransactionFlag]]:
    twin = build_twin(data)
    if flags is None:
        flags = detect_transaction_anomalies(data.transactions, data.today, twin.monthly_income)
    last_month = pd.Period(last_complete_month_end(data.today), "M")
    alerts = (
        ratio_alerts(twin) + anomaly_alerts(flags, data.today) + monthly_alerts(data, last_month)
    )
    alerts.sort(key=lambda a: SEVERITY_RANK[a.severity], reverse=True)
    return alerts, flags


def sync_alerts(user_id: int, alerts: list[Alert]) -> None:
    """Upsert by fingerprint; keep user dismissals; delete alerts that no longer apply."""
    existing = {
        a.fingerprint: a
        for a in db.session.scalars(db.select(RiskAlert).where(RiskAlert.user_id == user_id))
    }
    now = datetime.now(UTC)
    for alert in alerts:
        values = dict(
            type=alert.type, severity=alert.severity, title=alert.title,
            explanation=alert.explanation, affected_metric=alert.affected_metric,
            metric_value=alert.metric_value, recommended_action=alert.recommended_action,
            transaction_id=alert.transaction_id,
        )  # fmt: skip
        row = existing.pop(alert.fingerprint, None)
        if row is None:
            db.session.add(
                RiskAlert(
                    user_id=user_id,
                    fingerprint=alert.fingerprint,
                    detected_at=now,
                    status=AlertStatus.ACTIVE,
                    **values,
                )
            )
        else:
            for name, value in values.items():
                setattr(row, name, value)
    for stale in existing.values():
        db.session.delete(stale)
    db.session.commit()


def active_alerts(user_id: int) -> list[dict]:
    """The user's active (not dismissed) alerts, most severe first."""
    rows = db.session.scalars(
        db.select(RiskAlert).where(
            RiskAlert.user_id == user_id, RiskAlert.status == AlertStatus.ACTIVE
        )
    )
    return [
        {
            "id": a.id,
            "type": a.type,
            "severity": a.severity.value,
            "title": a.title,
            "explanation": a.explanation,
            "recommended_action": a.recommended_action,
        }
        for a in sorted(rows, key=lambda a: (-SEVERITY_RANK[a.severity], a.id))
    ]
