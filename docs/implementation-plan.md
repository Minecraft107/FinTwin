# FinTwin — Implementation Plan

Companion to [architecture.md](architecture.md). This file records scope, risks, decisions and the phase plan, and is updated at the end of every phase.

## 1. Scope: MVP vs secondary

**MVP** covers everything needed for the 18 acceptance criteria:

| Area | MVP content |
|---|---|
| Auth | Register, login, JWT, protected routes |
| Data in | Profile form; transaction CRUD; CSV preview → validate → import; investments & loans CRUD |
| Categorization | User memory → keyword rules → TF-IDF/LogReg → "Other"; manual correction |
| Digital Twin | `TwinState` builder, on-change + back-filled monthly snapshots, Twin page |
| Health Score | 7 weighted components, grade, strengths/weaknesses, change explanation, methodology endpoint |
| Analytics | Overview, categories, trends, essential vs discretionary, range filters incl. custom |
| Risk | Isolation Forest + MAD rule, category drift, ratio rules, structured alerts, dismiss |
| Forecasting | Naive / MA / Holt / global XGBoost, per-user backtest selection, intervals, insufficient-data handling |
| Simulation | Deterministic engine, 8 change types, combined scenarios, baseline-vs-scenario timeline, impact, risk level |
| Goals | CRUD, required contribution, projected completion, feasibility by priority, sensitivity |
| Coach | Intent + entities, context builder, simulation hook, RAG, OpenAI + Gemini + Local providers, grounding check, disclaimer, persisted conversations |
| Frontend | All 12 pages |
| Quality | Seed (24 months), pytest suite, ML eval reports, Docker compose, README, viva.md |

**Secondary** (built after the MVP is green, only if time allows):
- Saved-scenario library UI (the save endpoint is MVP; browsing/comparing past scenarios is secondary)
- Conversation-history sidebar in the Coach (conversations are persisted in the MVP; only the browsing UI is deferred)
- Dark mode, PDF export of the twin report, refresh tokens/httpOnly cookies, login rate limiting
- Frontend unit tests (the MVP verifies the frontend with a production build plus manual end-to-end checks)
- Inflation-adjusted simulation as a default (in the MVP it's an optional parameter)

## 2. Risks & ambiguities, and the assumption taken

| # | Issue | Decision |
|---|---|---|
| 1 | The synopsis/poster files are not in the project folder | The prompt is treated as the spec. Put the files in `docs/reference/` and I'll reconcile terminology. |
| 2 | **Declared** profile values vs **observed** transaction values can disagree | The twin uses observed values once ≥ 1 full month exists, otherwise declared. The source is shown per metric. |
| 3 | No transaction field holds an account balance | Profile stores `opening_balance` + `opening_balance_date`; cash balance = opening + Σ net transactions since then. |
| 4 | Too little per-user data for XGBoost | A global XGBoost is trained on a synthetic population, and per-user backtest selection chooses between it and the baselines. |
| 5 | XGBoost trained and evaluated on synthetic data is partly circular | Stated openly in `docs/ml.md`. Evaluation also holds out users and the generator uses randomised personas; real data can be swapped in later. |
| 6 | No labelled real anomalies exist | Labelled anomalies are injected and precision/recall reported, with the limitation documented. |
| 7 | Local embeddings without torch | TF-IDF + LSA hybrid. It's a real vector retrieval and fine for a ~12-document KB. Upgrade path is documented. |
| 8 | The app must work with no LLM key | A deterministic LocalProvider gives grounded template answers. Less fluent, but always correct. |
| 9 | Docker is installed but the daemon wasn't running; no local Postgres | Postgres runs only via docker-compose. Tests use SQLite, kept portable by avoiding Postgres-only column types. Start Docker Desktop before Phase 3. |
| 10 | Investment return / inflation assumptions | Per-investment `expected_annual_return` (seeded with conservative defaults); cash 0%; inflation optional. Every assumption is returned with the result. |
| 11 | Demo data must stay current | The seed generates the 24 months ending on the **current** month, so "last 30 days" always has data. |
| 12 | Multi-currency, joint accounts, taxes | Out of scope: INR only, single user, pre-tax not modelled (income is treated as take-home). |
| 13 | JWT in localStorage | Accepted for the prototype and documented, with the cookie+CSRF upgrade path. |
| 14 | Goal contributions have no ledger rows: money moved to a goal account is not an expense | `goal.current_amount` is a balance held outside the cash account. The simulator funds goals from the monthly surplus rather than adding them as an extra outflow, which avoids double counting (decided in Phase 3, implemented in Phase 8). |

## 3. Key technical decisions

1. **Pure service layer.** Financial logic takes dataclasses/DataFrames and returns dataclasses. Testable without DB or HTTP, and the twin, score, simulator and coach all share it.
2. **One ledger.** Income is a transaction type, so there's no `income_records` table and no double counting.
3. **Twin computed, snapshots stored.** Computed fresh for accuracy and stored for history and explanations.
4. **Score from documented anchors.** Each curve point cites a common guideline, weights live in one module, and the UI reads them through `/health-score/methodology`.
5. **Simulation is deterministic and uses trailing averages, not ML forecasts.** Results are reproducible by hand, which also keeps simulation clearly separate from prediction.
6. **The LLM explains and never computes,** and a numeric grounding check enforces this. If the answer cites a number that isn't in the context, the deterministic answer is used instead.
7. **No vendor SDKs.** LLM calls are plain HTTPS through `requests`, behind an `LLMProvider` interface.
8. **Backtest-based model selection.** The forecast tells the user which model produced it and how accurate that model has been on their own data.

## 4. Synthetic demo data design (Phase 3)

The demo persona is a salaried professional in a metro city. The seed covers 24 months ending this month, and its patterns are planted deliberately so each feature has something real to show:

| Pattern | Demonstrates |
|---|---|
| Salary ₹95k on the 1st, +8% raise at month 13, March bonus (0.6× salary), occasional freelance income | Income forecasting, `one_time_income` |
| Rent ₹26k, ₹8k monthly family support, utilities peaking Apr–Jun (AC) | Essential spend, seasonality |
| Weekly groceries with noise; food delivery ×1.3 → ×2.2 over the final months (≈ ₹7k → ₹14k/month) | Category drift alert, score-decrease explanation |
| Diwali (Oct–Nov) shopping spike each year; June insurance premium; December trip | Seasonality → XGBoost month features |
| SIP ₹10k (10th), education-loan EMI ₹11,115 (5th; ₹6L @ 10%, 72 months), Netflix/Spotify/gym | Investments, DTI, recurring detection |
| Injected anomalies: ₹48k laptop, ₹18.5k hospital bill, one duplicate charge, one Goa-trip month | Anomaly detection with known labels |
| Emergency fund ₹95k ≈ 1.8 months of essentials | Weakness in the score, emergency-fund alert, coach question |
| Goals: Car ₹8L in 24 months (₹2L saved), Europe trip ₹3L in 18 months, Higher studies ₹5L in 36 months. Planned contributions (₹29k/month) exceed the recent surplus | Goal feasibility with priorities, `goal_delay` scenario |

Resulting demo profile, from the generator: about 1,160 transactions. The savings ratio falls from ≈ 22% to ≈ 10% over the last three full months, and the cash balance is ≈ ₹2.3L.

The same generator, with randomised persona parameters, builds the ~300-user training population (§7 of architecture).

## 5. Phase plan

Each phase ends with: tests run → errors fixed → behaviour verified → docs updated → phase report.

| Phase | Deliverable | Verification |
|---|---|---|
| 1 | Architecture + plan (this doc, architecture.md) | Review |
| 2 | git init, backend skeleton (`create_app`, config, extensions, `/api/health`), Vite React skeleton, docker-compose (db), `.env.example`, pytest + lint setup | `pytest` passes; `/api/health` responds; `npm run build` succeeds; `docker compose up db` healthy |
| 3 | SQLAlchemy models, Alembic migration, category seed, synthetic generator, `flask seed` | Migration applies on Postgres and SQLite; seed creates 24 months; constraint tests |
| 4 | Auth, profile, transactions CRUD, CSV preview/import, investments, loans, categories, error envelope, `docs/api.md` | API tests incl. auth/ownership/validation/bad CSV rows |
| 5 | Twin builder, analytics endpoints, snapshots + backfill, categorizer (rules + memory, ML stub → filled in Phase 7) | Unit tests on hand-built frames (income 100k − expenses 60k = 40k, zero income, negative flow…) |
| 6 | Health score service, history, change explanation, methodology | Component-curve tests, renormalisation, grade boundaries, explanation ordering |
| 7 | Feature module, categorizer training, XGBoost + baselines + selector, Isolation Forest + rules, ML eval scripts, `docs/ml.md` | Forecast tests (short history, flat series, trend), anomaly tests (planted outlier detected), eval metrics files written |
| 8 | Simulation engine, 8 change types, impact, risk level, scenarios save, `docs/simulation.md` | Hand-calculated scenario tests (EMI formula, ₹1.3L purchase, 20% income cut, shortfall → CRITICAL) |
| 9 | Goal planner + goal simulate | Annuity/zero-rate tests, missing date, infeasible goal, priority allocation |
| 10 | KB documents, RAG index, intent model, entity parser, context builder, providers, grounding check, coach endpoint | Entity tests ("1,30,000", "5 lakh"), intent accuracy, grounding rejects a fabricated number, local fallback without key |
| 11 | React app: shell, auth, all 12 pages, charts, CSV wizard, simulator UI, coach chat | `npm run build`; each page manually verified against the live API |
| 12 | Integration: dashboard aggregate, deep links twin→simulator, recalculation after writes, empty/error states | Walk through all 18 acceptance criteria end-to-end as a new user |
| 13 | Testing hardening: edge-case sweep, coverage report, fix findings | Full suite green; coverage on `services/` ≥ 80% |
| 14 | Backend/frontend Dockerfiles, nginx, full compose, README, setup.md, viva.md, deployment notes | `docker compose up --build` from clean clone → seeded demo works |

## 6. Phase log

### Phase 1: Requirements analysis & architecture ✅ (2026-10-08)
- Produced `docs/architecture.md` (schema, twin model, score, analytics, forecasting, simulation, goals, coach/RAG, ML pipeline, API, frontend, security, degradation, folder structure) and this plan.
- Environment check: Python 3.11.9, Node 24.13 / npm 11.6, Docker 29.7 installed (daemon not running), no local `psql`.

### Phase 2: Repository & dev environment ✅ (2026-10-08), except the live Postgres check
- git repo (`main`), `.gitignore`, `.env.example`, `docker-compose.yml` (Postgres 16 with healthcheck).
- Backend: `create_app` factory, env config (production refuses the default JWT secret), extensions (SQLAlchemy, Migrate → `database/migrations`, JWT, CORS limited to `FRONTEND_ORIGIN`), JSON envelope + error handlers (400/404/405/413/503/500), `GET /api/health` with a DB probe (3 s connect timeout). Pinned `requirements.txt`, ruff + pytest config.
- Frontend: Vite 8 + React 19 + Tailwind 4, oxlint, `/api` dev proxy, `services/api.js` (envelope unwrap → `ApiError`), status page reading `/api/health`.
- Verified: 10 pytest tests pass; ruff clean; oxlint clean; `npm run build` ok; `docker compose config` valid; live backend returns 503 "degraded" with Postgres down and 200 with SQLite; browser shows "Backend ok · database up" through the Vite proxy.
- Open: Docker Desktop did not start non-interactively, so `docker compose up db` → healthy has to be confirmed once it is running (carried into Phase 3, which needs it anyway).
- Deviation: the Vite template now ships **oxlint** instead of ESLint. Kept, since it's faster and needs zero config.

### Phase 3: Schema & seed data ✅ (2026-10-08), PostgreSQL verified offline only
- 15 SQLAlchemy 2 models (`app/models/`) with CHECK/UNIQUE/FK constraints, cascades, indexes, portable enums, and a constraint naming convention. SQLite foreign-key enforcement is switched on for tests.
- Alembic migration `0001_initial_schema` in `database/migrations`. Removed the duplicate enum CHECKs that autogenerate adds.
- `services/financial/formulas.py`: EMI, outstanding balance and future value.
- `app/seed/`: 22 categories (idempotent), a deterministic synthetic generator with labelled anomalies, and the demo user with consistent loan, SIP, investments and goals. `flask seed [--reset]`.
- Tests: 48 pass. Formulas are checked against hand calculations; each constraint is tested with ORM and raw SQL; cascade and RESTRICT; generator determinism, coverage, labels, festive spike and dining creep; seed idempotency and reset; and the migration is checked to build exactly the models' tables and columns, enforce CHECKs, and downgrade cleanly.
- Verified via the CLI: `flask db upgrade` + `flask seed` on a fresh SQLite file (1,160 transactions in ~1 s, idempotent). `flask db upgrade --sql` compiles valid PostgreSQL DDL.
- Problems fixed:
  - The `date` column annotation shadowed the `date` type.
  - Autogenerate duplicated the enum CHECK constraints.
  - A deprecated `get_engine()` call in `env.py`.
  - The first demo data had dining creep hidden by noise and an unrealistically large cash pile; the persona was re-tuned.
  - A cp1252 encoding crash in a helper script emptied `docs/setup.md`; it was restored from git.
- Open: run `flask db upgrade` against live PostgreSQL once Docker Desktop is running.
