"""HTTP API for the "Agent" tab of the web front end.

Run from the agent folder:  uv run nutri-rewriter-api   (http://127.0.0.1:8001)
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
from dataclasses import asdict
from typing import Iterator, Literal, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import agent
from .llm import DEFAULT_MODEL, IngredientRewriter

load_dotenv()

app = FastAPI(title="Nutri-Score Rewriter API", version="0.2.0")


class ItemIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    grams: float = Field(gt=0, le=100_000)


class RewriteIn(BaseModel):
    items: list[ItemIn] = Field(min_length=1, max_length=60)
    category: Literal["beverage", "food"] = "beverage"
    max_rounds: int = Field(5, ge=1, le=10)
    model: Optional[str] = None


@app.get("/agent-api/health")
def health() -> dict:
    return {
        "ready": True,
        "llm_configured": bool(os.environ.get("GROQ_API_KEY")),
        "model": os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
    }


@app.post("/agent-api/rewrite")
def rewrite(body: RewriteIn) -> StreamingResponse:
    if not os.environ.get("GROQ_API_KEY"):
        raise HTTPException(503, "GROQ_API_KEY is not set. Put it in agent/.env and restart the agent API.")

    events: queue.Queue = queue.Queue()
    done = object()

    def work() -> None:
        try:
            result = agent.run(
                [i.model_dump() for i in body.items],
                IngredientRewriter(model=body.model),
                category=body.category,
                max_rounds=body.max_rounds,
                on_attempt=lambda a: events.put({"type": "attempt", "attempt": asdict(a)}),
                on_error=lambda rnd, e: events.put({"type": "round_error", "round": rnd, "message": str(e)}),
            )
            events.put({"type": "result", "result": asdict(result)})
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
        "nutri_rewriter.server:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("AGENT_PORT", "8001")),
    )
