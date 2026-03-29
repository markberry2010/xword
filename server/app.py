"""FastAPI server with SSE for puzzle generation."""

import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from crossword.main import generate_puzzle
from crossword.wordlist import WordList

if os.environ.get("ENV") != "production":
    from dotenv import load_dotenv
    load_dotenv()

# Structured logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("crossword.server")

app = FastAPI(title="Project Unemploy Joel")

# CORS — restrict origins in production via ALLOWED_ORIGINS env var
_allowed_origins = os.environ.get("ALLOWED_ORIGINS", "").split(",")
_allowed_origins = [o.strip() for o in _allowed_origins if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins if _allowed_origins else ["http://localhost:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Try again later."},
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
    log.info("Pre-loading wordlist...")
    await asyncio.to_thread(get_wordlist)
    log.info("Wordlist loaded (%d words)", len(get_wordlist()))


@app.get("/api/health")
async def health():
    return {"status": "ok", "words": len(get_wordlist())}


@app.get("/api/generate")
@limiter.limit("5/minute")
async def generate(
    request: Request,
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
