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
recipe (g) ──► composition per 100 g of each ingredient (once per ingredient)
                 │   1. LLM translates the name into French Ciqual terms ("귀리" → "Flocon d'avoine")
                 │   2. keyword search in the Ciqual table → candidate foods
                 │   3. LLM picks the matching food → values from Ciqual
                 │      (no match, e.g. additives or isolates → LLM estimate, marked as such)
                 ▼
           nutrition per 100 g ──► Nutri-Score A or B? ──yes──► done
                 ▲                        │ no
                 │                        ▼
                 └── new recipe (g) ◄── Groq LLM (original, points and their main sources,
                                         previous attempts)
                     (up to max-rounds; if never reached, return the lowest-scoring recipe)
```

- `src/nutri_rewriter/nutriscore.py`: nutrition per 100 g from grams, Nutri-Score points and grade
- `src/nutri_rewriter/ciqual.py`: Ciqual table and keyword search
- `src/nutri_rewriter/llm.py`: Groq calls (translate, choose, rewrite) and prompts
- `src/nutri_rewriter/agent.py`: the loop and attempt tracking

### Notes

- Compositions come from the Anses Ciqual table (CALNUT 2020: Ciqual 2020 with missing
  values filled in, 2,119 foods), stored in `src/nutri_rewriter/data/ciqual.json`.
  Rebuild it with `uv run python scripts/build_ciqual.py`. Source: "Anses. 2020. Table de
  composition nutritionnelle Ciqual pour le calcul des apports nutritionnels CALNUT."
- The LLM never supplies a number for a matched ingredient and never computes the score.
  Only ingredients with no Ciqual food get an LLM estimate; the web page and CLI show
  the source of each ingredient.
- An ingredient keeps its composition for the whole run, so a round cannot improve its
  score by re-estimating an ingredient it kept.
- The LLM picks the grams of new or replacing ingredients and is told to keep the
  total weight close to the original and not to just add water.
- Drinks are assumed to weigh 1 g per ml. Cheese, red meat and fats/oils/nuts have
  special Nutri-Score rules that are not implemented.
