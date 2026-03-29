"""Puzzle assembly and output formats."""

import json
from dataclasses import dataclass, field
from datetime import datetime

from crossword.grid import Grid, GridPattern, Slot


@dataclass
class Clue:
    slot_id: str
    word: str
    clue_text: str
    difficulty: str = "medium"
    alternatives: list[str] = field(default_factory=list)


@dataclass
class PuzzleMetadata:
    size: int = 5
    difficulty: str = "medium"
    theme: str | None = None
    generated_at: datetime = field(default_factory=datetime.now)
    generator_version: str = "0.1.0"


@dataclass
class Puzzle:
    grid: GridPattern
    fill: "Fill"  # from solver
    clues: list[Clue]
    metadata: PuzzleMetadata = field(default_factory=PuzzleMetadata)

    def to_text(self, title: str = "", author: str = "") -> str:
        """Render in Across Puzzle V2 format."""
        lines = ["<ACROSS PUZZLE V2>"]
        lines.append("<TITLE>")
        lines.append(f"    {title or 'Crossword Puzzle'}")
        lines.append("<AUTHOR>")
        lines.append(f"    {author or 'Crossword Generator'}")
        lines.append("<COPYRIGHT>")
        lines.append(f"    {self.metadata.generated_at.year}")
        lines.append("<SIZE>")
        lines.append(f"    {self.grid.size}x{self.grid.size}")
        lines.append("<GRID>")

        # Build grid rows
        size = self.grid.size
        for r in range(size):
            row = ""
            for c in range(size):
                if (r, c) in self.grid.blacks:
                    row += "."
                else:
                    row += self.fill.cell_letters.get((r, c), "?")
            lines.append(f"    {row}")

        # Across clues
        lines.append("<ACROSS>")
        across_clues = sorted(
            [cl for cl in self.clues if cl.slot_id.endswith("A")],
            key=lambda cl: int(cl.slot_id[:-1]),
        )
        for cl in across_clues:
            lines.append(f"    {cl.clue_text}")

        # Down clues
        lines.append("<DOWN>")
        down_clues = sorted(
            [cl for cl in self.clues if cl.slot_id.endswith("D")],
            key=lambda cl: int(cl.slot_id[:-1]),
        )
        for cl in down_clues:
            lines.append(f"    {cl.clue_text}")

        return "\n".join(lines) + "\n"

    def to_json(self) -> dict:
        """JSON representation."""
        size = self.grid.size
        grid_rows = []
        for r in range(size):
            row = ""
            for c in range(size):
                if (r, c) in self.grid.blacks:
                    row += "."
                else:
                    row += self.fill.cell_letters.get((r, c), "?")
            grid_rows.append(row)

        clue_data = {}
        for cl in self.clues:
            clue_data[cl.slot_id] = {
                "word": cl.word,
                "clue": cl.clue_text,
                "difficulty": cl.difficulty,
                "alternatives": cl.alternatives,
            }

        return {
            "size": size,
            "grid": grid_rows,
            "clues": clue_data,
            "metadata": {
                "difficulty": self.metadata.difficulty,
                "theme": self.metadata.theme,
                "generated_at": self.metadata.generated_at.isoformat(),
                "version": self.metadata.generator_version,
            },
        }

    def to_json_str(self) -> str:
        return json.dumps(self.to_json(), indent=2)

    def display(self) -> str:
        """Pretty-print the puzzle for terminal display."""
        size = self.grid.size
        lines = []

        # Grid with box drawing
        border = "+" + "---+" * size
        lines.append(border)
        for r in range(size):
            row = "|"
            for c in range(size):
                if (r, c) in self.grid.blacks:
                    row += "███|"
                else:
                    letter = self.fill.cell_letters.get((r, c), " ")
                    num = self.grid.numbering.get((r, c))
                    if num is not None:
                        row += f" {letter} |"
                    else:
                        row += f" {letter} |"
            lines.append(row)
            lines.append(border)

        lines.append("")

        # Clues
        across_clues = sorted(
            [cl for cl in self.clues if cl.slot_id.endswith("A")],
            key=lambda cl: int(cl.slot_id[:-1]),
        )
        down_clues = sorted(
            [cl for cl in self.clues if cl.slot_id.endswith("D")],
            key=lambda cl: int(cl.slot_id[:-1]),
        )

        lines.append("ACROSS")
        for cl in across_clues:
            num = cl.slot_id[:-1]
            lines.append(f"  {num}. {cl.clue_text}")

        lines.append("")
        lines.append("DOWN")
        for cl in down_clues:
            num = cl.slot_id[:-1]
            lines.append(f"  {num}. {cl.clue_text}")

        return "\n".join(lines)


def parse_puzzle_text(text: str) -> dict:
    """Parse an Across Puzzle V2 format file into components."""
    result = {
        "title": "",
        "author": "",
        "copyright": "",
        "size": "",
        "grid_rows": [],
        "across_clues": [],
        "down_clues": [],
    }

    section = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("<") and stripped.endswith(">"):
            tag = stripped[1:-1].upper()
            if tag == "ACROSS PUZZLE V2":
                continue
            section = tag
            continue

        if not stripped:
            continue

        if section == "TITLE":
            result["title"] = stripped
        elif section == "AUTHOR":
            result["author"] = stripped
        elif section == "COPYRIGHT":
            result["copyright"] = stripped
        elif section == "SIZE":
            result["size"] = stripped
        elif section == "GRID":
            result["grid_rows"].append(stripped)
        elif section == "ACROSS":
            result["across_clues"].append(stripped)
        elif section == "DOWN":
            result["down_clues"].append(stripped)

    return result
