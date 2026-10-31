"""Service layer tying data, rules, models and precedent together.

Recommend mode: current formula -> ranked simplification options.
Check mode: proposed formula with proportions -> health check.
Backtest: hide a clean product and see whether the tool supports what it does.
"""

from __future__ import annotations

import json
import random
from functools import lru_cache

import pandas as pd

from . import config, rules
from .additives import ADDITIVES, FUNCTIONS, functions_of
from .data import Dataset, normalise
from .explain import explain
from .models import FunctionModels
from .precedent import BARISTA_CHECKLIST, LAB_CHECKLIST, LIGHT_ORDER, analyse_function, edge_check, rank_options

# Which reference ingredient carries the base percentage.
BASE_INGREDIENT = {"oat": "oat_hydrolysed", "soy": "soybean", "almond": "almond", "rice": "rice_hydrolysed"}
SALT_INGREDIENTS = {"calcium_carbonate": "E170", "tricalcium_phosphate": "E341"}
NUTRIENTS = ["protein", "fat", "sugars", "carbs", "salt", "calcium_mg"]


@lru_cache(maxsize=1)
def ingredients_ref() -> dict:
    with open(config.INGREDIENTS_REF_PATH, encoding="utf-8") as fh:
        return json.load(fh)["ingredients"]


def _as_product(row: dict, ds: Dataset) -> dict:
    """Normalised row -> plain dict with an additives list and filled base %."""
    product = dict(row)
    adds = product.get("additives")
    product["additives"] = sorted(adds) if isinstance(adds, (list, set)) else [a for a in str(adds or "").split(",") if a]
    if product.get("base_pct") is None or pd.isna(product.get("base_pct")):
        same = ds.df[ds.df["base"] == product["base"]]["base_pct"]
        product["base_pct"] = float(same.median()) if len(same) else float(ds.df["base_pct"].median())
        product["base_pct_estimated"] = True
    for key in ("salt", "carbs", "calcium_mg", "kcal"):
        if product.get(key) is None or pd.isna(product.get(key)):
            product[key] = float(ds.df[key].median()) if key != "kcal" else None
    for key in ("barista", "organic", "vitamins"):
        product[key] = bool(product.get(key))
    return product


def product_from_input(payload: dict, ds: Dataset) -> dict:
    """Build a product from a barcode or from a typed ingredient list + nutrition."""
    if payload.get("code"):
        row = ds.lookup(payload["code"])
        if row is None:
            raise LookupError(f"No product with code {payload['code']} in the current dataset.")
        return _as_product(row, ds)
    raw = {
        "code": "INPUT",
        "product_name": payload.get("name") or ("barista" if payload.get("barista") else ""),
        "brands": "",
        "ingredients_text": payload.get("ingredients_text", ""),
        "additives_tags": "",
        "labels_tags": "en:organic" if payload.get("organic") else "",
        "proteins_100g": payload.get("protein"),
        "fat_100g": payload.get("fat"),
        "sugars_100g": payload.get("sugars"),
        "carbohydrates_100g": payload.get("carbs"),
        "salt_100g": payload.get("salt"),
        "calcium_100g": (payload["calcium_mg"] / 1000) if payload.get("calcium_mg") is not None else None,
    }
    norm = normalise(pd.DataFrame([raw]))
    if norm.empty:
        raise ValueError("Protein, fat and sugars per 100 ml are required.")
    row = norm.iloc[0].to_dict()
    row["barista"] = bool(payload.get("barista")) or row["barista"]
    row["organic"] = bool(payload.get("organic"))
    return _as_product(row, ds)


def _summary(product: dict, ds: Dataset) -> dict:
    return {
        "code": product.get("code"),
        "name": product.get("name"),
        "brands": product.get("brands"),
        "ingredients_text": product.get("ingredients_text"),
        "base": product["base"],
        "barista": product["barista"],
        "organic": product["organic"],
        "additives": [{"code": a, "name": ADDITIVES[a]["name"], "function": ADDITIVES[a]["function"]} for a in product["additives"] if a in ADDITIVES],
        "nutrition": {
            k: {"value": None if product.get(k) is None else round(float(product[k]), 2),
                "tag": "estimated" if (k == "base_pct" and product.get("base_pct_estimated")) else ("sample" if ds.is_sample else "sourced")}
            for k in NUTRIENTS + ["base_pct"]
        },
        "claims": rules.claims(product),
    }


def recommend(payload: dict, ds: Dataset, models: FunctionModels) -> dict:
    product = product_from_input(payload, ds)
    peers, filters = ds.peers(product["base"], product["barista"], product["organic"], exclude_code=product.get("code"))
    predictions = models.predict(product)
    options = []
    for func in sorted(functions_of(set(product["additives"]))):
        opt = analyse_function(ds, product, func, peers, filters, predictions.get(func), models.metrics.get(func))
        opt["explanation"] = explain(opt)
        options.append(opt)
    non_compliant = [a for o in options for a in o["additives"] if a["status"] == "fail"]
    return {
        "product": _summary(product, ds),
        "peers": {"n": len(peers), "filters": filters},
        "options": rank_options(options),
        "non_compliant": non_compliant,
        "data": {"is_sample": ds.is_sample, "source": ds.source},
    }


def nutrition_from_proportions(items: list[dict]) -> tuple[dict, list[str]]:
    """Weighted sum of reference compositions. Assumes density ~1, so per
    100 g of formula is read as per 100 ml (an assumption, flagged)."""
    ref = ingredients_ref()
    notes = []
    total = sum(float(i.get("pct") or 0) for i in items)
    if total > 100.5:
        raise ValueError(f"Proportions add up to {total:.1f} %, more than 100 %.")
    filled = list(items)
    if total < 99.5:
        filled.append({"id": "water", "pct": 100 - total})
        notes.append(f"Remaining {100 - total:.1f} % treated as water.")
    out = {k: 0.0 for k in NUTRIENTS}
    for item in filled:
        comp = ref.get(item["id"])
        if comp is None:
            raise ValueError(f"Unknown ingredient '{item['id']}'.")
        share = float(item.get("pct") or 0) / 100
        for k in NUTRIENTS:
            out[k] += share * float(comp[k])
    out["kcal"] = 4 * out["protein"] + 9 * out["fat"] + 4 * out["carbs"]
    notes.append("Nutrition estimated from placeholder compositions (replace with Ciqual) and a density of 1.")
    return {k: round(v, 3) for k, v in out.items()}, notes


def _percentile_flags(product: dict, peers: pd.DataFrame) -> list[dict]:
    flags = []
    for col, label in [("protein", "Protein"), ("fat", "Fat"), ("sugars", "Sugars"), ("base_pct", "Base ingredient %")]:
        series = peers[col].dropna()
        if len(series) < 5:
            continue
        pct = float((series < product[col]).mean() * 100)
        if pct < 5 or pct > 95:
            flags.append({"item": label, "value": round(float(product[col]), 2), "percentile": round(pct),
                          "peer_median": round(float(series.median()), 2)})
    return flags


def check(payload: dict, ds: Dataset, models: FunctionModels) -> dict:
    base = payload["base"]
    items = payload.get("ingredients", [])
    nutrition, notes = nutrition_from_proportions(items)
    base_item = next((i for i in items if i["id"] == BASE_INGREDIENT.get(base)), None)
    additives = {a for a in payload.get("additives", []) if a in ADDITIVES}
    # Calcium salts entered as ingredients count as the calcium-salt function.
    additives |= {SALT_INGREDIENTS[i["id"]] for i in items if i["id"] in SALT_INGREDIENTS and float(i.get("pct") or 0) > 0}
    additives = sorted(additives)
    product = {
        "code": None, "name": "Proposed formula", "brands": "", "ingredients_text": "",
        "base": base, "base_pct": float(base_item["pct"]) if base_item else None,
        **nutrition,
        "barista": bool(payload.get("barista")), "organic": bool(payload.get("organic")),
        "vitamins": bool(payload.get("vitamins")), "additives": additives,
    }
    product = _as_product(product, ds)
    peers, filters = ds.peers(base, product["barista"], product["organic"])
    predictions = models.predict(product)
    present = functions_of(set(additives))

    checks = []
    for a in additives:
        status = rules.additive_status(a, product["organic"])
        checks.append({"kind": "rule", "item": f"{a} {ADDITIVES[a]['name']}", **status,
                       "light": {"fail": "red", "unknown": "yellow", "pass": "green"}[status["status"]]})

    functions = []
    for func in FUNCTIONS:
        n_peers = len(peers)
        n_without = int((~peers[f"has_{func}"]).sum())
        share = n_without / n_peers if n_peers else 0.0
        pred = predictions.get(func)
        entry = {
            "function": func, "label": FUNCTIONS[func], "present": func in present,
            "share_without": {"value": round(share, 3), "tag": "sample" if ds.is_sample else "sourced"},
            "n_peers": n_peers, "n_without": n_without,
            "model_probability": None if pred is None else {"value": pred["probability"], "tag": "model"},
            "drivers": [] if pred is None else pred["drivers"],
        }
        if func in present:
            entry["light"], entry["note"] = "green", "Kept in this formula."
        elif share < config.RED_MAX_SHARE or n_without <= config.RED_MAX_COUNT:
            entry["light"], entry["note"] = "red", "Almost every comparable product uses this function. Expect a stability risk."
        elif share < config.GREEN_MIN_SHARE:
            entry["light"], entry["note"] = "yellow", "Most comparable products use this function. Precedent exists but is thin."
        else:
            entry["light"], entry["note"] = "green", "Most comparable products work without it."
        if not entry["present"]:
            entry["lab_checklist"] = LAB_CHECKLIST[func] + (BARISTA_CHECKLIST[func] if product["barista"] else [])
        functions.append(entry)

    edge = edge_check(ds, product, peers)
    outliers = _percentile_flags(product, peers)
    lights = [c["light"] for c in checks] + [f["light"] for f in functions]
    if edge["is_edge"] or outliers:
        lights.append("yellow")
    overall = max(lights, key=lambda l: LIGHT_ORDER[l]) if lights else "green"

    claim_list = [{**c, "tag": "estimated"} for c in rules.claims(product)]
    return {
        "overall": overall,
        "nutrition": {k: {"value": round(float(product[k]), 2), "tag": "estimated"} for k in NUTRIENTS + ["kcal"]},
        "claims": claim_list,
        "rule_checks": checks,
        "functions": functions,
        "edge": edge,
        "outliers": outliers,
        "peers": {"n": len(peers), "filters": filters},
        "notes": notes,
        "data": {"is_sample": ds.is_sample, "source": ds.source},
    }


def backtest(ds: Dataset, models: FunctionModels, per_function: int = 60, seed: int = 0) -> dict:
    """Leave-one-out check of the traffic light, per function.

    Clean group: products that already work without the function. Hide one,
    ask whether dropping the function has precedent. Green or yellow means
    the tool supports what the product actually does.
    Contrast group: products that use the function. If they get green just
    as often, the light is not discriminating and we report that.
    """
    rng = random.Random(seed)
    results = {}
    for func in FUNCTIONS:
        groups = {}
        for group, mask in (("clean", ~ds.df[f"has_{func}"]), ("contrast", ds.df[f"has_{func}"])):
            codes = list(ds.df.loc[mask, "code"])
            rng.shuffle(codes)
            counts = {"green": 0, "yellow": 0, "red": 0}
            for code in codes[:per_function]:
                product = _as_product(ds.lookup(code), ds)
                peers, filters = ds.peers(product["base"], product["barista"], product["organic"], exclude_code=code)
                counts[analyse_function(ds, product, func, peers, filters, None, None)["light"]] += 1
            n = sum(counts.values())
            groups[group] = {"n": n, **counts, "green_share": round(counts["green"] / n, 3) if n else None}
        clean, contrast = groups["clean"], groups["contrast"]
        results[func] = {
            "label": FUNCTIONS[func],
            "clean": clean,
            "contrast": contrast,
            "supported_share": round((clean["green"] + clean["yellow"]) / clean["n"], 3) if clean["n"] else None,
            "discriminates": None if not (clean["n"] and contrast["n"]) else clean["green_share"] > contrast["green_share"],
        }
    return results
