# FinTwin REST API

Base URL: `/api`. All bodies are JSON unless noted. Dates are `YYYY-MM-DD`; amounts are rupees (numbers, 2 dp).

## Conventions

**Authentication:** `Authorization: Bearer <access_token>` on every endpoint except `/health`, `/auth/register` and `/auth/login`. Tokens expire after 12 hours.

**Success envelope**
```json
{ "data": { }, "meta": { } }
```
**Error envelope**
```json
{ "error": { "code": "VALIDATION_ERROR", "message": "Request validation failed.", "details": [ ] } }
```

| Status | `code` | When |
|---|---|---|
| 400 | `VALIDATION_ERROR`, `INVALID_JSON` | Bad field, unknown field, body not a JSON object |
| 401 | `UNAUTHORIZED`, `INVALID_TOKEN`, `TOKEN_EXPIRED`, `INVALID_CREDENTIALS` | Missing, invalid or expired token; failed login |
| 404 | `NOT_FOUND` | Missing **or owned by another user** (existence is never revealed) |
| 405 | `METHOD_NOT_ALLOWED` | |
| 409 | `EMAIL_TAKEN`, `CONFLICT` | Duplicate email; database constraint violation |
| 413 | `REQUEST_ENTITY_TOO_LARGE` | Upload > 2 MB |
| 422 | `INVALID_CSV` | File unusable as a whole (empty, missing columns, > 5000 rows) |
| 503 | `DB_UNAVAILABLE` | Database down |
| 500 | `INTERNAL_ERROR` | Unexpected error (details logged server-side only) |

Request bodies reject unknown fields, so a typo such as `"amout"` returns 400 instead of being silently ignored.

---

## System
### `GET /health`
`200 {"data": {"status": "ok", "database": "up", "environment": "development"}}`, or `503` with `"status": "degraded", "database": "down"`.

## Auth
### `POST /auth/register`
```json
{ "email": "user@example.com", "password": "secret123", "full_name": "Asha Rao" }
```
The password must be 8–128 characters with at least one letter and one digit. The email is lower-cased. The endpoint also creates an empty financial profile.
→ `201 {"data": {"user": {"id", "email", "full_name", "created_at"}, "access_token": "..."}}` · `409 EMAIL_TAKEN`

### `POST /auth/login`
`{ "email", "password" }` → `200` (same shape as register) · `401 INVALID_CREDENTIALS`. The same error is returned whether the email or the password was wrong.

### `GET /auth/me`
→ `200 {"data": {"id", "email", "full_name", "created_at"}}`

## Financial profile
### `GET /financial-profile`
```json
{ "declared_monthly_income": 95000, "opening_balance": 25000, "opening_balance_date": "2024-11-01",
  "emergency_fund": 95000, "monthly_essential_expenses": 52000, "monthly_discretionary_expenses": 18000,
  "risk_tolerance": "medium", "dependents": 1, "employment_type": "salaried" }
```
### `PUT /financial-profile`
Partial update: send any subset of the fields above. Amounts must be ≥ 0. `risk_tolerance` ∈ `low|medium|high`; `employment_type` ∈ `salaried|self_employed|student|other`.

## Categories
### `GET /categories`
`[{"id", "name", "kind", "color", "icon"}]`, where `kind` ∈ `essential|discretionary|income|investment|debt`. Income transactions must use `income` categories, and expenses must use any other kind.

## Transactions
### `GET /transactions`
| Query | Meaning |
|---|---|
| `from`, `to` | Inclusive date range |
| `type` | `income` or `expense` |
| `category_id` | Category filter |
| `q` | Case-insensitive search in description and merchant |
| `page` (≥1, default 1), `per_page` (default 50, max 200) | Pagination |

→ `data: [Transaction]`, `meta: {"page", "per_page", "total"}`, newest first.

**Transaction**
```json
{ "id": 1, "date": "2026-09-04", "amount": 486.0, "type": "expense",
  "description": "UPI/882455/SWIGGY ORDER", "merchant": null, "payment_method": "upi",
  "is_recurring": false, "category": {"id": 14, "name": "Food & Dining", "kind": "discretionary", "color": "#f97316", "icon": "utensils"},
  "category_source": "rule", "category_confidence": 0.9 }
```
`category_source` ∈ `import` (from file) · `memory` (your earlier correction) · `rule` (keyword rules) · `ml` (classifier, Phase 7) · `manual` (set by you).

### `POST /transactions`
```json
{ "date": "2026-09-04", "amount": 486, "type": "expense", "description": "SWIGGY ORDER",
  "category_id": null, "merchant": null, "payment_method": "upi", "is_recurring": false }
```
`amount` > 0 (direction comes from `type`); `date` cannot be in the future. Omit `category_id` and the transaction is categorized automatically: memory → rules → fallback `Other` / `Other Income`. → `201 Transaction`

### `PUT /transactions/:id`
Partial update. Setting `category_id` marks it `manual`, and that correction is remembered for future transactions and imports with the same description. Changing `type` requires a compatible `category_id`.

### `DELETE /transactions/:id` → `204`

### `POST /transactions/import/preview` (multipart, field `file`, `.csv`, ≤ 2 MB)
Nothing is saved. The file is parsed, validated, cleaned, categorized and checked for duplicates.

Accepted columns (case-insensitive):
- **Generic:** `date, description, amount[, type, category, merchant, payment_method, is_recurring]`
- **Bank style:** `date, description, debit, credit`
- **Aliases:** `Narration/Particulars/Details/Remarks → description`, `Txn Date/Transaction Date → date`, `Withdrawal Amt → debit`, `Deposit Amt → credit`

Date formats: `YYYY-MM-DD`, `DD/MM/YYYY`, `DD-MM-YYYY`, `DD/MM/YY`, `DD-Mon-YYYY`, `DD Mon YYYY` (Indian day-first). Amounts may contain `₹`, `Rs`, Indian digit grouping (`1,30,000`) or `(300)` for negatives. Without a `type` column, a negative amount is an expense and a positive one is income; this inference is flagged as a warning.

```json
{ "summary": { "total": 17, "ok": 14, "warning": 0, "duplicate": 1, "error": 2, "importable": 14 },
  "rows": [
    { "row": 2, "status": "ok", "errors": [], "warnings": [], "duplicate_of": null, "category_name": "Salary",
      "transaction": { "date": "2026-09-01", "amount": 102600.0, "type": "income", "description": "...",
                       "merchant": null, "category_id": 1, "category_source": "rule", "category_confidence": 0.9,
                       "payment_method": "other", "is_recurring": false } },
    { "row": 16, "status": "error", "errors": ["Invalid date '31/09/2026'."], "transaction": null }
  ] }
```
- `row` is the line number in the file (header = 1).
- `status` ∈ `ok | warning | duplicate | error`.
- `duplicate_of` ∈ `existing` (already in your account) | `file` (repeated within the upload). Duplicates are matched on date + amount + type + description, with reference numbers kept, so two different UPI payments of the same amount are not treated as duplicates.

### `POST /transactions/import`
`{ "transactions": [ <preview row.transaction>, ... ] }` (1–5000 rows). The client sends back the rows the user confirmed, optionally with the category edited. Every row is re-validated on the server, and the import is all-or-nothing. → `201 {"data": {"imported": 14}}`

A sample file for trying this on a fresh account: `database/seed/sample_bank_statement.csv`. It includes one duplicate and two invalid rows on purpose.

## Investments · Loans · Goals
All three share the same shape: `GET /x` (list), `POST /x` (201), `PUT /x/:id` (partial), `DELETE /x/:id` (204). Each user sees only their own rows; another user's id returns 404.

| Resource | Fields |
|---|---|
| `/investments` | `name`, `asset_type` (`sip_equity, mutual_fund, stocks, fd, ppf, gold, other`), `invested_amount`, `current_value`, `monthly_contribution`, `expected_annual_return` (fraction, e.g. `0.11`) |
| `/loans` | `name`, `loan_type` (`home, car, personal, education, credit_card, other`), `principal` > 0, `outstanding` (default = principal, ≤ principal), `annual_interest_rate` (fraction), `emi` (default computed: P·r(1+r)ⁿ/((1+r)ⁿ−1)), `tenure_months`, `start_date` |
| `/goals` | `name`, `target_amount` > 0, `current_amount`, `target_date` (nullable; send `null` to clear), `priority` 1–5 (1 = highest), `monthly_contribution`, `status` (`active, achieved, paused`) |

## Digital Twin
### `GET /digital-twin[?as_of=YYYY-MM-DD]`
The derived financial state, computed fresh from all of your data. `as_of` (not in the future) rebuilds the twin as it stood on that date.
```json
{ "as_of": "2026-10-08", "window_months": 3, "window_start": "2026-07-01", "window_end": "2026-09-30",
  "months_of_history": 23,
  "monthly_income": 105211.67, "monthly_expenses": 76376.36, "essential_expenses": 52861.39,
  "discretionary_expenses": 23514.96, "debt_payments": 11115.5, "investment_contributions": 10000.0,
  "expenses_by_category": {"Housing": 26000.0, "Food & Dining": 11752.67, "...": 0},
  "net_cash_flow": 7719.81, "disposable_income": 41234.77, "burn_rate_daily": 2874.3,
  "cash_balance": 226800.01, "emergency_fund": 95000.0, "investments_value": 547078.69,
  "investment_allocation": {"sip_equity": 0.6041, "ppf": 0.3078, "gold": 0.0881},
  "total_debt": 392540.65, "goals_saved": 360000.0, "net_worth": 836338.05,
  "savings_ratio": 0.1684, "expense_ratio": 0.7259, "debt_to_income": 0.1056,
  "emergency_months": 1.4849, "investment_rate": 0.095,
  "recent_months": [{"month": "2026-09", "income": 103335.0, "essential": 55368.0, "discretionary": 26515.0,
                     "debt": 11115.5, "investment": 10000.0, "expenses": 81883.0, "net": 336.5}],
  "goals": [{"id": 1, "name": "Buy a car", "target_amount": 800000.0, "current_amount": 200000.0,
             "progress_pct": 25.0, "remaining": 600000.0, "monthly_contribution": 15000.0,
             "target_date": "2028-10-08", "priority": 1, "status": "active"}],
  "sources": {"income": "observed", "essential": "observed", "discretionary": "observed",
              "debt_payments": "observed", "investment_contributions": "observed"},
  "notes": [] }
```
**Definitions** (all flows are monthly averages over the last `window_months` *complete* months):

| Field | Formula |
|---|---|
| `monthly_expenses` | essential + discretionary consumption (EMIs and investments are tracked separately) |
| `net_cash_flow` | income − expenses − debt_payments − investment_contributions |
| `disposable_income` | income − essential − debt_payments |
| `savings_ratio` | (income − expenses − debt_payments) / income; money invested counts as saved |
| `expense_ratio` | expenses / income |
| `debt_to_income` | debt_payments / income |
| `emergency_months` | emergency_fund / (essential + debt_payments); EMIs must be paid in an emergency too |
| `investment_rate` | investment_contributions / income |
| `cash_balance` | opening balance (at the start of the opening date) ± every transaction since |
| `net_worth` | cash + emergency fund + investments + goal savings − loan outstanding |

Ratios are `null` when their denominator is 0 (e.g. zero income).

`sources` shows where each value came from:
- `observed`: averaged from your transactions.
- `declared`: your profile values, used when there is no complete month of history yet.
- `holdings`: scheduled EMIs or SIPs from your loans and investments, used when no matching transactions exist.

`notes` explains any fallback.

### `GET /digital-twin/history`
Month-end snapshots for every complete month with history, oldest first: `as_of, income, expenses, net_cash_flow, savings_ratio, expense_ratio, debt_to_income, emergency_months, cash_balance, investments_value, total_debt, net_worth, months_of_history`.

Snapshots are rebuilt automatically after every successful write: transactions, import, profile, investments, loans, goals. An import can change past months, so all of them are recomputed rather than appended. Loan balances and investment values for past months are worked back from today's stored values. The emergency fund and goal balances use today's values, since no history of them is kept.

## Analytics
Every endpoint takes a date range: `range=7d|30d|3m|6m|12m` (default `3m`, ending today), or a custom `from=YYYY-MM-DD&to=YYYY-MM-DD` (maximum 5 years). The resolved range is echoed in `meta.from` / `meta.to`.

| Endpoint | Returns |
|---|---|
| `GET /analytics/overview` | `current` and `previous` (the equal-length period immediately before), each with `income, expenses, essential, discretionary, debt_payments, investments, net_cash_flow, savings_ratio, avg_daily_spend, transaction_count`. Also `change.{metric}: {abs, pct}` (pct is relative to \|previous\|, and null when previous is 0) and `essential_share` / `discretionary_share` |
| `GET /analytics/categories` | Expense outflows per category: `category, kind, total, count, share, previous_total, change_pct`, largest first |
| `GET /analytics/trends[&granularity=day\|month]` | One row per day or month (auto: daily under 62 days): `period, income, expenses, essential, discretionary, debt_payments, investments, net_cash_flow, savings_ratio, cash_balance`. `cash_balance` is the running balance, i.e. the savings trend |
| `GET /analytics/merchants[&limit=1..50]` | Top merchants by spend (falls back to description): `merchant, total, count, category` |

## Financial Health Score
### `GET /health-score[?compare_months=1..12]`
```json
{ "as_of": "2026-10-08", "score": 64.9, "grade": "C", "label": "Fair",
  "components": [
    { "key": "emergency_fund", "label": "Emergency fund", "weight": 20, "score": 39.7, "status": "weak",
      "effective_weight": 0.2, "points": 7.94, "indicator": "Emergency-fund coverage",
      "value": 1.4849, "value_display": "1.5 months", "target": "3–6 months",
      "basis": "A common guideline is an emergency fund covering 3–6 months of essential costs.",
      "explanation": "Your emergency fund of ₹95,000 covers 1.5 months of essential expenses and EMIs (₹63,977/month); 3–6 months is recommended.",
      "excluded_reason": null } ],
  "excluded_components": [],
  "strengths": ["Debt burden: EMIs take 10.6% of your income (₹11,116/month)."],
  "weaknesses": ["Emergency fund: ...", "Goal progress: ..."],
  "recommendations": [
    { "component": "emergency_fund", "title": "Strengthen your emergency fund", "potential_points": 12.1,
      "action": "Reaching 3 months of cover needs ₹96,931 more — about ₹8,078/month over a year. Your account balance is ₹2,26,800; earmarking ₹96,931 of it as emergency savings would close the gap immediately." } ],
  "notes": [],
  "change": { "previous_as_of": "2026-03-31", "previous_score": 68.4, "delta": -3.5,
              "summary": "Your score fell by 4 points since 2026-03-31 (68 → 65), mainly because ...",
              "drivers": [{"component": "goals", "label": "Goal progress", "points_change": -3.8, "from": "50%", "to": "13%"}] } }
```
- `points` = `effective_weight × score`, and the points add up to `score`.
- `status`: `strong` (≥ 80), `fair`, `weak` (≤ 50), or `excluded`.
- Recommendations are ordered by `potential_points`, the score points available if that component reached 100.
- `change` compares with the twin rebuilt `compare_months` month-ends earlier (default 1). Each component's movement is attributed in score points.
- `score` is `null` (grade `N/A`) when nothing can be measured yet.

### `GET /health-score/history`
`[{"as_of", "score", "grade", "components": {"savings": 70.5, ...}}]`, one row per month-end, stored alongside the twin snapshots.

### `GET /health-score/methodology`
Weights, indicators, formulas, guideline anchors, grade bands and the missing-data rule, all generated from the same constants the scorer uses.

`GET /digital-twin` also includes a `health_score` summary: `{score, grade, label, components}`.

The forecast, risk, simulation and coach endpoints are documented as their phases land.
