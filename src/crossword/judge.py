"""LLM fill reranker using Anthropic API."""

import json
import os

import anthropic

from crossword.grid import GridPattern
from crossword.solver import Fill


class FillJudge:
    """Evaluate and rank candidate fills using an LLM."""

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

    def rank_fills(self, fills: list[Fill], grid: GridPattern) -> list[Fill]:
        """Rank fills by quality. Returns fills sorted best-first.

        Falls back to score-based ordering if no API client available.
        """
        if not fills:
            return []

        if self.client is None or len(fills) == 1:
            return sorted(fills, key=lambda f: f.score.composite, reverse=True)

        prompt = self._build_prompt(fills, grid)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )
            ranking = self._parse_response(response.content[0].text, fills)
            return ranking
        except Exception:
            # Fallback to score-based ranking
            return sorted(fills, key=lambda f: f.score.composite, reverse=True)

    def _build_prompt(self, fills: list[Fill], grid: GridPattern) -> str:
        parts = [
            "You are an expert NYT crossword constructor evaluating candidate fills "
            "for a mini crossword puzzle.\n\n"
            "For each fill below, evaluate on:\n"
            "1. Entry Quality: Are these good, lively crossword words?\n"
            "2. Variety: Good mix of word types and topics?\n"
            "3. Freshness: Feels current, not stale?\n"
            "4. Clueability: Can you write fun, misdirecting clues?\n"
            "5. Red flags: Offensive combos, unintended meanings?\n\n"
            "Respond with a JSON object: {\"ranking\": [1-indexed fill numbers best to worst], "
            "\"reasoning\": \"brief explanation\"}\n\n"
        ]

        for i, fill in enumerate(fills):
            parts.append(f"--- Fill {i + 1} ---")
            parts.append(self._format_fill(fill, grid))
            parts.append("")

        return "\n".join(parts)

    def _format_fill(self, fill: Fill, grid: GridPattern) -> str:
        size = grid.size
        lines = []

        # Render grid
        for r in range(size):
            row = ""
            for c in range(size):
                if (r, c) in grid.blacks:
                    row += "."
                else:
                    row += fill.cell_letters.get((r, c), "?")
            lines.append(row)

        # Word lists
        across = []
        down = []
        for slot in grid.slots:
            word = fill.assignments.get(slot.id, "???")
            if slot.direction == "across":
                across.append(f"{slot.id}: {word}")
            else:
                down.append(f"{slot.id}: {word}")
        lines.append(f"Across: {', '.join(across)}")
        lines.append(f"Down: {', '.join(down)}")
        lines.append(f"Score: {fill.score.composite:.0f}")

        return "\n".join(lines)

    def _parse_response(self, text: str, fills: list[Fill]) -> list[Fill]:
        """Parse LLM response to extract ranking."""
        try:
            # Try to extract JSON from response
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
            ranking = data.get("ranking", [])
            # Convert 1-indexed to 0-indexed
            return [fills[i - 1] for i in ranking if 1 <= i <= len(fills)]
        except (ValueError, json.JSONDecodeError, IndexError):
            return sorted(fills, key=lambda f: f.score.composite, reverse=True)
