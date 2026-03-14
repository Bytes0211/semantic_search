"""
Semantic Search package public interface.

This module exposes commonly used classes for convenience, allowing consumers
to import from ``semantic_search`` directly without drilling into subpackages.
"""

from .embeddings.base import EmbeddingInput, EmbeddingProvider, EmbeddingResult
from .evaluation.schema import EvalQuery, EvalReport, EvalResult
from .evaluation.evaluator import RelevanceEvaluator
from .runtime.api import (
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchRuntime,
    create_app,
)
from .vectorstores.faiss_store import (
    NumpyVectorStore,
    QueryResult,
    VectorRecord,
    VectorStoreError,
)

__all__ = [
    "EmbeddingInput",
    "EmbeddingProvider",
    "EmbeddingResult",
    "EvalQuery",
    "EvalResult",
    "EvalReport",
    "RelevanceEvaluator",
    "SearchRequest",
    "SearchResponse",
    "SearchResultItem",
    "SearchRuntime",
    "create_app",
    "NumpyVectorStore",
    "QueryResult",
    "VectorRecord",
    "VectorStoreError",
]
