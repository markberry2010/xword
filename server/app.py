"""FastAPI server with SSE for puzzle generation."""

import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from crossword.main import generate_puzzle
from crossword.wordlist import WordList

load_dotenv()

app = FastAPI(title="Project Unemploy Joel")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load wordlist once at startup
_wordlist: WordList | None = None


def get_wordlist() -> WordList:
    global _wordlist
    if _wordlist is None:
        from crossword.main import find_wordlist
        _wordlist = WordList(find_wordlist())
    return _wordlist


@app.on_event("startup")
async def startup():
    # Pre-load wordlist in background
    await asyncio.to_thread(get_wordlist)


@app.get("/api/health")
async def health():
    return {"status": "ok", "words": len(get_wordlist())}


@app.get("/api/generate")
async def generate(
    difficulty: str = Query(default="medium", pattern="^(easy|medium|hard)$"),
    size: int = Query(default=5, ge=5, le=5),
):
    """Generate a puzzle, streaming progress via SSE."""

    async def event_stream():
        progress_queue: asyncio.Queue = asyncio.Queue()

        def on_progress(stage: str, message: str, pct: int):
            # Called from worker thread — put into async queue
            progress_queue.put_nowait((stage, message, pct))

        async def run_generation():
            try:
                puzzle = await asyncio.to_thread(
                    generate_puzzle,
                    size=size,
                    difficulty=difficulty,
                    top_k_fills=15,
                    use_judge=True,
                    timeout=30.0,
                    min_word_score=60,
                    on_progress=on_progress,
                    wordlist=get_wordlist(),
                )
                return puzzle
            except Exception as e:
                return e

        # Start generation in background
        task = asyncio.create_task(run_generation())

        # Stream progress events while generation runs
        while not task.done():
            try:
                stage, message, pct = await asyncio.wait_for(
                    progress_queue.get(), timeout=0.5
                )
                yield {
                    "event": "progress",
                    "data": json.dumps({
                        "stage": stage,
                        "message": message,
                        "pct": pct,
                    }),
                }
            except asyncio.TimeoutError:
                continue

        # Drain remaining progress events
        while not progress_queue.empty():
            stage, message, pct = progress_queue.get_nowait()
            yield {
                "event": "progress",
                "data": json.dumps({
                    "stage": stage,
                    "message": message,
                    "pct": pct,
                }),
            }

        # Get result
        result = task.result()
        if isinstance(result, Exception):
            yield {
                "event": "error",
                "data": json.dumps({"message": str(result)}),
            }
        else:
            # Estimate cost: ~$0.003/fill judged + ~$0.006 for clue gen
            num_fills = 15  # top_k_fills
            cost_dollars = num_fills * 0.003 + 0.006
            cost_cents = cost_dollars * 100

            yield {
                "event": "complete",
                "data": json.dumps({
                    "puzzle": result.to_json(),
                    "cost_cents": round(cost_cents, 1),
                }),
            }

    return EventSourceResponse(event_stream())


# Serve frontend static files in production
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True))
