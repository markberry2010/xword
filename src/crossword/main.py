"""Orchestrator: wire together wordlist, grid, solver, judge, clues, and output."""

import argparse
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv

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
) -> Puzzle:
    """Generate a complete crossword puzzle."""
    # 1. Load wordlist
    wl_path = Path(wordlist_path) if wordlist_path else find_wordlist()
    wordlist = WordList(wl_path)
    print(f"Loaded {len(wordlist)} words")

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

    print(f"Grid: {size}x{size} with {len(pattern.blacks)} black squares, {len(pattern.slots)} slots")

    # 3. Generate fills
    config = SolverConfig(
        top_k=top_k_fills,
        timeout_seconds=timeout,
        min_word_score=min_word_score,
    )
    solver = Solver(wordlist, config)
    print("Solving...")
    fills = solver.solve(pattern)
    print(f"Found {len(fills)} fills")

    if not fills:
        raise RuntimeError("No valid fills found for this pattern. Try a different pattern or lower min_word_score.")

    # 4. Judge + clue generation (parallel where possible)
    judge = FillJudge()
    clue_gen = ClueGenerator()

    if use_judge and len(fills) > 1:
        # Run judge and speculative clue generation in parallel:
        # - Judge ranks all fills
        # - Clue gen starts on the top 3 fills by score (speculative)
        # Whichever fill the judge picks, we likely already have its clues.
        speculative_count = min(3, len(fills))
        top_by_score = sorted(fills, key=lambda f: f.score.composite, reverse=True)[:speculative_count]

        print("Ranking fills and generating clues in parallel...")
        judge_result = None
        clue_results = {}

        with ThreadPoolExecutor(max_workers=4) as executor:
            judge_future = executor.submit(judge.rank_fills, fills, pattern)
            clue_futures = {
                executor.submit(
                    clue_gen.generate_clues, fill, pattern,
                    difficulty=difficulty, theme=theme,
                ): fill
                for fill in top_by_score
            }

            judge_result = judge_future.result()
            for future in as_completed(clue_futures):
                fill = clue_futures[future]
                clue_results[id(fill)] = future.result()

        fills = judge_result
        best_fill = fills[0]
        print(f"Selected fill (score={best_fill.score.composite:.0f}):")
        _print_grid(best_fill, pattern)

        # Use speculative clues if we have them, otherwise generate
        if id(best_fill) in clue_results:
            print("Using pre-generated clues (cache hit)")
            clues = clue_results[id(best_fill)]
        else:
            print("Judge picked a different fill, generating clues...")
            clues = clue_gen.generate_clues(best_fill, pattern, difficulty=difficulty, theme=theme)
    else:
        best_fill = fills[0]
        print(f"Selected fill (score={best_fill.score.composite:.0f}):")
        _print_grid(best_fill, pattern)
        print("Generating clues...")
        clues = clue_gen.generate_clues(best_fill, pattern, difficulty=difficulty, theme=theme)

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
    parser.add_argument("--top-k", type=int, default=10, help="Number of candidate fills")
    parser.add_argument("--no-judge", action="store_true", help="Skip LLM judge")
    parser.add_argument("--timeout", type=float, default=30.0, help="Solver timeout in seconds")
    parser.add_argument("--min-score", type=int, default=30, help="Minimum word score (wordlist uses 0-50 scale)")
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
