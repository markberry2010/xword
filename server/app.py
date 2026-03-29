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

from crossword.clues import ClueGenerator
from crossword.grid import Grid
from crossword.main import generate_puzzle
from crossword.solver import Fill, FillScore
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
    allow_methods=["GET", "POST"],
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
    size: int = Query(default=5, ge=5, le=7),
):
    """Generate a puzzle, streaming progress via SSE."""

    async def event_stream():
        progress_queue: asyncio.Queue = asyncio.Queue()

        def on_progress(stage: str, message: str, pct: int):
            # Called from worker thread — put into async queue
            progress_queue.put_nowait((stage, message, pct))

        async def run_generation():
            # Scale solver params by grid size
            min_score = {5: 60, 7: 60, 9: 40, 11: 35, 15: 30}.get(size, 40)
            top_k = 15 if size <= 7 else 10 if size <= 9 else 5
            timeout = 15.0 if size <= 7 else 30.0

            try:
                puzzle = await asyncio.to_thread(
                    generate_puzzle,
                    size=size,
                    difficulty=difficulty,
                    top_k_fills=top_k,
                    use_judge=True,
                    timeout=timeout,
                    min_word_score=min_score,
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
            # Estimate cost: Haiku judge ~$0.0007/fill + Sonnet clues ~$0.006
            num_fills = 15
            cost_dollars = num_fills * 0.0007 + 0.006
            cost_cents = cost_dollars * 100

            yield {
                "event": "complete",
                "data": json.dumps({
                    "puzzle": result.to_json(),
                    "cost_cents": round(cost_cents, 1),
                }),
            }

    return EventSourceResponse(event_stream())


@app.post("/api/reclue")
@limiter.limit("3/minute")
async def reclue(request: Request):
    """Re-generate clues for an existing puzzle using Opus."""
    body = await request.json()
    puzzle_data = body.get("puzzle")
    difficulty = body.get("difficulty", "medium")

    if not puzzle_data:
        return JSONResponse(status_code=400, content={"detail": "Missing puzzle data"})

    def _reclue():
        size = puzzle_data["size"]
        grid_rows = puzzle_data["grid"]

        # Reconstruct grid and fill from puzzle JSON
        blacks = set()
        cell_letters = {}
        for r, row in enumerate(grid_rows):
            for c, ch in enumerate(row):
                if ch == ".":
                    blacks.add((r, c))
                else:
                    cell_letters[(r, c)] = ch

        grid = Grid(size, blacks)
        pattern = grid.build()
        slot_index = {s.id: i for i, s in enumerate(pattern.slots)}

        assignments = {}
        for slot in pattern.slots:
            word = "".join(cell_letters.get(cell, "?") for cell in slot.cells)
            assignments[slot.id] = word

        fill = Fill(
            grid=pattern,
            assignments=assignments,
            cell_letters=cell_letters,
            score=FillScore(),
        )

        clue_gen = ClueGenerator(model="claude-opus-4-20250514")
        clues = clue_gen.generate_clues(fill, pattern, difficulty=difficulty)

        clue_data = {}
        for cl in clues:
            clue_data[cl.slot_id] = {
                "word": cl.word,
                "clue": cl.clue_text,
                "difficulty": cl.difficulty,
                "alternatives": cl.alternatives,
            }
        return clue_data

    clue_data = await asyncio.to_thread(_reclue)

    # Opus clue cost: ~450 in × $15/M + ~350 out × $75/M = ~$0.033
    return {"clues": clue_data, "cost_cents": 3.3}


# Serve frontend static files in production
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True))
