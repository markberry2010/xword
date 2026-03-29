"""LLM clue generator for crossword puzzles."""

import json
import os

import anthropic

from crossword.grid import GridPattern
from crossword.puzzle import Clue
from crossword.solver import Fill

CLUE_SYSTEM_PROMPT = """\
You are a top-tier NYT crossword clue writer with the dry wit of a New Yorker \
cartoon and the precision of Will Shortz. Your clues are famous for making \
solvers groan, laugh, and slap their foreheads."""

CLUE_USER_PROMPT = """\
Write clues for this {size}x{size} crossword puzzle.

## Difficulty: {difficulty}

{difficulty_guide}

## Clue-writing rules

1. **Misdirect.** The best clues point the solver's mind in the wrong direction.
   - BARK: "It comes from a trunk" (tree trunk? car trunk? No — dog!)
   - CRUSH: "Orange ___" (the drink, not the emotion)
   - MARS: "It has two moons" (planet, not the candy bar)

2. **Concise.** 2-6 words ideal. Never exceed 8 words. Shorter = harder.

3. **Vary clue types** across the puzzle:
   - Straight definition: "Venetian transport" → GONDOLA
   - Misdirection: "Suit material?" → HEART (playing cards, not fabric)
   - Fill-in-the-blank: "___ and cheese" → MAC
   - Pop culture: "Frozen queen" → ELSA
   - Wordplay/pun: "Band with a sting?" → WASP (use ? to signal wordplay)
   - Cross-reference: "With 5-Down, a classic pair" (when entries relate)

4. **Every clue must be fair.** The solver should say "aha!" not "that's wrong."
   The clue must have a defensible, unambiguous path to the answer.

5. **Question marks signal wordplay.** Use ? when the clue involves a pun, \
double meaning, or non-literal interpretation. Do NOT use ? for straight clues.

6. **For proper nouns**, clue via the most widely known reference. Prefer \
pop culture over obscure historical figures.

## What NOT to do

BAD clues (generic, boring, or unfair):
- "A type of animal" → too vague, could be anything
- "Musical instrument with strings" → too long, no misdirection
- "Crossword staple" → self-referential, lazy
- "See dictionary" → useless
- "Famous person" → not a real clue
- Defining PEACE as "Opposite of war" → obvious, no craft

GOOD versions of the same:
- TIGER: "Cereal box mascot" (Tony the Tiger — misdirects from the animal)
- CELLO: "Yo-Yo Ma's instrument" (specific, evocative)
- PEACE: "Nobel category" (misdirects toward prizes, not the concept)

## Grid

```
{grid_text}
```

## Words to clue

{words_section}
{theme_line}
## Response format

Return ONLY a JSON object. No markdown, no explanation:
{{
    "1A": {{"clue": "Your clue text", "alternatives": ["alt 1", "alt 2"]}},
    "2D": {{"clue": "Your clue text", "alternatives": ["alt 1", "alt 2"]}}
}}

Each entry needs one primary clue and two alternatives (different angles/types)."""

DIFFICULTY_GUIDES = {
    "easy": """\
**Monday-level.** Straightforward but not boring. The solver should be able to \
get most clues without crosses, but still feel clever.

Real NYT Mini clues at this level:
- CUBE: "Shape of sugar or ice"
- DOCK: "Boat loading area"
- SLEET: "Freezing rain"
- HOST: "Game show leader"
- CHEF: "Many a cookbook author"
- CHILL: "Laid-back"
- ELITE: "Cream of the crop"
- HADES: "Greek underworld"
- INDEX: "Pointer finger"
- GRAIN: "Crop such as wheat or rice"

Avoid: obscure references, heavy wordplay, ? clues (use sparingly).""",

    "medium": """\
**Wednesday-level.** Misdirection and double meanings are expected. The solver \
should need some crosses to confirm answers.

Real NYT Mini clues at this level:
- DRAMA: "Result of inviting an ex to your wedding, maybe"
- OHIO: "State with cities named Lisbon, Milan, London, Moscow and Athens"
- RHYME: "Tissue or 'Miss you,' for this clue?"
- TORUS: "Shape of an inner tube"
- BUMPY: "Like rides on pothole-strewn roads"
- DONUT: "Some spell this with an 'ugh' in the middle"
- TIMER: "Stopwatch, e.g."
- ARMS: "What tank tops expose"
- HAND: "It makes waves"
- DAVID: "Renaissance masterpiece that stands at 17 feet tall"

Mix: ~half straight definitions, ~half misdirection/wordplay.""",

    "hard": """\
**Saturday-level.** Heavy misdirection, obscure angles, minimal giveaways. \
The solver should struggle without crosses.

Real NYT Mini clues at this level:
- MAY: "Month that's a vegetable spelled backward"
- TUDUM: "Official spelling of the Netflix opening sound"
- PSST: "[Hey you, over here!]"
- DOG: "On the Internet, nobody knows you're a ___"
- UHOH: "Equivalent to the Grimacing Face emoji"
- KARMA: "Cosmic comeuppance"
- NOFUN: "Like a party pooper"
- FOMO: "'Everyone is having fun without me' feeling, for short"
- BEAM: "Smile wide"
- SURF: "Ride the wave"

Nearly all clues should misdirect. Use ? liberally. Short clues preferred.""",
}


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
                system=CLUE_SYSTEM_PROMPT,
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
        size = grid.size
        grid_text = "\n".join(
            "".join(
                "." if (r, c) in grid.blacks
                else fill.cell_letters.get((r, c), "?")
                for c in range(size)
            )
            for r in range(size)
        )

        words_section = []
        for slot in sorted(grid.slots, key=lambda s: (s.direction != "across", s.id)):
            word = fill.assignments.get(slot.id, "???")
            direction = "Across" if slot.direction == "across" else "Down"
            num = slot.id[:-1]
            words_section.append(f"{num}-{direction}: {word} ({slot.length} letters)")

        theme_line = (
            f"\n**Theme: {theme}**\nWeave the theme into clues where it fits naturally. "
            "Not every clue needs to reference the theme.\n"
            if theme else ""
        )

        difficulty_guide = DIFFICULTY_GUIDES.get(difficulty, DIFFICULTY_GUIDES["medium"])

        return CLUE_USER_PROMPT.format(
            size=size,
            difficulty=difficulty,
            difficulty_guide=difficulty_guide,
            grid_text=grid_text,
            words_section="\n".join(words_section),
            theme_line=theme_line,
        )

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
