"""HTTP API for the "Agent" tab of the web front end.

Run from the agent folder:  uv run nova-rewriter-api   (http://127.0.0.1:8001)
Port 8001 so it runs next to the ListeCourte backend on 8000. The Vite dev server
proxies /agent-api to it.

POST /agent-api/rewrite streams NDJSON, one event per line:
  {"type": "attempt", "attempt": {...}}       original (round 0), then each LLM round
  {"type": "round_error", "round": n, "message": "..."}
  {"type": "result", "result": {...}}         last line on success
  {"type": "error", "message": "..."}         last line if the run itself failed
"""

from __future__ import annotations

import json
import os
import queue
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Iterator, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import agent
from .classifier import NovaClassifier
from .llm import DEFAULT_MODEL, IngredientRewriter

STATE: dict = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    load_dotenv()
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    STATE["classifier"] = NovaClassifier()
    yield


app = FastAPI(title="NOVA Rewriter API", version="0.1.0", lifespan=lifespan)


class RewriteIn(BaseModel):
    ingredients: str = Field(min_length=1, max_length=5000)
    threshold: float = Field(0.5, gt=0, lt=1)
    max_rounds: int = Field(5, ge=1, le=10)
    model: Optional[str] = None


def _probs(text: str) -> list[float]:
    """P(NOVA 1..4) for one list."""
    return STATE["classifier"].score(text).probs


@app.get("/agent-api/health")
def health() -> dict:
    clf = STATE.get("classifier")
    return {
        "ready": clf is not None,
        "llm_configured": bool(os.environ.get("GROQ_API_KEY")),
        "model": os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
        "labels": clf.labels if clf else [],
    }


@app.post("/agent-api/rewrite")
def rewrite(body: RewriteIn) -> StreamingResponse:
    ingredients = body.ingredients.strip()
    if not ingredients:
        raise HTTPException(422, "The ingredient list is empty.")
    if not os.environ.get("GROQ_API_KEY"):
        raise HTTPException(503, "GROQ_API_KEY is not set. Put it in agent/.env and restart the agent API.")

    events: queue.Queue = queue.Queue()
    done = object()

    def work() -> None:
        try:
            result = agent.run(
                ingredients,
                STATE["classifier"],
                IngredientRewriter(model=body.model),
                threshold=body.threshold,
                max_rounds=body.max_rounds,
                on_attempt=lambda a: events.put({"type": "attempt", "attempt": asdict(a)}),
                on_error=lambda rnd, e: events.put({"type": "round_error", "round": rnd, "message": str(e)}),
            )
            out = asdict(result)
            out["original"]["probs"] = _probs(result.original.ingredients)
            out["best"]["probs"] = _probs(result.best.ingredients)
            events.put({"type": "result", "result": out})
        except Exception as e:  # noqa: BLE001 - reported to the client
            events.put({"type": "error", "message": str(e)})
        finally:
            events.put(done)

    threading.Thread(target=work, daemon=True).start()

    def stream() -> Iterator[str]:
        while (event := events.get()) is not done:
            yield json.dumps(event, ensure_ascii=False) + "\n"

    return StreamingResponse(stream(), media_type="application/x-ndjson")


def serve() -> None:
    import uvicorn

    uvicorn.run(
        "nova_rewriter.server:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("AGENT_PORT", "8001")),
    )
