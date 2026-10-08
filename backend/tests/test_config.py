import pytest

from app.config import DEFAULT_JWT_SECRET, ProductionConfig, get_config


def test_unknown_env_rejected():
    with pytest.raises(RuntimeError, match="Unknown APP_ENV"):
        get_config("staging")


def test_production_refuses_default_secret(monkeypatch):
    monkeypatch.setattr(ProductionConfig, "JWT_SECRET_KEY", DEFAULT_JWT_SECRET)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        get_config("production")


def test_production_accepts_strong_secret(monkeypatch):
    monkeypatch.setattr(ProductionConfig, "JWT_SECRET_KEY", "x" * 48)
    assert get_config("production") is ProductionConfig
