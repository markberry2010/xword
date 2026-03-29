"""Shared test fixtures."""

from pathlib import Path
from textwrap import dedent

import pytest

from crossword.wordlist import WordList


@pytest.fixture
def small_wordlist(tmp_path: Path) -> WordList:
    """A small wordlist for testing."""
    words = dedent("""\
        CAT,60
        CUP,50
        CUT,55
        COT,45
        CAR,65
        CAN,60
        DOG,70
        DIG,50
        DUG,45
        RAT,55
        RUG,50
        RUN,60
        BAT,55
        BIG,50
        BUN,55
        TAN,50
        TIN,45
        TON,55
        AGO,40
        AGE,50
        ATE,55
        ARE,50
        ARC,45
        OAT,50
        OAK,55
        OWL,60
        CATS,60
        DOGS,70
        RUNS,60
        BATS,55
        OAKS,55
        CHARM,80
        LIARS,70
        ANGEL,75
        STEER,65
        PEACE,80
        CLASP,70
        HASTE,60
        ANGER,65
        REGAL,75
        SLEEP,70
        CRANE,75
        LEAST,65
        ARISE,70
        MEATS,60
        STERN,65
    """)
    wl_path = tmp_path / "test_wordlist.txt"
    wl_path.write_text(words)
    return WordList(wl_path)
