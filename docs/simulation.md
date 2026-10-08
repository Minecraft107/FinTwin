# FinTwin — What-If Simulation Engine

"What happens if I buy a ₹1,30,000 laptop?" is answered by a **deterministic financial model**, not by an LLM and not by an ML prediction. The same inputs always give the same outputs, and every number can be re-derived by hand from the formulas below. An AI Coach may later *explain* a result, but it never produces one.

```
Current Digital Twin ──► Baseline (starting balances + monthly flows)
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
  project(no changes)                    project(scenario changes)
          │                                       │
          ▼                                       ▼
  baseline timeline                       scenario timeline         (month by month)
          │                                       │
          └─► future TwinState @ checkpoint ◄─────┘  ──► Health Score (same code as today)
                              │
                              ▼
          impact (scenario − baseline) · goal outcomes · risk level · recommendation
```

Code: `backend/app/services/simulation/`, with `scenarios.py` (validated changes), `engine.py` (projection) and `service.py` (comparison, scoring, risk, text).

## 1. Starting point

Taken from the Digital Twin:
- **Monthly flows:** income, essential and discretionary spending, and SIPs, at the twin's trailing averages (the last 3 complete months; declared profile values for new users).
- **Balances:** cash, emergency fund, investments.
- **Loans:** recorded outstanding, rate and EMI. If EMIs are visible in transactions but no loan is recorded, they're kept constant.
- **Goals:** target, saved amount, planned monthly contribution, priority, target date.
- **Investment return:** the value-weighted expected return of the user's holdings.

## 2. Monthly step

Month 1 is the calendar month after today. Events dated in the current month, or earlier, apply in month 1.

```
income        = baseline income × (1 + pct changes) + amount changes            (≥ 0)
essential     = baseline essential × inflation(m) × (1 + pct) + amount changes   (≥ 0)
discretionary = same for discretionary; "extra savings" subtracts here          (≥ 0)
EMIs          = Σ over loans: interest = outstanding × r/12; payment = min(EMI, outstanding + interest)
SIP           = baseline SIP + SIP changes                                       (≥ 0)
net           = income + one-time inflows − essential − discretionary − EMIs − SIP − one-time outflows
investments   = investments × (1 + return/12) + SIP
cash         += net
goals         ← funded from the recurring surplus (income − spending − EMIs − SIP), in priority
                order, each up to its planned contribution, and only from cash above one month
                of outgoings (so saving for a goal never drains the account)
if cash < 0   → the emergency fund covers it; anything left negative is a SHORTFALL
net worth     = cash + emergency fund + investments + goal savings − loan outstanding
```

New loans use the standard EMI `P·r·(1+r)ⁿ / ((1+r)ⁿ − 1)`, and the first EMI falls due the month after disbursement.

## 3. Change types (combine up to 10 in one scenario)

| `type` | Parameters | Effect |
|---|---|---|
| `large_purchase` | `amount`, `date?`, `label?`, `financed_by_loan?` (+ `loan_annual_rate`, `loan_tenure_months`) | One-time outflow, or, if financed, a new loan with no upfront cost |
| `income_change` | `pct` **or** `amount`, `start_date?`, `duration_months?` | Changes monthly income, permanently or temporarily |
| `expense_change` | `pct` **or** `amount`, `kind` (`essential`/`discretionary`), `start_date?`, `duration_months?` | Changes monthly spending |
| `sip_change` | `amount` (±), `start_date?` | Moves money between cash and investments every month |
| `new_loan` | `principal`, `annual_rate`, `tenure_months`, `start_date?`, `disbursed_to_cash?` | Adds an amortising loan. With `disbursed_to_cash: false` the money is spent immediately (e.g. on a car) |
| `extra_savings` | `amount`, `start_date?` | Spend this much less discretionary money each month (saving = not spending) |
| `goal_delay` | `goal_id`, `months` | Moves a goal's target date later |
| `one_time_income` | `amount`, `date?`, `label?` | Bonus or windfall |

Options: `horizon_months` (6–60, default 24) and `inflation_pct` (annual, applied to spending, default 0).

## 4. Comparing futures

Both the baseline (no change) and the scenario are projected with the same engine, and the impact is **scenario − baseline at the same point in time**. Comparing the scenario against *today* would mix the scenario's effect with ordinary drift: even with no change, goals keep growing and the twin's 6-month stability window fills with projected steady months.

- **Checkpoint** = 12 months ahead (or the horizon, if shorter). Both futures are converted back into a full `TwinState` (`simulated_twin`) and scored by the *same* Health Score code used for the present (`derive()` in the twin builder is the single copy of every ratio formula).
- **Impact:**
  - **Cash and money flows:** `cash_change` (also at the horizon), `monthly_cash_flow_change`, `net_worth_change`
  - **Ratio changes:** `savings_change` (savings ratio), `emergency_months_change`, `debt_to_income_change`
  - **Balance changes:** `emergency_fund_change`, `debt_change`, `investment_change`, `goals_saved_change`
  - **Score and goals:** `health_score_change`, `goal_delay`, `goals_no_longer_reached`
  - **Liquidity:** `emergency_fund_drawn`, `first_shortfall_month`, `max_shortfall`, `lowest_cash`
- **Goals:** when each goal is reached in each future. Inside the horizon this is simulated; beyond it, it's extrapolated from the saving pace of the final 3 months and flagged `*_estimated`. `delay_months` > 0 means later, < 0 means sooner.

## 5. Risk level (first rule that applies)

| Level | When |
|---|---|
| **CRITICAL** | Any month with a shortfall: outgoings can't be covered even after emptying the emergency fund |
| **HIGH** | Emergency cover falls below 1 month of essentials + EMIs (when the baseline doesn't), EMIs exceed 50% of income, or the health score drops ≥ 15 |
| **MEDIUM** | Health score drops ≥ 5, the emergency fund is drawn on, cash falls below one month of outgoings (when the baseline doesn't), or a goal is delayed ≥ 3 months or no longer reached |
| **LOW** | None of the above |

Every triggered rule is listed in `risk_factors` with its numbers. The recommendation is deterministic text chosen by the risk level. For purchases, it adds how long saving up would take at the current surplus.

## 6. Worked example (demo user)

"Buy a ₹1,30,000 laptop in January 2027":

| | Without | With |
|---|---|---|
| Cash in Oct 2027 | ₹2,26,814 | ₹96,814 |
| Net worth in Oct 2027 | ₹12,07,450 | ₹10,77,450 |
| Monthly surplus | ₹7,720 | ₹7,720 |
| Health score (Oct 2027) | 68 | 68 |

Risk is **LOW**. The cash stays above one month of outgoings and the emergency fund isn't touched. Saving up instead would take about 17 months at the current surplus. The same purchase at ₹4,00,000 is **CRITICAL**: it's short ₹70,466 in Nov 2026, even after the full ₹95,000 emergency fund.

Hand check for the shortfall: ₹2,26,814.12 cash + ₹7,719.81 surplus − ₹4,00,000 + ₹95,000 emergency fund = −₹70,466.07, exactly the engine's figure.

## 7. Assumptions (also returned with every result)

1. Income and spending continue at the twin's averages, except where the scenario changes them.
2. Inflation is 0% unless `inflation_pct` is set. Cash earns nothing, and investments grow at their expected return.
3. Goals are funded from surplus, in priority order, above a one-month cash buffer.
4. The emergency fund covers deficits and is not automatically rebuilt.
5. One-off purchases and windfalls count as cash movements, not as monthly income or spending, in the scored future state. They still show in the cash-flow stability months.

**Simulation vs prediction:** forecasting (Phase 7) estimates what will *probably* happen, statistically and with uncertainty. Simulation computes what *would* happen under stated assumptions, deterministically. The simulator deliberately starts from trailing averages rather than ML forecasts, so its results are reproducible and explainable line by line.

## 8. Endpoints

`POST /api/simulation/what-if` · `POST/GET /api/simulation/scenarios` · `GET/DELETE /api/simulation/scenarios/:id` · `POST /api/simulation/scenarios/:id/run`. Schemas are in [api.md](api.md).
