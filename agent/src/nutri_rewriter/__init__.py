"""CLI: nutri-rewriter "Water 860 g, Oats 120 g, Salt 1 g" [--category beverage|food] [--max-rounds 5]"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Rewrite a recipe until its Nutri-Score is A or B.")
    parser.add_argument("recipe", nargs="?", help='recipe as "name 120 g, name 1 g, ..." (reads stdin if omitted)')
    parser.add_argument("--category", choices=["beverage", "food"], default="beverage", help="Nutri-Score table (default beverage)")
    parser.add_argument("--max-rounds", type=int, default=5, help="max LLM rewrite rounds (default 5)")
    parser.add_argument("--model", default=None, help="Groq model id (default: $GROQ_MODEL or openai/gpt-oss-120b)")
    parser.add_argument("--score-only", action="store_true", help="only print the Nutri-Score of the recipe")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    args = parser.parse_args()

    recipe = (args.recipe or sys.stdin.read()).strip()
    if not recipe:
        parser.error("no recipe given")
    if not os.environ.get("GROQ_API_KEY"):
        sys.exit("GROQ_API_KEY is not set (put it in .env or the environment).")

    from . import agent
    from .llm import IngredientRewriter

    def show(a: agent.Attempt) -> None:
        if args.json:
            return
        tag = "original" if a.round == 0 else f"round {a.round}"
        n = a.nutrition
        print(f"\n[{tag}] Nutri-Score {a.grade} (score {a.score})")
        print(f"  {a.ingredients}")
        print(
            f"  per 100 g: {n['kcal']:.0f} kcal, sugars {n['sugars']:.1f} g, sat. fat {n['sat_fat']:.1f} g, "
            f"salt {n['salt']:.2f} g, fibre {n['fibre']:.1f} g, protein {n['protein']:.1f} g"
        )
        for i in a.items:
            c = i["per_100g"]
            print(
                f"    {i['name']:<24} {i['grams']:>8g} g   per 100 g: {c['kcal']:g} kcal, sugars {c['sugars']:g}, "
                f"sat. fat {c['sat_fat']:g}, salt {c['salt']:g}, fibre {c['fibre']:g}, protein {c['protein']:g}"
            )
        for c in a.changes:
            print(f"    · {c}")

    result = agent.run(
        recipe,
        IngredientRewriter(model=args.model),
        category=args.category,
        max_rounds=0 if args.score_only else args.max_rounds,
        on_attempt=show,
    )
    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        return
    if args.score_only:
        return

    status = "SUCCESS" if result.success else f"not reached after {args.max_rounds} rounds, best found"
    print(f"\n=== {status} ===")
    print(f"Nutri-Score: {result.original.grade} ({result.original.score}) -> {result.best.grade} ({result.best.score})")
    print(result.best.ingredients)
