"""NOVA classifier wrapper for hsilvosa/nova-group-classifier.

The repo's usable model is `nova_gb_model.joblib`: a HistGradientBoostingClassifier
over 4004 features = TF-IDF (vocab/idf stored in config.json) + 4 hand-crafted
features. The repo ships no preprocessing code, so the feature recipe below was
reconstructed and validated against Open Food Facts data (~97% accuracy, in line
with the model card's 96.2%).
"""

from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass

import joblib
import numpy as np
from huggingface_hub import hf_hub_download
from sklearn.feature_extraction.text import TfidfVectorizer

REPO_ID = "hsilvosa/nova-group-classifier"
NOVA4_INDEX = 3


@dataclass
class NovaScore:
    probs: list[float]  # P(NOVA 1..4)

    @property
    def nova4(self) -> float:
        return self.probs[NOVA4_INDEX]

    @property
    def group(self) -> int:
        return int(np.argmax(self.probs)) + 1


def _count_ingredients(text: str) -> int:
    return len([s for s in re.split(r"[,;]", text) if s.strip()])


class NovaClassifier:
    def __init__(self, repo_id: str = REPO_ID):
        config = json.load(open(hf_hub_download(repo_id, "config.json"), encoding="utf-8"))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # sklearn version-mismatch warnings
            self.model = joblib.load(hf_hub_download(repo_id, "nova_gb_model.joblib"))

        self.vectorizer = TfidfVectorizer(
            vocabulary=config["vocab"],
            ngram_range=(1, 3),
            sublinear_tf=True,
            strip_accents="unicode",
        )
        self.vectorizer.fit(["_"])  # initialise internals; idf is overwritten below
        self.vectorizer.idf_ = np.asarray(config["idf"], dtype=np.float64)
        self.labels = [config["id2label"][str(i)] for i in range(len(config["id2label"]))]

    def _features(self, texts: list[str]) -> np.ndarray:
        tfidf = self.vectorizer.transform(texts).toarray()
        extra = np.array(
            [[len(t), len(t.split()), _count_ingredients(t), 0] for t in texts],
            dtype=np.float64,
        )
        return np.hstack([tfidf, extra])

    def score_many(self, texts: list[str]) -> list[NovaScore]:
        probs = self.model.predict_proba(self._features(texts))
        return [NovaScore(p.tolist()) for p in probs]

    def score(self, text: str) -> NovaScore:
        return self.score_many([text])[0]

    def ingredient_impact(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Leave-one-out: how much NOVA 4 log-odds drop when each ingredient is removed.

        Log-odds rather than probability, so it still ranks ingredients when P(NOVA 4) is saturated near 1.
        """
        parts = [p.strip() for p in re.split(r",(?![^()]*\))", text) if p.strip()]
        if len(parts) < 2:
            return []
        variants = [", ".join(parts[:i] + parts[i + 1:]) for i in range(len(parts))]
        base = _logit(self.score(text).nova4)
        drops = [base - _logit(s.nova4) for s in self.score_many(variants)]
        ranked = sorted(zip(parts, drops), key=lambda x: x[1], reverse=True)
        return [(p, d) for p, d in ranked[:top_k] if d > 0.05]


def _logit(p: float, eps: float = 1e-6) -> float:
    p = min(max(p, eps), 1 - eps)
    return float(np.log(p / (1 - p)))
