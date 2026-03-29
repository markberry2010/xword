"""Orchestrator: wire together wordlist, grid, solver, judge, clues, and output."""

import argparse
import logging
import random
import sys
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)

from crossword.clues import ClueGenerator
from crossword.grid import Grid, get_mini_patterns
from crossword.judge import FillJudge
from crossword.puzzle import Puzzle, PuzzleMetadata
from crossword.solver import Fill, Solver, SolverConfig
from crossword.wordlist import WordList


def find_wordlist() -> Path:
    """Locate the wordlist file, checking common paths."""
    candidates = [
        Path("data/wordlist.txt"),
        Path(__file__).parent.parent.parent / "data" / "wordlist.txt",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(
        "Could not find data/wordlist.txt. "
        "Run from the project root or pass --wordlist path."
    )


def generate_puzzle(
    size: int = 5,
    difficulty: str = "medium",
    theme: str | None = None,
    wordlist_path: str | None = None,
    top_k_fills: int = 10,
    use_judge: bool = True,
    timeout: float = 30.0,
    min_word_score: int = 20,
    pattern_index: int | None = None,
    on_progress: Callable[[str, str, int], None] | None = None,
    wordlist: WordList | None = None,
) -> Puzzle:
    """Generate a complete crossword puzzle.

    on_progress(stage, message, pct) is called at each pipeline stage.
    wordlist can be passed to avoid reloading from disk.
    """
    def progress(stage: str, message: str, pct: int) -> None:
        if on_progress:
            on_progress(stage, message, pct)
        log.info(message)

    # 1. Load wordlist
    if wordlist is None:
        wl_path = Path(wordlist_path) if wordlist_path else find_wordlist()
        wordlist = WordList(wl_path)
    progress("loading", f"Loaded {len(wordlist)} words", 5)

    # 2. Select grid pattern
    if size == 5:
        patterns = get_mini_patterns()
        if not patterns:
            raise RuntimeError("No valid 5x5 patterns available")
        if pattern_index is not None and 0 <= pattern_index < len(patterns):
            pattern = patterns[pattern_index]
        else:
            pattern = random.choice(patterns)
    else:
        # For non-5x5, create an open grid
        grid = Grid(size, set())
        pattern = grid.build()

    progress("grid", f"Grid: {size}x{size} with {len(pattern.blacks)} black squares, {len(pattern.slots)} slots", 10)

    # 3. Generate fills
    config = SolverConfig(
        top_k=top_k_fills,
        timeout_seconds=timeout,
        min_word_score=min_word_score,
    )
    solver = Solver(wordlist, config)
    progress("solving", "Finding fills...", 15)
    fills = solver.solve(pattern)
    progress("solving", f"Found {len(fills)} fills", 40)

    if not fills:
        raise RuntimeError("No valid fills found for this pattern. Try a different pattern or lower min_word_score.")

    # 4. Judge: score each fill independently in parallel
    if use_judge and len(fills) > 1:
        progress("judging", f"Scoring {len(fills)} fills...", 50)
        judge = FillJudge()
        fills = judge.rank_fills(fills, pattern)

    best_fill = fills[0]
    progress("judging", f"Selected fill (score={best_fill.score.composite:.0f})", 70)
    _print_grid(best_fill, pattern)

    # 5. Generate clues
    progress("cluing", "Writing clues...", 75)
    clue_gen = ClueGenerator()
    clues = clue_gen.generate_clues(best_fill, pattern, difficulty=difficulty, theme=theme)
    progress("done", "Puzzle complete!", 100)

    # 6. Assemble puzzle
    metadata = PuzzleMetadata(
        size=size,
        difficulty=difficulty,
        theme=theme,
    )
    return Puzzle(grid=pattern, fill=best_fill, clues=clues, metadata=metadata)


def _print_grid(fill: Fill, grid_pattern) -> None:
    """Print a filled grid to stdout."""
    size = grid_pattern.size
    for r in range(size):
        row = ""
        for c in range(size):
            if (r, c) in grid_pattern.blacks:
                row += "."
            else:
                row += fill.cell_letters.get((r, c), "?")
        print(f"  {row}")


def cli():
    load_dotenv()
    parser = argparse.ArgumentParser(description="Generate a crossword puzzle")
    parser.add_argument("--size", type=int, default=5, help="Grid size (default: 5)")
    parser.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    parser.add_argument("--theme", default=None, help="Optional theme for clues")
    parser.add_argument("--wordlist", default=None, help="Path to wordlist file")
    parser.add_argument("--output", "-o", default=None, help="Output file path")
    parser.add_argument("--format", default="text", choices=["text", "json", "display"])
    parser.add_argument("--top-k", type=int, default=15, help="Number of candidate fills to score")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM judge")
    parser.add_argument("--timeout", type=float, default=30.0, help="Solver timeout in seconds")
    parser.add_argument("--min-score", type=int, default=60, help="Minimum word score (1-100 scale)")
    parser.add_argument("--pattern", type=int, default=None, help="Pattern index (0-based)")
    parser.add_argument("--title", default="", help="Puzzle title")
    parser.add_argument("--author", default="", help="Puzzle author")
    args = parser.parse_args()

    puzzle = generate_puzzle(
        size=args.size,
        difficulty=args.difficulty,
        theme=args.theme,
        wordlist_path=args.wordlist,
        top_k_fills=args.top_k,
        use_judge=not args.no_judge,
        timeout=args.timeout,
        min_word_score=args.min_score,
        pattern_index=args.pattern,
    )

    if args.format == "text":
        output = puzzle.to_text(title=args.title, author=args.author)
    elif args.format == "json":
        output = puzzle.to_json_str()
    else:
        output = puzzle.display()

    if args.output:
        Path(args.output).write_text(output)
        print(f"\nSaved to {args.output}")
    else:
        print()
        print(output)


if __name__ == "__main__":
    cli()
