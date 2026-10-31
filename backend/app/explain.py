"""M4: plain-language explanations of an evidence bundle.

Templates are the default and the fallback. If ANTHROPIC_API_KEY is set and
the `anthropic` package is installed, an LLM rewrites the template text using
only the evidence passed to it. The LLM explains; it never changes the light.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger(__name__)

LLM_MODEL = os.getenv("LISTECOURTE_LLM_MODEL", "claude-sonnet-5-5")


def template(option: dict) -> str:
    """Deterministic explanation built only from the evidence fields."""
    p = option["precedent"]
    n_peers, n_without = p["n_peers"]["value"], p["n_without"]["value"]
    share = round(100 * p["share_without"]["value"])
    parts = [
        f"{n_without} of {n_peers} comparable products ({share} %) work without any {option['label'].lower()}."
    ]
    if option["model"]:
        prob = round(100 * option["model"]["probability"]["value"])
        drivers = ", ".join(d["feature"] for d in option["model"]["drivers"][:2])
        parts.append(f"For a product with this matrix, the model estimates a {prob} % chance of needing one" + (f", driven mainly by {drivers}." if drivers else "."))
    if option["twins"]:
        t = option["twins"][0]
        parts.append(f"The closest product without it is {t['name']} ({t['brands']}, {t['code']}).")
    if option["claims_lost"]:
        parts.append("Removing it would void: " + ", ".join(c["label"].lower() for c in option["claims_lost"]) + ".")
    return " ".join(parts)


def explain(option: dict) -> dict:
    """Return {"text", "source"} where source is "template" or "llm"."""
    base = template(option)
    if not os.getenv("ANTHROPIC_API_KEY"):
        return {"text": base, "source": "template"}
    try:
        import anthropic  # type: ignore

        evidence = {k: option[k] for k in ("label", "light", "reasons", "precedent", "model", "claims_lost", "substitutions")}
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=LLM_MODEL,
            max_tokens=300,
            system=(
                "You explain food-reformulation evidence to an R&D lead. Use only the numbers and "
                "facts in the JSON. Do not add regulations, products or figures that are not in it. "
                "Do not say a formula is feasible. Three sentences at most, plain English."
            ),
            messages=[{"role": "user", "content": json.dumps(evidence, default=str)}],
        )
        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip()
        return {"text": text or base, "source": "llm" if text else "template"}
    except Exception as exc:  # any failure falls back to the template
        log.warning("LLM explanation failed, using template: %s", exc)
        return {"text": base, "source": "template"}
