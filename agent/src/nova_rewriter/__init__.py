"""CLI: nova-rewriter "ingredient list" [--threshold 0.5] [--max-rounds 5]"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Rewrite an ingredient list until it is no longer NOVA 4.")
    parser.add_argument("ingredients", nargs="?", help="ingredient list (reads stdin if omitted)")
    parser.add_argument("--threshold", type=float, default=0.5, help="target NOVA 4 probability (default 0.5)")
    parser.add_argument("--max-rounds", type=int, default=5, help="max LLM rewrite rounds (default 5)")
    parser.add_argument("--model", default=None, help="Groq model id (default: $GROQ_MODEL or openai/gpt-oss-120b)")
    parser.add_argument("--score-only", action="store_true", help="only print NOVA probabilities")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args()

    ingredients = (args.ingredients or sys.stdin.read()).strip()
    if not ingredients:
        parser.error("no ingredient list given")

    from .classifier import NovaClassifier

    classifier = NovaClassifier()

    if args.score_only:
        s = classifier.score(ingredients)
        for label, p in zip(classifier.labels, s.probs):
            print(f"{p:.3f}  {label}")
        return

    if not os.environ.get("GROQ_API_KEY"):
        sys.exit("GROQ_API_KEY is not set (put it in .env or the environment).")

    from . import agent
    from .llm import IngredientRewriter

    def show(a: agent.Attempt) -> None:
        if args.json:
            return
        tag = "original" if a.round == 0 else f"round {a.round}"
        print(f"\n[{tag}] NOVA 4 = {a.score:.3f}  (predicted NOVA {a.group})")
        print(f"  {a.ingredients}")
        for c in a.changes:
            print(f"    · {c}")

    result = agent.run(
        ingredients,
        classifier,
        IngredientRewriter(model=args.model),
        threshold=args.threshold,
        max_rounds=args.max_rounds,
        on_attempt=show,
    )

    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return

    status = "SUCCESS" if result.success else f"not reached after {args.max_rounds} rounds, best found"
    print(f"\n=== {status} ===")
    print(f"NOVA 4: {result.original.score:.3f} -> {result.best.score:.3f}")
    print(result.best.ingredients)
