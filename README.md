# ListeCourte

Tool prototype for Hack the Fork Paris 2026, Track 2. Helps the R&D lead of a
co-manufacturer of retailer-brand plant drinks decide which additives to
remove, what comparable products do instead, and which lab trials to run first.

React (Vite) frontend, FastAPI backend, DuckDB over Open Food Facts.

## Run it

Backend (Python 3.10+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/make_sample_data.py        # synthetic data, so the app runs right away
uvicorn app.main:app --reload --port 8000
```

Frontend (Node 18+), in a second terminal:

```bash
cd frontend
npm install
npm run dev                                # http://localhost:5173, /api is proxied to :8000
```

Agent tab (optional, a third terminal, Python 3.12 + [uv](https://docs.astral.sh/uv/)):

```bash
cd agent
uv sync
cp .env.example .env                       # set GROQ_API_KEY
uv run nutri-rewriter-api                  # http://127.0.0.1:8001, /agent-api is proxied to it
```

The **Agent** tab takes a recipe in grams, lets the Nutri-Score rewriter agent change it
with a Groq LLM until the recipe reaches Nutri-Score B or better, and shows the
rewritten recipe in grams, the nutrition and Nutri-Score before and after, and what
the score means. It is independent of the backend: the other tabs work without
it, and it works without the backend. See `agent/README.md`.

## Switch to real data

Quickest route, the Open Food Facts search API (a few minutes, French plant drinks only):

```bash
cd backend && source .venv/bin/activate
python scripts/fetch_from_off_api.py --dry-run   # product count per category tag
python scripts/fetch_from_off_api.py             # writes data/products.parquet
```

Then restart the API. Alternative route, the full CSV export:

1. Download the Open Food Facts CSV export:
   https://static.openfoodfacts.org/data/en.openfoodfacts.org.products.csv.gz
2. Check which category tags French plant drinks use, and edit
   `CATEGORY_PATTERNS` in `scripts/build_from_off.py` if needed:
   `python scripts/build_from_off.py path/to/export.csv.gz --inspect`
3. Build the table: `python scripts/build_from_off.py path/to/export.csv.gz`
4. Restart the API. It uses `data/products.parquet` when present and shows
   the sample banner only for the synthetic data.

## Before the demo

- `backend/data/rules.json`: every additive entry is a draft (`verified: false`).
  Check each against Reg (EC) 1333/2008 Annex II and Reg (EU) 2021/1165 Annex V,
  then set `verified: true`. Unknown entries show as "to verify", never as a pass.
- `backend/data/ingredients_ref.json`: compositions used by Check mode are
  placeholders. Replace them with Ciqual values and switch `tag` to `sourced`.
- `backend/app/config.py`: extend `RETAILER_BRANDS` with the sub-brands you find.

## How it maps to the plan

| Plan | Code |
| --- | --- |
| Data layer (OFF + DuckDB) | `app/data.py`, `scripts/build_from_off.py` |
| Hard rules | `app/rules.py`, `data/rules.json` |
| M2 gradient boosting + SHAP | `app/models.py` |
| M3 similarity + substitution patterns | `app/precedent.py` |
| M4 explanations (template, optional LLM) | `app/explain.py` |
| Recommend / Check / backtest | `app/service.py` |
| API | `app/main.py` |
| Interface | `frontend/src` |
| Agent tab (Nutri-Score rewriter) | `agent/src/nutri_rewriter`, `frontend/src/views/AgentView.jsx` |

Optional LLM explanations: `pip install anthropic`, set `ANTHROPIC_API_KEY`.
The LLM rewrites the template text from the evidence only; it never changes a light.

## API

- `GET /api/meta`: dataset info, additive catalogue, ingredient list
- `GET /api/products/search?q=`: barcode, name or brand
- `POST /api/recommend`: `{ "code": "..." }` or ingredient text plus nutrition
- `POST /api/check`: base, ingredient proportions, additives kept, flags
- `GET /api/validation`: cross-validated AUC against baseline, backtest

## Data licence

Open Food Facts data is under the Open Database License (ODbL). Credit
"Open Food Facts contributors" and keep any derived database open.
