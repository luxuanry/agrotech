"""M2: how likely is a product with this matrix to need each additive function?

One gradient-boosting classifier per function, trained on the product matrix
(base, protein, fat, sugars, base %, barista, organic, vitamins). Each model is
compared with a baseline that only knows the base type, using 5-fold
cross-validated AUC. If a model does not beat its baseline, we say so.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold

from .additives import BASES, FUNCTIONS

log = logging.getLogger(__name__)

BASE_LEVELS = [b for b, _ in BASES] + ["other"]
NUMERIC = ["protein", "fat", "sugars", "base_pct"]
FLAGS = ["barista", "organic", "vitamins"]
FEATURE_LABELS = {
    **{f"base_{b}": f"{b} base" for b in BASE_LEVELS},
    "protein": "protein", "fat": "fat", "sugars": "sugars", "base_pct": "base %",
    "barista": "barista version", "organic": "organic", "vitamins": "added vitamins",
}
MIN_POSITIVES = 10

try:  # SHAP is optional; without it we fall back to global importances.
    import shap  # type: ignore
except ImportError:  # pragma: no cover
    shap = None


def features(frame: pd.DataFrame) -> pd.DataFrame:
    """Model input matrix, same columns for training and prediction."""
    out = pd.DataFrame(index=frame.index)
    for b in BASE_LEVELS:
        out[f"base_{b}"] = (frame["base"] == b).astype(float)
    for col in NUMERIC:
        out[col] = frame[col].astype(float)
    for col in FLAGS:
        out[col] = frame[col].astype(bool).astype(float)
    return out


def _baseline_scores(train: pd.DataFrame, test: pd.DataFrame, target: str) -> np.ndarray:
    """P(function | base) estimated on the training fold."""
    rates = train.groupby("base")[target].mean()
    overall = train[target].mean()
    return test["base"].map(rates).fillna(overall).to_numpy(dtype=float)


class FunctionModels:
    """Holds one trained model per function plus its validation metrics."""

    def __init__(self) -> None:
        self.models: dict[str, GradientBoostingClassifier] = {}
        self.metrics: dict[str, dict] = {}
        self.explainers: dict[str, object] = {}

    def fit(self, df: pd.DataFrame) -> "FunctionModels":
        X = features(df)
        for func in FUNCTIONS:
            target = f"has_{func}"
            y = df[target].astype(int)
            positives, negatives = int(y.sum()), int(len(y) - y.sum())
            if min(positives, negatives) < MIN_POSITIVES:
                self.metrics[func] = {"status": "skipped", "reason": f"only {min(positives, negatives)} examples in the minority class", "n": len(y)}
                continue
            self.metrics[func] = self._cross_validate(df, X, y, target)
            model = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=0)
            model.fit(X, y)
            self.models[func] = model
            if shap is not None:
                self.explainers[func] = shap.TreeExplainer(model)
        return self

    def _cross_validate(self, df: pd.DataFrame, X: pd.DataFrame, y: pd.Series, target: str) -> dict:
        model_scores = np.zeros(len(y))
        base_scores = np.zeros(len(y))
        folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
        for train_idx, test_idx in folds.split(X, y):
            m = GradientBoostingClassifier(n_estimators=150, max_depth=3, learning_rate=0.05, random_state=0)
            m.fit(X.iloc[train_idx], y.iloc[train_idx])
            model_scores[test_idx] = m.predict_proba(X.iloc[test_idx])[:, 1]
            base_scores[test_idx] = _baseline_scores(df.iloc[train_idx], df.iloc[test_idx], target)
        auc_model = float(roc_auc_score(y, model_scores))
        auc_base = float(roc_auc_score(y, base_scores))
        return {
            "status": "trained",
            "n": int(len(y)),
            "positives": int(y.sum()),
            "auc_model": round(auc_model, 3),
            "auc_baseline": round(auc_base, 3),
            "beats_baseline": auc_model > auc_base,
        }

    def predict(self, row: dict) -> dict[str, dict]:
        """Probability that a product with this matrix uses each function,
        plus the three features that pushed the prediction most."""
        X = features(pd.DataFrame([row]))
        out: dict[str, dict] = {}
        for func, model in self.models.items():
            prob = float(model.predict_proba(X)[0, 1])
            out[func] = {"probability": round(prob, 3), "drivers": self._drivers(func, model, X)}
        return out

    def _drivers(self, func: str, model: GradientBoostingClassifier, X: pd.DataFrame) -> list[dict]:
        if func in self.explainers:
            values = np.asarray(self.explainers[func].shap_values(X)).reshape(-1)[: X.shape[1]]
            order = np.argsort(-np.abs(values))[:3]
            return [
                {"feature": FEATURE_LABELS[X.columns[i]], "effect": "raises" if values[i] > 0 else "lowers", "kind": "shap"}
                for i in order if abs(values[i]) > 1e-6
            ]
        order = np.argsort(-model.feature_importances_)[:3]
        return [{"feature": FEATURE_LABELS[X.columns[i]], "effect": "matters", "kind": "global_importance"} for i in order]
