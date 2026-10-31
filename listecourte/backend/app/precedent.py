"""M3 and the traffic light: market precedent for dropping a function.

For one product and one additive function, answers:
- how many comparable French products work without this function,
- which ones are closest in composition ("clean twins"),
- what those products do differently (substitution patterns),
- which lab trials matter if the function is removed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config, rules
from .additives import ADDITIVES, FUNCTIONS
from .data import Dataset

LAB_CHECKLIST = {
    "stabiliser": ["Sedimentation over shelf life (accelerated storage)", "Viscosity and mouthfeel against the current formula", "Phase separation after UHT"],
    "emulsifier": ["Creaming or oil separation over shelf life", "Droplet size after homogenisation"],
    "acidity_regulator": ["Protein heat stability at UHT", "pH drift over shelf life"],
    "calcium_salt": ["Calcium content by analysis, if a calcium claim stays on pack", "Insoluble salt sediment"],
}
BARISTA_CHECKLIST = {
    "stabiliser": ["Foam stability in steamed drinks"],
    "emulsifier": ["Foam height and stability"],
    "acidity_regulator": ["Feathering or curdling in hot, acidic coffee"],
    "calcium_salt": ["Feathering in coffee (calcium can destabilise protein)"],
}


def nearest_distance_threshold(ds: Dataset, peers: pd.DataFrame) -> float:
    """90th percentile of nearest-neighbour distances inside the peer group.

    A product further than this from its closest peer sits at the edge of the
    market distribution.
    """
    if len(peers) < 3:
        return float("inf")
    m = ds.matrix(peers)
    dist = np.sqrt(((m[:, None, :] - m[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(dist, np.inf)
    return float(np.percentile(dist.min(axis=1), 90))


def edge_check(ds: Dataset, product: dict, peers: pd.DataFrame) -> dict:
    """Is the product unusually far from every comparable product?"""
    if peers.empty:
        return {"is_edge": True, "nearest": None, "threshold": None}
    distances = np.linalg.norm(ds.matrix(peers) - ds.vector(product), axis=1)
    nearest = float(distances.min())
    threshold = nearest_distance_threshold(ds, peers)
    return {"is_edge": nearest > threshold, "nearest": round(nearest, 3), "threshold": round(threshold, 3)}


def _twins(ds: Dataset, product: dict, pool: pd.DataFrame) -> list[dict]:
    if pool.empty:
        return []
    distances = np.linalg.norm(ds.matrix(pool) - ds.vector(product), axis=1)
    order = np.argsort(distances)[: config.N_TWINS]
    twins = []
    for i in order:
        row = pool.iloc[int(i)]
        twins.append({
            "code": row["code"], "name": row["name"], "brands": row["brands"],
            "additives": [a for a in str(row["additives"]).split(",") if a],
            "protein": row["protein"], "fat": row["fat"], "sugars": row["sugars"], "base_pct": row["base_pct"],
            "base_pct_estimated": bool(row.get("base_pct_estimated", False)),
            "retailer_brand": bool(row["retailer_brand"]),
            "distance": round(float(distances[i]), 3),
        })
    return twins


def substitution_patterns(peers: pd.DataFrame, func: str) -> list[dict]:
    """What products without the function do differently from those with it."""
    without = peers[~peers[f"has_{func}"]]
    with_ = peers[peers[f"has_{func}"]]
    if len(without) < 3 or len(with_) < 3:
        return []
    patterns = []
    for col, label, unit in [("base_pct", "base ingredient", "%"), ("fat", "fat", " g"), ("protein", "protein", " g")]:
        a, b = float(without[col].median()), float(with_[col].median())
        if b and abs(a - b) / abs(b) >= 0.10:
            patterns.append({"kind": "median", "item": label, "without": round(a, 1), "with": round(b, 1), "unit": unit})
    oil = lambda f: f["ingredients_text"].str.lower().str.contains("huile|oil", regex=True).mean()
    shares = [("oil in the ingredient list", oil(without), oil(with_))]
    for other in FUNCTIONS:
        if other != func:
            shares.append((FUNCTIONS[other].lower(), without[f"has_{other}"].mean(), with_[f"has_{other}"].mean()))
    for label, a, b in shares:
        if abs(a - b) >= 0.15:
            patterns.append({"kind": "share", "item": label, "without": round(float(a), 2), "with": round(float(b), 2), "unit": ""})
    return patterns


def _light(n_without: int, share: float, edge: bool, claim_loss: bool) -> tuple[str, list[str]]:
    reasons = []
    if claim_loss:
        reasons.append("Removing it voids a nutrition claim the product currently supports.")
        return "red", reasons
    if n_without <= config.RED_MAX_COUNT or share < config.RED_MAX_SHARE:
        reasons.append("Almost no comparable product works without this function.")
        return "red", reasons
    if share >= config.GREEN_MIN_SHARE and n_without >= config.GREEN_MIN_COUNT and not edge:
        reasons.append("Most comparable products work without this function.")
        return "green", reasons
    if n_without < config.GREEN_MIN_COUNT:
        reasons.append("Only a few comparable products work without this function.")
    elif share < config.GREEN_MIN_SHARE:
        reasons.append("Fewer than half of comparable products work without this function.")
    if edge:
        reasons.append("This formula sits at the edge of the market distribution, so peers are a weaker guide.")
    return "yellow", reasons


def _calcium_after_removal(peers: pd.DataFrame) -> float:
    """Estimated calcium once the salt is removed: median of peers without it."""
    pool = peers[~peers["has_calcium_salt"]]["calcium_mg"].dropna()
    return float(pool.median()) if len(pool) else 0.0


def analyse_function(ds: Dataset, product: dict, func: str, peers: pd.DataFrame, filters: list[str], prediction: dict | None, model_metrics: dict | None) -> dict:
    """Full evidence bundle for "can this product drop function `func`?"."""
    product_additives = [a for a in product["additives"] if ADDITIVES.get(a, {}).get("function") == func]
    without = peers[~peers[f"has_{func}"]]
    n_peers, n_without = len(peers), len(without)
    share = n_without / n_peers if n_peers else 0.0
    edge = edge_check(ds, product, peers)

    claim_loss = []
    if func == "calcium_salt":
        after = {**product, "calcium_mg": _calcium_after_removal(peers)}
        claim_loss = rules.lost_claims(product, after)
    light, reasons = _light(n_without, share, edge["is_edge"], bool(claim_loss))

    checklist = list(LAB_CHECKLIST[func])
    if product.get("barista"):
        checklist += BARISTA_CHECKLIST[func]

    return {
        "function": func,
        "label": FUNCTIONS[func],
        "additives": [{"code": a, "name": ADDITIVES[a]["name"], **rules.additive_status(a, bool(product.get("organic")))} for a in product_additives],
        "light": light,
        "reasons": reasons,
        "precedent": {
            "n_peers": {"value": n_peers, "tag": "sourced" if not ds.is_sample else "sample"},
            "n_without": {"value": n_without, "tag": "sourced" if not ds.is_sample else "sample"},
            "share_without": {"value": round(share, 3), "tag": "sourced" if not ds.is_sample else "sample"},
            "filters": filters,
        },
        "model": None if prediction is None else {
            "probability": {"value": prediction["probability"], "tag": "model"},
            "drivers": prediction["drivers"],
            "beats_baseline": (model_metrics or {}).get("beats_baseline"),
        },
        "edge": edge,
        "claims_lost": [{**c, "tag": "estimated"} for c in claim_loss],
        "twins": _twins(ds, product, without),
        "substitutions": substitution_patterns(peers, func),
        "lab_checklist": checklist,
    }


LIGHT_ORDER = {"green": 0, "yellow": 1, "red": 2}


def rank_options(options: list[dict]) -> list[dict]:
    """Green first, then by market share without the function, then by
    lower model probability of needing it."""
    def key(o: dict):
        prob = o["model"]["probability"]["value"] if o["model"] else 0.5
        return (LIGHT_ORDER[o["light"]], -o["precedent"]["share_without"]["value"], prob)
    return sorted(options, key=key)
