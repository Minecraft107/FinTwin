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

The analytics, twin, health score, forecast, risk, simulation and coach endpoints are documented as their phases land.
