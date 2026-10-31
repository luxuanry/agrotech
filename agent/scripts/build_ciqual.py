"""Build src/nutri_rewriter/data/ciqual.json from Anses CALNUT 2020.

CALNUT is the Ciqual 2020 table with missing values filled in (Anses), so every food
has every nutrient. The official site (ciqual.anses.fr) is the source; this script
reads the copy kept in the Open Food Facts repository, or a local CALNUT.csv.0 file.

    uv run python scripts/build_ciqual.py [path/to/CALNUT.csv.0]

Source to cite: "Anses. 2020. Table de composition nutritionnelle Ciqual pour le calcul
des apports nutritionnels CALNUT. https://ciqual.anses.fr/"
"""

from __future__ import annotations

import collections
import csv
import io
import json
import sys
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/openfoodfacts/openfoodfacts-server/main/external-data/ciqual/calnut/CALNUT.csv.0"
OUT = Path(__file__).resolve().parents[1] / "src" / "nutri_rewriter" / "data" / "ciqual.json"

# Nutri-Score counts fruit, vegetables and legumes (not potatoes, nuts or juices).
FVL_SUBGROUPS = {"0201", "0203", "0204"}  # légumes, légumineuses, fruits
COLUMNS = {"kcal": "nrj_kcal", "sugars": "sucres_g", "sat_fat": "ags_g", "salt": "sel_g", "fibre": "fibres_g", "protein": "proteines_g"}


def num(s: str) -> float:
    s = (s or "").strip().replace(",", ".").lstrip("<").strip()
    return float(s) if s and s not in {"-", "traces"} else 0.0


def main() -> None:
    if len(sys.argv) > 1:
        text = Path(sys.argv[1]).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(URL, timeout=60) as r:
            text = r.read().decode("utf-8")

    rows = [r for r in csv.DictReader(io.StringIO(text)) if r["HYPOTH"] == "MB"]  # middle of lower/upper bound

    # A few rows carry the wrong subgroup name for their code (oat flakes under
    # "biscuits apéritifs"); use the most common name of each subgroup code.
    names = collections.defaultdict(collections.Counter)
    for r in rows:
        names[r["alim_ssgrp_code"]][r["alim_ssgrp_nom_fr"]] += 1
    group_name = {code: c.most_common(1)[0][0] for code, c in names.items()}

    foods = []
    for row in rows:
        label = row["FOOD_LABEL"].strip()
        low = label.lower()
        food = {"code": int(row["alim_code"]), "name": label, "group": group_name[row["alim_ssgrp_code"]]}
        food.update({k: round(num(row[c]), 3) for k, c in COLUMNS.items()})
        food["fvl"] = row["alim_ssgrp_code"] in FVL_SUBGROUPS
        food["sweetener"] = "édulcorant" in low and "sans édulcorant" not in low
        foods.append(food)

    foods.sort(key=lambda f: f["code"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "source": "Anses. 2020. Table de composition nutritionnelle Ciqual pour le calcul des apports nutritionnels CALNUT. https://ciqual.anses.fr/",
                "per": "100 g",
                "foods": foods,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"{len(foods)} foods -> {OUT}")


if __name__ == "__main__":
    main()
