# Local development setup

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
python run.py
```
Check: `http://localhost:5000/api/health` → `{"data": {"status": "ok", "database": "up", ...}}`.
If Postgres is not running, the same endpoint returns **503** with `"database": "down"`; the app itself keeps running.

Quick try without Docker (temporary in-memory DB; data is lost on restart):
```bash
DATABASE_URL=sqlite:///:memory: python run.py
```
PowerShell: `$env:DATABASE_URL="sqlite:///:memory:"; python run.py`

## 4. Frontend (Vite + React, port 5173)
```bash
cd frontend
npm install
npm run dev
```
The dev server proxies `/api/*` to `http://localhost:5000`, so no CORS setup is needed during development.

## 5. Quality checks
| What | Command (run inside the folder) |
|---|---|
| Backend tests | `backend/`: `pytest` |
| Backend tests + coverage | `backend/`: `pytest --cov=app` |
| Backend lint / format | `backend/`: `ruff check .` and `ruff format --check .` |
| Frontend lint | `frontend/`: `npm run lint` |
| Frontend production build | `frontend/`: `npm run build` |

Backend tests use an in-memory SQLite database, so they need neither Docker nor Postgres.
