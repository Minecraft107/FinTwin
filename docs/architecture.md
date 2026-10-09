# FinTwin — Architecture

> Analyze. Predict. Simulate. Decide Better.

This document is the design reference for FinTwin. It explains **what** each part of the system does, **why** it is designed that way, and **where** it lives in the code. The implementation plan, risks and MVP scope are in [implementation-plan.md](implementation-plan.md).

---

## 1. System overview

```
                 ┌──────────────────────────── React (Vite) SPA ────────────────────────────┐
                 │ Dashboard · Twin · Transactions · Analytics · Forecast · Goals · What-If │
                 │ Risks · Coach · Profile                       (Recharts, Tailwind)       │
                 └───────────────────────────────┬──────────────────────────────────────────┘
                                                 │ REST/JSON + JWT (Bearer)
┌────────────────────────────────────────────────▼────────────────────────────────────────────┐
│ Flask API  (blueprints in app/routes, pydantic validation in app/schemas)                   │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Services (pure Python, DB-free, unit-testable)                                              │
│                                                                                             │
│   Data in ─► categorization ─► DIGITAL TWIN BUILDER ─► TwinState ─┬─► ANALYZE  (analytics,   │
│   (CSV/manual/seed)            (digital_twin/)                    │             health score,│
│                                                                   │             anomalies)   │
│                                                                   ├─► PREDICT  (forecasting) │
│                                                                   └─► SIMULATE (simulation,  │
│                                                                                goal planner) │
│                                         all results ─► AI COACH (intent → context → RAG → LLM)│
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Repositories (SQLAlchemy queries → DataFrames / dataclasses, always scoped by user_id)      │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ PostgreSQL 16                  │ ml/models/ (trained artifacts, metrics)  │ LLM API (optional)│
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Layering rule:** `routes → services ← repositories`. Routes do HTTP + validation only. Services take plain dataclasses / DataFrames and return dataclasses; they never import Flask or SQLAlchemy. That rule is what lets us unit-test every financial number without a database or a server.

**The LLM never calculates.** Every number originates in a service. The coach receives the verified numbers as structured context and only explains them (§9).

---

## 2. Technology choices

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 19 + Vite, JavaScript, React Router, Recharts, Tailwind CSS, lucide-react | Stack from the synopsis. Vite is the current standard React toolchain. Plain JS (not TS) so the whole team can read it. |
| Backend | Flask 3, Flask-SQLAlchemy 2, Flask-Migrate (Alembic), Flask-JWT-Extended, Flask-CORS, pydantic v2 | Stack from the synopsis. pydantic gives typed request validation with readable errors. |
| DB | PostgreSQL 16 (Docker). Tests run on SQLite in-memory | Models avoid Postgres-only types, so the same models run on both. |
| Data | pandas, NumPy | Synopsis. |
| ML | scikit-learn, XGBoost, joblib | Synopsis. Holt exponential smoothing is ~20 lines of NumPy, so there's no statsmodels dependency. |
| LLM | stdlib `urllib` → OpenAI / Gemini REST; deterministic `LocalProvider` fallback | No vendor SDKs. Provider is chosen by env var, and the app works without any key. |
| RAG | Markdown knowledge base → chunks → TF-IDF + LSA (TruncatedSVD) embeddings → in-memory NumPy vector store | Real retrieval with no torch/GPU download (~2 GB avoided). Upgrade path: sentence-transformers or pgvector. |
| Serving | gunicorn (backend), nginx (frontend build), docker-compose | `docker compose up --build` starts everything. |

Currency is **INR only**. Dates are calendar dates (no time-of-day, no time zones).

---

## 3. Database schema

All tables have `id` (PK), `created_at` and `updated_at`. Money is stored as `NUMERIC(14,2)` and converted to `float` only inside the computation services. Every user-owned table has `user_id FK → users.id ON DELETE CASCADE` plus an index on it.

```
users ─┬─< financial_profiles (1:1)
       ├─< transactions >── expense_categories
       ├─< investments
       ├─< loans
       ├─< financial_goals
       ├─< financial_snapshots ──< financial_health_scores (1:1)
       ├─< forecast_results
       ├─< risk_alerts >?─ transactions
       ├─< simulation_scenarios ──< simulation_results
       └─< coach_conversations ──< coach_messages
```

| Table | Key columns | Constraints / indexes |
|---|---|---|
| **users** | email, password_hash, full_name | `UNIQUE(email)` |
| **financial_profiles** | user_id, declared_monthly_income, opening_balance, opening_balance_date, emergency_fund, monthly_essential_expenses, monthly_discretionary_expenses, risk_tolerance (`low/medium/high`), dependents, employment_type | `UNIQUE(user_id)`, `CHECK(amounts ≥ 0)` |
| **expense_categories** | name, kind (`essential/discretionary/income/investment/debt`), color, icon | `UNIQUE(name)`. Global and seeded. |
| **transactions** | user_id, date, amount (>0), type (`income/expense`), category_id, description, merchant, payment_method (`upi/card/cash/netbanking/auto_debit/other`), is_recurring, category_source (`rule/ml/manual/import`), category_confidence | `CHECK(amount > 0)`, index `(user_id, date)`, index `(user_id, category_id)` |
| **investments** | user_id, name, asset_type (`sip_equity/mutual_fund/stocks/fd/ppf/gold/other`), invested_amount, current_value, monthly_contribution, expected_annual_return | `CHECK(values ≥ 0)` |
| **loans** | user_id, name, loan_type, principal, outstanding, annual_interest_rate, emi, tenure_months, start_date | `CHECK(outstanding ≤ principal)` |
| **financial_goals** | user_id, name, target_amount, current_amount, target_date (nullable), priority (1–5), monthly_contribution, status (`active/achieved/paused`) | `CHECK(target_amount > 0)` |
| **financial_snapshots** | user_id, as_of, period (`monthly/on_change`), income, expenses, net_cash_flow, savings_ratio, expense_ratio, dti, emergency_months, cash_balance, investments_value, total_debt, net_worth, months_of_history | `UNIQUE(user_id, as_of, period)` |
| **financial_health_scores** | snapshot_id, score, grade, savings, emergency_fund, debt, cash_flow, investments, goals, spending (component columns) | `UNIQUE(snapshot_id)`, `CHECK(score BETWEEN 0 AND 100)` |
| **forecast_results** | user_id, target (`expenses/cash_flow/savings`), model_name, horizon_months, generated_at, backtest_mae, points (JSON) | index `(user_id, target, generated_at)` |
| **risk_alerts** | user_id, type, severity (`LOW/MEDIUM/HIGH/CRITICAL`), title, explanation, affected_metric, metric_value, recommended_action, transaction_id (nullable FK), status (`active/dismissed`), fingerprint | `UNIQUE(user_id, fingerprint)` so re-running detection never duplicates alerts |
| **simulation_scenarios** | user_id, name, changes (JSON), horizon_months | — |
| **simulation_results** | scenario_id, risk_level, health_score_before/after, cash_change_12m, impact (JSON), timeline (JSON) | — |
| **coach_conversations** | user_id, title | — |
| **coach_messages** | conversation_id, role (`user/assistant`), content, intent, structured (JSON), provider | index `(conversation_id, created_at)` |

**JSON is used only where data is genuinely heterogeneous or never queried relationally.** That covers forecast point series, scenario change lists (each change type has different parameters), simulation timelines, and coach answer sections. Everything else is relational.

**Deliberate deviation: there is no separate `income_records` table.** Income is a `transaction` with `type='income'` and an income category (Salary, Freelance, Bonus, Interest…). A single ledger means cash flow is always `Σincome − Σexpense` over one table, so nothing can be double-counted between two sources.

**Categories (22, global):**
- **Income:** Salary, Freelance, Bonus, Interest, Other Income
- **Essential:** Housing, Utilities, Groceries, Transport, Healthcare, Insurance, Education, Family Support
- **Discretionary:** Food & Dining, Shopping, Entertainment, Subscriptions, Travel, Personal Care, Other
- **Investment:** Investment
- **Debt:** EMI/Debt

The synopsis' single "Food" category is split into Groceries (essential) and Food & Dining (discretionary). Without that split, the essential-vs-discretionary analysis would mix needs and wants.

**Enums** are stored as `VARCHAR + CHECK` rather than native PostgreSQL ENUM types, so new values never need an `ALTER TYPE` migration. Constraint names follow a fixed naming convention (`ck_<table>_<name>`, `fk_<table>_<col>_<ref>`…), which keeps Alembic diffs stable.

**Manual category correction** sets `category_source='manual'`. On later imports, the categorizer first looks up the user's own manual corrections for the same normalized description. This gives per-user learning without an extra table.

---

## 4. The Financial Digital Twin

A database row is not a twin. The twin is a **derived state object** that is rebuilt from raw data (transactions, profile, investments, loans, goals). It is the single input that every Analyze / Predict / Simulate component consumes.

```python
@dataclass(frozen=True)
class TwinState:
    as_of: date
    window_months: int                # trailing window used for averages (default 3)
    months_of_history: int
    # Income & expenses (monthly averages over the window, from transactions)
    monthly_income: float
    monthly_expenses: float
    essential_expenses: float
    discretionary_expenses: float
    debt_payments: float              # EMIs
    investment_contributions: float   # SIPs etc.
    expenses_by_category: dict[str, float]
    # Flows
    net_cash_flow: float              # income − expenses − debt − investments
    disposable_income: float          # income − essential − debt_payments
    burn_rate_daily: float
    # Balances
    cash_balance: float               # opening_balance + Σ net transactions since opening date
    emergency_fund: float
    investments_value: float
    investment_allocation: dict[str, float]
    total_debt: float
    net_worth: float
    # Ratios
    savings_ratio: float              # (income − all outflows except investments) / income
    expense_ratio: float
    debt_to_income: float             # debt_payments / income
    emergency_months: float           # emergency_fund / (essential + debt_payments)
    investment_rate: float
    # Derived blocks
    goals: list[GoalProgress]
    risks: list[RiskAlert]
    health: HealthScoreResult
    data_quality: DataQuality         # per-field source: 'observed' | 'declared', confidence notes
```

**Observed vs declared:** a user can declare a monthly income in their profile and also import transactions. The twin prefers **observed** values (trailing 3-month transaction averages) when at least one full month of data exists. Otherwise it falls back to the **declared** profile value, and `sources` records which source was used (`observed` / `declared` / `holdings`). Only *complete* calendar months are averaged; the current partial month is excluded, because it would understate spending. The UI shows that source, so the user knows whether a number is measured or self-reported.

**Recalculation:** building the twin from roughly 1,000 transactions takes milliseconds, so `GET /api/digital-twin` always computes it fresh. After every successful write (transactions, CSV import, profile, investments, loans, goals), an `after_request` hook rebuilds the `on_change` snapshot for today *and every monthly snapshot*. A CSV import can change any past month, so the history is recomputed rather than appended; for 24 months this takes about 0.12 s. Past snapshots rebuild the twin *as of* each month-end. Loan balances and investment values are worked back from today's stored values with the amortisation and compounding formulas; the emergency fund and goal balances use today's values. If recalculation fails, the error is logged and the user's write still succeeds. That powers the score-history chart and "why did my score change?" explanations.

**Pipeline:** `repositories.load_user_frame(user_id)` → `digital_twin.builder.build(frame, as_of)` → `TwinState`. The builder is pure, and the tests feed it hand-built DataFrames.

---

## 5. Financial Health Score (0–100)

`FinancialHealthScoreService.score(twin) → {score, grade, components, strengths, weaknesses, recommendations}`

Each component maps one measurable indicator to a 0–100 sub-score through a **piecewise-linear curve anchored on widely cited personal-finance thresholds**. The total is a weighted mean.

| Component | Weight | Indicator | Curve anchors (indicator → sub-score) | Basis |
|---|---|---|---|---|
| Savings | 20 | savings ratio | ≤0%→0 · 10%→50 · 20%→80 · ≥30%→100 | 50/30/20 rule (20% savings) |
| Emergency fund | 20 | months of essential expenses covered | 0→0 · 1→30 · 3→70 · ≥6→100 | 3–6-month emergency-fund guideline |
| Debt | 20 | debt-to-income (EMI / income) | 0%→100 · 20%→80 · 36%→50 · 50%→20 · ≥60%→0 | 36% common lending ceiling |
| Cash-flow stability | 15 | % of last 6 months with positive net flow (70%) + expense CV (30%) | positive share × 70 + (1 − min(CV/0.5, 1)) × 30 | — |
| Investments | 10 | investment contribution rate (70%) + asset-type diversification (30%) | 0%→0 · 10%→70 · ≥15%→100; 1 type→30 · 2→70 · ≥3→100 | — |
| Goals | 10 | priority-weighted (weight = 6 − priority) mean of min(1, *fundable* ÷ required monthly saving). "Fundable" means the monthly surplus is allocated to goals in priority order, capped at each goal's planned contribution | linear ×100 | Goals are funded from surplus, not as an extra outflow |
| Spending behaviour | 5 | discretionary / income; once anomaly detection (Phase 7) supplies it: 70% of that + 30% recent high-severity anomalies | ≤30%→100 · 50%→50 · ≥70%→0; −35 per HIGH/CRITICAL anomaly (last 30d) | 50/30/20 rule (30% wants) |

* **Missing data is not penalised arbitrarily.** If a component can't be computed (for example, the user has no goals), it is dropped and the remaining weights are renormalised. The response lists it under `excluded_components`.
* **Grade:** A ≥ 85 Excellent · B 70–84 Good · C 55–69 Fair · D 40–54 Weak · E < 40 Critical.
* **Explainability:** strengths are sub-scores ≥ 80 and weaknesses are ≤ 50. Each comes with a templated sentence that uses the real indicator ("Your emergency fund covers 2.1 months of essential expenses; 3–6 is recommended").
* **Score change explanation:** each component's contribution delta (`points = effective_weight × sub-score`) is computed against the twin rebuilt N month-ends earlier (`compare_months`, default 1) and sorted. The text names the top two drivers moving in the same direction as the score. Note that a one-month comparison can be dominated by a one-off month leaving the 3-month window. The output reads like "Score fell 6 points, mainly because discretionary spending rose 18% (−4.1) and emergency coverage fell to 2.1 months (−1.5)".
* All anchors and weights live in one constants module. The frontend fetches them, so the "How is this calculated?" panel can never drift from the code.

---

## 6. Analytics, categorization, anomaly detection

> **Implemented-design note (Phase 7):** [ml.md](ml.md) is the authoritative reference for the ML components, with measured results. Three things changed from the original plan below, each because the evaluation showed it was better:
> 1. Forecast selection is *champion–challenger*: XGBoost unless a baseline is ≥ 20% better over 6 backtest months.
> 2. Abnormal-month detection adds a same-month-last-year seasonal check.
> 3. The categorizer is trained on a curated merchant corpus and evaluated by merchant-grouped CV.


### 6.1 Analytics (`services/analytics`)
These are pandas aggregations over a date range (`7d/30d/3m/6m/12m/custom`): monthly income/expense/savings, category breakdown, essential vs discretionary split, income-vs-expense series, savings trend, top merchants, month-over-month change per category, and a debt overview built from loans.

### 6.2 Expense categorization (`services/ml/categorizer.py`)
Each transaction goes through a three-stage cascade, stopping at the first stage that answers:
1. **User memory:** the user's own manual corrections for the same normalised description.
2. **Keyword rules:** a curated merchant/keyword table (e.g. `swiggy|zomato → Food`, `uber|ola|metro → Transport`). This is high precision.
3. **ML classifier:** TF-IDF (char 3–5-grams + word 1–2-grams) → Logistic Regression, trained offline on a labelled description corpus. A prediction is accepted only if its probability is ≥ 0.55; otherwise the transaction goes to **Other**.

No external API is involved. Each transaction records `category_source` and `category_confidence`, so the UI can flag low-confidence categories for review.

### 6.3 Anomaly & risk detection (`services/analytics/anomalies.py`, `services/financial/risk_rules.py`)
Three detector families each produce `RiskAlert{type, severity, title, explanation, affected_metric, metric_value, recommended_action}`:

| Detector | Method | Example output |
|---|---|---|
| Transaction-level | **Isolation Forest** (fitted per user on log-amount, category-relative z-score, day-of-week, day-of-month, recurring flag), combined with a robust rule: amount > median + 3.5·MAD within the category. Both must agree for HIGH; one alone gives MEDIUM. | "₹48,000 at Croma is 6.2× your typical Shopping transaction" |
| Category drift | Month-over-month and vs. trailing 3-month mean, robust z-score per category | "Food delivery spending up 41% vs your 3-month average" |
| Ratio rules | Thresholds on twin ratios (same anchors as the health score) | Savings < 10% · DTI > 36% (HIGH) / > 50% (CRITICAL) · emergency < 3 months (MEDIUM) / < 1 (HIGH) · negative cash flow 2+ months (HIGH) |

Isolation Forest is only fitted once there are at least 60 transactions. Below that, only the robust statistical rule runs, and the API says so.

---

## 7. Forecasting (`services/forecasting`)

**Data reality:** a user has roughly 12–24 monthly points per category. That is far too few to train XGBoost on one user's data alone, so the design uses two levels:

| Model | Trained on | When used |
|---|---|---|
| Naive (last month) | user history | ≥ 1 month (floor baseline) |
| Moving average (3m) | user history | ≥ 3 months |
| Holt exponential smoothing (level + damped trend, NumPy) | user history | ≥ 6 months |
| **Global XGBoost regressor** | Offline, on a synthetic population of ~300 users × 24 months × categories. Features: lags 1/2/3/6/12, rolling mean/std, month-of-year (sin/cos), category one-hot, festive-month flag, income level | ≥ 3 months (needs lags) |

**Per-user model selection:** at request time, each eligible model is scored on the user's own history with a **rolling-origin backtest** (last 3 months held out, one step ahead). The model with the lowest MAE produces the forecast. The response names the chosen model and its backtest MAE, so every forecast is honest about the model behind it.

**Uncertainty:** an empirical prediction interval of `forecast ± 1.28·σ_residual·√h` (≈80%) is built from the backtest residuals. It widens with the horizon `h`.

**Targets**
* Expenses: per category, summed to a total (forecast horizon 1–6 months, default 3).
* Cash flow: forecast income (median of recurring income over the last 3 months) − forecast expenses − scheduled EMIs/SIPs from the loans/investments tables.
* Savings trajectory: cumulative cash balance from the cash-flow forecast.

**Insufficient data:** with fewer than 1 month of data, the API returns `status: "insufficient_data"`, the declared-profile estimate and a message. With fewer than 6 months, it returns `confidence: "low"` and notes that more history will improve accuracy.

**Offline evaluation (`ml/evaluation`):** XGBoost is evaluated against all three baselines on held-out synthetic users *and* held-out final months. The report gives **MAE, RMSE and R²**, and is written to `ml/models/metrics/forecast_eval.json` and `docs/ml.md`. If XGBoost fails to beat the baselines, the docs say so and per-user selection simply won't pick it.

---

## 8. What-If Simulation Engine (`services/simulation`)

> **Implemented-design note (Phase 8):** [simulation.md](simulation.md) is the authoritative reference. Refinements made over this plan:
> - Goals are funded only from cash above a one-month buffer.
> - The first EMI falls due the month after disbursement.
> - Impact is scenario − baseline at a 12-month checkpoint, with both futures scored by the same `derive()` / Health Score code.
> - Goal completion beyond the horizon is extrapolated and flagged as estimated.
> - An extra MEDIUM rule fires when cash falls below one month of outgoings.


The engine is deterministic. It's a month-by-month cash-flow projector, and no randomness or LLM is involved.

```
TwinState ──► baseline_inputs (monthly income, essential, discretionary, EMIs, SIPs, balances, goals)
                │
Scenario ───────┼──► apply changes ──► scenario_inputs
(list of        │
 changes)       ▼
           project(inputs, horizon=24) for BOTH baseline and scenario  ──► monthly timelines
                │
                ▼
     simulated TwinState @ month 1 after event and @ month 12  ──► HealthScoreService
                │
                ▼
     compare → impact metrics → risk level → deterministic recommendation ──► (Coach explains)
```

**Monthly step** (for each month *m*):
```
cash += income − essential − discretionary − Σ EMI − Σ SIP − Σ goal contributions − one_time_outflows + one_time_inflows
investments = investments·(1 + r_inv/12) + SIP           # r_inv from investments.expected_annual_return
loan.outstanding amortised with standard EMI formula
goal.current += contribution until target reached → completion month
if cash < 0: draw from emergency fund; if emergency fund exhausted → shortfall (flag)
```

**Change types** (several can be combined in one scenario):

| type | params | Effect |
|---|---|---|
| `large_purchase` | amount, date, `financed_by_loan?` | one-time outflow at the event month |
| `income_change` | pct or amount, start_date, duration_months? | changes monthly income |
| `expense_change` | amount or pct, category?, start_date | changes essential/discretionary spend |
| `sip_change` | amount (±), start_date | changes the monthly SIP (cash → investments) |
| `new_loan` | principal, annual_rate, tenure_months, start_date, disbursed_to_cash | EMI = P·r(1+r)ⁿ/((1+r)ⁿ−1) added; debt += P |
| `extra_savings` | amount, start_date | cuts discretionary spend by that amount (saving more = spending less) |
| `goal_delay` | goal_id, months | target date moves later, so the required contribution is recalculated |
| `one_time_income` | amount, date | bonus/windfall |

**Outputs:** `current_state`, `simulated_state`, `timeline[]` (baseline vs scenario per month: cash, emergency fund, investments, debt, net worth), and `impact`. The impact block contains `cash_change` at 12 months, `savings_ratio_change`, `emergency_months_change`, `dti_change`, `health_score_change`, `goal_delays{goal: months}`, `first_shortfall_month`, `months_of_runway`. The response also includes `risk_level`, `recommendation` and `assumptions[]`.

**Risk level rules:** CRITICAL if any month has a shortfall · HIGH if emergency coverage < 1 month, DTI > 50% or the score drops ≥ 15 · MEDIUM if the score drops ≥ 5 or any goal is delayed ≥ 3 months · otherwise LOW.

**Assumptions are explicit.** Income, essential and discretionary spending are held at trailing 3-month averages unless a change says otherwise. Investments compound at their recorded expected return. Cash earns 0%. There is no inflation (an optional `inflation_pct` can be passed). The response returns every assumption, and the UI prints them under the result.

**Simulation vs prediction:** forecasting estimates what will *probably* happen if behaviour continues (statistical, with uncertainty). Simulation computes what *would* happen under stated assumptions (deterministic, so the same inputs always give the same output). The baseline in the simulator deliberately uses trailing averages rather than ML forecasts. That keeps every simulated number reproducible by hand.

---

## 9. Goal planner (`services/financial/goals.py`, `goal_planner.py`)

> **Implemented-design note (Phase 9):**
> - Planned contributions are distinguished from *fundable* ones (what the surplus covers after higher priorities).
> - Statuses: on_track / at_risk / off_track / overdue / no_target_date / achieved / paused.
> - Each plan includes concrete options (increase, free up spending, extend date, reduce target).
> - `POST /goals/:id/simulate` uses planner arithmetic and reports which other goals gain or lose surplus. Whole-finance effects stay with the What-If engine.
> - Schemas are in [api.md](api.md).

For each goal:
* `required_monthly` = the annuity payment that reaches the target by the target date: `(FV − PV·(1+r)ⁿ)·r / ((1+r)ⁿ − 1)`. With r = 0 this reduces to `(FV − PV)/n`. Here r is the goal's assumed monthly return (default 0, i.e. savings account).
* `projected_completion` = solve n for the current contribution: `n = ln((FV·r + P)/(PV·r + P)) / ln(1+r)`, or `(FV − PV)/P` when r = 0.
* `shortfall` = required − current contribution · `feasible` if the required contribution fits in the surplus left after higher-priority goals. Disposable surplus is allocated to goals in priority order.
* `sensitivity`: completion date at the current contribution and at ±₹2k, ±₹5k, plus the contribution needed for the original date.
* Missing target date: the planner reports the completion date at the current contribution and skips the feasibility check.

`POST /api/goals/:id/simulate` runs the same simulation engine with a contribution or date change.

---

## 10. AI Financial Coach + RAG (`services/coach`)

> **Implemented-design note (Phase 10):**
> - **Intent detection:** uses weighted keyword rules instead of a trained classifier, since there is no real labelled question data and rules are deterministic and testable.
> - **RAG index:** built in memory rather than persisted (~60 ms), and rebuilt when a guide changes.
> - **LLM calls:** go over the standard library's `urllib`, with no vendor SDKs.
> - **Grounding:** compares every ₹, % and decimal against the context (1% / 0.05 tolerance).
> - **Answer sections:** answers add a `background` section for general knowledge.
> - **Score explanations:** pick the comparison window (3, 6, 1 or 12 months) that matches what the user asks, and always state the date compared against.
> - **References:** [ml.md](ml.md) §5 and [api.md](api.md).

```
question
  │
  ├─► 1. Intent detection: weighted keyword rules (see the note above)
  │      (affordability, score_explanation, overspending, goal_planning, emergency_fund, what_if,
  │       improve_health, forecast, risk, concept_question, out_of_scope), confidence < 0.4 → concept_question
  ├─► 2. Entity extraction: regex for ₹ amounts ("1,30,000", "5 lakh", "2 cr", "15k"), %, durations, goal names
  ├─► 3. Context builder: picks the sections the intent needs
  │      CURRENT_FINANCIAL_STATE · FINANCIAL_HEALTH_SCORE · RECENT_TRANSACTIONS · FORECAST ·
  │      RISKS · GOALS · SIMULATION_RESULTS
  ├─► 4. Calculations: affordability / what_if → parsed into a scenario → SIMULATION ENGINE
  ├─► 5. RAG retrieval: top-3 knowledge chunks (hybrid cosine ≥ 0.12 and ≥ half the best) with source ids
  ├─► 6. LLM (provider chosen by env) with strict system prompt; requested JSON output:
  │      {facts[], calculations[], predictions[], recommendations[], summary}
  ├─► 7. Grounding check: every ₹ / % number in the answer must match a number in the context
  │      (±1% / rounding tolerance). Unverified numbers → answer discarded → LocalProvider answer used
  └─► 8. Response + disclaimer, persisted to coach_messages
```

**Providers** (`services/coach/llm/`): `LLMProvider` (abstract `generate(system, context, question) → CoachAnswer`), plus `OpenAIProvider`, `GeminiProvider` and `LocalProvider`. `LLM_PROVIDER=openai|gemini|local` selects one. If the key is missing, the call times out (15 s) or the JSON is invalid, the coach falls back to `LocalProvider`. The local provider is deterministic: per-intent templates filled from the same structured context, so it is grounded by construction. The UI shows which provider answered.

**Safety:** the system prompt forbids inventing numbers, naming specific securities, or giving buy/sell instructions. `out_of_scope` intents such as "which stock should I buy" get an educational redirect. Every answer ends with: *"FinTwin is a decision-support and educational tool, not a licensed financial advisor. Projections are estimates based on available data."*

**RAG pipeline** (`services/coach/rag.py`):
```
knowledge_base/*.md (13 guides written for this project: budgeting, 50/30/20, emergency funds,
debt & EMIs, DTI, SIPs & compounding, asset allocation basics, goal planning, insurance basics,
credit score, inflation, reading your health score)
  → chunk by heading, ~120 words with 30-word overlap, metadata {doc, heading}
  → TF-IDF (word 1–2-grams, sublinear tf) + TruncatedSVD(≤64 dims) → L2-normalised dense vectors
  → NumPy matrix + metadata held in memory (~60 ms to build; rebuilt automatically when KB files change)
  → retrieve: hybrid cosine (0.5·tfidf + 0.5·lsa), top-k = 3, one per guide, ≥ 0.12 and ≥ half the best
```
If there are no documents, retrieval returns an empty list and the coach still answers from user data.

---

## 11. ML pipeline (training separate from inference)

```
ml/
├── pipeline.py    build data → train → evaluate → save artifacts + metrics (one command)
├── datasets/      population.py → synthetic users (same generator as the seed, in memory)
│                  categorizer_corpus.csv (349 labelled merchants)
├── training/      forecaster.py (train + MAE/RMSE/R² vs baselines, user + time split)
│                  categorizer.py (train + merchant-grouped CV)
├── evaluation/    anomaly.py (precision/recall/F1 on injected, labelled anomalies)
└── models/        *.joblib artifacts (git-ignored, built by training) + metrics/*.json (committed)
```
* Feature engineering lives once, in `backend/app/services/ml/features.py`. Training scripts import it, so training and inference can't diverge.
* Inference code lives in `backend/app/services/ml/` and loads artifacts lazily. If an artifact is missing, the matching fallback runs and `/api/ml/status` reports it (categorizer → rules + Other · forecaster → baselines only).
* `flask ml train` (or `python -m ml.pipeline`) retrains everything and refreshes the metrics. Docker images run it at build time.
* **Anomaly validation:** real labelled personal anomalies don't exist, so the synthetic generator injects anomalies with known labels (oversized purchases, duplicate charges, category spikes). Detection is scored against those labels. The limitation (synthetic labels, so the scores are optimistic) is stated in `docs/ml.md`.

---

## 12. API design

Base path `/api`. Auth is a JWT in `Authorization: Bearer <token>` on everything except `/auth/*` and `/health`.

**Envelope:** success `{"data": ..., "meta": {...}}` · error `{"error": {"code": "VALIDATION_ERROR", "message": "...", "details": {...}}}`.
**Status codes:** 200/201/204 · 400 validation · 401 unauthenticated · 404 not found *or not owned* (never leaks existence) · 409 conflict · 422 unprocessable CSV · 503 DB/dependency unavailable.

| Area | Endpoints |
|---|---|
| System | `GET /health` (DB + model status) · `GET /ml/status` |
| Auth | `POST /auth/register` · `POST /auth/login` · `GET /auth/me` |
| Profile | `GET/PUT /financial-profile` |
| Categories | `GET /categories` |
| Transactions | `GET /transactions?from&to&category&type&q&page` · `POST` · `PUT /:id` · `DELETE /:id` · `POST /transactions/import/preview` (multipart, nothing saved) · `POST /transactions/import` (commit confirmed rows) |
| Investments / Loans | `GET/POST /investments` · `PUT/DELETE /investments/:id` · same for `/loans` |
| Dashboard | `GET /dashboard` (one call that aggregates twin KPIs, score, alerts, goals, forecast summary) |
| Twin | `GET /digital-twin` · `GET /digital-twin/history` |
| Health | `GET /health-score` · `GET /health-score/history` · `GET /health-score/methodology` |
| Analytics | `GET /analytics/overview` · `/analytics/categories` · `/analytics/trends` · `/analytics/merchants` (all accept `range=7d|30d|3m|6m|12m` or `from&to`) |
| Forecast | `GET /forecast/expenses?horizon=3` · `GET /forecast/cash-flow?horizon=6` |
| Risks | `GET /risks` · `POST /risks/scan` · `PATCH /risks/:id` (dismiss) |
| Goals | `GET/POST /goals` · `PUT/DELETE /goals/:id` · `GET /goals/:id/plan` · `POST /goals/:id/simulate` |
| Simulation | `POST /simulation/what-if` · `GET/POST /simulation/scenarios` · `GET /simulation/scenarios/:id` |
| Coach | `POST /coach/chat` · `GET /coach/conversations` · `GET /coach/conversations/:id` |

The full request/response schemas go in `docs/api.md` (Phase 4).

---

## 13. Frontend

> **Implemented-design note (Phase 11):**
> - **Stack:** React 19 + React Router 8 + Recharts 3 + Tailwind 4 + lucide icons. Pages are lazy-loaded, so the chart library only downloads for app pages.
> - **Data loading:** `GET /api/dashboard` aggregates the dashboard in one request.
> - **Demo access:** `POST /api/auth/demo` gives one-click demo access without the password living in frontend code.
> - **Charts:** follow a validated colour/marks spec. The categorical order is blue, orange, aqua (colour-blind check passed). Status colours always come with icon + label. There's never a dual axis, and every chart has tooltips.
> - **Resilience:** an error boundary per page keeps the shell alive if one page fails.
> - **Dark mode:** deferred, as listed under secondary scope.

```
frontend/src/
├── services/api.js        fetch wrapper: base URL, JWT header, envelope unwrap, 401 → logout
├── context/AuthContext.jsx
├── hooks/useApi.js        {data, error, loading, refetch} for any GET
├── layouts/AppShell.jsx   sidebar + topbar + disclaimer footer
├── components/            KpiCard, ScoreGauge, ComponentBar, AlertCard, GoalCard, RangeFilter,
│                          DataSourceBadge (observed/declared), EmptyState, ErrorState, …
├── charts/                IncomeExpenseChart, CategoryDonut, TrendChart, ForecastChart (band),
│                          ScenarioComparisonChart, ScoreHistoryChart, AllocationChart
├── pages/                 Landing, Login, Register, Dashboard, DigitalTwin, Transactions (+CSV import
│                          wizard), Analytics, Forecasts, Goals, Simulator, Risks, Coach, Profile
└── utils/format.js        ₹ Indian grouping (Intl 'en-IN'), %, dates
```
**Digital Twin page:** a top-to-bottom flow that mirrors the concept. Data sources → indicator tiles (Income, Expenses, Savings, Investments, Debt, Emergency Fund, Goals, Risk) → Health Score with component breakdown → predicted state (3-month forecast) → "try a scenario" cards that deep-link into the simulator with the parameters prefilled.

Every chart and KPI is fetched from the API, with no static numbers anywhere in the frontend.

---

## 14. Security

* Passwords are hashed with `werkzeug.security` (scrypt). Pydantic validates the email and enforces a minimum password length of 8.
* JWT access tokens (HS256, 12 h expiry), with the secret taken from `JWT_SECRET_KEY`. The app refuses to start in production mode with the default secret.
* Every repository query filters by `user_id` taken from the token and never from the request body.
* SQLAlchemy ORM only (parameterised queries). CSV uploads are size-limited (2 MB, enforced by both nginx and Flask) and parsed with the `csv` module; they are never executed or stored raw.
* CORS is restricted to `FRONTEND_ORIGIN`. All secrets come from env vars, with `.env.example` committed and `.env` git-ignored.
* Known trade-off: the token lives in `localStorage` (simple for an SPA, but exposed to XSS). The upgrade path is httpOnly cookies + CSRF, which Flask-JWT-Extended supports.

---

## 15. Error handling & graceful degradation

| Failure | Behaviour |
|---|---|
| DB unavailable | Global handler for `OperationalError` → 503 `DB_UNAVAILABLE`. `/health` reports it, and the frontend shows a retry banner. |
| ML artifact missing | Fallback model (§11), with a `meta.model` field naming what actually ran |
| < 1 month of history | Twin uses declared profile values; forecasts return `insufficient_data` with an explanation |
| LLM key missing / API error | LocalProvider answer; `provider: "local"` shown in the UI |
| CSV bad rows | Row-level errors in the preview (`row`, `field`, `message`); good rows can still be imported |
| Forecast model throws | Logged; falls back to the next-best baseline |
| Empty knowledge base | Retrieval returns `[]`; the answer is built from user data only |

---

## 16. Folder structure

```
fintwin/
├── backend/
│   ├── app/
│   │   ├── __init__.py            create_app() factory, error handlers, blueprint registration
│   │   ├── config.py              env-driven config classes
│   │   ├── extensions.py          db, migrate, jwt, cors
│   │   ├── cli.py                 flask seed · flask sample-csv · flask ml train
│   │   ├── models/                SQLAlchemy models (one module per aggregate)
│   │   ├── schemas/               pydantic request/response models
│   │   ├── repositories/          user-scoped queries → DataFrames/dataclasses
│   │   ├── routes/                one blueprint per API area
│   │   ├── services/
│   │   │   ├── digital_twin/      builder.py, state.py
│   │   │   ├── financial/         health_score.py, goals.py, risk_rules.py, formulas.py (EMI, annuity)
│   │   │   ├── analytics/         aggregations.py, anomalies.py
│   │   │   ├── forecasting/       baselines.py, selector.py, service.py
│   │   │   ├── ml/                features.py, categorizer.py, forecaster.py, artifacts.py
│   │   │   ├── simulation/        engine.py, scenarios.py, impact.py
│   │   │   ├── coach/             intent.py, entities.py, context.py, rag.py, grounding.py, llm/
│   │   │   └── importer/          csv_import.py
│   │   ├── seed/                  synthetic.py (generator shared with ml/), demo.py
│   │   └── utils/
│   ├── knowledge_base/            RAG source documents (.md)
│   ├── tests/
│   ├── requirements.txt
│   ├── Dockerfile
│   └── run.py
├── ml/  datasets/ training/ evaluation/ models/
├── database/
│   ├── migrations/                Alembic (Flask-Migrate pointed here)
│   └── seed/                      sample CSVs for the import demo
├── frontend/                      Vite React app + Dockerfile + nginx.conf
├── docs/                          architecture, implementation-plan, api, ml, simulation, setup, viva
├── docker-compose.yml
├── .env.example
└── README.md
```
**Deviation from the suggested structure:** there are no `ml/preprocessing` or `ml/inference` folders. Preprocessing would duplicate `services/ml/features.py`, and inference runs inside the backend. Keeping a single copy of each is what prevents train/serve skew.
