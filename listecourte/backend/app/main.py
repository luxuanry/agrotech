"""ListeCourte API.

Run from the backend folder:  uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import rules, service
from .additives import ADDITIVES, FUNCTIONS
from .data import load_dataset
from .models import FunctionModels

logging.basicConfig(level=logging.INFO)
STATE: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    ds = load_dataset()
    STATE["ds"] = ds
    STATE["models"] = FunctionModels().fit(ds.df)
    STATE["backtest"] = None  # computed lazily, it takes a few seconds
    logging.info("Loaded %d products from %s", len(ds.df), ds.source)
    yield


app = FastAPI(title="ListeCourte API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])


class RecommendIn(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    ingredients_text: Optional[str] = None
    protein: Optional[float] = None
    fat: Optional[float] = None
    sugars: Optional[float] = None
    carbs: Optional[float] = None
    salt: Optional[float] = None
    calcium_mg: Optional[float] = None
    barista: bool = False
    organic: bool = False


class IngredientIn(BaseModel):
    id: str
    pct: float = Field(ge=0, le=100)


class CheckIn(BaseModel):
    base: Literal["oat", "soy", "almond", "rice", "coconut", "other"]
    ingredients: list[IngredientIn]
    additives: list[str] = []
    barista: bool = False
    organic: bool = False
    vitamins: bool = False


@app.get("/api/meta")
def meta() -> dict:
    ds = STATE["ds"]
    return {
        "data": {"is_sample": ds.is_sample, "source": ds.source, "n_products": int(len(ds.df))},
        "functions": FUNCTIONS,
        "additives": [{"code": c, "name": a["name"], "function": a["function"], "aliases": a["aliases"]} for c, a in ADDITIVES.items()],
        "ingredients": [{"id": k, "label": v["label"], "tag": v["tag"]} for k, v in service.ingredients_ref().items() if k != "water"],
        "rule_sources": rules.sources(),
    }


@app.get("/api/products/search")
def search(q: str) -> list[dict]:
    return STATE["ds"].search(q)


@app.post("/api/recommend")
def recommend(body: RecommendIn) -> dict:
    try:
        return service.recommend(body.model_dump(), STATE["ds"], STATE["models"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.post("/api/check")
def check(body: CheckIn) -> dict:
    try:
        return service.check(body.model_dump(), STATE["ds"], STATE["models"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/validation")
def validation() -> dict:
    if STATE["backtest"] is None:
        STATE["backtest"] = service.backtest(STATE["ds"], STATE["models"])
    return {
        "models": {f: {"label": FUNCTIONS[f], **m} for f, m in STATE["models"].metrics.items()},
        "backtest": STATE["backtest"],
        "data": {"is_sample": STATE["ds"].is_sample, "source": STATE["ds"].source},
    }
