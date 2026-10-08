"""Offline ML pipeline (dataset building, training, evaluation). Separate from inference,
which lives in backend/app/services. Feature code is imported from the backend package so
training and serving use exactly the same transformations."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
MODELS_DIR = ROOT / "ml" / "models"
METRICS_DIR = MODELS_DIR / "metrics"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
