"""Relevance evaluation suite for the semantic search runtime.

Public surface::

    from semantic_search.evaluation import EvalQuery, EvalResult, EvalReport
    from semantic_search.evaluation import RelevanceEvaluator
"""

from semantic_search.evaluation.evaluator import RelevanceEvaluator
from semantic_search.evaluation.schema import EvalQuery, EvalReport, EvalResult

__all__ = [
    "EvalQuery",
    "EvalResult",
    "EvalReport",
    "RelevanceEvaluator",
]
