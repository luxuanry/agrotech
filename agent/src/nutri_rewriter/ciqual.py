"""Ingredient compositions from the Anses Ciqual table (CALNUT 2020, values per 100 g).

Lookup happens in three steps, driven by agent.py:
1. the LLM turns each ingredient name into French search terms in Ciqual's wording,
2. search() below finds candidate foods by keyword overlap,
3. the LLM picks one candidate (or none, e.g. for additives) and the values come
   from the table, never from the LLM. Only unmatched ingredients get an LLM estimate.

data/ciqual.json is built by scripts/build_ciqual.py.
"""

from __future__ import annotations

import json
import re
import unicodedata
from importlib.resources import files

_STOP = {"de", "du", "des", "la", "le", "les", "l", "d", "a", "au", "aux", "et", "ou", "en", "un", "une", "avec", "pour", "type", "aliment", "moyen"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c)).replace("œ", "oe")


def _tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", _norm(s)) if t and t not in _STOP]


def _match(token: str, label_tokens: list[str]) -> float:
    best = 0.0
    for u in label_tokens:
        if token == u:
            return 1.0
        # plural/singular and compounds: "flocons" ~ "flocon", "tournesol" ~ "tournesols"
        if len(token) >= 4 and len(u) >= 4 and (u.startswith(token) or token.startswith(u)):
            best = 0.8
    return best


class Ciqual:
    def __init__(self) -> None:
        data = json.loads((files(__package__) / "data" / "ciqual.json").read_text(encoding="utf-8"))
        self.source: str = data["source"]
        self.foods: list[dict] = data["foods"]
        self.by_code = {f["code"]: f for f in self.foods}
        self._indexed = [(_tokens(f["name"]), f) for f in self.foods]

    def search(self, queries: list[str], limit: int = 8) -> list[dict]:
        """Foods whose name shares the most words with any of the queries, best first."""
        scores: dict[int, float] = {}
        for q in queries:
            qt = _tokens(q)
            if not qt:
                continue
            for label_tokens, food in self._indexed:
                if not label_tokens:
                    continue
                s = sum(_match(t, label_tokens) for t in qt) / len(qt)
                if s < 0.5:
                    continue
                if _match(qt[0], label_tokens[:1]):  # the head noun leads the label: "Huile de tournesol"
                    s += 0.3
                s -= 0.02 * len(label_tokens)  # prefer the plain food over long composite dishes
                if s > scores.get(food["code"], float("-inf")):
                    scores[food["code"]] = s
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:limit]
        return [self.by_code[code] for code, _ in ranked]

    def composition(self, code: int) -> dict:
        f = self.by_code[code]
        comp = {k: f[k] for k in ("kcal", "sugars", "sat_fat", "salt", "fibre", "protein", "fvl", "sweetener")}
        comp["source"] = {"type": "ciqual", "code": code, "name": f["name"]}
        return comp
