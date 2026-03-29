"""Tests for puzzle module."""

from pathlib import Path

from crossword.puzzle import parse_puzzle_text


SAMPLE_PUZZLE = """\
<ACROSS PUZZLE V2>
<TITLE>
    NY Times, Mon, Jul 03, 2023
<AUTHOR>
    Joel Fagliano
<COPYRIGHT>
    2023, The New York Times
<SIZE>
    5x5
<GRID>
    ..MAY
    .CUBE
    TORUS
    OVAL.
    YELL.
<ACROSS>
    Month that's a vegetable spelled backward
    Shape of sugar or ice
    Shape of an inner tube
    Shape of a planet's orbital path
    Raise one's voice
<DOWN>
    Artwork on the side of a building
    Like ___ in a china shop
    "That's correct"
    Secluded bay
    Plastic bone, for a dog
"""


def test_parse_puzzle_text():
    result = parse_puzzle_text(SAMPLE_PUZZLE)
    assert result["title"] == "NY Times, Mon, Jul 03, 2023"
    assert result["author"] == "Joel Fagliano"
    assert result["size"] == "5x5"
    assert len(result["grid_rows"]) == 5
    assert result["grid_rows"][0] == "..MAY"
    assert len(result["across_clues"]) == 5
    assert len(result["down_clues"]) == 5


def test_parse_grid_rows():
    result = parse_puzzle_text(SAMPLE_PUZZLE)
    assert result["grid_rows"][2] == "TORUS"


def test_parse_all_sample_files():
    """Parse all July23-Minis files if they exist."""
    minis_dir = Path("July23-Minis")
    if not minis_dir.exists():
        return

    for f in sorted(minis_dir.glob("*.TXT")):
        text = f.read_text(errors="replace")
        result = parse_puzzle_text(text)
        assert result["title"], f"No title in {f.name}"
        assert len(result["grid_rows"]) > 0, f"No grid in {f.name}"
        assert len(result["across_clues"]) > 0, f"No across clues in {f.name}"
        assert len(result["down_clues"]) > 0, f"No down clues in {f.name}"
