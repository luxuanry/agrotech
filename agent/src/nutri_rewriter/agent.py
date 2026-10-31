"""Agent loop: score -> rewrite -> re-score, until the Nutri-Score is A or B or out of rounds.

A recipe is a list of items {"name": str, "grams": float}. The LLM gives each
ingredient's composition per 100 g (with the original recipe, and alongside every
rewritten recipe); nutrition and the Nutri-Score are computed in nutriscore.py, never
by the LLM.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from . import nutriscore
from .llm import IngredientRewriter

_GRAMS_RE = re.compile(r"\s*(\d+(?:[.,]\d+)?)\s*g\.?\s*$", re.IGNORECASE)


def parse_items(text: str) -> list[dict]:
    """"Oats 120 g, salt 0,5 g" -> items. Commas inside parentheses or before a digit don't split."""
    items = []
    for part in re.split(r",(?!\d)(?![^()]*\))", text):
        part = part.strip()
        if not part:
            continue
        m = _GRAMS_RE.search(part)
        if not m:
            raise ValueError(f'No amount in grams for "{part}". Write it like "{part} 10 g".')
        items.append({"name": part[: m.start()].strip(), "grams": float(m.group(1).replace(",", "."))})
    return items


def clean_items(items: list[dict]) -> list[dict]:
    """Drop empty names, merge duplicates, require a positive weight for each ingredient."""
    out: dict[str, dict] = {}
    for i in items:
        name = str(i.get("name") or "").strip()
        if not name:
            continue
        try:
            grams = float(i.get("grams"))
        except (TypeError, ValueError):
            raise ValueError(f'No amount in grams for "{name}".') from None
        if grams <= 0:
            continue
        k = nutriscore.key(name)
        if k in out:
            out[k]["grams"] += grams
        else:
            out[k] = {"name": name, "grams": grams}
    return [{"name": i["name"], "grams": round(i["grams"], 2)} for i in out.values()]


def format_items(items: list[dict]) -> str:
    """"Oats 120 g, Salt 1 g"."""
    return ", ".join(f"{i['name']} {i['grams']:g} g" for i in items)


@dataclass
class Attempt:
    round: int
    ingredients: str  # formatted list with grams
    score: int  # Nutri-Score points, lower is better
    grade: str
    items: list[dict] = field(default_factory=list)
    nutrition: dict = field(default_factory=dict)
    breakdown: dict = field(default_factory=dict)
    changes: list[str] = field(default_factory=list)


@dataclass
class Result:
    success: bool
    category: str
    best: Attempt
    original: Attempt
    attempts: list[Attempt]


def fill_compositions(names: list[str], compositions: dict, rewriter: IngredientRewriter) -> None:
    """Ask the LLM for the compositions still missing from `compositions` (two tries)."""
    for _ in range(2):
        missing = list(dict.fromkeys(n for n in names if nutriscore.key(n) not in compositions))
        if not missing:
            return
        compositions.update(rewriter.estimate(missing))
    still = [n for n in names if nutriscore.key(n) not in compositions]
    if still:
        raise ValueError("No composition for: " + ", ".join(still))


def _attempt(rnd: int, items: list[dict], compositions: dict, category: str, changes: list[str]) -> Attempt:
    n, s = nutriscore.evaluate(items, compositions, category)
    shown = [{**i, "per_100g": compositions[nutriscore.key(i["name"])]} for i in items]
    return Attempt(rnd, format_items(items), s["score"], s["grade"], shown, n, s, changes)


def run(
    items: list[dict] | str,
    rewriter: IngredientRewriter,
    category: str = "beverage",
    max_rounds: int = 5,
    on_attempt: Callable[[Attempt], None] = lambda a: None,
    on_error: Callable[[int, Exception], None] = lambda rnd, e: print(f"  [round {rnd}] LLM error: {e}"),
) -> Result:
    if category not in nutriscore.CATEGORIES:
        raise ValueError(f"Unknown category {category!r}; use one of {nutriscore.CATEGORIES}.")
    items = clean_items(parse_items(items) if isinstance(items, str) else items)
    if not items:
        raise ValueError("The recipe is empty.")

    compositions: dict[str, dict] = {}
    fill_compositions([i["name"] for i in items], compositions, rewriter)

    original = _attempt(0, items, compositions, category, [])
    on_attempt(original)
    if nutriscore.is_target(original.grade):
        return Result(True, category, original, original, [])

    attempts: list[Attempt] = []
    best = original

    for rnd in range(1, max_rounds + 1):
        try:
            proposal = rewriter.rewrite(
                items, compositions, original.nutrition, original.breakdown, category, [vars(a) for a in attempts]
            )
            new_items = clean_items(proposal["items"])
            if not new_items:
                raise ValueError("The LLM returned an empty recipe.")
            # New ingredients take the composition the LLM returned with the recipe. Known ones keep
            # their first values, so a round can't improve its score by re-estimating a kept ingredient.
            for raw in proposal["items"]:
                k = nutriscore.key(raw["name"])
                if raw["per_100g"] and k not in compositions:
                    compositions[k] = raw["per_100g"]
            fill_compositions([i["name"] for i in new_items], compositions, rewriter)  # any it left out
        except Exception as e:  # bad JSON / API hiccup / missing amounts: skip this round
            on_error(rnd, e)
            continue

        attempt = _attempt(rnd, new_items, compositions, category, proposal["changes"])
        attempts.append(attempt)
        on_attempt(attempt)

        if attempt.score < best.score:
            best = attempt
        if nutriscore.is_target(attempt.grade):
            return Result(True, category, attempt, original, attempts)

    return Result(False, category, best, original, attempts)
