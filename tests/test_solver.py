"""Tests for solver module."""

from pathlib import Path

import pytest

from crossword.grid import Grid
from crossword.solver import Solver, SolverConfig
from crossword.wordlist import WordList


@pytest.fixture
def solver_wordlist(tmp_path: Path) -> WordList:
    """Wordlist with enough 3-letter words for a 3x3 solve."""
    # Includes words forming known valid 3x3 word squares:
    # TAP/AGE/PEN (symmetric) and BAD/ATE/DEN
    words = "\n".join([
        "CAT,70", "CUP,60", "CUT,55", "COT,50", "CAR,65", "CAN,60",
        "DOG,70", "DIG,50", "DUG,45", "DAM,55",
        "RAT,55", "RUG,50", "RUN,60", "RAM,55",
        "BAT,55", "BIG,50", "BUN,55", "BAD,50",
        "TAN,50", "TIN,45", "TON,55", "TAR,50", "TAP,55",
        "AGO,40", "AGE,50", "ATE,55", "ARE,50",
        "OAT,50", "OAK,55", "OWL,60", "ODD,45",
        "GUN,55", "GUM,50", "GUT,50", "GAP,50",
        "AND,40", "ANT,50", "AID,45", "ARM,55",
        "NOT,50", "NUT,55", "NAP,50", "NET,55",
        "LOG,50", "LET,50", "LIT,45", "LOT,55",
        "MAP,50", "MAT,55", "MUD,45", "MIX,50",
        "SET,55", "SIT,50", "SAT,55", "SUN,60",
        "PAN,50", "PIG,50", "PUT,50", "PAT,55", "PEN,55",
        "HAT,55", "HIT,50", "HUG,55", "HOP,50",
        "DEN,50", "END,50", "RAN,50", "TEN,50",
        "ERA,50", "EAR,50", "TEA,50", "BET,50",
    ])
    wl_path = tmp_path / "solver_wl.txt"
    wl_path.write_text(words)
    return WordList(wl_path)


def test_solve_3x3_open(solver_wordlist: WordList):
    """Solver should find at least one fill for a 3x3 open grid."""
    grid = Grid(3, set())
    pattern = grid.build()
    solver = Solver(solver_wordlist, SolverConfig(top_k=3, timeout_seconds=10.0, min_word_score=1))
    fills = solver.solve(pattern)
    assert len(fills) > 0

    # Verify fill consistency: crossings match
    for fill in fills:
        for slot in pattern.slots:
            word = fill.assignments[slot.id]
            for pos, cell in enumerate(slot.cells):
                assert fill.cell_letters[cell] == word[pos]


def test_no_duplicate_words(solver_wordlist: WordList):
    """No fill should contain the same word twice."""
    grid = Grid(3, set())
    pattern = grid.build()
    solver = Solver(solver_wordlist, SolverConfig(top_k=5, timeout_seconds=10.0, min_word_score=1))
    fills = solver.solve(pattern)
    for fill in fills:
        words = list(fill.assignments.values())
        assert len(words) == len(set(words)), f"Duplicate word in fill: {words}"


def test_fill_scoring(solver_wordlist: WordList):
    """Fills should have non-zero scores."""
    grid = Grid(3, set())
    pattern = grid.build()
    solver = Solver(solver_wordlist, SolverConfig(top_k=3, timeout_seconds=10.0, min_word_score=1))
    fills = solver.solve(pattern)
    assert len(fills) > 0
    for fill in fills:
        assert fill.score.total > 0
        assert fill.score.composite > 0


def test_timeout_respected(solver_wordlist: WordList):
    """Solver should respect timeout (not hang forever)."""
    grid = Grid(3, set())
    pattern = grid.build()
    solver = Solver(solver_wordlist, SolverConfig(top_k=100, timeout_seconds=0.5, min_word_score=1))
    # Should return quickly even if can't find 100 fills
    fills = solver.solve(pattern)
    assert isinstance(fills, list)


def test_empty_wordlist(tmp_path: Path):
    """Solver should return empty list with insufficient wordlist."""
    wl_path = tmp_path / "empty.txt"
    wl_path.write_text("XYZ,50\n")
    wl = WordList(wl_path)
    grid = Grid(3, set())
    pattern = grid.build()
    solver = Solver(wl, SolverConfig(top_k=1, timeout_seconds=5.0, min_word_score=1))
    fills = solver.solve(pattern)
    assert fills == []
