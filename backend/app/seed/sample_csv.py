"""Bank-statement-style CSV for trying the import as a new user: a different persona from the
demo account, ending on the last complete month so the Digital Twin has full months to use."""

import csv
import io
from datetime import date

from app.seed.synthetic import Persona, generate_transactions
from app.utils.dates import last_complete_month_end

SAMPLE_PERSONA = Persona(
    employer="BRIGHTWAVE SOFTWARE LLP",
    salary=72_000,
    rent=18_000,
    family_support=0,
    groceries_weekly=1_800,
    dining_orders_per_month=8,
    dining_creep=(),
    sips=(("SIP - PARAG PARIKH FLEXI CAP", 6_000, 10),),
    anomalies={2: "large_electronics"},
)


def sample_statement(months: int = 6, today: date | None = None, seed: int = 99) -> str:
    end = last_complete_month_end(today or date.today())
    rows = generate_transactions(SAMPLE_PERSONA, end, months, seed=seed)
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Txn Date", "Narration", "Withdrawal Amt", "Deposit Amt"])
    for i, r in enumerate(rows):
        narration = (
            f"UPI/{40_000 + i}/{r['description']}"
            if r["payment_method"] == "upi"
            else r["description"]
        )
        amount = f"{r['amount']:,.2f}"
        writer.writerow(
            [r["date"].strftime("%d/%m/%Y"), narration,
             amount if r["type"] == "expense" else "", amount if r["type"] == "income" else ""]
        )  # fmt: skip
    return out.getvalue()
