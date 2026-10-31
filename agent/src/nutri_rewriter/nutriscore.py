"""Nutri-Score (2023 update of the algorithm) computed from a recipe in grams.

Each ingredient has a composition per 100 g of ingredient (estimated by the LLM, see
llm.py). The product's nutrition per 100 g is the weight-averaged composition; a
density of 1 is assumed for drinks, so per 100 g = per 100 ml.

Two tables are implemented: general foods and beverages (plant-based drinks are scored
as beverages since the 2023 update). Cheese, red meat and fats/oils/nuts have their
own rules that are not implemented.
"""

from __future__ import annotations

import re

COMPOSITION_KEYS = ("kcal", "sugars", "sat_fat", "salt", "fibre", "protein")
CATEGORIES = ("beverage", "food")
TARGET_GRADES = ("A", "B")

# Upper bounds of each point band: points = number of thresholds the value exceeds.
_SAT_FAT = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
_SALT = [round(0.2 * i, 1) for i in range(1, 21)]
_FIBRE = [3.0, 4.1, 5.2, 6.3, 7.4]

_TABLES = {
    "food": {
        "energy": [335, 670, 1005, 1340, 1675, 2010, 2345, 2680, 3015, 3350],
        "sugars": [3.4, 6.8, 10, 14, 17, 20, 24, 27, 31, 34, 37, 41, 44, 48, 51],
        "protein": [2.4, 4.8, 7.2, 9.6, 12, 14, 17],
        "fvl": [(80, 5), (60, 2), (40, 1)],
    },
    "beverage": {
        "energy": [30, 90, 150, 210, 240, 270, 300, 330, 360, 390],
        "sugars": [0, 1.5, 3, 4.5, 6, 7.5, 9, 10.5, 12, 13.5],
        "protein": [1.2, 1.5, 1.8, 2.1, 2.4, 2.7, 3.0],
        "fvl": [(80, 6), (60, 4), (40, 2)],
    },
}

# Highest score for each grade.
_GRADES = {
    "food": [(0, "A"), (2, "B"), (10, "C"), (18, "D")],
    "beverage": [(2, "B"), (6, "C"), (9, "D")],  # A is reserved for water
}

_WATER_NAMES = {"water", "eau", "wasser", "agua", "acqua", "물", "drinking water", "eau de source", "eau minérale"}


# Non-nutritive sweeteners, so the beverage penalty applies even if the LLM forgets the flag.
_SWEETENER_RE = re.compile(
    r"stevi|steviol|rebaudios|sucralos|aspartam|acesulfam|saccharin|sacharin|cyclamat|neotam|advantam|thaumatin"
    r"|monk ?fruit|luo han|mogrosid|e ?9(5[0-9]|6[0-9])\b"
    r"|스테비|스테비올|수크랄로스|아스파탐|아세설팜|아세술팜|사카린|사이클라메이트|네오탐|나한과|몽크\s?프루트"
    r"|édulcorant|edulcorant|sweetener|감미료",
    re.IGNORECASE,
)


def is_sweetener(name: str) -> bool:
    return bool(_SWEETENER_RE.search(name))


def _points(value: float, thresholds: list[float]) -> int:
    return sum(1 for t in thresholds if value > t)


def is_target(grade: str) -> bool:
    return grade in TARGET_GRADES


def nutrition(items: list[dict], compositions: dict[str, dict]) -> dict:
    """Nutrition per 100 g of product. items: [{"name", "grams"}], compositions keyed by key(name)."""
    total = sum(i["grams"] for i in items)
    out = {k: 0.0 for k in COMPOSITION_KEYS}
    fvl_grams = 0.0
    sweetener = False
    for i in items:
        comp = compositions[key(i["name"])]
        share = i["grams"] / total if total else 0.0
        for k in COMPOSITION_KEYS:
            out[k] += share * comp[k]
        if comp["fvl"]:
            fvl_grams += i["grams"]
        sweetener = sweetener or comp["sweetener"] or is_sweetener(i["name"])
    out = {k: round(v, 3) for k, v in out.items()}
    out["kj"] = round(out["kcal"] * 4.184, 1)
    out["fvl_pct"] = round(100 * fvl_grams / total, 1) if total else 0.0
    out["sweetener"] = sweetener
    out["total_grams"] = round(total, 2)
    return out


def score(n: dict, category: str, water_only: bool = False) -> dict:
    """Nutri-Score points and grade from nutrition per 100 g."""
    t = _TABLES[category]
    pts = {
        "energy": _points(n["kj"], t["energy"]),
        "sugars": _points(n["sugars"], t["sugars"]),
        "sat_fat": _points(n["sat_fat"], _SAT_FAT),
        "salt": _points(n["salt"], _SALT),
    }
    if category == "beverage":
        pts["sweeteners"] = 4 if n["sweetener"] else 0
    negative = sum(pts.values())

    fvl = next((p for limit, p in t["fvl"] if n["fvl_pct"] > limit), 0)
    protein = _points(n["protein"], t["protein"])
    # Foods with 11+ negative points don't get protein points; beverages always do.
    protein_counted = category == "beverage" or negative < 11
    pts.update(protein=protein if protein_counted else 0, fibre=_points(n["fibre"], _FIBRE), fvl=fvl)
    positive = pts["protein"] + pts["fibre"] + pts["fvl"]

    total = negative - positive
    if category == "beverage" and water_only:
        grade = "A"
    else:
        grade = next((g for limit, g in _GRADES[category] if total <= limit), "E")
    return {
        "score": total,
        "grade": grade,
        "negative": negative,
        "positive": positive,
        "points": pts,
        "protein_counted": protein_counted,
    }


def evaluate(items: list[dict], compositions: dict[str, dict], category: str) -> tuple[dict, dict]:
    n = nutrition(items, compositions)
    water_only = all(key(i["name"]) in _WATER_NAMES for i in items)
    return n, score(n, category, water_only)


def sources(items: list[dict], compositions: dict[str, dict], nutrient: str, top: int = 3) -> list[tuple[str, float]]:
    """Ingredients contributing most of a nutrient, as g (or kcal) per 100 g of product."""
    total = sum(i["grams"] for i in items) or 1.0
    contrib = [(i["name"], i["grams"] / total * compositions[key(i["name"])][nutrient]) for i in items]
    contrib = [(name, round(v, 2)) for name, v in sorted(contrib, key=lambda x: x[1], reverse=True) if v > 0.005]
    return contrib[:top]


def key(name: str) -> str:
    return " ".join(name.lower().split()).rstrip(".")


def clean_composition(raw: dict) -> dict:
    """Coerce an LLM-supplied composition into numbers within physical limits."""
    out = {}
    for k in COMPOSITION_KEYS:
        try:
            v = float(raw.get(k) or 0)
        except (TypeError, ValueError):
            v = 0.0
        out[k] = min(max(v, 0.0), 900.0 if k == "kcal" else 100.0)
    out["fvl"] = bool(raw.get("fvl"))
    out["sweetener"] = bool(raw.get("sweetener"))
    return out
