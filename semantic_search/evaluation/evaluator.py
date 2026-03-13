"""Relevance evaluator that runs labeled queries through a :class:`SearchRuntime`.

Typical usage::

    from semantic_search.evaluation import RelevanceEvaluator, EvalQuery
    from semantic_search.runtime.api import SearchRuntime

    evaluator = RelevanceEvaluator(runtime, hit_rate_threshold=0.90)
    report = evaluator.run(queries)

    if report.passes_threshold():
        print(f"PASS  hit_rate={report.hit_rate:.1%}")
    else:
        print(f"FAIL  hit_rate={report.hit_rate:.1%}  (target >= 90%)")
"""

from __future__ import annotations

import logging
from time import perf_counter
from typing import List, Sequence

from semantic_search.runtime.api import SearchRequest, SearchRuntime

from .metrics import hit_rate, ndcg_at_k, precision_at_k, reciprocal_rank
from .schema import EvalQuery, EvalReport, EvalResult

LOGGER = logging.getLogger(__name__)


class RelevanceEvaluator:
    """Runs a labelled query set through a :class:`SearchRuntime` and measures relevance.

    Each query in the input set is executed against the live runtime; the
    results are compared to the provided ground-truth ``relevant_ids`` and
    four IR metrics are computed: hit rate (Recall@K), MRR, Precision@K, and
    nDCG@K.

    The evaluator is intentionally stateless between :meth:`run` calls so the
    same instance can be reused across multiple query sets or after index
    updates.
    """

    def __init__(
        self,
        runtime: SearchRuntime,
        *,
        hit_rate_threshold: float = 0.90,
    ) -> None:
        """Initialise the evaluator.

        Args:
            runtime: Configured :class:`SearchRuntime` to evaluate against.
            hit_rate_threshold: Hit-rate target used by
                :meth:`~schema.EvalReport.passes_threshold`.  Defaults to
                ``0.90`` (≥90% of queries must have at least one relevant
                result in the top-K).
        """
        if not 0.0 <= hit_rate_threshold <= 1.0:
            raise ValueError(
                f"hit_rate_threshold must be in [0, 1]; got {hit_rate_threshold}"
            )
        self._runtime = runtime
        self._threshold = hit_rate_threshold

    def run(self, queries: Sequence[EvalQuery]) -> EvalReport:
        """Execute all queries and return an aggregate :class:`EvalReport`.

        Queries are executed sequentially.  A failed runtime call for a single
        query is caught and logged at WARNING level; the query is counted as a
        miss (hit=False, all metrics 0.0) so the run can complete.

        Args:
            queries: Sequence of labeled queries to evaluate.  May be empty,
                in which case the report has zero queries and all metrics are
                ``0.0``.

        Returns:
            :class:`EvalReport` containing per-query breakdowns and aggregate
            statistics.
        """
        if not queries:
            LOGGER.info("RelevanceEvaluator.run called with empty query list.")
            return EvalReport(
                num_queries=0,
                hit_rate=0.0,
                mean_reciprocal_rank=0.0,
                mean_precision_at_k=0.0,
                mean_ndcg_at_k=0.0,
                mean_latency_ms=0.0,
            )

        results: List[EvalResult] = []

        for query in queries:
            result = self._evaluate_single(query)
            results.append(result)

        return self._aggregate(results)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _evaluate_single(self, query: EvalQuery) -> EvalResult:
        """Execute a single :class:`EvalQuery` and produce its :class:`EvalResult`.

        Args:
            query: The labeled query to evaluate.

        Returns:
            Per-query :class:`EvalResult` with computed metrics.
        """
        relevant = frozenset(query.relevant_ids)
        start = perf_counter()
        returned_ids: List[str] = []

        try:
            request = SearchRequest(query=query.query_text, top_k=query.top_k)
            response = self._runtime.search(request)
            returned_ids = [item.record_id for item in response.results]
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Query %r failed during evaluation: %s — counting as miss.",
                query.query_id,
                exc,
            )

        elapsed_ms = (perf_counter() - start) * 1000.0

        return EvalResult(
            query_id=query.query_id,
            query_text=query.query_text,
            top_k=query.top_k,
            returned_ids=returned_ids,
            relevant_ids=list(query.relevant_ids),
            hit=hit_rate(returned_ids, relevant),
            reciprocal_rank=reciprocal_rank(returned_ids, relevant),
            precision_at_k=precision_at_k(returned_ids, relevant),
            ndcg_at_k=ndcg_at_k(returned_ids, relevant),
            elapsed_ms=elapsed_ms,
        )

    @staticmethod
    def _aggregate(results: List[EvalResult]) -> EvalReport:
        """Compute aggregate statistics from a list of per-query results.

        Args:
            results: Non-empty list of :class:`EvalResult` objects.

        Returns:
            :class:`EvalReport` with mean metrics across all results.
        """
        n = len(results)
        return EvalReport(
            num_queries=n,
            hit_rate=sum(1 for r in results if r.hit) / n,
            mean_reciprocal_rank=sum(r.reciprocal_rank for r in results) / n,
            mean_precision_at_k=sum(r.precision_at_k for r in results) / n,
            mean_ndcg_at_k=sum(r.ndcg_at_k for r in results) / n,
            mean_latency_ms=sum(r.elapsed_ms for r in results) / n,
            results=results,
        )


__all__ = ["RelevanceEvaluator"]
