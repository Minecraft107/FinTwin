# FinTwin — AI-Powered Financial Health Digital Twin

> **Analyze. Predict. Simulate. Decide Better.**

```bash
docker compose up --build        # then open http://localhost:8080 → Log in → "Explore the demo account"
```

*FinTwin is a decision-support and educational tool, not a licensed financial advisor. Forecasts and simulations are estimates based on your data and stated assumptions.*

---

## Contents
1. [Project overview](#1-project-overview) · 2. [Problem statement](#2-problem-statement) · 3. [Solution](#3-solution) · 4. [Features](#4-features) · 5. [Architecture](#5-architecture) · 6. [Technology stack](#6-technology-stack) · 7. [Folder structure](#7-folder-structure) · 8. [Database schema](#8-database-schema) · 9. [API documentation](#9-api-documentation) · 10. [ML pipeline](#10-ml-pipeline) · 11. [Digital Twin](#11-digital-twin-explanation) · 12. [Simulation engine](#12-simulation-engine-explanation) · 13. [AI Coach](#13-ai-coach-architecture) · 14. [RAG](#14-rag-architecture) · 15. [Installation](#15-installation) · 16. [Environment variables](#16-environment-variables) · 17. [Database setup](#17-database-setup) · 18. [Running locally](#18-running-locally) · 19. [Running tests](#19-running-tests) · 20. [Training ML models](#20-training-ml-models) · 21. [Demo credentials](#21-demo-credentials) · 22. [Deployment](#22-deployment) · 23. [Limitations](#23-limitations) · 24. [Future scope](#24-future-scope)

Further reading: [architecture](docs/architecture.md) · [API reference](docs/api.md) · [ML & evaluation](docs/ml.md) · [simulation engine](docs/simulation.md) · [setup](docs/setup.md) · [viva guide](docs/viva.md) · [phase log](docs/implementation-plan.md)

---

## 1. Project overview
FinTwin builds a **Financial Digital Twin**: a live, derived model of a person's finances, rebuilt from their transactions, profile, investments, loans and goals. Everything else works on that twin:

- **Analyze:** spending analytics, a transparent 0–100 Financial Health Score, and risk alerts.
- **Predict:** ML spending forecasts with likely ranges, and anomaly detection.
- **Simulate:** a deterministic What-If engine ("Can I afford a ₹1.3 lakh laptop?", "What if my income falls 20%?").
- **Decide:** an AI Financial Coach that explains these results in plain language, grounded in the user's own numbers.

It is an Indian-context product: ₹ with lakh/crore grouping, UPI/NEFT bank statements, SIPs, EMIs, PPF and festive-season spending.

## 2. Problem statement
Most people track money in hindsight. A bank app or an expense tracker answers *"what did I spend?"*, but not the questions that drive decisions:
- Am I financially healthy, and **why** did that change?
- Where is my spending heading?
- **What happens if** I buy this, take this loan, or lose part of my income?
- Is my goal realistic, and what would make it realistic?

Generic chatbots are no answer either: they don't know the user's data, and they can confidently invent numbers.

## 3. Solution
FinTwin separates **calculation** from **explanation**:

1. All numbers come from deterministic services and trained ML models: the twin builder, the health score, forecasting, anomaly detection, the simulation engine and the goal planner. Each one is unit-tested against hand calculations.
2. The AI Coach (rule-based intent detection, entity parsing, RAG and an optional LLM) only **explains** those numbers. A grounding check rejects any LLM answer that quotes a number not found in the user's data, and falls back to a deterministic answer.
3. Every result says what happened, why, what is likely next and what the user could do, with its assumptions and the estimate disclaimer.

## 4. Features
| Area | What the user gets |
|---|---|
| Accounts | Register / log in (JWT); a one-click demo account |
| Data in | Manual transactions; a **CSV import wizard** for real bank statements (preview, per-row errors, duplicate detection, auto-categorization, category correction that is remembered); profile, investments, loans, goals |
| Dashboard | Health score, KPIs, 12-month income vs spending, alerts, goals, forecast, quick what-if |
| Digital Twin | Current state → health (with "how it's calculated") → predicted state → scenario shortcuts |
| Analytics | 7d/30d/3m/6m/12m/custom ranges; essential vs discretionary; categories; trends; cash balance; category changes; top merchants |
| Health Score | 7 components on published guideline anchors; strengths, weaknesses, ranked improvements; "why did my score change?" |
| Forecasts | Per-category spending forecast with an 80% range; the model chosen and its backtest; cash-flow projection |
| Risks | Ratio rules, unusual transactions (robust statistics + Isolation Forest), abnormal months, category drift, duplicates |
| Goals | Required monthly saving, fundable amount by priority, projected completion, concrete options to get back on track |
| What-If | 8 combinable change types, 6–60 month horizon, inflation, current vs simulated comparison, saved scenarios |
| AI Coach | Questions in plain English (lakh/crore understood), answers split into your data / calculations / estimates / options / background, sources cited, conversation history |

## 5. Architecture
```
 React SPA (Vite, Recharts, Tailwind)  ──REST/JSON + JWT──►  nginx (prod) / Vite proxy (dev)
                                                                      │
 Flask API: routes (HTTP + pydantic validation) ──► services (pure Python, no Flask/DB) ◄── repositories (SQLAlchemy, user-scoped)
                                                                      │
   data ─► categorize ─► DIGITAL TWIN ─┬─► ANALYZE  analytics · health score · anomalies · risks
                                       ├─► PREDICT  forecasting (baselines + global XGBoost)
                                       └─► SIMULATE simulation engine · goal planner
                    all results ─► AI COACH  intent → entities → context → RAG → LLM / local → grounding check
                                                                      │
 PostgreSQL 16              ml/models (trained artifacts + metrics)          LLM API (optional: OpenAI / Gemini)
```
**Rules that hold everywhere:** routes never compute; services never touch Flask or the database, so every number is unit-testable; the LLM never calculates; every feature has a fallback when data, a model or the LLM is missing. Details: [docs/architecture.md](docs/architecture.md).

## 6. Technology stack
| Layer | Technology |
|---|---|
| Frontend | React 19, Vite, React Router, Recharts, Tailwind CSS 4, lucide-react, oxlint |
| Backend | Python 3.11, Flask 3, Flask-SQLAlchemy, Flask-Migrate (Alembic), Flask-JWT-Extended, flask-cors, pydantic v2, gunicorn |
| Database | PostgreSQL 16 (SQLite for tests / quick local try) |
| Data & ML | pandas, NumPy, scikit-learn (Logistic Regression, Isolation Forest, TF-IDF, TruncatedSVD), XGBoost, joblib |
| AI | Rule-based NLU, hybrid TF-IDF + LSA retrieval (RAG), OpenAI / Gemini over REST (optional), deterministic local provider |
| Ops | Docker, docker compose, nginx |
| Quality | pytest (499 tests, 98% coverage), ruff, Node's built-in test runner, oxlint |

## 7. Folder structure
```
Fintwin/
├── backend/
│   ├── app/
│   │   ├── routes/           one blueprint per area (auth, transactions, twin, analytics, health, forecast,
│   │   │                     risks, simulation, goals, coach, dashboard, profile, holdings, system)
│   │   ├── schemas/          pydantic request models
│   │   ├── models/           SQLAlchemy models
│   │   ├── repositories/     user-scoped queries → DataFrames / dataclasses
│   │   ├── services/
│   │   │   ├── digital_twin/ builder.py (the twin), state.py, service.py (snapshots, recalculation)
│   │   │   ├── financial/    health_score.py, goals.py, goal_planner.py, formulas.py (EMI, annuity)
│   │   │   ├── analytics/    aggregations.py, anomalies.py, risk_service.py
│   │   │   ├── forecasting/  models.py (baselines, XGBoost), service.py (selection, bands)
│   │   │   ├── simulation/   engine.py, scenarios.py, service.py
│   │   │   ├── coach/        intent, entities, scenario_parser, context, rag, grounding, local, llm/
│   │   │   ├── ml/           features.py (shared with training), categorizer.py, artifacts.py
│   │   │   └── importer/     csv_import.py
│   │   ├── seed/             categories, synthetic data generator, demo user, sample statement
│   │   └── utils/
│   ├── knowledge_base/       13 guides used by the coach's retrieval
│   ├── tests/                pytest suite
│   ├── Dockerfile · docker-entrypoint.sh · requirements*.txt · run.py
├── frontend/
│   ├── src/                  pages/, components/, charts/, layouts/, context/, hooks/, services/api.js, utils/
│   ├── Dockerfile · nginx.conf
├── ml/                       datasets/ (synthetic population, categorizer corpus) · training/ · evaluation/ ·
│                             pipeline.py · models/ (artifacts git-ignored, metrics/ committed)
├── database/                 migrations/ (Alembic) · seed/ (sample CSV with deliberate errors)
├── docs/                     architecture, api, ml, simulation, setup, viva, implementation-plan
├── docker-compose.yml · .env.example
```

## 8. Database schema
15 tables, all user data scoped by `user_id` with `ON DELETE CASCADE`. Money is `NUMERIC(14,2)`; enums are `VARCHAR + CHECK`.
```
users ─┬─< financial_profiles (1:1)            ├─< financial_snapshots ──< financial_health_scores (1:1)
       ├─< transactions >── expense_categories  ├─< forecast_results
       ├─< investments                          ├─< risk_alerts (fingerprint-unique)
       ├─< loans                                ├─< simulation_scenarios ──< simulation_results
       ├─< financial_goals                      └─< coach_conversations ──< coach_messages
```
Income is a transaction with `type='income'` (one ledger, so nothing is double-counted). There are 22 global categories, each with a kind: income / essential / discretionary / investment / debt. Full column list: [architecture §3](docs/architecture.md#3-database-schema).

## 9. API documentation
Base path `/api`. Every route except `/health` and `/auth/register|login|demo` requires `Authorization: Bearer <token>`. Responses use `{"data": …, "meta": …}` or `{"error": {"code", "message", "details"}}`.

| Area | Endpoints |
|---|---|
| System | `GET /health` · `GET /ml/status` |
| Auth | `POST /auth/register` · `POST /auth/login` · `POST /auth/demo` · `GET /auth/me` |
| Profile & holdings | `GET/PUT /financial-profile` · `/investments` · `/loans` · `/goals` (CRUD) · `GET /categories` |
| Transactions | `GET/POST /transactions` · `PUT/DELETE /transactions/:id` · `POST /transactions/import/preview` · `POST /transactions/import` · `GET /transactions/import/sample` |
| Twin & score | `GET /dashboard` · `GET /digital-twin` · `/digital-twin/history` · `GET /health-score` · `/health-score/history` · `/health-score/methodology` |
| Analytics | `GET /analytics/overview` · `/categories` · `/trends` · `/merchants` |
| Prediction | `GET /forecast/expenses` · `GET /forecast/cash-flow` · `GET /risks` · `POST /risks/scan` · `PATCH /risks/:id` |
| Simulation | `POST /simulation/what-if` · `GET/POST /simulation/scenarios` · `GET/DELETE /simulation/scenarios/:id` · `POST /simulation/scenarios/:id/run` |
| Goals | `GET /goals/plan` · `GET /goals/:id/plan` · `POST /goals/:id/simulate` |
| Coach | `POST /coach/chat` · `GET /coach/conversations` · `GET/DELETE /coach/conversations/:id` |

Request and response schemas with examples: [docs/api.md](docs/api.md).

## 10. ML pipeline
Training is offline and separate from serving. `ml/pipeline.py` builds a **synthetic population** (300 personas × 30 months ≈ 404k transactions, with labelled injected anomalies), then trains and evaluates every model and writes `ml/models/*.joblib` plus `ml/models/metrics/*.json`. The backend only loads artifacts. Feature engineering is a single module (`services/ml/features.py`) imported by both sides, so training and serving can't drift.

| Model | Method | Measured result (held-out data) | Baseline |
|---|---|---|---|
| Spending forecast | Global XGBoost (absolute-error loss) on scale-normalised lags, rolling stats and seasonality; champion–challenger against naive / moving average / seasonal naive / Holt | MAE **₹5,312**, R² **0.87** (total monthly spending, 60 unseen users) | best baseline ₹6,975 / 0.78 |
| Categorization | Cascade: the user's corrections → ~140 keyword rules → TF-IDF + Logistic Regression (accepted at p ≥ 0.55) | **61.9%** on unseen merchants (merchant-grouped CV); 92.7% where ML fills the rules' gaps | rules alone 56.5% |
| Transaction anomalies | Robust z-score (median/MAD) + per-user Isolation Forest; agreement → HIGH | F1 **0.79** (precision 0.65, recall 1.00) | Isolation Forest alone F1 0.27 |
| Abnormal months | ≥ 2 sd above the prior 6 months, plus a same-month-last-year seasonal check | F1 **0.69** with a year of history | without the seasonal check 0.41 |

Every limitation (synthetic data, optimistic recall) is written up in [docs/ml.md](docs/ml.md).

## 11. Digital Twin explanation
The twin is not a table. It is a **derived state object** (`TwinState`) rebuilt from raw data whenever it's needed, and it is the single input to everything else:
- **Flows:** monthly income, essential and discretionary spending, EMIs and SIPs, averaged over the last 3 *complete* months. A partial month would understate spending.
- **Balances:** cash, emergency fund, investments, debt, goal savings, net worth.
- **Ratios:** savings ratio, debt-to-income, emergency months, investment rate.
- **Provenance:** each figure is marked *observed* (from transactions) or *declared* (from the profile, used until there is history), and every assumption is listed in `notes`.

After any write (transaction, import, profile, holdings, goals), the twin is rebuilt *as of every past month-end*. Those snapshots feed the score history and the "why did my score change?" explanations. The simulator scores its projected futures with the same `derive()` formulas, so "current" and "simulated" are directly comparable.

## 12. Simulation engine explanation
A deterministic month-by-month cash-flow projector ([docs/simulation.md](docs/simulation.md)). The same inputs always give the same output, and every figure can be checked by hand.
- **Baseline:** the twin's flows continue (optionally with inflation); investments compound at their recorded return; loans amortise.
- **Scenario:** the baseline plus up to 10 combinable changes (big purchase, optionally EMI-financed · income change · spending change · SIP change · new loan · save more · delay a goal · one-time income).
- **Each month:** cash += income − spending − EMIs − SIPs − goal contributions (only from cash above a one-month buffer). If cash goes negative, the emergency fund covers it; anything beyond is a **shortfall**.
- **Output:** baseline vs scenario timelines, the impact at 12 months (cash, net worth, surplus, health score, goal delays), a risk level, the recommendation and the full list of assumptions.
- **Risk level:** CRITICAL on any shortfall · HIGH if emergency cover < 1 month, debt-to-income > 50% or the score falls ≥ 15 · MEDIUM for a score drop ≥ 5, any use of the emergency fund, a goal delayed ≥ 3 months, or cash below one month of outgoings · otherwise LOW.

## 13. AI Coach architecture
```
question → intent (weighted keyword rules) → entities (₹, lakh/crore, %, months, goal names)
        → context builder (only the twin / score / forecast / risks / goals sections the intent needs)
        → calculations: affordability & what-if questions run the SIMULATION ENGINE
        → RAG: top guides from the knowledge base
        → provider: local (deterministic, default) | OpenAI | Gemini (LLM_PROVIDER)
        → grounding check: every ₹ / % / decimal must match the context (±1%) or the answer is replaced by the local one
        → sections: your data · calculations · estimates · what you could do · background · sources · disclaimer
```
The LLM receives verified numbers and is told to explain, never to compute. A missing key, timeout, invalid JSON or failed grounding check all fall back to the local provider. Questions asking for specific stock picks get an educational redirect.

## 14. RAG architecture
- **Knowledge base:** 13 original guides (`backend/knowledge_base/*.md`), e.g. 50/30/20 budgeting, emergency funds, EMIs and debt-to-income, SIPs and compounding, goal planning, insurance, inflation, and how the health score works.
- **Indexing:** heading-aware chunks (~120 words, 30-word overlap) → TF-IDF vectors and 64-dimension LSA (TruncatedSVD) embeddings → an in-memory NumPy vector store, rebuilt automatically when a guide changes (~60 ms).
- **Retrieval:** hybrid cosine 0.5 · TF-IDF + 0.5 · LSA. It returns the top 3 hits, one per guide, each scoring ≥ 0.12 and ≥ half the best. TF-IDF catches exact terms ("EMI"); LSA catches paraphrases ("rainy day savings" → *Emergency funds*).
- **Measured:** hit@1 95%, hit@3 100% on 20 labelled questions. Off-topic questions retrieve nothing.
- No GPU or torch download is needed. The upgrade path is sentence-transformer embeddings or pgvector.

## 15. Installation
**Option A, Docker (recommended):** install Docker Desktop, then run:
```bash
git clone <repository-url> fintwin
```
```bash
cd fintwin
```
```bash
docker compose up --build
```
The first build takes a few minutes, because it trains the ML models into the image. Then open **http://localhost:8080**.

**Option B, local development:** Python 3.11, Node 20+, and Docker (for PostgreSQL only). Step-by-step instructions are in [docs/setup.md](docs/setup.md).

## 16. Environment variables
Copy `.env.example` to `.env`. Docker works without it, and `.env` values override the defaults.

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `development` | `production` requires a real `JWT_SECRET_KEY` and disables the demo login |
| `JWT_SECRET_KEY` | `change-me` | Token signing secret. Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `DATABASE_URL` | local Postgres | SQLAlchemy URL (compose points it at the `db` service) |
| `POSTGRES_USER` / `_PASSWORD` / `_DB` / `_PORT` | `fintwin` / `fintwin` / `fintwin` / `5432` | Database container; change `POSTGRES_PORT` if 5432 is taken |
| `WEB_PORT` | `8080` | Port of the Docker web app |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | CORS origin for the Vite dev server |
| `DEMO_EMAIL` / `DEMO_PASSWORD` / `DEMO_LOGIN_ENABLED` | see `.env.example` | Seeded demo account and the one-click demo login |
| `LLM_PROVIDER` | `local` | `local` · `openai` · `gemini` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | — / `gpt-4o-mini` | Optional |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | — / `gemini-2.0-flash` | Optional |
| `TRAIN_MODELS` | `true` | Docker build argument; `false` skips training (baselines are used) |
| `SEED_DEMO` | `true` | Container start-up creates the demo user if missing |

## 17. Database setup
- **Docker:** automatic. On start, the backend runs `flask db upgrade` (Alembic migrations in `database/migrations`) and `flask seed`. Seeding is idempotent: it creates the 22 categories and a demo user with 24 months of synthetic history ending today.
- **Local:** `docker compose up -d db`, then from `backend/` run `flask db upgrade` and `flask seed`. Use `flask seed --reset` to regenerate the demo history.
- **Without Docker:** set `DATABASE_URL=sqlite:///fintwin-dev.db` for a quick try. PostgreSQL remains the supported database.

## 18. Running locally
```bash
docker compose up -d db
```
In `backend/`, with the virtual environment active:
```bash
python run.py
```
In `frontend/`:
```bash
npm run dev
```
Open http://localhost:5173. The Vite dev server proxies `/api` to Flask on port 5000. To try the CSV import as a new user, go to **Transactions → Import CSV → Download a sample statement**.

## 19. Running tests
| Suite | Command | What it covers |
|---|---|---|
| Backend | `pytest` in `backend/` (add `--cov=app` for coverage) | 499 tests, 98% coverage. Financial formulas against hand calculations, twin builder, health score, forecasting, anomalies, simulation scenarios, goal planner, coach NLU / RAG / grounding, CSV edge cases, every API route with junk input, calendar edges, auth and ownership. Runs on in-memory SQLite, so no database is needed |
| Backend lint | `ruff check .` and `ruff format --check .` | Style and import order |
| Frontend | `npm test` and `npm run lint` in `frontend/` | Formatting helpers (Node's test runner); oxlint |
| Build | `npm run build` | Production bundle |

## 20. Training ML models
```bash
flask ml train
```
Run it from `backend/` (≈ 90 s). Equivalent: `python -m ml.pipeline` from the repository root. Docker images train automatically at build time. Without trained models, forecasting uses the statistical baselines and categorization uses rules only; `GET /api/ml/status` shows what is loaded. XGBoost results vary by about 1–2% between operating systems (multithreaded floating-point order); the committed metrics come from a Windows run.

## 21. Demo credentials
- **One click:** Log in → **Explore the demo account** (enabled outside production).
- **Manual:** `demo@fintwin.app` / `FinTwin@Demo2026`, the defaults of `DEMO_EMAIL` / `DEMO_PASSWORD` in `.env.example`. Change them for any shared deployment.

The demo user, Aarav Sharma, has 24 months of realistic history: salary with raises and a bonus, rent, an education-loan EMI, an equity SIP, PPF and gold, festive spending, a few planted anomalies, and three goals (a car, a Europe trip, a higher-studies fund).

## 22. Deployment
The compose stack is production-shaped: PostgreSQL 16 with a volume, Flask on gunicorn, and nginx serving the built SPA and proxying `/api` (one origin, so no CORS). Uploads are capped at 2 MB with JSON errors.

**Checklist for a public deployment:**
1. Set `APP_ENV=production` and a long random `JWT_SECRET_KEY`. The app refuses to start with the default.
2. Set strong `POSTGRES_PASSWORD` / `DEMO_PASSWORD`; keep `DEMO_LOGIN_ENABLED=false` unless it is a demo site.
3. Don't publish the database port: remove `ports:` from the `db` service.
4. Put TLS in front of nginx (a load balancer, or Caddy / Traefik with Let's Encrypt).
5. Back up the `pgdata` volume (`pg_dump`).

**Free hosted setup (used for the live demo): Vercel + Render + Neon**

| Part | Host | Config in this repo |
|---|---|---|
| React frontend | Vercel (CDN, always on) | `frontend/vercel.json` (SPA routes) |
| Flask API + ML (Docker image) | Render free web service | `render.yaml` (blueprint) |
| PostgreSQL | Neon free tier | — |

1. **Neon:** create a project (Singapore region) and copy its connection string. A `postgresql://` URL is fine; the app switches it to the psycopg 3 driver.
2. **Render:** New → Blueprint → this repository. Paste the Neon string as `DATABASE_URL`, and put a placeholder in `FRONTEND_ORIGIN` for now. The first build takes 5–8 minutes (it trains the models). Check `https://<service>.onrender.com/api/health` → `"database": "up"`.
3. **Vercel:** New Project → this repository, with **Root Directory** `frontend` (Vite is detected). Add the environment variable `VITE_API_URL=https://<service>.onrender.com/api`, then deploy.
4. **Render:** set `FRONTEND_ORIGIN` to the Vercel URL (comma-separate several, e.g. a custom domain) and save. CORS then allows the frontend.

Render's free instance sleeps after 15 idle minutes; the first request afterwards takes about a minute. Open the site a few minutes before a demo.

**Other options:**
- **Single VM** (e.g. AWS EC2, Azure VM, DigitalOcean): install Docker, run `docker compose up -d --build`.
- **Managed services:** a managed PostgreSQL (RDS, Azure Database, Neon, Supabase), the backend image on Render / Railway / Cloud Run / Azure Container Apps with `DATABASE_URL` set, and the frontend `dist/` on any static host with `/api` routed to the backend.

## 23. Limitations
- **Synthetic training data.** ML models are trained and evaluated on generated personas, because no public labelled Indian household transaction dataset exists. Results show the methods work as designed, not accuracy on real users.
- **Categorizer:** about 62% accurate on unseen merchants; pure brand names ("Zara") can't be categorized from text. User corrections are remembered.
- **Forecasts:**
  - Income is projected at its recent median; raises and bonuses are not forecast.
  - Categories are forecast independently.
  - Bands assume roughly normal errors.
- **Simulation:** a deterministic model of stated assumptions, not a prediction. No taxes, no investment volatility, and cash earns nothing.
- **Coach:**
  - Intent detection is rule-based (no real question data to train on).
  - Real OpenAI / Gemini calls are covered only by mocked tests; the local provider is the default.
- **Product scope:** INR only. The JWT is kept in `localStorage` (XSS-exposed; httpOnly cookies are the upgrade). No bank API integration, no dark mode.

## 24. Future scope
- Consented, anonymised real data to retrain and re-evaluate the same pipeline; live tracking of forecast error.
- Account Aggregator (India's RBI framework) or bank APIs instead of CSV upload.
- Sentence-transformer embeddings or pgvector for retrieval; a trained intent model once real questions exist.
- Monte-Carlo simulation (income and return uncertainty) alongside the deterministic engine.
- Tax-aware planning (old vs new regime, 80C), insurance adequacy, retirement corpus planning.
- Household / shared accounts, budgets with notifications, dark mode, PWA / mobile app.

---
*FinTwin is a decision-support and educational tool, not a licensed financial advisor. Forecasts and simulations are estimates based on your data and stated assumptions.*
