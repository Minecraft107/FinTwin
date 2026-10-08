"""Loads trained model artifacts from MODEL_DIR. A missing or unreadable artifact returns
None, and every caller has a non-ML fallback, so the app never depends on training having run."""

import json
import logging
from functools import lru_cache
from pathlib import Path

import joblib
from flask import current_app, has_app_context

from app.config import Config

logger = logging.getLogger(__name__)

ARTIFACTS = {
    "forecaster": "forecaster_xgb.joblib",
    "categorizer": "categorizer.joblib",
}


def model_dir() -> Path:
    if has_app_context():
        return Path(current_app.config["MODEL_DIR"])
    return Path(Config.MODEL_DIR)


@lru_cache(maxsize=8)
def _load(path: str, mtime: float):  # mtime in the key -> retrained files are picked up
    try:
        return joblib.load(path)
    except Exception:
        logger.exception("Could not load model artifact %s", path)
        return None


def load_artifact(name: str):
    path = model_dir() / ARTIFACTS[name]
    if not path.exists():
        return None
    return _load(str(path), path.stat().st_mtime)


def status() -> dict:
    metrics_dir = model_dir() / "metrics"
    metrics = {}
    if metrics_dir.exists():
        for file in sorted(metrics_dir.glob("*.json")):
            try:
                metrics[file.stem] = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                logger.warning("Unreadable metrics file %s", file)
    return {
        "artifacts": {
            name: {"available": (model_dir() / file).exists(), "file": file}
            for name, file in ARTIFACTS.items()
        },
        "metrics": metrics,
    }
