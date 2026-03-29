"""Tests for grid module."""

from crossword.grid import Grid, get_mini_patterns


def test_open_grid_slots():
    """5x5 with no blacks: 5 across + 5 down = 10 slots."""
    grid = Grid(5, set())
    pattern = grid.build()
    assert len(pattern.slots) == 10
    across = [s for s in pattern.slots if s.direction == "across"]
    down = [s for s in pattern.slots if s.direction == "down"]
    assert len(across) == 5
    assert len(down) == 5
    assert all(s.length == 5 for s in pattern.slots)


def test_corner_blacks():
    """Grid with two corner blacks."""
    blacks = {(0, 0), (4, 4)}
    grid = Grid(5, blacks)
    pattern = grid.build()
    # Should have fewer cells but still valid slots
    for slot in pattern.slots:
        assert slot.length >= 2


def test_crossings():
    """Every across slot should cross every down slot it shares a cell with."""
    grid = Grid(5, set())
    pattern = grid.build()
    for slot in pattern.slots:
        if slot.direction == "across":
            # In an open 5x5, each across slot crosses all 5 down slots
            assert len(slot.crossings) == 5


def test_numbering():
    """Open 5x5 should number the top row and left column."""
    grid = Grid(5, set())
    pattern = grid.build()
    # Cell (0,0) should be number 1
    assert pattern.numbering[(0, 0)] == 1


def test_validate_symmetric():
    """Symmetric grid should pass validation."""
    blacks = {(0, 0), (4, 4)}
    valid, violations = Grid.validate(5, blacks)
    assert valid, violations


def test_validate_asymmetric():
    """Non-symmetric grid should fail validation."""
    blacks = {(0, 0)}  # missing (4,4)
    valid, violations = Grid.validate(5, blacks)
    assert not valid
    assert any("symmetric" in v for v in violations)


def test_validate_disconnected():
    """Grid where whites are disconnected should fail."""
    # Black row splitting the grid
    blacks = {(2, c) for c in range(5)}
    valid, violations = Grid.validate(5, blacks)
    assert not valid


def test_from_strings():
    """Grid.from_strings parses dot patterns correctly."""
    rows = [
        ".DOCK",
        "NOFUN",
        "OUTRO",
        "SLEET",
        "HAND.",
    ]
    grid = Grid.from_strings(rows)
    assert (0, 0) in grid.blacks
    assert (4, 4) in grid.blacks
    assert (1, 0) not in grid.blacks


def test_get_mini_patterns():
    """get_mini_patterns should return at least one valid pattern."""
    patterns = get_mini_patterns()
    assert len(patterns) > 0
    for p in patterns:
        assert p.size == 5
        assert len(p.slots) > 0


def test_slot_ids_assigned():
    """All slots should have non-empty IDs after build."""
    grid = Grid(5, set())
    pattern = grid.build()
    for slot in pattern.slots:
        assert slot.id != ""
        assert slot.id[-1] in ("A", "D")
