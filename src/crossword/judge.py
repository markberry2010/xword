"""LLM fill reranker using parallel independent scoring."""

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import anthropic

from crossword.grid import GridPattern
from crossword.solver import Fill

log = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """\
You are an expert NYT crossword constructor and editor evaluating candidate \
grid fills. You have decades of experience constructing and editing puzzles \
for major outlets.

You evaluate BOTH the across and down words — every word in the grid matters."""

SCORE_FILL_PROMPT = """\
Rate this crossword fill for a {size}x{size} grid.

```
{grid_text}
```
All words: {all_words}

Score each criterion 1-10:

**Entry Quality**: Are ALL words real, recognizable words or well-known proper \
nouns? Severely penalize:
- Non-words or gibberish (SSSSS, TIETO, ARTIS)
- Space-stripped phrases that aren't standalone words (NOTME, IFIDO, EATAT, IMAKE)
- Obscure abbreviations (SRSLY, RETAG)
- Crossword-ese nobody enjoys (ESNE, OLEO, ANOA)
A single bad word can ruin an otherwise good fill.

**Variety**: Good mix of word types? Look for:
- Mix of nouns, verbs, adjectives, proper nouns
- Different topic areas (not all sports, not all names)
- At most 2 proper nouns per fill
- Interesting letter variety

**Clueability**: Can you imagine writing fun, misdirecting clues? Best words have:
- Multiple meanings (CRUSH = romantic interest OR to destroy)
- Surprising alternate angles (BARK = tree OR dog)
- Pop culture potential (ELSA = Frozen OR Pataky)
Words with only one narrow meaning score low.

**Freshness**: Does the fill feel current and engaging?
- Modern words and references score high (EMOJI, TESLA, PODCAST)
- Stale but valid words are okay (STEER, RATIO)
- Dated or stuffy words score low

**Red flags**: Any problems?
- Offensive words or unfortunate adjacencies
- Unintended words formed by adjacent letters

Respond with ONLY this JSON:
{{"entry_quality": N, "variety": N, "clueability": N, "freshness": N, \
"red_flags": "none or description", "weak_words": [...], \
"strong_words": [...], "overall": N}}"""


@dataclass
class JudgeScore:
    fill_index: int
    entry_quality: int = 0
    variety: int = 0
    clueability: int = 0
    freshness: int = 0
    red_flags: str = "none"
    weak_words: list[str] | None = None
    strong_words: list[str] | None = None
    overall: int = 0


class FillJudge:
    """Score and rank fills using parallel independent LLM evaluations."""

    def __init__(
        self,
        client: anthropic.Anthropic | None = None,
        model: str = "claude-haiku-4-5-20251001",
        max_workers: int = 5,
    ):
        self.model = model
        self.max_workers = max_workers
        if client is not None:
            self.client = client
        elif os.environ.get("ANTHROPIC_API_KEY"):
            self.client = anthropic.Anthropic()
        else:
            self.client = None

    def rank_fills(self, fills: list[Fill], grid: GridPattern) -> list[Fill]:
        """Score each fill independently in parallel, return sorted best-first."""
        if not fills:
            return []

        if self.client is None:
            return sorted(fills, key=lambda f: f.score.composite, reverse=True)

        scores = self._score_all(fills, grid)

        # Sort by LLM overall score descending, break ties with solver composite
        ranked_indices = sorted(
            range(len(fills)),
            key=lambda i: (scores[i].overall, fills[i].score.composite),
            reverse=True,
        )

        ranked = [fills[i] for i in ranked_indices]

        # Log top pick reasoning
        if ranked_indices:
            best = scores[ranked_indices[0]]
            log.info(
                "Judge picked fill %d (overall=%d, entry=%d, clue=%d) "
                "strong=%s weak=%s",
                ranked_indices[0] + 1,
                best.overall,
                best.entry_quality,
                best.clueability,
                best.strong_words,
                best.weak_words,
            )

        return ranked

    def _score_all(
        self, fills: list[Fill], grid: GridPattern
    ) -> list[JudgeScore]:
        """Score all fills in parallel. Returns one JudgeScore per fill."""
        scores = [JudgeScore(fill_index=i) for i in range(len(fills))]

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._score_one, fill, grid, i): i
                for i, fill in enumerate(fills)
            }
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    scores[idx] = future.result()
                except Exception:
                    # Keep default zero score on failure
                    pass

        return scores

    def _score_one(
        self, fill: Fill, grid: GridPattern, index: int
    ) -> JudgeScore:
        """Score a single fill via LLM."""
        prompt = self._build_single_prompt(fill, grid)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=512,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text
        return self._parse_single_response(text, index)

    def _build_single_prompt(self, fill: Fill, grid: GridPattern) -> str:
        size = grid.size
        grid_text = "\n".join(
            "".join(
                "." if (r, c) in grid.blacks
                else fill.cell_letters.get((r, c), "?")
                for c in range(size)
            )
            for r in range(size)
        )
        all_words = ", ".join(sorted(fill.assignments.values()))

        return SCORE_FILL_PROMPT.format(
            size=size,
            grid_text=grid_text,
            all_words=all_words,
        )

    def _parse_single_response(self, text: str, index: int) -> JudgeScore:
        """Parse a single-fill JSON score response."""
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
            return JudgeScore(
                fill_index=index,
                entry_quality=data.get("entry_quality", 0),
                variety=data.get("variety", 0),
                clueability=data.get("clueability", 0),
                freshness=data.get("freshness", 0),
                red_flags=data.get("red_flags", "none"),
                weak_words=data.get("weak_words"),
                strong_words=data.get("strong_words"),
                overall=data.get("overall", 0),
            )
        except (ValueError, json.JSONDecodeError):
            return JudgeScore(fill_index=index)
