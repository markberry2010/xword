"""Tests for wordlist module."""

from pathlib import Path

from crossword.wordlist import WordList


def test_load_and_length(small_wordlist: WordList):
    assert len(small_wordlist) > 0


def test_contains(small_wordlist: WordList):
    assert small_wordlist.contains("CAT")
    assert small_wordlist.contains("cat")  # case insensitive
    assert not small_wordlist.contains("ZZZ")


def test_score(small_wordlist: WordList):
    assert small_wordlist.score("DOG") == 70
    assert small_wordlist.score("dog") == 70
    assert small_wordlist.score("ZZZ") == 0


def test_candidates_by_length(small_wordlist: WordList):
    threes = small_wordlist.candidates(3)
    assert len(threes) > 0
    assert all(len(e.word) == 3 for e in threes)
    # Should be sorted by score descending
    scores = [e.score for e in threes]
    assert scores == sorted(scores, reverse=True)


def test_candidates_with_pattern(small_wordlist: WordList):
    # 3-letter words starting with 'C'
    results = small_wordlist.candidates(3, {0: "C"})
    assert len(results) > 0
    assert all(e.word[0] == "C" for e in results)

    # 3-letter words with 'A' at position 1
    results = small_wordlist.candidates(3, {1: "A"})
    assert all(e.word[1] == "A" for e in results)


def test_candidates_multi_constraint(small_wordlist: WordList):
    # 3-letter words: C at 0, T at 2
    results = small_wordlist.candidates(3, {0: "C", 2: "T"})
    for e in results:
        assert e.word[0] == "C"
        assert e.word[2] == "T"


def test_candidates_no_match(small_wordlist: WordList):
    results = small_wordlist.candidates(3, {0: "Z"})
    assert results == []


def test_candidates_five_letter(small_wordlist: WordList):
    fives = small_wordlist.candidates(5)
    assert len(fives) > 0
    assert all(len(e.word) == 5 for e in fives)


def test_short_words_excluded(tmp_path: Path):
    """Words shorter than 3 should be excluded."""
    wl_path = tmp_path / "wl.txt"
    wl_path.write_text("AB,50\nABC,60\nA,70\n")
    wl = WordList(wl_path)
    assert len(wl) == 1
    assert wl.contains("ABC")
    assert not wl.contains("AB")
