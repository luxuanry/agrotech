"""Generate a synthetic product table for development and offline demos.

The products are invented. Codes start with "SAMPLE-" and brands are generic
("Retailer A", "National brand X") so nothing can be mistaken for a real
product. Replace with real data via scripts/build_from_off.py.

Usage: python scripts/make_sample_data.py [--n 400] [--seed 42]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.data import normalise  # noqa: E402

BASES = {
    # base: (weight, french word, base % range, protein, fat, sugars)
    "oat": (0.45, "avoine", (8, 16), 1.0, 1.5, 4.0),
    "soy": (0.25, "soja", (6, 9), 3.3, 1.8, 1.0),
    "almond": (0.15, "amande", (2, 7), 0.5, 1.2, 0.8),
    "rice": (0.10, "riz", (12, 17), 0.1, 1.0, 6.0),
    "coconut": (0.05, "coco", (4, 6), 0.2, 1.0, 2.0),
}
STABILISERS_ORGANIC = ["gomme gellane", "gomme de guar", "gomme xanthane", "farine de graines de caroube", "carraghénanes"]
STABILISERS_OTHER = STABILISERS_ORGANIC + ["carboxyméthylcellulose", "cellulose microcristalline"]
ACIDITY = ["phosphate dipotassique", "phosphate dipotassique", "citrate de potassium", "citrate de sodium"]
CALCIUM = ["carbonate de calcium", "phosphate tricalcique"]
RETAILERS = ["Retailer A", "Retailer A Bio", "Retailer B", "Retailer C", "Retailer C Bio", "Retailer D"]
NATIONAL = ["National brand X", "National brand Y", "National brand Z"]


def sigmoid(x: float) -> float:
    return 1 / (1 + np.exp(-x))


def make_product(i: int, rng: np.random.Generator) -> dict:
    names = list(BASES)
    base = rng.choice(names, p=[BASES[b][0] for b in names])
    _, fr, pct_range, protein, fat, sugars = BASES[base]
    barista = rng.random() < 0.15
    organic = rng.random() < 0.40
    retailer = rng.random() < 0.60
    pct = round(float(rng.uniform(*pct_range)), 0)

    # Function probabilities depend on the product matrix, which is what the
    # models are meant to recover.
    p_stab = sigmoid({"oat": -0.6, "soy": -1.0, "almond": 1.0, "rice": 0.2, "coconut": 0.8}[base] + 1.2 * barista - 0.4 * organic)
    p_emul = sigmoid(-1.4 + 1.8 * barista + 0.4 * (base == "almond"))
    p_acid = sigmoid(-2.0 + 3.0 * barista + 0.3 * (base == "soy") - 0.6 * organic)
    p_calc = sigmoid(-0.3 - 0.8 * organic + 0.5 * (base == "oat"))

    has_stab = rng.random() < p_stab
    has_emul = rng.random() < p_emul
    has_acid = rng.random() < p_acid
    has_calc = rng.random() < p_calc
    has_vit = rng.random() < (0.7 if has_calc else 0.1)
    has_oil = base in ("oat", "rice") or barista or rng.random() < 0.3
    has_sugar = base in ("soy", "almond") and rng.random() < 0.35

    parts = ["Eau", f"{fr} {pct:.0f}%" if rng.random() < 0.8 else fr]
    if has_sugar:
        parts.append("sucre de canne")
    if has_oil:
        parts.append(rng.choice(["huile de tournesol", "huile de colza"]))
    if has_calc:
        parts.append(rng.choice(CALCIUM))
    if has_acid:
        parts.append(f"correcteur d'acidité : {rng.choice(ACIDITY)}")
    parts.append("sel marin")
    if has_stab:
        pool = STABILISERS_ORGANIC if organic else STABILISERS_OTHER
        parts.append(f"stabilisant : {rng.choice(pool)}")
    if has_emul:
        parts.append(f"émulsifiant : {'lécithine de tournesol' if organic or rng.random() < 0.6 else 'mono- et diglycérides d’acides gras'}")
    if has_vit:
        parts.append("vitamines (D2, B12)")

    p = max(0.05, rng.normal(protein + 0.3 * barista, 0.25))
    f = max(0.3, rng.normal(fat + (0.9 if barista else 0) + (0.4 if has_oil else 0), 0.3))
    s = max(0.0, rng.normal(sugars + (2.5 if has_sugar else 0), 0.6))
    carbs = s + max(0.0, rng.normal(2.5 if base in ("oat", "rice") else 0.6, 0.4))
    brand = rng.choice(RETAILERS if retailer else NATIONAL)
    if organic and "Bio" not in brand and retailer:
        brand = f"{brand} Bio"
    style = "barista" if barista else rng.choice(["nature", "original", "sans sucres"])

    return {
        "code": f"SAMPLE-{i:04d}",
        "product_name": f"Boisson {fr} {style}{' bio' if organic else ''}",
        "brands": brand,
        "ingredients_text": ", ".join(parts),
        "additives_tags": "",
        "labels_tags": "en:vegan,en:organic" if organic else "en:vegan",
        "proteins_100g": round(p, 1),
        "fat_100g": round(f, 1),
        "sugars_100g": round(s, 1),
        "carbohydrates_100g": round(carbs, 1),
        "salt_100g": round(max(0.0, rng.normal(0.1, 0.03)), 2),
        "calcium_100g": 0.12 if has_calc else {"soy": 0.015}.get(base, 0.005),
        "energy-kcal_100g": None,
        "_retailer": retailer,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=400)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)
    raw = pd.DataFrame([make_product(i, rng) for i in range(1, args.n + 1)])
    df = normalise(raw.drop(columns=["_retailer"]))
    # Sample brands are generic, so set the retailer flag directly.
    df["retailer_brand"] = raw["_retailer"].to_numpy()[: len(df)]
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(config.SAMPLE_DATA_PATH, index=False)
    print(f"Wrote {len(df)} synthetic products to {config.SAMPLE_DATA_PATH}")


if __name__ == "__main__":
    main()
