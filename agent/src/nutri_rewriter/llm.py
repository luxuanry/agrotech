"""Groq LLM: estimates ingredient compositions and proposes recipes with a better Nutri-Score."""

from __future__ import annotations

import json
import os

from groq import Groq

from . import nutriscore

DEFAULT_MODEL = "openai/gpt-oss-120b"

_COMPOSITION_FIELDS = """"kcal": <energy>, "sugars": <g>, "sat_fat": <g saturated fat>, "salt": <g>, \
"fibre": <g>, "protein": <g>, "fvl": <true if it is a fruit, vegetable or legume (pulse)>, \
"sweetener": <true if it is a non-nutritive sweetener such as sucralose or steviol glycosides>"""

_COMPOSITION_RULES = """Composition values are per 100 g of the ingredient itself (not of the product), \
for the ingredient as a manufacturer buys it (raw, unprepared), as in standard food composition \
tables (Ciqual, USDA). "sugars" means total sugars (mono- and disaccharides), not total \
carbohydrates. "salt" is sodium chloride equivalent (sodium x 2.5). Water has no energy or \
nutrients. Hydrocolloids and gums (gellan, xanthan, guar, carrageenan) are mostly fibre with almost \
no protein or sugar; mineral salts and vitamin premixes have no energy. Set "sweetener" to true for \
any non-nutritive sweetener, including stevia extracts."""

ESTIMATE_PROMPT = f"""You are a food composition database. For each ingredient give its typical \
composition. {_COMPOSITION_RULES}

Respond with JSON only, one entry per ingredient, names copied exactly as given:
{{"ingredients": [{{"name": "<name>", {_COMPOSITION_FIELDS}}}, ...]}}"""

REWRITE_PROMPT = f"""You are a food formulation expert. You change a recipe so that its Nutri-Score \
(2023 algorithm) reaches A or B, while keeping it the same kind of product.

Rules:
- Work on what costs points (energy, sugars, saturated fat, salt, and sweeteners for drinks) and on \
what earns points (protein, fibre, share of fruit, vegetables and legumes).
- Keep the product recognisable: an oat drink stays an oat drink, a biscuit stays a biscuit. The core \
ingredient (the largest one that is not water) keeps at least two thirds of its original amount, and \
added ingredients must not take over what the product is. Do not reach the target only by adding water.
- Non-nutritive sweeteners (stevia, sucralose, ...) cost points in drinks; don't use them to replace sugar.
- Prefer whole-food or kitchen-style ingredients to additives.
- Amounts are in grams. Keep the amount of an ingredient you don't change. For every new or \
replacing ingredient, choose a realistic amount for this recipe. Keep the total weight close to the \
original total.
- Write names in the same language as the original, without amounts in the name. Keep the exact \
name of an ingredient you keep. List ingredients in descending order of weight, as on a label.
- For every ingredient give its composition in "per_100g". {_COMPOSITION_RULES}

Respond with JSON only:
{{"ingredients": [{{"name": "<name>", "grams": <number>, "per_100g": {{{_COMPOSITION_FIELDS}}}}}, ...],
"changes": ["<old> -> <new>", ...]}}"""

def _fmt_items(items: list[dict]) -> str:
    return "\n".join(f"- {i['name']}: {i['grams']:g} g" for i in items)


def _score_lines(n: dict, s: dict, items: list[dict], compositions: dict) -> list[str]:
    p = s["points"]
    lines = [
        f"Nutri-Score {s['grade']} (score {s['score']}: {s['negative']} negative points - {s['positive']} positive points).",
        "Per 100 g of product, with points and main sources:",
        f"- Energy {n['kcal']:.0f} kcal ({n['kj']:.0f} kJ): {p['energy']} points. Sources (kcal): "
        + _fmt_sources(nutriscore.sources(items, compositions, "kcal")),
        f"- Sugars {n['sugars']:.2f} g: {p['sugars']} points. Sources: " + _fmt_sources(nutriscore.sources(items, compositions, "sugars")),
        f"- Saturated fat {n['sat_fat']:.2f} g: {p['sat_fat']} points. Sources: "
        + _fmt_sources(nutriscore.sources(items, compositions, "sat_fat")),
        f"- Salt {n['salt']:.2f} g: {p['salt']} points. Sources: " + _fmt_sources(nutriscore.sources(items, compositions, "salt")),
    ]
    if "sweeteners" in p:
        lines.append(f"- Non-nutritive sweeteners: {p['sweeteners']} points.")
    lines += [
        f"- Protein {n['protein']:.2f} g: {p['protein']} points" + ("" if s["protein_counted"] else " (not counted: 11+ negative points)") + ".",
        f"- Fibre {n['fibre']:.2f} g: {p['fibre']} points.",
        f"- Fruit, vegetables, legumes {n['fvl_pct']:.0f}%: {p['fvl']} points.",
    ]
    return lines


def _fmt_sources(src: list[tuple[str, float]]) -> str:
    return ", ".join(f"{name} {v:g}" for name, v in src) or "none"


class IngredientRewriter:
    def __init__(self, model: str | None = None, temperature: float = 0.7):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self.temperature = temperature

    def _ask(self, system: str, user: str, temperature: float, effort: str = "low") -> dict:
        extra = {}
        if "gpt-oss" in self.model:
            # gpt-oss reasons before answering; with Groq's default output limit the reasoning
            # used it all up and the JSON came back cut off ("Failed to validate JSON").
            extra = {"reasoning_effort": effort, "max_completion_tokens": 16384}
        for attempt in range(2):  # one retry for API hiccups
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    **extra,
                )
                return json.loads(response.choices[0].message.content)
            except Exception:
                if attempt == 1:
                    raise
        raise AssertionError("unreachable")

    @staticmethod
    def _by_name(data: dict, names: list[str]) -> dict[str, dict]:
        """Map the LLM's per-ingredient entries back to our names (by name, else by position)."""
        entries = [e for e in data.get("ingredients", []) if isinstance(e, dict)]
        wanted = {nutriscore.key(n): n for n in names}
        out = {}
        for e in entries:
            k = nutriscore.key(str(e.get("name") or ""))
            if k in wanted:
                out[k] = e
        if len(out) < len(names) and len(entries) == len(names):
            for n, e in zip(names, entries):
                out.setdefault(nutriscore.key(n), e)
        return out

    def estimate(self, names: list[str]) -> dict[str, dict]:
        """Composition per 100 g for each ingredient, keyed by nutriscore.key(name)."""
        data = self._ask(ESTIMATE_PROMPT, "Ingredients:\n" + "\n".join(f"- {n}" for n in names), 0.1, effort="medium")
        return {k: nutriscore.clean_composition(e) for k, e in self._by_name(data, names).items()}

    def rewrite(
        self,
        original: list[dict],
        compositions: dict[str, dict],
        nutrition: dict,
        result: dict,
        category: str,
        attempts: list[dict],
    ) -> dict:
        kind = "a drink (beverage table)" if category == "beverage" else "a food (general table)"
        lines = [
            f"The product is {kind}.",
            f"Original recipe, total {nutrition['total_grams']:g} g:",
            _fmt_items(original),
            "",
            *_score_lines(nutrition, result, original, compositions),
            "",
            "Goal: Nutri-Score A or B.",
        ]
        if category == "beverage":
            lines.append("Beverage grades: B for a score of 2 or less, C up to 6, D up to 9, E above (A is water only).")
        else:
            lines.append("Food grades: A for a score of 0 or less, B up to 2, C up to 10, D up to 18, E above.")
        if attempts:
            lines += ["", "Your previous attempts did not reach the goal:"]
            for a in attempts:
                lines.append(f"- Round {a['round']} (Nutri-Score {a['grade']}, score {a['score']}): {a['ingredients']}")
            lines.append("Try a different, more thorough approach than before.")

        data = self._ask(REWRITE_PROMPT, "\n".join(lines), self.temperature, effort="medium")
        items = [
            {
                "name": str(e.get("name") or "").strip(),
                "grams": e.get("grams"),
                "per_100g": nutriscore.clean_composition(e["per_100g"]) if isinstance(e.get("per_100g"), dict) else None,
            }
            for e in data.get("ingredients", [])
            if isinstance(e, dict)
        ]
        return {"items": items, "changes": [str(c) for c in data.get("changes", [])]}
