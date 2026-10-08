import json
import sys

import joblib
import numpy as np
import pytest

from app.config import REPO_ROOT
from app.models.enums import CategorySource
from app.services.ml.categorizer import categorize

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class StubClassifier:
    """Stands in for the trained text classifier: fixed probabilities over two classes."""

    classes_ = np.array(["Healthcare", "Shopping"])

    def __init__(self, healthcare_probability: float):
        self.p = healthcare_probability

    def predict_proba(self, texts):
        return np.array([[self.p, 1 - self.p] for _ in texts])


@pytest.mark.parametrize("probability,expected,source", [
    (0.9, "Healthcare", CategorySource.ML),
    (0.5, "Other", CategorySource.RULE),  # below the 0.55 threshold -> fallback
])  # fmt: skip
def test_ml_stage_runs_after_rules_and_respects_threshold(
    app, tmp_path, probability, expected, source
):
    joblib.dump(StubClassifier(probability), tmp_path / "categorizer.joblib")
    app.config["MODEL_DIR"] = str(tmp_path)
    result = categorize("UPI/88/SRI LAKSHMI MEDICALS", None, "expense")
    assert (result.category, result.source) == (expected, source)
    # Rules still win when they match, and income never goes to the expense model.
    assert categorize("SWIGGY ORDER", None, "expense").source == CategorySource.RULE
    assert categorize("ACME PAYOUT", None, "income").category == "Other Income"


def test_corrupt_artifact_falls_back(app, tmp_path):
    (tmp_path / "categorizer.joblib").write_bytes(b"not a model")
    app.config["MODEL_DIR"] = str(tmp_path)
    assert categorize("UPI/88/SRI LAKSHMI MEDICALS", None, "expense").category == "Other"


def test_pipeline_end_to_end_on_small_population(tmp_path):
    from ml.pipeline import run

    result = run(n_users=24, models_dir=tmp_path)
    assert (tmp_path / "forecaster_xgb.joblib").exists()
    assert (tmp_path / "categorizer.joblib").exists()
    metrics = {p.stem: json.loads(p.read_text()) for p in (tmp_path / "metrics").glob("*.json")}
    assert set(metrics) == {"forecaster", "categorizer", "anomaly"}
    total = metrics["forecaster"]["total_level"]
    assert {"naive", "moving_average", "holt", "xgboost", "per_user_selection"} <= set(total)
    assert all({"mae", "rmse", "r2"} <= set(v) for v in total.values())
    assert 0 <= metrics["categorizer"]["cascade"]["overall_accuracy"] <= 1
    assert metrics["anomaly"]["recall_by_type"]["duplicate"] is not None
    assert result["seconds"] > 0
