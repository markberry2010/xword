"""Word database with scoring and fast indexed lookups."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WordEntry:
    word: str       # uppercase, e.g. "CHARM"
    score: int      # 1-100, higher = better fill quality
    tags: list[str] = field(default_factory=list)


class WordList:
    """Scored wordlist with indexed lookups by length and letter-position pattern.

    The constraint index (used only by the Python fallback solver) is built
    lazily on first use to save ~300MB of memory when the Rust solver handles
    constraint lookups internally.
    """

    def __init__(self, source_path: str | Path):
        self._words: dict[str, WordEntry] = {}
        self._by_length: dict[int, list[WordEntry]] = {}
        self._by_constraint: dict[tuple[int, int, str], set[str]] | None = None
        self._load(Path(source_path))

    def _load(self, path: Path) -> None:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(",")
            if len(parts) < 2:
                continue
            word = parts[0].strip().upper()
            try:
                score = int(parts[1].strip())
            except ValueError:
                continue
            if len(word) < 3:
                continue
            score = max(1, min(100, score))
            entry = WordEntry(word=word, score=score)
            self._words[word] = entry

        # Build length index only — constraint index is lazy
        for entry in self._words.values():
            length = len(entry.word)
            self._by_length.setdefault(length, []).append(entry)

        # Sort each length bucket by score descending
        for length in self._by_length:
            self._by_length[length].sort(key=lambda e: e.score, reverse=True)

    def _ensure_constraint_index(self) -> dict[tuple[int, int, str], set[str]]:
        """Build constraint index on first use."""
        if self._by_constraint is None:
            self._by_constraint = {}
            for entry in self._words.values():
                length = len(entry.word)
                for pos, letter in enumerate(entry.word):
                    key = (length, pos, letter)
                    self._by_constraint.setdefault(key, set()).add(entry.word)
        return self._by_constraint

    def candidates(
        self, length: int, pattern: dict[int, str] | None = None
    ) -> list[WordEntry]:
        """Return words of given length matching an optional pattern.

        Pattern is a dict of {position: letter}, e.g. {0: 'C', 3: 'R'}.
        Results sorted by score descending.
        """
        if not pattern:
            return list(self._by_length.get(length, []))

        # Intersect constraint index sets
        by_constraint = self._ensure_constraint_index()
        sets: list[set[str]] = []
        for pos, letter in pattern.items():
            key = (length, pos, letter.upper())
            constraint_set = by_constraint.get(key)
            if constraint_set is None:
                return []
            sets.append(constraint_set)

        # Intersect smallest-first for efficiency
        sets.sort(key=len)
        result = sets[0]
        for s in sets[1:]:
            result = result & s
            if not result:
                return []

        # Look up entries and sort by score
        entries = [self._words[w] for w in result if w in self._words]
        entries.sort(key=lambda e: e.score, reverse=True)
        return entries

    def score(self, word: str) -> int:
        entry = self._words.get(word.upper())
        return entry.score if entry else 0

    def contains(self, word: str) -> bool:
        return word.upper() in self._words

    def __len__(self) -> int:
        return len(self._words)
