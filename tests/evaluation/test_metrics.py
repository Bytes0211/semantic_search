"""Unit tests for :mod:`semantic_search.evaluation.metrics`.

Every test exercises pure functions only — no I/O, no external dependencies.
"""

from __future__ import annotations

import math

import pytest

from semantic_search.evaluation.metrics import (
    dcg_at_k,
    hit_rate,
    ndcg_at_k,
    precision_at_k,
    reciprocal_rank,
)


# ────────────────────────────────────────────────────────────────────────────
# hit_rate
# ────────────────────────────────────────────────────────────────────────────


class TestHitRate:
    """Tests for :func:`hit_rate`."""

    def test_returns_true_when_relevant_in_results(self) -> None:
        assert hit_rate(["a", "b", "c"], {"b"}) is True

    def test_returns_true_when_relevant_is_first(self) -> None:
        assert hit_rate(["a"], {"a"}) is True

    def test_returns_false_when_no_overlap(self) -> None:
        assert hit_rate(["a", "b"], {"z"}) is False

    def test_returns_false_for_empty_returned_ids(self) -> None:
        assert hit_rate([], {"a"}) is False

    def test_returns_false_for_empty_relevant_ids(self) -> None:
        assert hit_rate(["a", "b"], set()) is False

    def test_returns_false_for_both_empty(self) -> None:
        assert hit_rate([], set()) is False

    def test_multiple_relevant_ids_at_least_one_present(self) -> None:
        assert hit_rate(["a", "b", "c"], {"x", "b", "y"}) is True

    def test_multiple_relevant_ids_none_present(self) -> None:
        assert hit_rate(["a", "b", "c"], {"x", "y", "z"}) is False


# ────────────────────────────────────────────────────────────────────────────
# reciprocal_rank
# ────────────────────────────────────────────────────────────────────────────


class TestReciprocalRank:
    """Tests for :func:`reciprocal_rank`."""

    def test_first_position_returns_one(self) -> None:
        assert reciprocal_rank(["a", "b", "c"], {"a"}) == pytest.approx(1.0)

    def test_second_position_returns_half(self) -> None:
        assert reciprocal_rank(["x", "a", "c"], {"a"}) == pytest.approx(0.5)

    def test_third_position_returns_third(self) -> None:
        assert reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)

    def test_no_relevant_returns_zero(self) -> None:
        assert reciprocal_rank(["a", "b", "c"], {"z"}) == pytest.approx(0.0)

    def test_empty_returned_ids(self) -> None:
        assert reciprocal_rank([], {"a"}) == pytest.approx(0.0)

    def test_empty_relevant_ids(self) -> None:
        assert reciprocal_rank(["a"], set()) == pytest.approx(0.0)

    def test_returns_rank_of_first_relevant_when_multiple_relevant(self) -> None:
        # "b" is at position 2, "c" is at position 3 — expect 1/2.
        assert reciprocal_rank(["a", "b", "c"], {"b", "c"}) == pytest.approx(0.5)


# ────────────────────────────────────────────────────────────────────────────
# precision_at_k
# ────────────────────────────────────────────────────────────────────────────


class TestPrecisionAtK:
    """Tests for :func:`precision_at_k`."""

    def test_all_relevant(self) -> None:
        assert precision_at_k(["a", "b"], {"a", "b"}) == pytest.approx(1.0)

    def test_no_relevant(self) -> None:
        assert precision_at_k(["a", "b"], {"x", "y"}) == pytest.approx(0.0)

    def test_half_relevant(self) -> None:
        assert precision_at_k(["a", "b", "c", "d"], {"a", "c"}) == pytest.approx(0.5)

    def test_empty_returned(self) -> None:
        assert precision_at_k([], {"a"}) == pytest.approx(0.0)

    def test_empty_relevant(self) -> None:
        assert precision_at_k(["a", "b"], set()) == pytest.approx(0.0)

    def test_single_hit_from_three(self) -> None:
        assert precision_at_k(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)


# ────────────────────────────────────────────────────────────────────────────
# dcg_at_k
# ────────────────────────────────────────────────────────────────────────────


class TestDcgAtK:
    """Tests for :func:`dcg_at_k`."""

    def test_single_relevant_at_position_one(self) -> None:
        # gain = 1 / log2(2) = 1.0
        assert dcg_at_k(["a"], {"a"}) == pytest.approx(1.0)

    def test_single_relevant_at_position_two(self) -> None:
        # gain = 1 / log2(3) ≈ 0.6309
        expected = 1.0 / math.log2(3)
        assert dcg_at_k(["x", "a"], {"a"}) == pytest.approx(expected)

    def test_empty_returned(self) -> None:
        assert dcg_at_k([], {"a"}) == pytest.approx(0.0)

    def test_no_overlap(self) -> None:
        assert dcg_at_k(["a", "b", "c"], {"z"}) == pytest.approx(0.0)

    def test_two_relevant_items(self) -> None:
        # positions 1 and 2 → 1/log2(2) + 1/log2(3)
        expected = 1.0 / math.log2(2) + 1.0 / math.log2(3)
        assert dcg_at_k(["a", "b"], {"a", "b"}) == pytest.approx(expected)


# ────────────────────────────────────────────────────────────────────────────
# ndcg_at_k
# ────────────────────────────────────────────────────────────────────────────


class TestNdcgAtK:
    """Tests for :func:`ndcg_at_k`."""

    def test_perfect_single_relevant(self) -> None:
        # DCG == IDCG ⟹ nDCG == 1.0
        assert ndcg_at_k(["a", "b", "c"], {"a"}) == pytest.approx(1.0)

    def test_zero_when_no_relevant_retrieved(self) -> None:
        assert ndcg_at_k(["a", "b", "c"], {"z"}) == pytest.approx(0.0)

    def test_empty_returned(self) -> None:
        assert ndcg_at_k([], {"a"}) == pytest.approx(0.0)

    def test_empty_relevant(self) -> None:
        assert ndcg_at_k(["a", "b"], set()) == pytest.approx(0.0)

    def test_all_relevant_perfect_order(self) -> None:
        # Every returned item is relevant ⟹ nDCG == 1.0
        assert ndcg_at_k(["a", "b", "c"], {"a", "b", "c"}) == pytest.approx(1.0)

    def test_relevant_at_second_position_less_than_one(self) -> None:
        # relevant at position 2 vs ideal at position 1 ⟹ nDCG < 1
        score = ndcg_at_k(["x", "a"], {"a"})
        assert 0.0 < score < 1.0

    def test_score_degrades_with_rank(self) -> None:
        # Same single relevant item, but at progressively lower ranks.
        score_rank1 = ndcg_at_k(["a", "x", "y"], {"a"})
        score_rank2 = ndcg_at_k(["x", "a", "y"], {"a"})
        score_rank3 = ndcg_at_k(["x", "y", "a"], {"a"})
        assert score_rank1 >= score_rank2 >= score_rank3

    def test_multiple_relevant_partial_recall(self) -> None:
        # Retrieve two of three relevant docs ⟹ nDCG between 0 and 1.
        score = ndcg_at_k(["a", "b", "x"], {"a", "b", "c"})
        assert 0.0 < score < 1.0
