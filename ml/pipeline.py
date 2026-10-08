"""Run the whole offline pipeline: build data -> train -> evaluate -> save artifacts + metrics.

python -m ml.pipeline            (from the repository root)
flask ml train                   (from backend/, same thing)
"""

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import joblib

from ml import MODELS_DIR
from ml.datasets.population import build_population, split_users

logger = logging.getLogger("ml.pipeline")

N_USERS = 300
MONTHS = 30


def _save_metrics(models_dir: Path, name: str, metrics: dict) -> None:
    metrics_dir = models_dir / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds")} | metrics
    (metrics_dir / f"{name}.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")


def run(n_users: int = N_USERS, models_dir: Path = MODELS_DIR) -> dict:
    from ml.training import categorizer, forecaster

    started = time.perf_counter()
    models_dir.mkdir(parents=True, exist_ok=True)
    population = build_population(n_users=n_users, months=MONTHS)
    train_users, test_users = split_users(n_users)
    logger.info("Population: %d users, %d transactions", n_users, len(population))

    model, report = forecaster.train_and_evaluate(population, train_users, test_users)
    joblib.dump(model, models_dir / "forecaster_xgb.joblib")
    _save_metrics(models_dir, "forecaster", report)
    logger.info("Forecaster: total-level MAE %s", report["total_level"]["xgboost"]["mae"])

    cat_model, cat_report = categorizer.train_and_evaluate()
    joblib.dump(cat_model, models_dir / "categorizer.joblib")
    _save_metrics(models_dir, "categorizer", cat_report)
    logger.info("Categorizer: cascade accuracy %s", cat_report["cascade"]["overall_accuracy"])

    from ml.evaluation import anomaly

    anomaly_report = anomaly.evaluate(population)
    _save_metrics(models_dir, "anomaly", anomaly_report)
    logger.info(
        "Anomaly detection: F1 %s",
        anomaly_report["transaction_level"]["production (MEDIUM+ alerts)"]["f1"],
    )

    return {
        "seconds": round(time.perf_counter() - started, 1),
        "forecaster": report,
        "categorizer": cat_report,
        "anomaly": anomaly_report,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    result = run()
    print(f"Done in {result['seconds']}s")
