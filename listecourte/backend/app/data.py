"""Data layer: normalise raw product rows and load them into one table.

Both the real Open Food Facts build and the synthetic sample go through
`normalise()`, so feature engineering is identical in both cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb
import numpy as np
import pandas as pd

from . import config
from .additives import FUNCTIONS, base_percentage, detect_base, functions_of, has_vitamins, parse_additives

# Columns used for composition similarity ("clean twins").
SIMILARITY_COLS = ["protein", "fat", "sugars", "salt", "base_pct"]

# Columns of the normalised table, in order.
NORMALISED_COLS = [
    "code", "name", "brands", "ingredients_text", "additives", "base", "base_pct",
    "protein", "fat", "sugars", "carbs", "salt", "calcium_mg", "kcal",
    "barista", "organic", "vitamins", "retailer_brand",
] + [f"has_{f}" for f in FUNCTIONS]


def _num(value) -> float | None:
    """Convert to float, returning None for blanks and non-numbers."""
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(out) else out


def _is_retailer_brand(brands: str | None) -> bool:
    parts = [b.strip().lower() for b in (brands or "").split(",")]
    return any(p in config.RETAILER_BRANDS for p in parts)


def normalise(raw: pd.DataFrame) -> pd.DataFrame:
    """Turn raw OFF-style rows into the normalised product table.

    Expected raw columns (OFF CSV export names): code, product_name, brands,
    ingredients_text, additives_tags, labels_tags, proteins_100g, fat_100g,
    sugars_100g, carbohydrates_100g, salt_100g, calcium_100g (grams),
    energy-kcal_100g. Missing optional columns are tolerated.
    """
    rows = []
    for rec in raw.to_dict("records"):
        text = rec.get("ingredients_text") or ""
        name = rec.get("product_name") or ""
        additives = parse_additives(text, rec.get("additives_tags"))
        funcs = functions_of(additives)
        base = detect_base(text, name)
        calcium_g = _num(rec.get("calcium_100g"))
        protein = _num(rec.get("proteins_100g"))
        fat = _num(rec.get("fat_100g"))
        carbs = _num(rec.get("carbohydrates_100g"))
        kcal = _num(rec.get("energy-kcal_100g"))
        if kcal is None and None not in (protein, fat, carbs):
            kcal = 4 * protein + 9 * fat + 4 * carbs
        labels = (rec.get("labels_tags") or "").lower()
        row = {
            "code": str(rec.get("code")),
            "name": name,
            "brands": rec.get("brands") or "",
            "ingredients_text": text,
            "additives": ",".join(sorted(additives)),
            "base": base,
            "base_pct": base_percentage(text, base),
            "protein": protein,
            "fat": fat,
            "sugars": _num(rec.get("sugars_100g")),
            "carbs": carbs,
            "salt": _num(rec.get("salt_100g")),
            "calcium_mg": calcium_g * 1000 if calcium_g is not None else None,
            "kcal": kcal,
            "barista": "barista" in name.lower(),
            "organic": "en:organic" in labels or "en:eu-organic" in labels,
            "vitamins": has_vitamins(text),
            "retailer_brand": _is_retailer_brand(rec.get("brands")),
        }
        for f in FUNCTIONS:
            row[f"has_{f}"] = f in funcs
        rows.append(row)
    df = pd.DataFrame(rows, columns=NORMALISED_COLS)
    # Products without the core nutrition values cannot be compared.
    return df.dropna(subset=["protein", "fat", "sugars"]).reset_index(drop=True)


@dataclass
class Dataset:
    """In-memory product table plus helpers for peers and similarity."""

    df: pd.DataFrame
    is_sample: bool
    source: str
    _scale: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Fill missing base percentages with the median of the same base,
        # so similarity still works; the fill is an estimate, not a fact.
        self.df["base_pct_estimated"] = self.df["base_pct"].isna()
        medians = self.df.groupby("base")["base_pct"].transform("median")
        self.df["base_pct"] = self.df["base_pct"].fillna(medians).fillna(self.df["base_pct"].median())
        self.df["salt"] = self.df["salt"].fillna(self.df["salt"].median())
        for col in SIMILARITY_COLS:
            std = float(self.df[col].std()) or 1.0
            self._scale[col] = std

    def vector(self, row: dict | pd.Series) -> np.ndarray:
        """Standardised composition vector for one product."""
        return np.array([float(row[c] or 0.0) / self._scale[c] for c in SIMILARITY_COLS])

    def matrix(self, frame: pd.DataFrame) -> np.ndarray:
        return np.column_stack([frame[c].astype(float).to_numpy() / self._scale[c] for c in SIMILARITY_COLS])

    def peers(self, base: str, barista: bool, organic: bool, exclude_code: str | None = None) -> tuple[pd.DataFrame, list[str]]:
        """Comparable products, with the filters actually applied.

        Starts strict (same base, barista flag, organic flag) and relaxes
        organic, then barista, until at least MIN_PEERS products remain.
        """
        df = self.df if exclude_code is None else self.df[self.df["code"] != exclude_code]
        attempts = [
            (["base", "barista", "organic"], (df["base"] == base) & (df["barista"] == barista) & (df["organic"] == organic)),
            (["base", "barista"], (df["base"] == base) & (df["barista"] == barista)),
            (["base"], df["base"] == base),
        ]
        for filters, mask in attempts:
            subset = df[mask]
            if len(subset) >= config.MIN_PEERS:
                return subset, filters
        return df[attempts[-1][1]], ["base"]

    def lookup(self, code: str) -> dict | None:
        hit = self.df[self.df["code"] == code]
        return None if hit.empty else hit.iloc[0].to_dict()

    def search(self, query: str, limit: int = 8) -> list[dict]:
        q = query.strip().lower()
        if not q:
            return []
        mask = (
            self.df["code"].str.lower().str.startswith(q)
            | self.df["name"].str.lower().str.contains(q, regex=False)
            | self.df["brands"].str.lower().str.contains(q, regex=False)
        )
        cols = ["code", "name", "brands", "base", "barista", "organic", "retailer_brand"]
        return self.df.loc[mask, cols].head(limit).to_dict("records")


def load_dataset() -> Dataset:
    """Load real data if built, else the synthetic sample (flagged as such)."""
    if config.REAL_DATA_PATH.exists():
        df = duckdb.sql(f"SELECT * FROM read_parquet('{config.REAL_DATA_PATH.as_posix()}')").df()
        return Dataset(df=df, is_sample=False, source=f"Open Food Facts ({config.REAL_DATA_PATH.name})")
    df = duckdb.sql(f"SELECT * FROM read_csv_auto('{config.SAMPLE_DATA_PATH.as_posix()}', all_varchar=false)").df()
    df["code"] = df["code"].astype(str)
    for col in ["additives", "brands", "ingredients_text", "name"]:
        df[col] = df[col].fillna("").astype(str)
    return Dataset(df=df, is_sample=True, source="Synthetic sample (not real products)")
