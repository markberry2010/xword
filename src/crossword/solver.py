"""Score-weighted CSP fill engine with AC-3 and branch-and-bound."""

import random
import time
from collections import deque
from dataclasses import dataclass, field

from crossword.grid import GridPattern, Slot
from crossword.wordlist import WordList


@dataclass
class SolverConfig:
    top_k: int = 10
    timeout_seconds: float = 30.0
    min_word_score: int = 30
    beam_width: int | None = None  # optional: limit candidates per slot
    randomize: bool = True  # shuffle candidates within same score tier


@dataclass
class FillScore:
    total: float = 0.0
    min_word: float = 0.0
    variety: float = 0.0
    composite: float = 0.0


@dataclass
class Fill:
    grid: GridPattern
    assignments: dict[str, str]                 # slot_id -> word
    cell_letters: dict[tuple[int, int], str]    # (row, col) -> letter
    score: FillScore = field(default_factory=FillScore)


class Solver:
    """CSP solver: backtracking + AC-3 + branch-and-bound for crossword fill."""

    def __init__(self, wordlist: WordList, config: SolverConfig | None = None):
        self.wordlist = wordlist
        self.config = config or SolverConfig()

    def solve(self, grid: GridPattern) -> list[Fill]:
        """Return up to top_k fills, sorted by composite score descending."""
        slots = grid.slots
        if not slots:
            return []

        # Build slot index for fast lookup
        slot_index = {slot.id: i for i, slot in enumerate(slots)}

        # Initialize domains: list of (word, score) per slot
        domains: list[list[tuple[str, int]]] = []
        for slot in slots:
            candidates = self.wordlist.candidates(slot.length)
            filtered = [
                (e.word, e.score)
                for e in candidates
                if e.score >= self.config.min_word_score
            ]
            if self.config.randomize:
                # Shuffle within same-score tiers for variety between runs
                filtered = self._shuffle_by_score(filtered)
            if self.config.beam_width:
                filtered = filtered[: self.config.beam_width]
            domains.append(filtered)

        # Build crossing structure as (slot_i, pos_i, slot_j, pos_j)
        arcs: list[tuple[int, int, int, int]] = []
        for i, slot in enumerate(slots):
            for crossing in slot.crossings:
                j = slot_index[crossing.other_slot_id]
                arcs.append((i, crossing.self_pos, j, crossing.other_pos))

        # Build adjacency: for each slot, which other slots does it cross?
        neighbors: list[list[tuple[int, int, int]]] = [[] for _ in slots]
        for i, pos_i, j, pos_j in arcs:
            neighbors[i].append((j, pos_i, pos_j))

        # Initial AC-3
        domain_words: list[set[str]] = [
            {w for w, _ in d} for d in domains
        ]
        if not self._ac3(domain_words, arcs, neighbors, slots):
            return []

        # Rebuild scored domains after AC-3 filtering
        for i in range(len(slots)):
            domains[i] = [(w, s) for w, s in domains[i] if w in domain_words[i]]

        # Backtracking search
        results: list[dict[str, str]] = []
        scores: list[float] = []
        self._start_time = time.time()
        assignment: list[str | None] = [None] * len(slots)
        used_words: set[str] = set()

        self._backtrack(
            slots, domains, neighbors, slot_index,
            assignment, used_words, results, scores, 0.0,
        )

        # Build Fill objects
        fills = []
        for assigns, total_score in zip(results, scores):
            cell_letters = {}
            assignment_dict = {}
            for sid, word in assigns.items():
                slot = slots[slot_index[sid]]
                assignment_dict[sid] = word
                for pos, cell in enumerate(slot.cells):
                    cell_letters[cell] = word[pos]
            fill = Fill(
                grid=grid,
                assignments=assignment_dict,
                cell_letters=cell_letters,
                score=self.score_fill_from_assignments(assignment_dict),
            )
            fills.append(fill)

        fills.sort(key=lambda f: f.score.composite, reverse=True)
        return fills

    def _backtrack(
        self,
        slots: list[Slot],
        domains: list[list[tuple[str, int]]],
        neighbors: list[list[tuple[int, int, int]]],
        slot_index: dict[str, int],
        assignment: list[str | None],
        used_words: set[str],
        results: list[dict[str, str]],
        scores: list[float],
        current_score: float,
    ) -> None:
        # Timeout check
        if time.time() - self._start_time > self.config.timeout_seconds:
            return

        # All slots assigned?
        if all(a is not None for a in assignment):
            result = {
                slots[i].id: assignment[i]
                for i in range(len(slots))
            }
            results.append(result)
            scores.append(current_score)
            return

        # Have enough results?
        if len(results) >= self.config.top_k:
            return

        # MRV: pick unassigned slot with smallest domain
        best_i = -1
        best_size = float("inf")
        for i in range(len(slots)):
            if assignment[i] is None:
                size = sum(
                    1 for w, _ in domains[i]
                    if w not in used_words and self._consistent(
                        i, w, assignment, neighbors
                    )
                )
                if size < best_size:
                    best_size = size
                    best_i = i

        if best_i == -1 or best_size == 0:
            return

        # Branch-and-bound: compute optimistic bound
        if results:
            worst_result_score = min(scores)
            if len(results) >= self.config.top_k:
                optimistic = current_score + sum(
                    max((s for w, s in domains[i] if w not in used_words), default=0)
                    for i in range(len(slots))
                    if assignment[i] is None
                )
                if optimistic <= worst_result_score:
                    return

        # Try candidates in score-descending order
        for word, wscore in domains[best_i]:
            if word in used_words:
                continue
            if not self._consistent(best_i, word, assignment, neighbors):
                continue

            # Assign
            assignment[best_i] = word
            used_words.add(word)

            # Forward check: ensure all unassigned neighbors have valid options
            if self._forward_check(best_i, word, slots, domains, neighbors, assignment, used_words):
                self._backtrack(
                    slots, domains, neighbors, slot_index,
                    assignment, used_words, results, scores,
                    current_score + wscore,
                )

            # Undo
            assignment[best_i] = None
            used_words.discard(word)

            if len(results) >= self.config.top_k:
                return
            if time.time() - self._start_time > self.config.timeout_seconds:
                return

    def _consistent(
        self,
        slot_i: int,
        word: str,
        assignment: list[str | None],
        neighbors: list[list[tuple[int, int, int]]],
    ) -> bool:
        """Check if assigning word to slot_i is consistent with current assignment."""
        for j, pos_i, pos_j in neighbors[slot_i]:
            other_word = assignment[j]
            if other_word is not None:
                if word[pos_i] != other_word[pos_j]:
                    return False
        return True

    def _forward_check(
        self,
        slot_i: int,
        word: str,
        slots: list[Slot],
        domains: list[list[tuple[str, int]]],
        neighbors: list[list[tuple[int, int, int]]],
        assignment: list[str | None],
        used_words: set[str],
    ) -> bool:
        """Check that all unassigned neighbors still have at least one valid candidate."""
        for j, pos_i, pos_j in neighbors[slot_i]:
            if assignment[j] is not None:
                continue
            required_letter = word[pos_i]
            has_option = False
            for w, _ in domains[j]:
                if w in used_words:
                    continue
                if w[pos_j] != required_letter:
                    continue
                # Also check consistency with other assigned neighbors
                if self._consistent(j, w, assignment, neighbors):
                    has_option = True
                    break
            if not has_option:
                return False
        return True

    def _ac3(
        self,
        domains: list[set[str]],
        arcs: list[tuple[int, int, int, int]],
        neighbors: list[list[tuple[int, int, int]]],
        slots: list[Slot],
    ) -> bool:
        """Enforce arc consistency. Returns False if any domain becomes empty."""
        queue = deque(arcs)
        while queue:
            i, pos_i, j, pos_j = queue.popleft()
            if self._revise(domains, i, pos_i, j, pos_j):
                if not domains[i]:
                    return False
                # Add arcs from neighbors of i (excluding j)
                for k, pos_ik, pos_ki in neighbors[i]:
                    if k != j:
                        queue.append((k, pos_ki, i, pos_ik))
        return True

    def _revise(
        self,
        domains: list[set[str]],
        i: int, pos_i: int,
        j: int, pos_j: int,
    ) -> bool:
        """Remove values from domain[i] that have no support in domain[j]."""
        # Collect letters at pos_j that exist in domain[j]
        supported_letters = {w[pos_j] for w in domains[j]}
        to_remove = {w for w in domains[i] if w[pos_i] not in supported_letters}
        if to_remove:
            domains[i] -= to_remove
            return True
        return False

    @staticmethod
    def _shuffle_by_score(items: list[tuple[str, int]]) -> list[tuple[str, int]]:
        """Shuffle items within same-score tiers, preserving score ordering."""
        from itertools import groupby
        result = []
        for _score, group in groupby(items, key=lambda x: x[1]):
            tier = list(group)
            random.shuffle(tier)
            result.extend(tier)
        return result

    def score_fill(self, fill: Fill) -> FillScore:
        """Score a complete fill."""
        return self.score_fill_from_assignments(fill.assignments)

    def score_fill_from_assignments(self, assignments: dict[str, str]) -> FillScore:
        word_scores = [self.wordlist.score(w) for w in assignments.values()]
        if not word_scores:
            return FillScore()
        total = sum(word_scores)
        min_word = min(word_scores)
        # Variety: count unique letters
        all_letters = "".join(assignments.values())
        unique = len(set(all_letters))
        variety = unique / 26.0  # 0-1 scale
        composite = total * 0.7 + min_word * 10 * 0.2 + variety * 100 * 0.1
        return FillScore(
            total=total,
            min_word=min_word,
            variety=variety,
            composite=composite,
        )
