"""Build data/products.parquet from the Open Food Facts CSV export.

1. Download the export (tab-separated, about 1 GB gzipped):
   https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz
2. Run:  python scripts/build_from_off.py path/to/en.openfoodfacts.org.products.csv.gz
   Add --inspect first to see which category tags French plant drinks use,
   and adjust CATEGORY_PATTERNS if needed.

Data: Open Food Facts, Open Database License (ODbL). Derived databases must
stay open; credit "Open Food Facts contributors".
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402
from app.data import normalise  # noqa: E402

# Matched with ILIKE against categories_tags. Check with --inspect.
CATEGORY_PATTERNS = [
    "%plant-based-milk%",
    "%plant-milk%",
    "%non-dairy-milk%",
    "%oat-based-drink%",
    "%soy-based-drink%",
    "%soy-milk%",
    "%almond-based-drink%",
    "%almond-milk%",
    "%rice-based-drink%",
    "%rice-milk%",
]

COLUMNS = [
    "code", "product_name", "brands", "categories_tags", "countries_tags", "labels_tags",
    "ingredients_text", "additives_tags", "ingredients_analysis_tags",
    "proteins_100g", "fat_100g", "sugars_100g", "carbohydrates_100g", "salt_100g",
    "calcium_100g", "\"energy-kcal_100g\"",
]


def source(path: str) -> str:
    return (
        f"read_csv('{path}', delim='\\t', header=true, quote='', all_varchar=true, "
        f"ignore_errors=true, max_line_size=10000000)"
    )


def inspect(con: duckdb.DuckDBPyConnection, path: str) -> None:
    """Print the most common category tags among French drinks named like plant milks."""
    rows = con.sql(f"""
        SELECT tag, count(*) AS n
        FROM (SELECT unnest(string_split(categories_tags, ',')) AS tag
              FROM {source(path)}
              WHERE countries_tags ILIKE '%en:france%'
                AND (product_name ILIKE '%boisson%' OR product_name ILIKE '%drink%')
                AND (product_name ILIKE '%avoine%' OR product_name ILIKE '%soja%'
                     OR product_name ILIKE '%amande%' OR product_name ILIKE '%riz%'))
        GROUP BY tag ORDER BY n DESC LIMIT 40
    """).fetchall()
    for tag, n in rows:
        print(f"{n:6d}  {tag}")


def build(con: duckdb.DuckDBPyConnection, path: str) -> None:
    cats = " OR ".join(f"categories_tags ILIKE '{p}'" for p in CATEGORY_PATTERNS)
    raw = con.sql(f"""
        SELECT {", ".join(COLUMNS)}
        FROM {source(path)}
        WHERE countries_tags ILIKE '%en:france%'
          AND ({cats})
          AND (ingredients_analysis_tags ILIKE '%en:vegan%' AND ingredients_analysis_tags NOT ILIKE '%en:non-vegan%'
               OR labels_tags ILIKE '%en:vegan%')
          AND coalesce(ingredients_text, '') <> ''
          AND proteins_100g IS NOT NULL AND fat_100g IS NOT NULL AND sugars_100g IS NOT NULL
    """).df()
    print(f"{len(raw)} raw rows after filters")
    df = normalise(raw)
    df = df.drop_duplicates(subset="code")
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con.register("products", df)
    con.sql(f"COPY products TO '{config.REAL_DATA_PATH.as_posix()}' (FORMAT parquet)")
    print(f"Wrote {len(df)} products to {config.REAL_DATA_PATH}")
    print(df["base"].value_counts().to_string())
    print(f"retailer brands: {int(df['retailer_brand'].sum())}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    con = duckdb.connect()
    if args.inspect:
        inspect(con, args.csv_path)
    else:
        build(con, args.csv_path)


if __name__ == "__main__":
    main()
