# Local development setup

## Quick start: everything in Docker
```bash
docker compose up --build
```
This starts PostgreSQL, the Flask API (migrations, demo seed and model training happen automatically) and nginx serving the React build. Open **http://localhost:8080** and use **Log in → Explore the demo account**. No `.env` is needed; if one exists, its values are used. If port 5432 or 8080 is taken, set `POSTGRES_PORT` / `WEB_PORT` in `.env`. To stop, run `docker compose down`; add `-v` to also delete the database volume.

## Local development
Prerequisites: **Python 3.11**, **Node 20+**, **Docker Desktop** (for PostgreSQL).

## 1. Environment file
```bash
cp .env.example .env
```
The defaults work for local development. Set a real `JWT_SECRET_KEY` before deploying anywhere.

## 2. Database (PostgreSQL in Docker)
Start Docker Desktop first, then from the repo root:
```bash
docker compose up -d db
```
```bash
docker compose ps
```
Wait until `db` shows `healthy`.

## 3. Backend (Flask, port 5000)
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
```
Create the schema and the demo data. Run these once, and again after pulling new migrations:
```bash
flask db upgrade
```
```bash
flask seed
```
`flask seed` is idempotent. It creates the 22 reference categories and a demo user with 24 months of synthetic history ending **today**. The demo login is the `DEMO_EMAIL` / `DEMO_PASSWORD` pair in `.env`. To regenerate the demo data, for example after a month has passed:
```bash
flask seed --reset
```
Train the ML models (≈ 90 s). This is optional: without them the app falls back to baseline forecasting and rule-only categorization. Re-run it after changing anything in `ml/`:
```bash
flask ml train
```
Artifacts go to `ml/models/` (git-ignored); evaluation metrics go to `ml/models/metrics/` (committed). See [ml.md](ml.md).

AI Coach (optional). By default `LLM_PROVIDER=local`: the coach answers deterministically from your data, with no API key. To have an LLM write the explanations, set these in `.env`:
- `LLM_PROVIDER=openai` with `OPENAI_API_KEY` (model `OPENAI_MODEL`, default `gpt-4o-mini`), or
- `LLM_PROVIDER=gemini` with `GEMINI_API_KEY` (model `GEMINI_MODEL`, default `gemini-2.0-flash`).

If the key is missing or invalid, the API fails, or an answer quotes a number not found in your data, the coach falls back to the local answer automatically.

Start the API:
```bash
python run.py
```
Check: `http://localhost:5000/api/health` → `{"data": {"status": "ok", "database": "up", ...}}`.
If Postgres is not running, the same endpoint returns **503** with `"database": "down"`; the app itself keeps running.

Quick try without Docker: set `DATABASE_URL=sqlite:///fintwin-dev.db` in `.env`, then run the same upgrade → seed → run steps. PostgreSQL remains the supported database.

## 4. Frontend (Vite + React, port 5173)
```bash
cd frontend
npm install
npm run dev
```
The dev server proxies `/api/*` to `http://localhost:5000`, so no CORS setup is needed during development.

Open `http://localhost:5173`, then use **Log in → Explore the demo account** (one click, no password needed; it requires `flask seed` and `DEMO_LOGIN_ENABLED=true`, the default outside production), or create your own account.

To try the import as a new user: **Transactions → Import CSV → Download a sample statement** (6 months of realistic data), then upload that file. It can also be generated from `backend/`:
```bash
flask sample-csv --out sample_statement.csv
```

Production build: `npm run build` produces `frontend/dist/` (served by nginx in the Docker image).

## 5. Quality checks
| What | Command (run inside the folder) |
|---|---|
| Backend tests | `backend/`: `pytest` |
| Backend tests + coverage | `backend/`: `pytest --cov=app` |
| Backend lint / format | `backend/`: `ruff check .` and `ruff format --check .` |
| Frontend lint | `frontend/`: `npm run lint` |
| Frontend unit tests | `frontend/`: `npm test` (Node's built-in runner) |
| Frontend production build | `frontend/`: `npm run build` |

Backend tests use an in-memory SQLite database, so they need neither Docker nor Postgres.
