"""Data types shared across the relevance evaluation suite.

Three classes form the data contract:

* :class:`EvalQuery` — a single labeled query with known-relevant record IDs.
* :class:`EvalResult` — per-query outcome produced by the evaluator.
* :class:`EvalReport` — aggregate report summarising all query results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class EvalQuery:
    """A single evaluation query together with its ground-truth relevant records.

    Attributes:
        query_id: Unique identifier for this query (e.g. ``"q001"``).
        query_text: Natural-language query string submitted to the search runtime.
        relevant_ids: List of record IDs that are considered relevant for this
            query.  At least one must appear in the top-K results for the query
            to count as a *hit*.
        top_k: Maximum number of results to request from the runtime.
            Defaults to ``10``.
    """

    query_id: str
    query_text: str
    relevant_ids: List[str]
    top_k: int = 10


@dataclass
class EvalResult:
    """Relevance metrics produced for a single :class:`EvalQuery`.

    Attributes:
        query_id: Matches the source :attr:`EvalQuery.query_id`.
        query_text: The query string that was evaluated.
        top_k: The ``top_k`` value used for this query.
        returned_ids: Ordered list of record IDs returned by the runtime.
        relevant_ids: Ground-truth relevant record IDs (copied from the query).
        hit: ``True`` if at least one relevant record appears in
            ``returned_ids``.
        reciprocal_rank: ``1 / rank`` of the first relevant result, or ``0.0``
            when no relevant result is found.
        precision_at_k: Fraction of ``returned_ids`` that are relevant.
        ndcg_at_k: Normalised Discounted Cumulative Gain at ``top_k``.
        elapsed_ms: End-to-end query latency in milliseconds as measured by
            the evaluator.
    """

    query_id: str
    query_text: str
    top_k: int
    returned_ids: List[str]
    relevant_ids: List[str]
    hit: bool
    reciprocal_rank: float
    precision_at_k: float
    ndcg_at_k: float
    elapsed_ms: float


@dataclass
class EvalReport:
    """Aggregate relevance report produced after running all evaluation queries.

    Attributes:
        num_queries: Total number of queries evaluated.
        hit_rate: Proportion of queries with at least one relevant result in
            the top-K (Recall@K).  Target: ``>= 0.90``.
        mean_reciprocal_rank: Mean of per-query reciprocal ranks (MRR).
        mean_precision_at_k: Mean of per-query Precision@K values.
        mean_ndcg_at_k: Mean of per-query nDCG@K values.
        mean_latency_ms: Mean end-to-end query latency in milliseconds.
        results: Full list of per-query :class:`EvalResult` objects in
            evaluation order.
    """

    num_queries: int
    hit_rate: float
    mean_reciprocal_rank: float
    mean_precision_at_k: float
    mean_ndcg_at_k: float
    mean_latency_ms: float
    results: List[EvalResult] = field(default_factory=list)

    def passes_threshold(self, threshold: float = 0.90) -> bool:
        """Return ``True`` when :attr:`hit_rate` meets or exceeds ``threshold``.

        Args:
            threshold: Minimum acceptable hit rate.  Defaults to ``0.90``,
                matching the Phase 5 quality target.

        Returns:
            ``True`` if the report's hit rate is at or above the threshold.
        """
        return self.hit_rate >= threshold


__all__ = ["EvalQuery", "EvalResult", "EvalReport"]
