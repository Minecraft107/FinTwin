"""Synthetic training population: many randomised personas from the same generator as the demo
seed. Labels for injected anomalies are kept (the `anomaly` column) for evaluation."""

from datetime import date

import numpy as np
import pandas as pd

import ml  # noqa: F401  (puts backend/ on sys.path)
from app.seed.categories import CATEGORIES
from app.seed.synthetic import generate_transactions, random_persona

KIND = {name: kind.value for name, kind, *_ in CATEGORIES}
POPULATION_END = date(2026, 9, 30)  # fixed, so training is reproducible regardless of today


def build_population(
    n_users: int = 300, months: int = 30, end: date = POPULATION_END, seed: int = 7
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frames = []
    for user_id in range(n_users):
        persona = random_persona(rng, months)
        rows = generate_transactions(persona, end, months, seed=seed * 100_000 + user_id)
        frame = pd.DataFrame(rows)
        frame["user_id"] = user_id
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"])
    df["kind"] = df["category"].map(KIND)
    df["id"] = np.arange(len(df))
    return df


def split_users(n_users: int, test_share: float = 0.2, seed: int = 11) -> tuple[set, set]:
    users = np.random.default_rng(seed).permutation(n_users)
    cut = int(n_users * (1 - test_share))
    return set(users[:cut].tolist()), set(users[cut:].tolist())
