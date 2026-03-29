# Project Unemploy Joel

AI-generated NYT-style mini crossword puzzles. Named after Joel Fagliano, the NYT Mini crossword editor whose job we're automating for ~5 cents a puzzle.

## How it works

```
Wordlist (523K scored words)
  → Rust CSP Solver (generates diverse candidate fills in <1s)
    → LLM Judge (scores each fill independently, in parallel)
      → LLM Clue Writer (generates NYT-style clues)
        → Playable puzzle in the browser
```

**Full pipeline: ~11 seconds per puzzle.**

### The solver

A constraint satisfaction problem (CSP) solver written in Rust, exposed to Python via PyO3. Uses backtracking with:

- Bitmap-based domain filtering for O(1) constraint checks
- Incremental constraint propagation (assign/unassign without rebuilding)
- MRV variable ordering (most constrained slot first)
- Multiple restarts with weighted shuffles for fill diversity
- Greedy diverse subset selection from the candidate pool

88x faster than the pure Python solver (0.3s vs 30s for a 5×5 open grid).

### The judge

Each candidate fill is scored independently by Claude Sonnet via parallel API calls. Evaluates entry quality, variety, clueability, freshness, and red flags. ~$0.003 per fill scored.

### The clue writer

Claude Sonnet generates clues with difficulty-calibrated prompts (easy = Monday-style straightforward, hard = Saturday-style misdirection). Each word gets a primary clue and two alternatives.

### The wordlist

523K words merged from three sources:
- [Spread the Wordlist](https://www.spreadthewordlist.com/) — 311K community-scored crossword words
- [Christopher Jones' wordlist](https://github.com/christophsjones/crossword-wordlist) — 176K words from NYT/WSJ/WaPo puzzles
- [Matt Abate's SVM-scored list](https://github.com/mattabate/wordlist) — 418K words scored by an ML model trained on 42K hand-labeled entries

Matt's SVM scores are used as the primary quality signal (captures clueability), with frequency-based scores as fallback for words not in his list.

## Setup

### Prerequisites

- Python 3.11+
- Rust toolchain (`curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`)
- Node.js 18+ (for the frontend)
- An [Anthropic API key](https://console.anthropic.com/)

### Install

```bash
# Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Rust solver (88x faster than pure Python)
pip install maturin
cd solver-rs && maturin develop --release && cd ..

# Frontend
cd frontend && npm install && cd ..

# API key
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

### Run

```bash
# Web app (two terminals)
source .venv/bin/activate && uvicorn server.app:app --port 8000
cd frontend && npm run dev

# Or CLI only
source .venv/bin/activate
python -m crossword --difficulty easy --format display
```

Open `http://localhost:5173` for the web app.

## CLI options

```
python -m crossword [options]

--difficulty    easy|medium|hard  (clue style, default: medium)
--format        text|json|display (output format, default: text)
--output, -o    path              (write to file)
--top-k         N                 (candidate fills to generate, default: 15)
--min-score     N                 (minimum word quality 1-100, default: 60)
--timeout       N                 (solver timeout in seconds, default: 30)
--no-judge                        (skip LLM ranking, use solver scores)
--pattern       N                 (grid pattern index, 0-based)
```

## Project structure

```
src/crossword/          Python package
  wordlist.py            Word database with indexed lookups
  grid.py                Grid patterns, slots, crossings, validation
  solver.py              CSP solver (delegates to Rust when available)
  judge.py               LLM fill reranker (parallel independent scoring)
  clues.py               LLM clue generator
  puzzle.py              Puzzle assembly and output formats
  main.py                Orchestrator and CLI

solver-rs/              Rust CSP solver (PyO3)
  src/lib.rs             Backtracking + bitmap domains + constraint propagation

server/                 FastAPI backend
  app.py                 SSE endpoint for puzzle generation

frontend/               React + TypeScript + Vite
  src/components/        CrosswordGrid, ClueList, GeneratePage, PlayPage
  src/hooks/             usePuzzle, useNavigation, useTimer
  src/styles/            Art Deco themed CSS

data/                   Wordlists (not checked into git due to size)
tests/                  Python test suite
```

## Cost

~5 cents per puzzle:
- Judge: 15 fills × $0.003 = $0.045
- Clues: ~$0.006
- **Total: ~$0.05**

That's roughly 5,000x cheaper than a human crossword editor. And it doesn't need health insurance.

## License

Code: MIT. Wordlists are CC BY-NC-SA 4.0 (see their respective repos for details).
