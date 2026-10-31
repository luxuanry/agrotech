# nutri-rewriter

Reformulates a recipe (ingredients in grams) with an LLM (Groq) until its
Nutri-Score (2023 algorithm) reaches **B or better**.

## Setup

```bash
uv sync
cp .env.example .env   # put your key in GROQ_API_KEY
```

## Usage

```bash
# Run the rewrite loop (each ingredient needs an amount in grams)
uv run nutri-rewriter "Eau 860 g, Avoine 120 g, Huile de tournesol 12 g, Sucre 30 g, Sel 1 g"

# Options
uv run nutri-rewriter "..." --category food --max-rounds 8 --model openai/gpt-oss-120b
uv run nutri-rewriter "..." --json          # print the result as JSON
uv run nutri-rewriter "..." --score-only    # only score the recipe
```

`--category beverage` (default) uses the Nutri-Score table for drinks, which since the
2023 update includes plant-based drinks; `--category food` uses the general table.

## Web API (Agent tab)

```bash
uv run nutri-rewriter-api      # http://127.0.0.1:8001 (AGENT_PORT to change), used by the web Agent tab
```

- `GET /agent-api/health`: Groq key set, model id
- `POST /agent-api/rewrite`:
  `{ "items": [{"name": "Avoine", "grams": 120}, ...], "category": "beverage", "max_rounds": 5 }`.
  Streams NDJSON: one `attempt` per round (`round_error` when the LLM call fails), then `result`.

## How it works

```
recipe (g) ──► LLM: composition per 100 g of each ingredient
                 │
                 ▼
           nutrition per 100 g (code) ──► Nutri-Score A or B? ──yes──► done
                 ▲                              │ no
                 │                              ▼
                 └── new recipe (g) + composition ◄── Groq LLM (original, points and their
                     of each ingredient per 100 g       main sources, previous attempts)
                     (up to max-rounds; if never reached, return the lowest-scoring recipe)
```

- `src/nutri_rewriter/nutriscore.py`: nutrition per 100 g from grams, Nutri-Score points and grade
- `src/nutri_rewriter/llm.py`: Groq calls (composition estimate, rewrite) and prompts
- `src/nutri_rewriter/agent.py`: the loop and attempt tracking

### Notes

- The LLM supplies compositions per 100 g of ingredient (with every rewritten recipe,
  and in a separate call for the original). It never computes the score: nutrition per
  100 g and the Nutri-Score are calculated in `nutriscore.py` from those values and the grams.
- An ingredient keeps its composition for the whole run, so a round cannot improve its
  score by re-estimating an ingredient it kept.
- The LLM picks the grams of new or replacing ingredients and is told to keep the
  total weight close to the original and not to just add water.
- Drinks are assumed to weigh 1 g per ml. Cheese, red meat and fats/oils/nuts have
  special Nutri-Score rules that are not implemented.
