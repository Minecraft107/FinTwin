"""Train and evaluate the ML stage of the categorizer (used only when keyword rules miss).

Data: a hand-curated list of real-world Indian merchants per category
(ml/datasets/categorizer_corpus.csv), expanded into bank-statement-style descriptions
("UPI/48213/ZOMATO", "POS 4411 CROMA BLR", ...).

Evaluation uses GroupKFold *by merchant*: every score is on merchant names the model never
saw in training — the situation it faces in production. Reported: ML alone, keyword rules
alone, and the production cascade (rules -> ML above threshold -> "Other").
"""

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import FeatureUnion, Pipeline

import ml  # noqa: F401
from app.services.ml.categorizer import (
    ML_CONFIDENCE_THRESHOLD,
    match_rules,
    normalize_description,
)

CORPUS = Path(__file__).resolve().parents[1] / "datasets" / "categorizer_corpus.csv"
TEMPLATES = [
    "{M}",
    "{m}",
    "UPI/{ref}/{M}",
    "UPI-{M}-{ref}",
    "POS {ref4} {M} {city}",
    "{M} ORDER {ref}",
    "NEFT/{ref}/{M}",
    "ACH/{M}/{ref}",
    "IMPS {ref} {M}",
    "PAYMENT TO {M}",
    "{M} {city}",
    "BIL/{ref}/{M}",
]
CITIES = ["BANGALORE", "MUMBAI", "DELHI", "PUNE", "HYDERABAD", "CHENNAI", "KOLKATA", "BLR", "MUM"]


def make_examples(corpus: pd.DataFrame, seed: int = 0, per_merchant: int = 8) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for merchant, category in corpus.itertuples(index=False):
        for template in rng.choice(TEMPLATES, size=per_merchant, replace=False):
            text = template.format(
                M=merchant.upper(),
                m=merchant,
                ref=int(rng.integers(10_000, 99_999_999)),
                ref4=int(rng.integers(1000, 9999)),
                city=str(rng.choice(CITIES)),
            )
            rows.append((text, category, merchant))
    return pd.DataFrame(rows, columns=["text", "category", "merchant"])


def build_model() -> Pipeline:
    def vectorizer(**kwargs) -> TfidfVectorizer:
        return TfidfVectorizer(preprocessor=normalize_description, sublinear_tf=True, **kwargs)

    return Pipeline(
        [
            (
                "features",
                FeatureUnion(
                    [
                        ("char", vectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=2)),
                        ("word", vectorizer(ngram_range=(1, 2))),
                    ]
                ),
            ),
            ("clf", LogisticRegression(max_iter=3000, C=4.0, class_weight="balanced")),
        ]
    )


def evaluate(examples: pd.DataFrame, folds: int = 5) -> dict:
    predicted = np.empty(len(examples), dtype=object)
    confidence = np.zeros(len(examples))
    for train_idx, test_idx in GroupKFold(n_splits=folds).split(
        examples, groups=examples["merchant"]
    ):
        model = build_model().fit(
            examples["text"].iloc[train_idx], examples["category"].iloc[train_idx]
        )
        proba = model.predict_proba(examples["text"].iloc[test_idx])
        predicted[test_idx] = model.classes_[proba.argmax(axis=1)]
        confidence[test_idx] = proba.max(axis=1)

    truth = examples["category"].to_numpy()
    rules = np.array([match_rules(t, None, "expense") or "Other" for t in examples["text"]])
    rule_hit = rules != "Other"
    confident = confidence >= ML_CONFIDENCE_THRESHOLD
    cascade = np.where(rule_hit, rules, np.where(confident, predicted, "Other"))
    rules_only = np.where(rule_hit, rules, "Other")
    misses = ~rule_hit
    return {
        "protocol": f"GroupKFold({folds}) by merchant: scored only on unseen merchant names",
        "examples": len(examples),
        "merchants": int(examples["merchant"].nunique()),
        "categories": int(examples["category"].nunique()),
        "ml_alone": {
            "accuracy": round(accuracy_score(truth, predicted), 4),
            "macro_f1": round(f1_score(truth, predicted, average="macro"), 4),
        },
        "ml_above_threshold": {
            "threshold": ML_CONFIDENCE_THRESHOLD,
            "coverage": round(float(confident.mean()), 4),
            "accuracy": round(accuracy_score(truth[confident], predicted[confident]), 4)
            if confident.any()
            else None,
        },
        "rules_only": {
            "coverage": round(float(rule_hit.mean()), 4),
            "accuracy_when_matched": round(accuracy_score(truth[rule_hit], rules[rule_hit]), 4),
            "overall_accuracy": round(accuracy_score(truth, rules_only), 4),
        },
        "cascade": {
            "overall_accuracy": round(accuracy_score(truth, cascade), 4),
            "macro_f1": round(f1_score(truth, cascade, average="macro"), 4),
            "ml_resolved_rule_misses": round(
                float((confident & misses).sum() / max(misses.sum(), 1)), 4
            ),
            "ml_accuracy_on_rule_misses": round(
                accuracy_score(truth[misses & confident], predicted[misses & confident]), 4
            )
            if (misses & confident).any()
            else None,
        },
    }


def train_and_evaluate(seed: int = 0) -> tuple[Pipeline, dict]:
    corpus = pd.read_csv(CORPUS)
    examples = make_examples(corpus, seed)
    report = evaluate(examples)
    model = build_model().fit(examples["text"], examples["category"])
    return model, report
