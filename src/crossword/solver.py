"""Score-weighted CSP fill engine with AC-3 and branch-and-bound."""

import random
import time
from collections import deque
from dataclasses import dataclass, field
from itertools import groupby

from crossword.grid import GridPattern, Slot
from crossword.wordlist import WordList


@dataclass
class SolverConfig:
    top_k: int = 10
    timeout_seconds: float = 30.0
    min_word_score: int = 60
    min_diversity: int = 6  # minimum word differences between returned fills


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
        """Return up to top_k diverse fills, sorted by composite score descending."""
        slots = grid.slots
        if not slots:
            return []

        # Try Rust solver first
        rust_result = self._try_rust_solve(grid)
        if rust_result is not None:
            return rust_result

        slot_index = {slot.id: i for i, slot in enumerate(slots)}

        # Base domains (score-filtered, not shuffled yet)
        base_domains: list[list[tuple[str, int]]] = []
        for slot in slots:
            candidates = self.wordlist.candidates(slot.length)
            base_domains.append([
                (e.word, e.score)
                for e in candidates
                if e.score >= self.config.min_word_score
            ])

        arcs, neighbors = self._build_arcs(slots, slot_index)

        # AC-3 on base domains (do once, reuse across restarts)
        domain_words = [{w for w, _ in d} for d in base_domains]
        if not self._ac3(domain_words, arcs, neighbors, slots):
            return []
        for i in range(len(slots)):
            base_domains[i] = [(w, s) for w, s in base_domains[i] if w in domain_words[i]]

        # Multiple restarts with different shuffles
        pool: list[dict[str, str]] = []
        pool_scores: list[float] = []
        seen_keys: set[frozenset[str]] = set()
        global_start = time.time()
        num_restarts = max(1, self.config.top_k)
        fills_per_restart = 3
        time_per_restart = self.config.timeout_seconds / num_restarts

        for restart in range(num_restarts):
            if time.time() - global_start > self.config.timeout_seconds:
                break
            if len(pool) >= self.config.top_k * 5:
                break  # enough candidates in pool

            # Shuffle domains for this restart
            if restart == 0:
                # First restart: normal score-descending with tier shuffle
                domains = [self._shuffle_by_score(list(d)) for d in base_domains]
            else:
                # Later restarts: full random shuffle (weighted toward high scores)
                # This forces exploration of completely different regions
                domains = [self._weighted_shuffle(list(d)) for d in base_domains]

            results: list[dict[str, str]] = []
            scores: list[float] = []
            self._start_time = time.time()
            self._deadline = min(
                self._start_time + time_per_restart,
                global_start + self.config.timeout_seconds,
            )
            assignment = [None] * len(slots)

            self._backtrack(
                slots, domains, neighbors, slot_index,
                assignment, set(), results, scores, 0.0,
                max_results=fills_per_restart,
            )

            for i, r in enumerate(results):
                key = frozenset(r.values())
                if key not in seen_keys:
                    seen_keys.add(key)
                    pool.append(r)
                    pool_scores.append(scores[i])

        if not pool:
            return []

        return self._select_diverse(pool, pool_scores, grid, slot_index, slots)

    def _try_rust_solve(self, grid: GridPattern) -> list[Fill] | None:
        """Try to use the Rust solver. Returns None if not available."""
        try:
            import xword_solver
        except ImportError:
            return None

        slots = grid.slots
        slot_index = {slot.id: i for i, slot in enumerate(slots)}

        # Serialize wordlist: collect all words across needed lengths
        needed_lengths = {slot.length for slot in slots}
        words = []
        for length in needed_lengths:
            for entry in self.wordlist.candidates(length):
                words.append((entry.word, entry.score))

        # Serialize slots: (id, length, crossings_as_tuples)
        slot_data = []
        for slot in slots:
            crossings = []
            for c in slot.crossings:
                other_idx = slot_index[c.other_slot_id]
                crossings.append((other_idx, c.self_pos, c.other_pos))
            slot_data.append((slot.id, slot.length, crossings))

        # Call Rust solver
        raw_results = xword_solver.solve(
            words=words,
            slots=slot_data,
            top_k=self.config.top_k,
            timeout_secs=self.config.timeout_seconds,
            min_score=self.config.min_word_score,
            num_restarts=max(1, self.config.top_k),
            min_diversity=self.config.min_diversity,
        )

        if not raw_results:
            return None

        # Convert to Fill objects
        fills = []
        for raw_fill in raw_results:
            assignments = {}
            cell_letters = {}
            for slot_id, word, score in raw_fill:
                assignments[slot_id] = word
                slot = slots[slot_index[slot_id]]
                for pos, cell in enumerate(slot.cells):
                    cell_letters[cell] = word[pos]
            fill = Fill(
                grid=grid,
                assignments=assignments,
                cell_letters=cell_letters,
                score=self.score_fill_from_assignments(assignments),
            )
            fills.append(fill)

        fills.sort(key=lambda f: f.score.composite, reverse=True)
        return fills

    def _build_arcs(
        self, slots: list[Slot], slot_index: dict[str, int]
    ) -> tuple[list[tuple[int, int, int, int]], list[list[tuple[int, int, int]]]]:
        arcs = []
        neighbors: list[list[tuple[int, int, int]]] = [[] for _ in slots]
        for i, slot in enumerate(slots):
            for crossing in slot.crossings:
                j = slot_index[crossing.other_slot_id]
                arcs.append((i, crossing.self_pos, j, crossing.other_pos))
                neighbors[i].append((j, crossing.self_pos, crossing.other_pos))
        return arcs, neighbors

    def _select_diverse(
        self,
        pool: list[dict[str, str]],
        pool_scores: list[float],
        grid: GridPattern,
        slot_index: dict[str, int],
        slots: list[Slot],
    ) -> list[Fill]:
        """Greedily select diverse fills from pool."""
        if not pool:
            return []

        all_fills = []
        for assigns, total_score in zip(pool, pool_scores):
            cell_letters = {}
            for sid, word in assigns.items():
                slot = slots[slot_index[sid]]
                for pos, cell in enumerate(slot.cells):
                    cell_letters[cell] = word[pos]
            fill = Fill(
                grid=grid,
                assignments=assigns,
                cell_letters=cell_letters,
                score=self.score_fill_from_assignments(assigns),
            )
            all_fills.append(fill)

        # Greedy: start with best, then pick most-diverse-yet-good
        selected: list[Fill] = []
        remaining = list(range(len(all_fills)))

        best_idx = max(remaining, key=lambda i: all_fills[i].score.composite)
        selected.append(all_fills[best_idx])
        remaining.remove(best_idx)

        max_score = all_fills[best_idx].score.composite

        while len(selected) < self.config.top_k and remaining:
            best_candidate = None
            best_value = -1.0

            for i in remaining:
                candidate = all_fills[i]
                min_diff = min(
                    self._fill_distance(candidate, s) for s in selected
                )
                if min_diff < self.config.min_diversity:
                    continue
                score_norm = candidate.score.composite / max_score if max_score else 0
                diversity_norm = min_diff / (len(slots) * 2)
                value = 0.4 * score_norm + 0.6 * diversity_norm
                if value > best_value:
                    best_value = value
                    best_candidate = i

            if best_candidate is not None:
                selected.append(all_fills[best_candidate])
                remaining.remove(best_candidate)
            else:
                break

        selected.sort(key=lambda f: f.score.composite, reverse=True)
        return selected

    @staticmethod
    def _fill_distance(a: Fill, b: Fill) -> int:
        """Count words that differ between two fills."""
        words_a = set(a.assignments.values())
        words_b = set(b.assignments.values())
        return len(words_a - words_b) + len(words_b - words_a)

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
        max_results: int = 10,
    ) -> None:
        if time.time() > self._deadline:
            return

        if all(a is not None for a in assignment):
            result = {
                slots[i].id: assignment[i]
                for i in range(len(slots))
            }
            results.append(result)
            scores.append(current_score)
            return

        if len(results) >= max_results:
            return

        # MRV: pick unassigned slot with fewest viable candidates
        best_i = -1
        best_size = float("inf")
        for i in range(len(slots)):
            if assignment[i] is not None:
                continue
            # Build required letter constraints from assigned crossings
            required: dict[int, str] = {}
            for j, pos_i, pos_j in neighbors[i]:
                if assignment[j] is not None:
                    required[pos_i] = assignment[j][pos_j]
            if required:
                size = sum(
                    1 for w, _ in domains[i]
                    if w not in used_words and all(
                        w[p] == letter for p, letter in required.items()
                    )
                )
            else:
                size = len(domains[i])
            if size < best_size:
                best_size = size
                best_i = i

        if best_i == -1 or best_size == 0:
            return

        # Try candidates in score-descending order (already sorted)
        for word, wscore in domains[best_i]:
            if word in used_words:
                continue
            if not self._consistent(best_i, word, assignment, neighbors):
                continue

            assignment[best_i] = word
            used_words.add(word)

            if self._forward_check(best_i, word, slots, domains, neighbors, assignment, used_words):
                self._backtrack(
                    slots, domains, neighbors, slot_index,
                    assignment, used_words, results, scores,
                    current_score + wscore,
                    max_results=max_results,
                )

            assignment[best_i] = None
            used_words.discard(word)

            if len(results) >= max_results:
                return
            if time.time() > self._deadline:
                return

    def _consistent(
        self,
        slot_i: int,
        word: str,
        assignment: list[str | None],
        neighbors: list[list[tuple[int, int, int]]],
    ) -> bool:
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
        queue = deque(arcs)
        while queue:
            i, pos_i, j, pos_j = queue.popleft()
            if self._revise(domains, i, pos_i, j, pos_j):
                if not domains[i]:
                    return False
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
        supported_letters = {w[pos_j] for w in domains[j]}
        to_remove = {w for w in domains[i] if w[pos_i] not in supported_letters}
        if to_remove:
            domains[i] -= to_remove
            return True
        return False

    @staticmethod
    def _shuffle_by_score(items: list[tuple[str, int]]) -> list[tuple[str, int]]:
        """Shuffle items within same-score tiers, preserving score ordering."""
        result = []
        for _score, group in groupby(items, key=lambda x: x[1]):
            tier = list(group)
            random.shuffle(tier)
            result.extend(tier)
        return result

    @staticmethod
    def _weighted_shuffle(items: list[tuple[str, int]]) -> list[tuple[str, int]]:
        """Fully randomize order with score-based weighting.

        Higher-scored words are more likely to appear early, but any word
        can appear anywhere. This produces much more diverse starting points
        than tier-preserving shuffles.
        """
        if not items:
            return items
        # Use score as weight for random sorting
        result = list(items)
        random.shuffle(result)  # base randomization
        # Sort with jittered scores: score + random noise
        # The noise range controls diversity vs quality tradeoff
        max_score = max(s for _, s in result) if result else 1
        noise_range = max_score * 0.5  # 50% noise
        result.sort(
            key=lambda x: -(x[1] + random.uniform(0, noise_range)),
        )
        return result

    def score_fill(self, fill: Fill) -> FillScore:
        return self.score_fill_from_assignments(fill.assignments)

    def score_fill_from_assignments(self, assignments: dict[str, str]) -> FillScore:
        word_scores = [self.wordlist.score(w) for w in assignments.values()]
        if not word_scores:
            return FillScore()
        total = sum(word_scores)
        min_word = min(word_scores)
        all_letters = "".join(assignments.values())
        unique = len(set(all_letters))
        variety = unique / 26.0
        composite = total * 0.7 + min_word * 10 * 0.2 + variety * 100 * 0.1
        return FillScore(
            total=total,
            min_word=min_word,
            variety=variety,
            composite=composite,
        )
