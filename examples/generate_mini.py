#!/usr/bin/env python3
"""Example: generate a 5x5 mini crossword puzzle."""

import sys
from pathlib import Path

# Add src to path for direct execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from crossword.main import generate_puzzle


def main():
    puzzle = generate_puzzle(
        size=5,
        difficulty="easy",
        top_k_fills=5,
        use_judge=False,  # skip LLM judge for quick demo
        timeout=30.0,
        min_word_score=30,
    )

    print("\n" + "=" * 40)
    print(puzzle.display())
    print("=" * 40)
    print()
    print(puzzle.to_text())


if __name__ == "__main__":
    main()
