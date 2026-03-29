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


def get_mini_patterns() -> list[GridPattern]:
    """Return all curated 5x5 mini patterns as built GridPatterns."""
    patterns = []
    for blacks in MINI_PATTERNS:
        grid = Grid(5, blacks)
        valid, _ = Grid.validate(5, blacks)
        if valid:
            patterns.append(grid.build())
    return patterns
