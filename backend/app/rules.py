"""Hard rules (layer 1): additive authorisation and nutrition-claim validity.

Claim thresholds below are the liquid-food values from the Annex of
Regulation (EC) No 1924/2006, with the calcium NRV (800 mg) from
Regulation (EU) No 1169/2011 Annex XIII. Additive authorisation comes from
data/rules.json, which is a draft until each entry is verified.
"""

from __future__ import annotations

import json
from functools import lru_cache

from . import config

CALCIUM_NRV_MG = 800.0

# (claim id, label, test, threshold description)
CLAIMS = [
    ("low_energy", "Low energy", lambda n: n["kcal"] <= 20, "≤ 20 kcal / 100 ml"),
    ("low_fat", "Low fat", lambda n: n["fat"] <= 1.5, "≤ 1.5 g fat / 100 ml"),
    ("low_sugars", "Low sugars", lambda n: n["sugars"] <= 2.5, "≤ 2.5 g sugars / 100 ml"),
    ("sugars_free", "Sugars-free", lambda n: n["sugars"] <= 0.5, "≤ 0.5 g sugars / 100 ml"),
    ("source_protein", "Source of protein", lambda n: n["protein_energy_pct"] >= 12, "≥ 12 % of energy from protein"),
    ("high_protein", "High protein", lambda n: n["protein_energy_pct"] >= 20, "≥ 20 % of energy from protein"),
    ("source_calcium", "Source of calcium", lambda n: n["calcium_mg"] >= 0.075 * CALCIUM_NRV_MG, "≥ 60 mg calcium / 100 ml (7.5 % NRV)"),
    ("high_calcium", "High calcium", lambda n: n["calcium_mg"] >= 0.15 * CALCIUM_NRV_MG, "≥ 120 mg calcium / 100 ml (15 % NRV)"),
]


@lru_cache(maxsize=1)
def _rules() -> dict:
    with open(config.RULES_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def sources() -> dict:
    return _rules()["sources"]


def additive_status(code: str, organic: bool) -> dict:
    """Authorisation status of one additive for this product.

    Returns status "fail" only on an explicit False, "unknown" when any
    relevant entry is missing or null, "pass" otherwise. Every answer
    carries `verified` so the UI can show draft entries as such.
    """
    entry = _rules()["additives"].get(code, {})
    category = entry.get("category")
    organic_ok = entry.get("organic") if organic else True
    if category is False or organic_ok is False:
        status = "fail"
    elif category is None or organic_ok is None:
        status = "unknown"
    else:
        status = "pass"
    return {
        "code": code,
        "category_authorised": category,
        "organic_authorised": entry.get("organic") if organic else None,
        "status": status,
        "verified": bool(entry.get("verified", False)),
    }


def complete_nutrition(n: dict) -> dict:
    """Fill kcal and protein energy share when missing (Atwater factors)."""
    out = {k: float(n.get(k) or 0.0) for k in ("protein", "fat", "sugars", "carbs", "calcium_mg", "kcal")}
    if not out["kcal"]:
        out["kcal"] = 4 * out["protein"] + 9 * out["fat"] + 4 * out["carbs"]
    out["protein_energy_pct"] = 100 * 4 * out["protein"] / out["kcal"] if out["kcal"] else 0.0
    return out


def claims(nutrition: dict) -> list[dict]:
    """Which nutrition claims the given values support."""
    n = complete_nutrition(nutrition)
    return [
        {"id": cid, "label": label, "eligible": bool(test(n)), "threshold": threshold}
        for cid, label, test, threshold in CLAIMS
    ]


def lost_claims(before: dict, after: dict) -> list[dict]:
    """Claims eligible before a change that are no longer eligible after it."""
    after_ok = {c["id"]: c["eligible"] for c in claims(after)}
    return [c for c in claims(before) if c["eligible"] and not after_ok[c["id"]]]
