"""Tests for :class:`~semantic_search.evaluation.evaluator.RelevanceEvaluator`.

Tests run entirely in-memory using the same deterministic hash-based embedding
provider and ``NumpyVectorStore`` fixtures already established in the runtime
test suite.  No AWS calls are made.
"""

from __future__ import annotations

import hashlib
from typing import List, Sequence

import numpy as np
import pytest

from semantic_search.embeddings.base import (
    EmbeddingInput,
    EmbeddingProvider,
    EmbeddingResult,
)
from semantic_search.evaluation.evaluator import RelevanceEvaluator
from semantic_search.evaluation.schema import EvalQuery, EvalReport
from semantic_search.runtime.api import SearchRuntime
from semantic_search.vectorstores.faiss_store import NumpyVectorStore, VectorRecord


# ──────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ──────────────────────────────────────────────────────────────────────────────

_DIMENSION = 8


class _HashProvider(EmbeddingProvider):
    """Deterministic, dependency-free embedding provider for tests."""

    def __init__(self, dimension: int = _DIMENSION) -> None:
        self._dimension = dimension

    def generate(
        self,
        inputs: Sequence[EmbeddingInput],
        *,
        model: str | None = None,
        **_: object,
    ) -> Sequence[EmbeddingResult]:
        results: List[EmbeddingResult] = []
        for item in inputs:
            vector = self._hash_to_vector(item.text)
            results.append(
                EmbeddingResult(
                    record_id=item.record_id,
                    vector=vector,
                    metadata={"model": "hash-test"},
                )
            )
        return results

    def _hash_to_vector(self, text: str) -> List[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = np.frombuffer(digest, dtype=np.uint8).astype(np.float32)
        values = (
            values[: self._dimension]
            if values.size >= self._dimension
            else np.resize(values, self._dimension)
        )
        values -= 127.5
        norm = np.linalg.norm(values)
        if norm > 0:
            values /= norm
        return values.tolist()


@pytest.fixture()
def provider() -> EmbeddingProvider:
    """Return the deterministic hash embedding provider."""
    return _HashProvider()


@pytest.fixture()
def store() -> NumpyVectorStore:
    """Return a small, populated vector store.

    The store contains three records whose vectors are standard basis vectors
    (orthogonal), so queries hashing to the same text will reliably return
    the expected record.
    """
    vs = NumpyVectorStore(dimension=_DIMENSION, metric="cosine")
    records = [
        VectorRecord(
            record_id="alpha",
            vector=np.eye(_DIMENSION, dtype=np.float32)[0],
            metadata={"category": "docs"},
        ),
        VectorRecord(
            record_id="bravo",
            vector=np.eye(_DIMENSION, dtype=np.float32)[1],
            metadata={"category": "tickets"},
        ),
        VectorRecord(
            record_id="charlie",
            vector=np.eye(_DIMENSION, dtype=np.float32)[2],
            metadata={"category": "docs"},
        ),
    ]
    vs.upsert(records)
    return vs


@pytest.fixture()
def runtime(provider: EmbeddingProvider, store: NumpyVectorStore) -> SearchRuntime:
    """Return a configured SearchRuntime for evaluator tests."""
    return SearchRuntime(
        provider,
        store,
        default_top_k=5,
        max_top_k=10,
        candidate_multiplier=3,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────


class TestRelevanceEvaluatorInit:
    """Constructor validation tests."""

    def test_invalid_threshold_below_zero_raises(self, runtime: SearchRuntime) -> None:
        with pytest.raises(ValueError, match="hit_rate_threshold"):
            RelevanceEvaluator(runtime, hit_rate_threshold=-0.1)

    def test_invalid_threshold_above_one_raises(self, runtime: SearchRuntime) -> None:
        with pytest.raises(ValueError, match="hit_rate_threshold"):
            RelevanceEvaluator(runtime, hit_rate_threshold=1.1)

    def test_boundary_zero_is_valid(self, runtime: SearchRuntime) -> None:
        evaluator = RelevanceEvaluator(runtime, hit_rate_threshold=0.0)
        assert evaluator is not None

    def test_boundary_one_is_valid(self, runtime: SearchRuntime) -> None:
        evaluator = RelevanceEvaluator(runtime, hit_rate_threshold=1.0)
        assert evaluator is not None


class TestRelevanceEvaluatorEmptyQueries:
    """Behaviour when the query list is empty."""

    def test_run_empty_returns_report_with_zero_queries(
        self, runtime: SearchRuntime
    ) -> None:
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run([])
        assert report.num_queries == 0

    def test_run_empty_all_metrics_zero(self, runtime: SearchRuntime) -> None:
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run([])
        assert report.hit_rate == 0.0
        assert report.mean_reciprocal_rank == 0.0
        assert report.mean_precision_at_k == 0.0
        assert report.mean_ndcg_at_k == 0.0
        assert report.mean_latency_ms == 0.0

    def test_run_empty_results_list_is_empty(self, runtime: SearchRuntime) -> None:
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run([])
        assert report.results == []

    def test_run_empty_fails_default_threshold(self, runtime: SearchRuntime) -> None:
        evaluator = RelevanceEvaluator(runtime, hit_rate_threshold=0.90)
        report = evaluator.run([])
        assert not report.passes_threshold()


class TestRelevanceEvaluatorSingleHit:
    """Single query that produces a hit."""

    def test_hit_rate_is_one(self, runtime: SearchRuntime) -> None:
        query = EvalQuery(
            query_id="q1",
            query_text="any text",
            relevant_ids=["alpha", "bravo", "charlie"],
            top_k=3,
        )
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run([query])
        # The store has all three IDs, so at least one must be returned.
        assert report.hit_rate == pytest.approx(1.0)

    def test_num_queries_is_one(self, runtime: SearchRuntime) -> None:
        query = EvalQuery(
            query_id="q1",
            query_text="some text",
            relevant_ids=["alpha"],
            top_k=3,
        )
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run([query])
        assert report.num_queries == 1

    def test_elapsed_ms_is_positive(self, runtime: SearchRuntime) -> None:
        query = EvalQuery(
            query_id="q1",
            query_text="any text",
            relevant_ids=["alpha"],
            top_k=3,
        )
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run([query])
        assert report.mean_latency_ms > 0.0
        assert report.results[0].elapsed_ms > 0.0

    def test_result_query_id_matches(self, runtime: SearchRuntime) -> None:
        query = EvalQuery(
            query_id="unique-id-99",
            query_text="any text",
            relevant_ids=["alpha"],
            top_k=3,
        )
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run([query])
        assert report.results[0].query_id == "unique-id-99"


class TestRelevanceEvaluatorAllMiss:
    """All queries produce misses (no relevant records in the store)."""

    def test_hit_rate_is_zero_when_no_relevant_records_exist(
        self, runtime: SearchRuntime
    ) -> None:
        queries = [
            EvalQuery(
                query_id=f"q{i}",
                query_text=f"text {i}",
                relevant_ids=["does-not-exist"],
                top_k=5,
            )
            for i in range(3)
        ]
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run(queries)
        assert report.hit_rate == pytest.approx(0.0)

    def test_mrr_is_zero_for_all_misses(self, runtime: SearchRuntime) -> None:
        queries = [
            EvalQuery(
                query_id="q1",
                query_text="anything",
                relevant_ids=["nonexistent"],
                top_k=5,
            )
        ]
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run(queries)
        assert report.mean_reciprocal_rank == pytest.approx(0.0)


class TestRelevanceEvaluatorThreshold:
    """Threshold pass/fail behaviour."""

    def _make_report_with_hit_rate(
        self, runtime: SearchRuntime, hit: bool
    ) -> EvalReport:
        """Helper: build a report with a predictable hit/miss outcome."""
        relevant = ["alpha", "bravo", "charlie"] if hit else ["nonexistent"]
        query = EvalQuery(
            query_id="q1",
            query_text="any text",
            relevant_ids=relevant,
            top_k=3,
        )
        evaluator = RelevanceEvaluator(runtime, hit_rate_threshold=0.90)
        return evaluator.run([query])

    def test_passes_threshold_when_hit_rate_is_one(
        self, runtime: SearchRuntime
    ) -> None:
        report = self._make_report_with_hit_rate(runtime, hit=True)
        assert report.hit_rate == pytest.approx(1.0)
        assert report.passes_threshold(0.90)

    def test_fails_threshold_when_hit_rate_is_zero(
        self, runtime: SearchRuntime
    ) -> None:
        report = self._make_report_with_hit_rate(runtime, hit=False)
        assert report.hit_rate == pytest.approx(0.0)
        assert not report.passes_threshold(0.90)

    def test_passes_when_threshold_is_zero(self, runtime: SearchRuntime) -> None:
        # Any hit rate (including 0.0) must pass a zero threshold.
        query = EvalQuery(
            query_id="q1",
            query_text="text",
            relevant_ids=["nonexistent"],
            top_k=3,
        )
        evaluator = RelevanceEvaluator(runtime, hit_rate_threshold=0.0)
        report = evaluator.run([query])
        assert report.passes_threshold(0.0)


class TestRelevanceEvaluatorMultipleQueries:
    """Multi-query aggregation sanity checks."""

    def test_num_queries_matches_input_length(self, runtime: SearchRuntime) -> None:
        queries = [
            EvalQuery(
                query_id=f"q{i}",
                query_text=f"text {i}",
                relevant_ids=["alpha"],
                top_k=3,
            )
            for i in range(5)
        ]
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run(queries)
        assert report.num_queries == 5

    def test_results_length_equals_num_queries(self, runtime: SearchRuntime) -> None:
        queries = [
            EvalQuery(
                query_id=f"q{i}",
                query_text=f"text {i}",
                relevant_ids=["alpha"],
                top_k=3,
            )
            for i in range(4)
        ]
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run(queries)
        assert len(report.results) == 4

    def test_mean_latency_is_positive(self, runtime: SearchRuntime) -> None:
        queries = [
            EvalQuery(
                query_id=f"q{i}",
                query_text=f"text {i}",
                relevant_ids=["alpha"],
                top_k=3,
            )
            for i in range(3)
        ]
        evaluator = RelevanceEvaluator(runtime)
        report = evaluator.run(queries)
        assert report.mean_latency_ms > 0.0
