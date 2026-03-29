"""Grid structure, patterns, slot extraction, and validation."""

from collections import deque
from dataclasses import dataclass, field


@dataclass
class Crossing:
    other_slot_id: str  # the slot this one crosses
    self_pos: int       # index within this slot's cells
    other_pos: int      # index within the other slot's cells


@dataclass
class Slot:
    id: str                         # e.g. "1A" (1-Across), "3D" (3-Down)
    direction: str                  # "across" or "down"
    cells: list[tuple[int, int]]    # list of (row, col) coordinates
    length: int                     # len(cells)
    crossings: list[Crossing] = field(default_factory=list)


@dataclass
class GridPattern:
    size: int                                   # 5 for 5x5, 15 for 15x15
    blacks: set[tuple[int, int]]                # black square coordinates
    slots: list[Slot]                           # all across and down slots
    numbering: dict[tuple[int, int], int]       # cell -> clue number


class Grid:
    """Build and validate crossword grid structures."""

    def __init__(self, size: int, blacks: set[tuple[int, int]] | None = None):
        self.size = size
        self.blacks = blacks or set()
        self._pattern: GridPattern | None = None

    def build(self) -> GridPattern:
        """Extract slots, crossings, numbering and return a GridPattern."""
        slots = self._extract_slots()
        self._compute_crossings(slots)
        numbering = self._assign_numbering(slots)
        self._pattern = GridPattern(
            size=self.size,
            blacks=frozenset(self.blacks),
            slots=slots,
            numbering=numbering,
        )
        return self._pattern

    @staticmethod
    def validate(size: int, blacks: set[tuple[int, int]]) -> tuple[bool, list[str]]:
        """Check structural validity. Returns (is_valid, list_of_violations)."""
        violations = []

        # 180° rotational symmetry
        for r, c in blacks:
            partner = (size - 1 - r, size - 1 - c)
            if partner not in blacks:
                violations.append(
                    f"Black at ({r},{c}) missing symmetric partner at {partner}"
                )

        # All white cells connected
        whites = {
            (r, c) for r in range(size) for c in range(size) if (r, c) not in blacks
        }
        if whites:
            visited = set()
            queue = deque([next(iter(whites))])
            visited.add(queue[0])
            while queue:
                r, c = queue.popleft()
                for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nr, nc = r + dr, c + dc
                    if (nr, nc) in whites and (nr, nc) not in visited:
                        visited.add((nr, nc))
                        queue.append((nr, nc))
            if visited != whites:
                violations.append(
                    f"Grid not connected: {len(visited)} reachable of {len(whites)} white cells"
                )

        # Build temporary slots to check lengths
        grid = Grid(size, blacks)
        slots = grid._extract_slots()

        for slot in slots:
            if slot.length < 3:
                violations.append(
                    f"Slot {slot.id} has length {slot.length} (minimum 3)"
                )

        # Every white cell belongs to at least one across and one down slot
        across_cells = set()
        down_cells = set()
        for slot in slots:
            target = across_cells if slot.direction == "across" else down_cells
            for cell in slot.cells:
                target.add(cell)
        for cell in whites:
            if cell not in across_cells:
                violations.append(f"Cell {cell} not in any across slot")
            if cell not in down_cells:
                violations.append(f"Cell {cell} not in any down slot")

        return (len(violations) == 0, violations)

    def _extract_slots(self) -> list[Slot]:
        """Extract all across and down slots from the grid."""
        slots = []

        # Across slots: scan each row left to right
        for r in range(self.size):
            c = 0
            while c < self.size:
                if (r, c) in self.blacks:
                    c += 1
                    continue
                # Start of a potential across word
                cells = []
                while c < self.size and (r, c) not in self.blacks:
                    cells.append((r, c))
                    c += 1
                if len(cells) >= 2:
                    slots.append(Slot(
                        id="",  # assigned later
                        direction="across",
                        cells=cells,
                        length=len(cells),
                    ))

        # Down slots: scan each column top to bottom
        for c in range(self.size):
            r = 0
            while r < self.size:
                if (r, c) in self.blacks:
                    r += 1
                    continue
                cells = []
                while r < self.size and (r, c) not in self.blacks:
                    cells.append((r, c))
                    r += 1
                if len(cells) >= 2:
                    slots.append(Slot(
                        id="",
                        direction="down",
                        cells=cells,
                        length=len(cells),
                    ))

        return slots

    def _assign_numbering(self, slots: list[Slot]) -> dict[tuple[int, int], int]:
        """Assign clue numbers per NYT convention and set slot IDs."""
        # Find cells that start a slot
        starts_across: dict[tuple[int, int], Slot] = {}
        starts_down: dict[tuple[int, int], Slot] = {}
        for slot in slots:
            first = slot.cells[0]
            if slot.direction == "across":
                starts_across[first] = slot
            else:
                starts_down[first] = slot

        numbering = {}
        num = 1
        for r in range(self.size):
            for c in range(self.size):
                cell = (r, c)
                if cell in self.blacks:
                    continue
                needs_number = cell in starts_across or cell in starts_down
                if needs_number:
                    numbering[cell] = num
                    if cell in starts_across:
                        starts_across[cell].id = f"{num}A"
                    if cell in starts_down:
                        starts_down[cell].id = f"{num}D"
                    num += 1

        return numbering

    def _compute_crossings(self, slots: list[Slot]) -> None:
        """Compute crossing information between slots."""
        # Build cell -> (slot, position_in_slot) index
        cell_to_slot: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for i, slot in enumerate(slots):
            for pos, cell in enumerate(slot.cells):
                cell_to_slot.setdefault(cell, []).append((i, pos))

        # For each cell shared by two slots, record the crossing
        for cell, occupants in cell_to_slot.items():
            if len(occupants) == 2:
                (i, pos_i), (j, pos_j) = occupants
                slots[i].crossings.append(Crossing(
                    other_slot_id="",  # filled after numbering
                    self_pos=pos_i,
                    other_pos=pos_j,
                ))
                slots[j].crossings.append(Crossing(
                    other_slot_id="",
                    self_pos=pos_j,
                    other_pos=pos_i,
                ))

        # We'll fix up other_slot_id references after numbering.
        # For now, store slot index references and fix after.
        # Actually, let's store index refs and fix in build().
        # Re-approach: store index directly, fix after numbering.
        # For simplicity, store the slot index in other_slot_id temporarily.
        # Reset and redo with proper approach:
        for slot in slots:
            slot.crossings.clear()

        for cell, occupants in cell_to_slot.items():
            if len(occupants) == 2:
                (i, pos_i), (j, pos_j) = occupants
                slots[i].crossings.append(Crossing(
                    other_slot_id=str(j),  # temporary index
                    self_pos=pos_i,
                    other_pos=pos_j,
                ))
                slots[j].crossings.append(Crossing(
                    other_slot_id=str(i),  # temporary index
                    self_pos=pos_j,
                    other_pos=pos_i,
                ))

    def build(self) -> GridPattern:
        """Extract slots, crossings, numbering and return a GridPattern."""
        slots = self._extract_slots()
        self._compute_crossings(slots)
        numbering = self._assign_numbering(slots)

        # Fix up crossing references: replace index with slot id
        for slot in slots:
            for crossing in slot.crossings:
                other_idx = int(crossing.other_slot_id)
                crossing.other_slot_id = slots[other_idx].id

        self._pattern = GridPattern(
            size=self.size,
            blacks=frozenset(self.blacks),
            slots=slots,
            numbering=numbering,
        )
        return self._pattern

    @staticmethod
    def from_strings(rows: list[str]) -> "Grid":
        """Create a Grid from a list of row strings where '.' = black square."""
        size = len(rows)
        blacks = set()
        for r, row in enumerate(rows):
            for c, ch in enumerate(row):
                if ch == ".":
                    blacks.add((r, c))
        return Grid(size, blacks)


# --- Curated 5x5 patterns ---

MINI_PATTERNS: list[set[tuple[int, int]]] = [
    # Open grid: no blacks (like Jul 11)
    set(),

    # Two corner blacks (like Jul 07: .DOCK / HAND.)
    {(0, 0), (4, 4)},

    # Two opposite corners (like Jul 09: ASKS. / .PSST)
    {(0, 4), (4, 0)},

    # Diagonal pair top-right + bottom-left with extras (like Jul 03)
    {(0, 0), (0, 1), (1, 0), (3, 4), (4, 3), (4, 4)},

    # Staircase (like Jul 12: ..BPA / .HEAD / TORSO / LEGS. / CDS..)
    {(0, 0), (0, 1), (1, 0), (3, 4), (4, 3), (4, 4)},

    # Light L-shape (like Jul 10: .HOST / .OHIO / BUMPY / ASAP. / DENY.)
    {(0, 0), (1, 0), (3, 4), (4, 4)},

    # Single center column blocks (like Jul 13: .BEAM / DOSE.)
    {(0, 0), (4, 4)},

    # Diamond (like Jul 14: .DOG. / .YET.)
    {(0, 0), (0, 4), (4, 0), (4, 4)},

    # Asymmetric L (like Jul 16: ..HUB / MAY..)
    {(0, 0), (0, 1), (3, 4), (4, 3), (4, 4)},
]


# --- Curated 7x7 patterns (from NYT July 2023) ---

MIDI_PATTERNS: list[set[tuple[int, int]]] = [
    # Staircase (Jul 08): 12 blacks, word lengths 4-5-6-7
    {(0, 4), (0, 5), (0, 6), (1, 5), (1, 6), (2, 6),
     (4, 0), (5, 0), (5, 1), (6, 0), (6, 1), (6, 2)},

    # Center bar (Jul 15): 4 blacks, 3s and 7s
    {(3, 0), (3, 1), (3, 5), (3, 6)},

    # Diamond: 4 blacks, center cross
    {(0, 3), (3, 0), (3, 6), (6, 3)},

    # Vertical pillars: 4 blacks
    {(0, 3), (1, 3), (5, 3), (6, 3)},

    # Corner stairs: 5 blacks, mixed lengths
    {(0, 0), (0, 1), (5, 6), (6, 5), (6, 6)},

    # Center dot + corners: 5 blacks
    {(0, 6), (1, 6), (3, 3), (5, 0), (6, 0)},

    # Opposite corners: 5 blacks
    {(0, 0), (0, 1), (3, 3), (6, 5), (6, 6)},

    # Bookends: 6 blacks
    {(0, 0), (1, 0), (2, 0), (4, 6), (5, 6), (6, 6)},
]


def get_mini_patterns() -> list[GridPattern]:
    """Return all curated 5x5 mini patterns as built GridPatterns."""
    patterns = []
    for blacks in MINI_PATTERNS:
        grid = Grid(5, blacks)
        valid, _ = Grid.validate(5, blacks)
        if valid:
            patterns.append(grid.build())
    return patterns


def get_midi_patterns() -> list[GridPattern]:
    """Return all curated 7x7 patterns as built GridPatterns."""
    patterns = []
    for blacks in MIDI_PATTERNS:
        grid = Grid(7, blacks)
        valid, violations = Grid.validate(7, blacks)
        if valid:
            patterns.append(grid.build())
    return patterns


def generate_pattern(size: int, target_blacks: int = 0, max_attempts: int = 2000) -> GridPattern | None:
    """Generate a random valid grid pattern of the given size.

    Uses an incremental approach: place one symmetric pair of blacks at a time,
    checking validity after each placement. This avoids creating short words
    or disconnected regions.

    target_blacks: approximate number of black squares desired.
        If 0, uses a reasonable default based on size.
    """
    import random

    if target_blacks == 0:
        # Heuristic: scale with grid size
        if size <= 7:
            target_blacks = max(4, int(size * size * 0.12))
        else:
            target_blacks = int(size * size * 0.18)

    pairs_needed = target_blacks // 2

    for _ in range(max_attempts):
        blacks: set[tuple[int, int]] = set()

        # Build candidate positions (half of the grid for symmetry)
        candidates = []
        for r in range(size):
            for c in range(size):
                if r < size - 1 - r or (r == size - 1 - r and c <= size - 1 - c):
                    candidates.append((r, c))
        random.shuffle(candidates)

        # Incrementally place blacks, validating after each
        for r, c in candidates:
            if len(blacks) // 2 >= pairs_needed:
                break

            partner = (size - 1 - r, size - 1 - c)
            trial = blacks | {(r, c), partner}

            # Quick reject: would this create a word shorter than 3?
            if _creates_short_word(size, trial, r, c) or (
                (r, c) != partner and _creates_short_word(size, trial, *partner)
            ):
                continue

            # Quick reject: would this isolate a cell?
            if _isolates_cell(size, trial, r, c) or (
                (r, c) != partner and _isolates_cell(size, trial, *partner)
            ):
                continue

            blacks = trial

        # Final validation
        if len(blacks) >= 2:
            valid, _ = Grid.validate(size, blacks)
            if valid:
                grid = Grid(size, blacks)
                return grid.build()

    return None


def _creates_short_word(size: int, blacks: set, r: int, c: int) -> bool:
    """Check if adding a black at (r,c) creates any word shorter than 3."""
    # Check the horizontal word segments adjacent to (r,c)
    for dr, dc in [(0, 1), (1, 0)]:  # horizontal, vertical
        # Check segment before (r,c)
        length = 0
        nr, nc = r - dr, c - dc
        while 0 <= nr < size and 0 <= nc < size and (nr, nc) not in blacks:
            length += 1
            nr -= dr
            nc -= dc
        if 1 <= length <= 2:
            return True

        # Check segment after (r,c)
        length = 0
        nr, nc = r + dr, c + dc
        while 0 <= nr < size and 0 <= nc < size and (nr, nc) not in blacks:
            length += 1
            nr += dr
            nc += dc
        if 1 <= length <= 2:
            return True

    return False


def _isolates_cell(size: int, blacks: set, r: int, c: int) -> bool:
    """Check if placing a black at (r,c) would leave an adjacent cell
    with no across or no down word (isolated in one direction)."""
    for nr, nc in [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]:
        if not (0 <= nr < size and 0 <= nc < size) or (nr, nc) in blacks:
            continue
        # Check this neighbor has at least one horizontal and one vertical neighbor
        h_count = 0
        for dc in [-1, 1]:
            cc = nc + dc
            if 0 <= cc < size and (nr, cc) not in blacks:
                h_count += 1
        v_count = 0
        for dr in [-1, 1]:
            rr = nr + dr
            if 0 <= rr < size and (rr, nc) not in blacks:
                v_count += 1
        if h_count == 0 or v_count == 0:
            return True
    return False


def get_patterns(size: int) -> list[GridPattern]:
    """Get patterns for a given grid size. Uses curated patterns where
    available, generates random valid patterns as supplement."""
    if size == 5:
        return get_mini_patterns()
    elif size == 7:
        return get_midi_patterns()
    else:
        # Generate a few random patterns
        patterns = []
        for _ in range(10):
            p = generate_pattern(size)
            if p is not None:
                patterns.append(p)
            if len(patterns) >= 3:
                break
        return patterns
