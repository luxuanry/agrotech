"""Groq LLM that proposes less-processed rewrites of an ingredient list."""

from __future__ import annotations

import json
import os

from groq import Groq

DEFAULT_MODEL = "openai/gpt-oss-120b"

SYSTEM_PROMPT = """You are a food formulation expert. You rewrite a product's ingredient list so it is \
no longer ultra-processed (NOVA group 4), while keeping it the same kind of product.

Rules:
- Replace industrial additives and ultra-processed ingredients (emulsifiers, flavourings, \
colourings, sweeteners, modified starches, hydrogenated/interesterified fats, syrups, isolates, \
preservatives, E-numbers, etc.) with whole-food or kitchen-style alternatives.
- Keep the product recognisable: keep core ingredients, don't just delete everything.
- Use the same language as the original list and a plain comma-separated format.
- Do not invent quantities or percentages that weren't there.

Respond with JSON only:
{"ingredients": "<new comma-separated list>", "changes": ["<old> -> <new>", ...]}"""


class IngredientRewriter:
    def __init__(self, model: str | None = None, temperature: float = 0.7):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self.temperature = temperature

    def rewrite(
        self,
        original: str,
        original_score: float,
        threshold: float,
        attempts: list[dict],
        hints: list[tuple[str, float]],
    ) -> dict:
        lines = [
            f"Original ingredient list (NOVA 4 probability {original_score:.3f}):",
            original,
            "",
            f"Goal: NOVA 4 probability below {threshold}.",
        ]
        if hints:
            lines += ["", "Ingredients pushing the classifier toward NOVA 4 the most (strongest first):"]
            lines += [f"- {name}" for name, _ in hints]
        if attempts:
            lines += ["", "Your previous attempts did not reach the goal:"]
            for a in attempts:
                lines.append(f"- Round {a['round']} (NOVA 4 = {a['score']:.3f}): {a['ingredients']}")
            lines.append("Try a different, more thorough approach than before.")

        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "\n".join(lines)},
            ],
        )
        data = json.loads(response.choices[0].message.content)
        return {
            "ingredients": str(data.get("ingredients", "")).strip(),
            "changes": list(data.get("changes", [])),
        }
