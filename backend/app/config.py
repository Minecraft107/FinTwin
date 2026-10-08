"""Environment-driven configuration. All secrets come from env vars (see .env.example)."""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

DEFAULT_JWT_SECRET = "change-me"
DEFAULT_DATABASE_URL = "postgresql+psycopg://fintwin:fintwin@localhost:5432/fintwin"


def _engine_options(uri: str) -> dict:
    options: dict = {"pool_pre_ping": True}
    if uri.startswith("postgresql"):
        # Fail fast instead of hanging when Postgres is down; /api/health then reports 503.
        options["connect_args"] = {"connect_timeout": 3}
    return options


class Config:
    APP_ENV = "development"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options(SQLALCHEMY_DATABASE_URI)
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", DEFAULT_JWT_SECRET)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=12)
    FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024  # CSV upload limit
    MIGRATIONS_DIR = str(REPO_ROOT / "database" / "migrations")
    MODEL_DIR = os.getenv("MODEL_DIR", str(REPO_ROOT / "ml" / "models"))
    # AI Coach: "local" (no key needed, deterministic), "openai" or "gemini".
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "local")
    LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "20"))
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@fintwin.app")
    DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "FinTwin@Demo2026")


class TestingConfig(Config):
    APP_ENV = "testing"
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = _engine_options("sqlite://")
    JWT_SECRET_KEY = "test-secret-key-that-is-long-enough-for-hs256"
    LLM_PROVIDER = "local"


class ProductionConfig(Config):
    APP_ENV = "production"


CONFIGS: dict[str, type[Config]] = {
    "development": Config,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(env: str | None = None) -> type[Config]:
    env = env or os.getenv("APP_ENV", "development")
    if env not in CONFIGS:
        raise RuntimeError(f"Unknown APP_ENV '{env}'. Use one of: {', '.join(CONFIGS)}")
    config = CONFIGS[env]
    if config is ProductionConfig and config.JWT_SECRET_KEY == DEFAULT_JWT_SECRET:
        raise RuntimeError("JWT_SECRET_KEY must be set to a strong random value in production.")
    return config
