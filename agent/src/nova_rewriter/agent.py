"""Agent loop: classify -> rewrite -> re-classify, until below threshold or out of rounds."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .classifier import NovaClassifier
from .llm import IngredientRewriter


@dataclass
class Attempt:
    round: int
    ingredients: str
    score: float
    group: int
    changes: list[str] = field(default_factory=list)


@dataclass
class Result:
    success: bool
    best: Attempt
    original: Attempt
    attempts: list[Attempt]


def run(
    ingredients: str,
    classifier: NovaClassifier,
    rewriter: IngredientRewriter,
    threshold: float = 0.5,
    max_rounds: int = 5,
    on_attempt: Callable[[Attempt], None] = lambda a: None,
) -> Result:
    s = classifier.score(ingredients)
    original = Attempt(0, ingredients, s.nova4, s.group)
    on_attempt(original)
    if original.score < threshold:
        return Result(True, original, original, [])

    hints = classifier.ingredient_impact(ingredients)
    attempts: list[Attempt] = []
    best = original

    for rnd in range(1, max_rounds + 1):
        try:
            proposal = rewriter.rewrite(
                ingredients,
                original.score,
                threshold,
                [vars(a) for a in attempts],
                hints,
            )
        except Exception as e:  # bad JSON / API hiccup: skip this round
            print(f"  [round {rnd}] LLM error: {e}")
            continue
        if not proposal["ingredients"]:
            continue

        s = classifier.score(proposal["ingredients"])
        attempt = Attempt(rnd, proposal["ingredients"], s.nova4, s.group, proposal["changes"])
        attempts.append(attempt)
        on_attempt(attempt)

        if attempt.score < best.score:
            best = attempt
        if attempt.score < threshold:
            return Result(True, attempt, original, attempts)
        hints = classifier.ingredient_impact(attempt.ingredients)

    return Result(False, best, original, attempts)
