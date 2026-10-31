# nova-rewriter

Rewrites a product's ingredient list with an LLM (Groq) until the NOVA classifier
([hsilvosa/nova-group-classifier](https://huggingface.co/hsilvosa/nova-group-classifier))
no longer rates it as ultra-processed (NOVA 4).

## Setup

```bash
uv sync
cp .env.example .env   # put your key in GROQ_API_KEY
```

The model files (about 2 MB) download automatically from Hugging Face on the first run.

## Usage

```bash
# Run the rewrite loop
uv run nova-rewriter "Sugar, palm oil, hazelnuts, skimmed milk powder, fat-reduced cocoa, emulsifier: lecithins (soya), vanillin"

# Options
uv run nova-rewriter "..." --threshold 0.3 --max-rounds 8 --model openai/gpt-oss-120b
uv run nova-rewriter "..." --json          # print the result as JSON
uv run nova-rewriter "..." --score-only    # classify only (no Groq key needed)
```

## Web API (Agent tab)

```bash
uv run nova-rewriter-api      # http://127.0.0.1:8001 (AGENT_PORT to change), used by the web Agent tab
```

- `GET /agent-api/health`: classifier loaded, Groq key set, model id
- `POST /agent-api/rewrite`: `{ "ingredients": "...", "threshold": 0.5, "max_rounds": 5 }`.
  Streams NDJSON: one `attempt` per round (`round_error` when the LLM call fails), then
  `result`.

## How it works

```
ingredients ──► NOVA classifier ──► P(NOVA 4) < threshold? ──yes──► done
                     ▲                        │ no
                     │                        ▼
                     └── new list ◄── Groq LLM (original + previous attempts/scores + flagged ingredients)
                                       (up to max-rounds; if never reached, return the lowest-scoring list)
```

- `src/nova_rewriter/classifier.py`: NOVA classifier. `score()` and `ingredient_impact()`
- `src/nova_rewriter/llm.py`: Groq call and prompt (JSON responses)
- `src/nova_rewriter/agent.py`: the loop and attempt tracking

### Notes on the classifier

- The model card's `pipeline(...)` example does **not work**. `config.json` holds TF-IDF data
  instead of a transformer config, and the DistilBERT weights (`model.safetensors`) barely
  separate the classes when loaded manually.
- The model actually used is `nova_gb_model.joblib`, a HistGradientBoosting classifier with 4,004 inputs.
  The repo has no preprocessing code, so the features were reconstructed:
  - TF-IDF (vocab and idf from config.json, 1–3-grams, `sublinear_tf`, accent stripping), 4,000 dimensions
  - character count, word count, ingredient count (split on `,`/`;`), and 0
  - Validated on 6,000 Open Food Facts records at **97.2% accuracy** (the model card reports 96.2%)
- Length and ingredient count are features, so shorter lists score lower on their own.
  The prompt tells the LLM to replace ingredients rather than delete them.
- `ingredient_impact()` removes one ingredient at a time and measures the drop in NOVA 4 log-odds.
  It passes the most influential ingredients to the LLM as hints.
