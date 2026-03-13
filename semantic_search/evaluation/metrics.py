"""Pure relevance metric functions used by the evaluation suite.

All functions operate on plain Python lists and sets so they are trivially
testable without any runtime dependencies.

Metrics implemented
-------------------
* :func:`hit_rate` — binary indicator: did any relevant result appear?
* :func:`reciprocal_rank` — 1 / rank of first relevant result (MRR component).
* :func:`precision_at_k` — fraction of returned results that are relevant.
* :func:`dcg_at_k` — Discounted Cumulative Gain.
* :func:`ndcg_at_k` — Normalised DCG (DCG / Ideal DCG).
"""

from __future__ import annotations

import math
from typing import FrozenSet, List, Set, Union

RelevantSet = Union[Set[str], FrozenSet[str]]


def hit_rate(returned_ids: List[str], relevant_ids: RelevantSet) -> bool:
    """Return ``True`` if at least one relevant record appears in the result list.

    Args:
        returned_ids: Ordered list of record IDs returned by the search runtime.
        relevant_ids: Set of record IDs considered relevant for the query.

    Returns:
        ``True`` when any element of ``returned_ids`` is in ``relevant_ids``.
    """
    return any(rid in relevant_ids for rid in returned_ids)


def reciprocal_rank(returned_ids: List[str], relevant_ids: RelevantSet) -> float:
    """Return 1/rank of the first relevant result, or 0.0 if none found.

    Rank is 1-indexed, so the first position yields ``1.0``, the second
    ``0.5``, and so on.

    Args:
        returned_ids: Ordered list of record IDs returned by the search runtime.
        relevant_ids: Set of record IDs considered relevant for the query.

    Returns:
        Reciprocal rank in ``[0.0, 1.0]``.
    """
    for rank, rid in enumerate(returned_ids, start=1):
        if rid in relevant_ids:
            return 1.0 / rank
    return 0.0


def precision_at_k(returned_ids: List[str], relevant_ids: RelevantSet) -> float:
    """Return the fraction of returned results that are relevant (Precision@K).

    Args:
        returned_ids: Ordered list of record IDs returned by the search runtime.
        relevant_ids: Set of record IDs considered relevant for the query.

    Returns:
        A value in ``[0.0, 1.0]``.  Returns ``0.0`` when ``returned_ids`` is
        empty.
    """
    if not returned_ids:
        return 0.0
    hits = sum(1 for rid in returned_ids if rid in relevant_ids)
    return hits / len(returned_ids)


def dcg_at_k(returned_ids: List[str], relevant_ids: RelevantSet) -> float:
    """Return the Discounted Cumulative Gain for a ranked result list.

    Uses binary relevance (1 for relevant, 0 otherwise) with the standard
    ``1 / log2(rank + 1)`` discount applied at each position.

    Args:
        returned_ids: Ordered list of record IDs returned by the search runtime.
        relevant_ids: Set of record IDs considered relevant for the query.

    Returns:
        DCG score (``>= 0.0``).
    """
    return sum(
        1.0 / math.log2(rank + 1)
        for rank, rid in enumerate(returned_ids, start=1)
        if rid in relevant_ids
    )


def ndcg_at_k(returned_ids: List[str], relevant_ids: RelevantSet) -> float:
    """Return the Normalised Discounted Cumulative Gain (nDCG@K).

    The ideal DCG is computed by placing as many relevant results as possible
    at the top positions (capped at ``len(returned_ids)``).  When the ideal
    DCG is zero (no relevant results exist) the function returns ``0.0``.

    Args:
        returned_ids: Ordered list of record IDs returned by the search runtime.
        relevant_ids: Set of record IDs considered relevant for the query.

    Returns:
        nDCG score in ``[0.0, 1.0]``.
    """
    actual = dcg_at_k(returned_ids, relevant_ids)
    # Ideal: fill top positions with relevant items up to len(returned_ids).
    ideal_count = min(len(relevant_ids), len(returned_ids))
    if ideal_count == 0:
        return 0.0
    ideal_ids = list(relevant_ids)[:ideal_count]
    ideal = dcg_at_k(ideal_ids, relevant_ids)
    if ideal == 0.0:
        return 0.0
    return actual / ideal


__all__ = [
    "hit_rate",
    "reciprocal_rank",
    "precision_at_k",
    "dcg_at_k",
    "ndcg_at_k",
]
