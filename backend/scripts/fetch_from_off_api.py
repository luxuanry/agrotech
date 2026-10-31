"""Build data/products.parquet from the Open Food Facts search API.

Much lighter than the full CSV export: it only fetches French plant drinks.
Run from the backend folder, with the virtual environment active:

    python scripts/fetch_from_off_api.py            # fetch and build
    python scripts/fetch_from_off_api.py --dry-run  # only show counts per category
    python scripts/fetch_from_off_api.py --from-cache  # build from pages already fetched

Pages are fetched by popularity, so a partial cache holds the most-scanned
products first.

The search API allows about 10 requests per minute, so the script waits
between pages. Expect a few minutes for a full run.

Data: Open Food Facts, Open Database License (ODbL). Credit
"Open Food Facts contributors" and keep any derived database open.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.data import normalise  # noqa: E402

API = "https://world.openfoodfacts.org/api/v2/search"
USER_AGENT = "ListeCourte/0.1 (Hack the Fork Paris 2026 prototype)"
PAGE_SIZE = 100
PAUSE_SECONDS = 15  # stays under the search rate limit
CACHE_DIR = config.DATA_DIR / "off_cache"

# "en:plant-milks" is an alias of this tag and the oat/soy/almond/rice tags are
# subsets of it, so one tag covers the segment (2,492 French products on
# 2026-10-31). Add tags here only if --dry-run shows they bring new products.
CATEGORIES = [
    "en:plant-based-milk-alternatives",
]

FIELDS = [
    "code", "product_name", "product_name_fr", "brands", "categories_tags", "countries_tags",
    "labels_tags", "ingredients_text", "ingredients_text_fr", "additives_tags",
    "ingredients_analysis_tags", "nutriments",
]
NUTRIMENTS = [
    "proteins_100g", "fat_100g", "sugars_100g", "carbohydrates_100g",
    "salt_100g", "calcium_100g", "energy-kcal_100g",
]


def _v2_url(category: str, page: int) -> str:
    params = {
        "categories_tags": category, "countries_tags": "en:france",
        "fields": ",".join(FIELDS), "page_size": PAGE_SIZE, "page": page,
    }
    return f"{API}?{urllib.parse.urlencode(params)}"


def _legacy_url(category: str, page: int) -> str:
    params = {
        "action": "process", "json": 1,
        "tagtype_0": "categories", "tag_contains_0": "contains", "tag_0": category,
        "tagtype_1": "countries", "tag_contains_1": "contains", "tag_1": "en:france",
        "fields": ",".join(FIELDS), "page_size": PAGE_SIZE, "page": page,
    }
    return f"https://world.openfoodfacts.org/cgi/search.pl?{urllib.parse.urlencode(params)}"


def _searchalicious_url(category: str, page: int) -> str:
    params = {
        "q": f'categories_tags:"{category}" AND countries_tags:"en:france"',
        "fields": ",".join(FIELDS), "page_size": PAGE_SIZE, "page": page,
    }
    return f"https://search.openfoodfacts.org/search?{urllib.parse.urlencode(params)}"


# Tried in order; the first that answers is used for the rest of the run.
# search-a-licious (_searchalicious_url) is kept for reference but not used:
# its results have no ingredient list or additives, which the analysis needs,
# and its ordering differs, so mixing it with the others skips products.
BACKENDS = [("search API v2", _v2_url), ("legacy search", _legacy_url)]
_working_backend: list = []


def _fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def _standardise(data: dict) -> dict:
    """Give every backend the same shape: {"count": int, "products": [...]}."""
    if "hits" in data:  # search-a-licious
        return {"count": int(data.get("count") or 0), "products": data.get("hits") or []}
    return {"count": int(data.get("count") or 0), "products": data.get("products") or []}


def _cache_path(category: str, page: int) -> Path:
    return CACHE_DIR / f"{category.replace(':', '_')}_p{page}.json"


def get_page(category: str, page: int) -> dict:
    """One page of results. Pages already fetched are read from the cache, so
    a run interrupted by server errors resumes where it stopped."""
    cached = _cache_path(category, page)
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    # The endpoint that worked last is tried first, the others after it.
    order = _working_backend + [b for b in BACKENDS if b not in _working_backend]
    for attempt in range(6):
        for name, make_url in order:
            try:
                data = _standardise(_fetch_json(make_url(category, page)))
            except Exception as exc:  # unavailable or rate limited: try the next one
                print(f"  {name} failed ({exc})")
                continue
            if _working_backend != [(name, make_url)]:
                print(f"  using {name}")
                _working_backend[:] = [(name, make_url)]
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(data), encoding="utf-8")
            return data
        wait = 30 * (attempt + 1)  # 503 here usually means "slow down"
        print(f"  all endpoints failed, retrying in {wait}s")
        time.sleep(wait)
    raise RuntimeError(
        f"Open Food Facts did not answer for {category} page {page}. "
        "Run the script again later: pages already fetched are kept."
    )


def fetch_category(category: str, dry_run: bool) -> list[dict]:
    first = get_page(category, 1)
    total = int(first.get("count", 0))
    print(f"{category}: {total} products")
    if dry_run or total == 0:
        return []
    products = list(first.get("products", []))
    pages = (total + PAGE_SIZE - 1) // PAGE_SIZE
    for page in range(2, pages + 1):
        if not _cache_path(category, page).exists():
            time.sleep(PAUSE_SECONDS)
        print(f"  page {page}/{pages}")
        products += get_page(category, page).get("products", [])
    return products


def as_text(value) -> str:
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return value or ""


def flatten(p: dict) -> dict:
    """API product -> row with the same column names as the CSV export."""
    nutr = p.get("nutriments") or {}
    row = {
        "code": p.get("code"),
        "product_name": p.get("product_name_fr") or p.get("product_name") or "",
        "brands": as_text(p.get("brands")),
        "categories_tags": as_text(p.get("categories_tags")),
        "countries_tags": as_text(p.get("countries_tags")),
        "labels_tags": as_text(p.get("labels_tags")),
        "ingredients_text": p.get("ingredients_text_fr") or p.get("ingredients_text") or "",
        "additives_tags": as_text(p.get("additives_tags")),
        "ingredients_analysis_tags": as_text(p.get("ingredients_analysis_tags")),
    }
    for key in NUTRIMENTS:
        row[key] = nutr.get(key)
    return row


def is_vegan(row: dict) -> bool:
    analysis = row["ingredients_analysis_tags"].lower()
    labels = row["labels_tags"].lower()
    return ("en:vegan" in analysis and "en:non-vegan" not in analysis) or "en:vegan" in labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="only print product counts per category")
    parser.add_argument("--from-cache", action="store_true",
                        help="build from the pages already fetched, without calling the API")
    args = parser.parse_args()

    raw: list[dict] = []
    if args.from_cache:
        for path in sorted(CACHE_DIR.glob("*.json")):
            raw += json.loads(path.read_text(encoding="utf-8")).get("products", [])
        print(f"{len(raw)} products read from {CACHE_DIR}")
    else:
        for category in CATEGORIES:
            raw += fetch_category(category, args.dry_run)
    if args.dry_run:
        return

    rows = {}
    for p in raw:
        row = flatten(p)
        if row["code"]:
            rows[row["code"]] = row  # de-duplicate across categories
    df = pd.DataFrame(list(rows.values()))
    print(f"\n{len(df)} unique products fetched")
    if df.empty:
        print("Nothing to build. Check the category tags with --dry-run.")
        return

    keep = df[df.apply(is_vegan, axis=1) & (df["ingredients_text"].str.strip() != "")]
    print(f"{len(keep)} with an ingredient list and vegan status")
    out = normalise(keep)
    print(f"{len(out)} with protein, fat and sugars (kept)")

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(config.REAL_DATA_PATH, index=False)
    print(f"\nWrote {config.REAL_DATA_PATH}")
    print(out["base"].value_counts().to_string())
    print(f"retailer brands: {int(out['retailer_brand'].sum())}")
    for col in [c for c in out.columns if c.startswith("has_")]:
        print(f"{col}: {int(out[col].sum())}")


if __name__ == "__main__":
    main()
