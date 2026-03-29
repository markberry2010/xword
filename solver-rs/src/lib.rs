use pyo3::prelude::*;
use rand::seq::SliceRandom;
use std::collections::{HashMap, HashSet};
use std::time::Instant;

#[derive(Clone)]
struct Crossing {
    other_slot: usize,
    self_pos: usize,
    other_pos: usize,
}

struct Slot {
    id: String,
    length: usize,
    crossings: Vec<Crossing>,
}

/// Words stored as byte arrays for fast comparison.
struct WordBank {
    by_length: HashMap<usize, Vec<(Vec<u8>, i32)>>,
    /// (length, position, letter) -> bitmap of word indices (true = has that letter there)
    index: HashMap<(usize, usize, u8), Vec<bool>>,
}

impl WordBank {
    fn new(words: Vec<(String, i32)>, min_score: i32) -> Self {
        let mut by_length: HashMap<usize, Vec<(Vec<u8>, i32)>> = HashMap::new();
        for (text, score) in words {
            if score < min_score || text.len() < 3 {
                continue;
            }
            let bytes = text.into_bytes();
            let length = bytes.len();
            by_length.entry(length).or_default().push((bytes, score));
        }
        for bucket in by_length.values_mut() {
            bucket.sort_by(|a, b| b.1.cmp(&a.1));
        }

        // Build bitmap index: for each (length, pos, letter), a bool vec of size bucket_len
        let mut index: HashMap<(usize, usize, u8), Vec<bool>> = HashMap::new();
        for (&length, bucket) in &by_length {
            let n = bucket.len();
            for (word_idx, (bytes, _)) in bucket.iter().enumerate() {
                for (pos, &letter) in bytes.iter().enumerate() {
                    let bm = index
                        .entry((length, pos, letter))
                        .or_insert_with(|| vec![false; n]);
                    bm[word_idx] = true;
                }
            }
        }

        WordBank { by_length, index }
    }

    #[inline]
    fn get(&self, length: usize, idx: usize) -> (&[u8], i32) {
        let entry = &self.by_length[&length][idx];
        (&entry.0, entry.1)
    }

    fn bucket_len(&self, length: usize) -> usize {
        self.by_length.get(&length).map_or(0, |b| b.len())
    }

    /// Get the bitmap for (length, pos, letter). Returns None if no words match.
    fn bitmap(&self, length: usize, pos: usize, letter: u8) -> Option<&Vec<bool>> {
        self.index.get(&(length, pos, letter))
    }
}

/// Core backtracking solver with bitmap-based domain filtering.
struct Solver<'a> {
    slots: &'a [Slot],
    bank: &'a WordBank,
    /// Live domain bitmaps: domain[slot_idx][word_idx] = true if word is still viable
    /// Maintained incrementally on assign/unassign.
    domain_bitmaps: Vec<Vec<bool>>,
    /// domain_sizes[slot_idx] = number of true entries in domain_bitmaps[slot_idx]
    domain_sizes: Vec<usize>,
    neighbors: Vec<Vec<(usize, usize, usize)>>,
    assignment: Vec<Option<usize>>,
    used_words: HashSet<Vec<u8>>,
    results: Vec<Vec<(String, String, i32)>>,
    deadline: Instant,
    max_results: usize,
    /// Track how many slots are assigned for quick completion check
    num_assigned: usize,
}

impl<'a> Solver<'a> {
    fn new(
        slots: &'a [Slot],
        bank: &'a WordBank,
        domain_order: Vec<Vec<usize>>,
        timeout_secs: f64,
        max_results: usize,
    ) -> Self {
        let neighbors: Vec<Vec<(usize, usize, usize)>> = slots
            .iter()
            .map(|s| {
                s.crossings
                    .iter()
                    .map(|c| (c.other_slot, c.self_pos, c.other_pos))
                    .collect()
            })
            .collect();

        // Build initial domain bitmaps from domain_order
        let mut domain_bitmaps: Vec<Vec<bool>> = Vec::with_capacity(slots.len());
        let mut domain_sizes: Vec<usize> = Vec::with_capacity(slots.len());
        for (i, slot) in slots.iter().enumerate() {
            let n = bank.bucket_len(slot.length);
            let mut bm = vec![false; n];
            for &idx in &domain_order[i] {
                bm[idx] = true;
            }
            domain_sizes.push(domain_order[i].len());
            domain_bitmaps.push(bm);
        }

        Solver {
            slots,
            bank,
            domain_bitmaps,
            domain_sizes,
            neighbors,
            assignment: vec![None; slots.len()],
            used_words: HashSet::new(),
            results: Vec::new(),
            deadline: Instant::now() + std::time::Duration::from_secs_f64(timeout_secs),
            max_results,
            num_assigned: 0,
        }
    }

    fn solve(&mut self) {
        self.backtrack();
    }

    fn backtrack(&mut self) {
        if Instant::now() > self.deadline || self.results.len() >= self.max_results {
            return;
        }

        // Complete?
        if self.num_assigned == self.slots.len() {
            let mut result = Vec::new();
            for (i, slot) in self.slots.iter().enumerate() {
                let word_idx = self.assignment[i].unwrap();
                let (bytes, score) = self.bank.get(slot.length, word_idx);
                result.push((
                    slot.id.clone(),
                    String::from_utf8(bytes.to_vec()).unwrap(),
                    score,
                ));
            }
            self.results.push(result);
            return;
        }

        // MRV: pick unassigned slot with smallest domain
        let best_slot = self.select_variable();
        if best_slot == usize::MAX {
            return;
        }

        // Collect viable candidates (in domain bitmap and not used)
        let length = self.slots[best_slot].length;
        let n = self.bank.bucket_len(length);
        let mut viable: Vec<usize> = Vec::new();
        for idx in 0..n {
            if self.domain_bitmaps[best_slot][idx] {
                let (bytes, _) = self.bank.get(length, idx);
                if !self.used_words.contains(bytes) {
                    viable.push(idx);
                }
            }
        }

        if viable.is_empty() {
            return;
        }

        // Sort by score descending
        viable.sort_by(|&a, &b| {
            self.bank.get(length, b).1.cmp(&self.bank.get(length, a).1)
        });

        for word_idx in viable {
            let (bytes, _) = self.bank.get(length, word_idx);
            let bytes_owned = bytes.to_vec();

            // Assign
            self.assignment[best_slot] = Some(word_idx);
            self.used_words.insert(bytes_owned.clone());
            self.num_assigned += 1;

            // Propagate: filter crossing slot domains
            let saved = self.propagate(best_slot, word_idx);

            // Forward check: all unassigned neighbors have domain_size > 0
            let ok = self.neighbors[best_slot]
                .iter()
                .all(|&(other, _, _)| self.assignment[other].is_some() || self.domain_sizes[other] > 0);

            if ok {
                self.backtrack();
            }

            // Undo propagation
            self.unpropate(saved);
            self.num_assigned -= 1;
            self.used_words.remove(&bytes_owned);
            self.assignment[best_slot] = None;

            if self.results.len() >= self.max_results || Instant::now() > self.deadline {
                return;
            }
        }
    }

    /// MRV: return index of unassigned slot with smallest domain. Returns usize::MAX if none.
    fn select_variable(&self) -> usize {
        let mut best = usize::MAX;
        let mut best_size = usize::MAX;
        for i in 0..self.slots.len() {
            if self.assignment[i].is_some() {
                continue;
            }
            if self.domain_sizes[i] < best_size {
                best_size = self.domain_sizes[i];
                best = i;
                if best_size == 0 {
                    return best; // Dead end, return immediately
                }
            }
        }
        best
    }

    /// Propagate constraints after assigning word_idx to slot.
    /// For each crossing slot, remove words that don't match at the crossing position.
    /// Returns a list of (slot_idx, word_idx) pairs that were removed (for undo).
    fn propagate(&mut self, slot: usize, word_idx: usize) -> Vec<(usize, Vec<usize>)> {
        let (assigned_bytes, _) = self.bank.get(self.slots[slot].length, word_idx);
        let assigned_bytes = assigned_bytes.to_vec(); // own it to avoid borrow issues

        let mut removed: Vec<(usize, Vec<usize>)> = Vec::new();

        let crossings: Vec<(usize, usize, usize)> = self.neighbors[slot].clone();
        for (other, self_pos, other_pos) in crossings {
            if self.assignment[other].is_some() {
                continue;
            }

            let required_letter = assigned_bytes[self_pos];
            let other_length = self.slots[other].length;
            let n = self.bank.bucket_len(other_length);

            // Get bitmap of words that have the required letter at other_pos
            let compatible = self.bank.bitmap(other_length, other_pos, required_letter);

            let mut slot_removed = Vec::new();
            for idx in 0..n {
                if !self.domain_bitmaps[other][idx] {
                    continue;
                }
                let keep = compatible.is_some_and(|bm| bm[idx]);
                if !keep {
                    self.domain_bitmaps[other][idx] = false;
                    self.domain_sizes[other] -= 1;
                    slot_removed.push(idx);
                }
            }
            if !slot_removed.is_empty() {
                removed.push((other, slot_removed));
            }
        }

        removed
    }

    /// Undo propagation by restoring removed entries.
    fn unpropate(&mut self, removed: Vec<(usize, Vec<usize>)>) {
        for (slot, indices) in removed {
            for idx in indices {
                self.domain_bitmaps[slot][idx] = true;
                self.domain_sizes[slot] += 1;
            }
        }
    }
}

fn fill_distance(a: &[(String, String, i32)], b: &[(String, String, i32)]) -> usize {
    let a_words: HashSet<&str> = a.iter().map(|(_, w, _)| w.as_str()).collect();
    let b_words: HashSet<&str> = b.iter().map(|(_, w, _)| w.as_str()).collect();
    a_words.symmetric_difference(&b_words).count()
}

#[pyfunction]
fn solve(
    words: Vec<(String, i32)>,
    slots: Vec<(String, usize, Vec<(usize, usize, usize)>)>,
    top_k: usize,
    timeout_secs: f64,
    min_score: i32,
    num_restarts: usize,
    min_diversity: usize,
) -> PyResult<Vec<Vec<(String, String, i32)>>> {
    let global_start = Instant::now();
    let global_deadline = global_start + std::time::Duration::from_secs_f64(timeout_secs);

    let solver_slots: Vec<Slot> = slots
        .iter()
        .map(|(id, length, crossings)| Slot {
            id: id.clone(),
            length: *length,
            crossings: crossings
                .iter()
                .map(|&(other, self_pos, other_pos)| Crossing {
                    other_slot: other,
                    self_pos,
                    other_pos,
                })
                .collect(),
        })
        .collect();

    let bank = WordBank::new(words, min_score);

    let mut pool: Vec<Vec<(String, String, i32)>> = Vec::new();
    let mut seen: HashSet<Vec<String>> = HashSet::new();
    let mut rng = rand::rng();
    let time_per_restart = timeout_secs / num_restarts as f64;
    let fills_per_restart = 10;

    for restart in 0..num_restarts {
        if Instant::now() > global_deadline || pool.len() >= top_k * 10 {
            break;
        }

        // Build domain ordering for this restart
        let mut domains: Vec<Vec<usize>> = Vec::new();
        for slot in &solver_slots {
            let n = bank.bucket_len(slot.length);
            let mut indices: Vec<usize> = (0..n).collect();
            if restart > 0 {
                let max_s = if n > 0 { bank.get(slot.length, 0).1 as f64 } else { 1.0 };
                let noise = max_s * 0.5;
                let mut jittered = vec![0.0f64; n];
                for &idx in &indices {
                    jittered[idx] = bank.get(slot.length, idx).1 as f64
                        + rand::random::<f64>() * noise;
                }
                indices.sort_by(|&a, &b| jittered[b].total_cmp(&jittered[a]));
            } else {
                let mut i = 0;
                while i < indices.len() {
                    let tier_score = bank.get(slot.length, indices[i]).1;
                    let mut j = i;
                    while j < indices.len() && bank.get(slot.length, indices[j]).1 == tier_score {
                        j += 1;
                    }
                    indices[i..j].shuffle(&mut rng);
                    i = j;
                }
            }
            domains.push(indices);
        }

        let remaining = (global_deadline - Instant::now()).as_secs_f64().min(time_per_restart);
        if remaining <= 0.0 {
            break;
        }

        let mut solver = Solver::new(&solver_slots, &bank, domains, remaining, fills_per_restart);
        solver.solve();

        for result in solver.results {
            let mut key: Vec<String> = result.iter().map(|(_, w, _)| w.clone()).collect();
            key.sort();
            if seen.insert(key) {
                pool.push(result);
            }
        }
    }

    if pool.is_empty() {
        return Ok(Vec::new());
    }

    // Diverse selection
    let scores: Vec<f64> = pool
        .iter()
        .map(|fill| fill.iter().map(|(_, _, s)| *s as f64).sum())
        .collect();
    let max_score = scores.iter().cloned().fold(f64::NEG_INFINITY, f64::max);

    let mut selected: Vec<usize> = Vec::new();
    let best = scores
        .iter()
        .enumerate()
        .max_by(|a, b| a.1.partial_cmp(b.1).unwrap())
        .map(|(i, _)| i)
        .unwrap();
    selected.push(best);

    while selected.len() < top_k && selected.len() < pool.len() {
        let mut best_candidate = None;
        let mut best_value = -1.0f64;

        for i in 0..pool.len() {
            if selected.contains(&i) {
                continue;
            }
            let min_diff = selected
                .iter()
                .map(|&j| fill_distance(&pool[i], &pool[j]))
                .min()
                .unwrap_or(0);
            if min_diff < min_diversity {
                continue;
            }
            let score_norm = if max_score > 0.0 { scores[i] / max_score } else { 0.0 };
            let num_words = pool[i].len().max(1) as f64;
            let diversity_norm = min_diff as f64 / (num_words * 2.0);
            let value = 0.4 * score_norm + 0.6 * diversity_norm;
            if value > best_value {
                best_value = value;
                best_candidate = Some(i);
            }
        }

        match best_candidate {
            Some(idx) => selected.push(idx),
            None => break,
        }
    }

    selected.sort_by(|&a, &b| scores[b].partial_cmp(&scores[a]).unwrap());
    let result: Vec<Vec<(String, String, i32)>> = selected.into_iter().map(|i| pool[i].clone()).collect();
    Ok(result)
}

#[pymodule]
fn xword_solver(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(solve, m)?)?;
    Ok(())
}
