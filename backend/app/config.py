"""Central configuration: file paths, retailer brands, traffic-light thresholds."""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

# Real data (built by scripts/build_from_off.py) is used when present;
# otherwise the API falls back to the synthetic sample and says so.
REAL_DATA_PATH = Path(os.getenv("LISTECOURTE_DATA", DATA_DIR / "products.parquet"))
SAMPLE_DATA_PATH = DATA_DIR / "sample_products.csv"
RULES_PATH = DATA_DIR / "rules.json"
INGREDIENTS_REF_PATH = DATA_DIR / "ingredients_ref.json"

# Hand-built list of French retailer brands and sub-brands, matched
# case-insensitively against the OFF `brands` field. Extend as needed.
RETAILER_BRANDS: list[str] = [
    "carrefour", "carrefour bio", "carrefour veggie", "simpl",
    "marque repère", "bio village", "eco+",
    "auchan", "auchan bio", "mmm!",
    "monoprix", "monoprix bio",
    "u", "bio u", "u bio",
    "casino", "casino bio",
    "vemondo", "lidl",
    "franprix", "intermarché", "netto",
]

# Traffic-light thresholds for market precedent (share of comparable
# products that work WITHOUT a given function).
GREEN_MIN_SHARE = 0.50
GREEN_MIN_COUNT = 5
RED_MAX_SHARE = 0.10
RED_MAX_COUNT = 2

# Minimum peer group size before we relax filters (organic first, then barista).
MIN_PEERS = 15

# Number of "clean twins" returned per option.
N_TWINS = 5
