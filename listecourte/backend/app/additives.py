"""Additive taxonomy and ingredient-text parsing.

Maps E-numbers (and their common French/English names) to the technological
function they serve in a plant drink. The function, not the E-number, is the
unit of analysis: "can we drop the stabiliser?" rather than "can we drop E418?".
"""

from __future__ import annotations

import re

# Technological functions we reason about in plant drinks.
FUNCTIONS: dict[str, str] = {
    "stabiliser": "Stabiliser / thickener",
    "emulsifier": "Emulsifier",
    "acidity_regulator": "Acidity regulator",
    "calcium_salt": "Calcium fortification salt",
}

# E-number -> (function, display name, name aliases found in ingredient text).
ADDITIVES: dict[str, dict] = {
    "E407": {"function": "stabiliser", "name": "Carrageenan", "aliases": ["carraghénanes", "carraghénane", "carrageenan"]},
    "E410": {"function": "stabiliser", "name": "Locust bean gum", "aliases": ["farine de graines de caroube", "gomme de caroube", "locust bean gum"]},
    "E412": {"function": "stabiliser", "name": "Guar gum", "aliases": ["gomme de guar", "gomme guar", "guar gum"]},
    "E415": {"function": "stabiliser", "name": "Xanthan gum", "aliases": ["gomme xanthane", "xanthane", "xanthan gum"]},
    "E418": {"function": "stabiliser", "name": "Gellan gum", "aliases": ["gomme gellane", "gellane", "gellan gum"]},
    "E460": {"function": "stabiliser", "name": "Cellulose", "aliases": ["cellulose microcristalline"]},
    "E466": {"function": "stabiliser", "name": "Carboxymethylcellulose", "aliases": ["carboxyméthylcellulose", "carboxymethylcellulose"]},
    "E322": {"function": "emulsifier", "name": "Lecithins", "aliases": ["lécithine de tournesol", "lécithine de soja", "lécithines", "lécithine", "lecithin"]},
    "E471": {"function": "emulsifier", "name": "Mono- and diglycerides of fatty acids", "aliases": ["mono- et diglycérides", "mono et diglycérides", "mono- and diglycerides"]},
    "E331": {"function": "acidity_regulator", "name": "Sodium citrates", "aliases": ["citrate de sodium", "citrates de sodium"]},
    "E332": {"function": "acidity_regulator", "name": "Potassium citrates", "aliases": ["citrate de potassium", "citrates de potassium"]},
    "E339": {"function": "acidity_regulator", "name": "Sodium phosphates", "aliases": ["phosphate de sodium", "phosphates de sodium"]},
    "E340": {"function": "acidity_regulator", "name": "Potassium phosphates", "aliases": ["phosphate dipotassique", "phosphate de potassium", "phosphates de potassium", "dipotassium phosphate"]},
    "E170": {"function": "calcium_salt", "name": "Calcium carbonate", "aliases": ["carbonate de calcium", "calcium carbonate"]},
    "E341": {"function": "calcium_salt", "name": "Calcium phosphates", "aliases": ["phosphate tricalcique", "phosphate de calcium", "phosphates de calcium", "tricalcium phosphate"]},
}

# Matches "E418", "e 418", "E340ii", "E-471" and similar.
_ENUM_RE = re.compile(r"\bE\s?-?(\d{3,4})[a-z]*\b", re.IGNORECASE)

# Base ingredient keywords, checked in order (first match wins).
BASES: list[tuple[str, list[str]]] = [
    ("oat", ["avoine", "oat"]),
    ("soy", ["soja", "soy"]),
    ("almond", ["amande", "almond"]),
    ("rice", ["riz", "rice"]),
    ("coconut", ["coco", "coconut"]),
]

# Percentage right after a base keyword, e.g. "avoine 10%" or "avoine (12 %)".
_PCT_AFTER = r"[^,;%]{0,40}?(\d{1,2}(?:[.,]\d)?)\s?%"


def parse_additives(text: str | None, tags: str | None = None) -> set[str]:
    """Return the set of known E-numbers declared in ingredient text and/or OFF tags.

    `tags` may be an Open Food Facts `additives_tags` string such as
    "en:e418,en:e340ii". Unknown E-numbers are ignored.
    """
    found: set[str] = set()
    blob = f"{text or ''} {tags or ''}"
    for match in _ENUM_RE.finditer(blob.replace("en:e", " E")):
        code = f"E{match.group(1)}"
        if code in ADDITIVES:
            found.add(code)
    lowered = (text or "").lower()
    for code, info in ADDITIVES.items():
        if any(alias in lowered for alias in info["aliases"]):
            found.add(code)
    return found


def functions_of(additives: set[str]) -> set[str]:
    """Return the set of functions covered by a set of E-numbers."""
    return {ADDITIVES[a]["function"] for a in additives if a in ADDITIVES}


def detect_base(text: str | None, name: str | None = None) -> str:
    """Guess the plant base from the product name first, then ingredients."""
    for source in (name or "", text or ""):
        lowered = source.lower()
        for base, keywords in BASES:
            if any(k in lowered for k in keywords):
                return base
    return "other"


def base_percentage(text: str | None, base: str) -> float | None:
    """Extract the declared percentage of the base ingredient, if present."""
    if not text or base == "other":
        return None
    keywords = dict(BASES)[base]
    lowered = text.lower()
    for k in keywords:
        match = re.search(re.escape(k) + _PCT_AFTER, lowered)
        if match:
            return float(match.group(1).replace(",", "."))
    return None


def has_vitamins(text: str | None) -> bool:
    """True when the ingredient list declares added vitamins.

    Kept separate from calcium salts so the calcium-salt model does not see
    its own target through a "fortified" feature.
    """
    lowered = (text or "").lower()
    return "vitamine" in lowered or "vitamin" in lowered
