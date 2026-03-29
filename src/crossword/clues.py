"""LLM clue generator for crossword puzzles."""

import json
import os

import anthropic

from crossword.grid import GridPattern
from crossword.puzzle import Clue
from crossword.solver import Fill


class ClueGenerator:
    """Generate NYT-style clues using an LLM."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.model = model
        if client is not None:
            self.client = client
        elif os.environ.get("ANTHROPIC_API_KEY"):
            self.client = anthropic.Anthropic()
        else:
            self.client = None

    def generate_clues(
        self,
        fill: Fill,
        grid: GridPattern,
        difficulty: str = "medium",
        theme: str | None = None,
    ) -> list[Clue]:
        """Generate clues for all entries in the fill."""
        if self.client is None:
            return self._placeholder_clues(fill, grid, difficulty)

        prompt = self._build_prompt(fill, grid, difficulty, theme)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            return self._parse_response(response.content[0].text, fill, grid, difficulty)
        except Exception:
            return self._placeholder_clues(fill, grid, difficulty)

    def _build_prompt(
        self,
        fill: Fill,
        grid: GridPattern,
        difficulty: str,
        theme: str | None,
    ) -> str:
        # Render the filled grid
        size = grid.size
        grid_lines = []
        for r in range(size):
            row = ""
            for c in range(size):
                if (r, c) in grid.blacks:
                    row += "."
                else:
                    row += fill.cell_letters.get((r, c), "?")
            grid_lines.append(row)

        difficulty_guide = {
            "easy": "Monday-level: straightforward definitions, common knowledge, no tricks.",
            "medium": "Wednesday-level: some misdirection, double meanings, light wordplay.",
            "hard": "Saturday-level: heavy misdirection, obscure angles, tricky wordplay.",
        }

        words_section = []
        for slot in sorted(grid.slots, key=lambda s: (s.direction != "across", s.id)):
            word = fill.assignments.get(slot.id, "???")
            direction = "Across" if slot.direction == "across" else "Down"
            num = slot.id[:-1]
            words_section.append(f"{num}-{direction}: {word} ({slot.length} letters)")

        theme_line = f"\nTheme: {theme}\nTry to connect clues to this theme where natural.\n" if theme else ""

        return f"""You are a witty NYT crossword clue writer. Write clues for a {size}x{size} mini crossword.

Difficulty: {difficulty} — {difficulty_guide.get(difficulty, difficulty_guide['medium'])}
{theme_line}
Guidelines:
- Clues should misdirect where possible. Exploit alternate meanings.
- Keep clues concise (2-8 words).
- Vary clue types: definitions, wordplay, fill-in-the-blank, pop culture refs.
- Every clue must be fair — a solver should say "aha!" not "that's wrong."
- For proper nouns, clue via the most well-known reference.
- Do NOT clue with "crossword staple" or self-referential meta-clues.

Grid:
{chr(10).join(grid_lines)}

Words to clue:
{chr(10).join(words_section)}

Respond with a JSON object mapping slot IDs to clue objects:
{{
    "1A": {{"clue": "Your clue text", "alternatives": ["alt clue 1", "alt clue 2"]}},
    "2D": {{"clue": "Your clue text", "alternatives": ["alt clue 1", "alt clue 2"]}},
    ...
}}

Write ONLY the JSON, no other text."""

    def _parse_response(
        self,
        text: str,
        fill: Fill,
        grid: GridPattern,
        difficulty: str,
    ) -> list[Clue]:
        """Parse LLM response into Clue objects."""
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            return self._placeholder_clues(fill, grid, difficulty)

        clues = []
        for slot in grid.slots:
            word = fill.assignments.get(slot.id, "???")
            clue_data = data.get(slot.id, {})
            if isinstance(clue_data, str):
                clue_text = clue_data
                alternatives = []
            else:
                clue_text = clue_data.get("clue", f"Clue for {word}")
                alternatives = clue_data.get("alternatives", [])
            clues.append(Clue(
                slot_id=slot.id,
                word=word,
                clue_text=clue_text,
                difficulty=difficulty,
                alternatives=alternatives,
            ))
        return clues

    def _placeholder_clues(
        self, fill: Fill, grid: GridPattern, difficulty: str
    ) -> list[Clue]:
        """Generate placeholder clues when LLM is not available."""
        clues = []
        for slot in grid.slots:
            word = fill.assignments.get(slot.id, "???")
            clues.append(Clue(
                slot_id=slot.id,
                word=word,
                clue_text=f"[{word}]",
                difficulty=difficulty,
            ))
        return clues
