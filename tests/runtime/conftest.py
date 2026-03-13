from __future__ import annotations

import hashlib
from typing import Iterable, List, Sequence

import numpy as np
import pytest

from semantic_search.embeddings.base import (
    EmbeddingInput,
    EmbeddingProvider,
    EmbeddingResult,
)
from semantic_search.runtime.api import SearchRuntime
from semantic_search.vectorstores.faiss_store import NumpyVectorStore, VectorRecord


class InMemoryEmbeddingProvider(EmbeddingProvider):
    """Deterministic embedding provider for runtime unit tests.

    This implementation hashes the input text into a fixed-length vector so that
    tests can operate without relying on external services.
    """

    def __init__(self, *, dimension: int = 8) -> None:
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
                    metadata={"model": model or "in-memory-test"},
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


@pytest.fixture(scope="session")
def embedding_dimension() -> int:
    """Shared embedding/vector dimension for runtime tests."""
    return 8


@pytest.fixture()
def mock_embedding_provider(embedding_dimension: int) -> EmbeddingProvider:
    """Provide the deterministic in-memory embedding provider."""
    return InMemoryEmbeddingProvider(dimension=embedding_dimension)


@pytest.fixture()
def vector_store(embedding_dimension: int) -> NumpyVectorStore:
    """Populate an in-memory vector store with sample records for search tests."""
    store = NumpyVectorStore(dimension=embedding_dimension, metric="cosine")
    records: Iterable[VectorRecord] = [
        VectorRecord(
            record_id="alpha",
            vector=np.eye(embedding_dimension, dtype=np.float32)[0],
            metadata={"category": "documents", "region": "us-east-1"},
        ),
        VectorRecord(
            record_id="bravo",
            vector=np.eye(embedding_dimension, dtype=np.float32)[1],
            metadata={"category": "tickets", "region": "eu-west-1"},
        ),
        VectorRecord(
            record_id="charlie",
            vector=np.eye(embedding_dimension, dtype=np.float32)[2],
            metadata={"category": "documents", "region": "ap-southeast-2"},
        ),
    ]
    store.upsert(records)
    return store


@pytest.fixture()
def search_runtime(
    mock_embedding_provider: EmbeddingProvider,
    vector_store: NumpyVectorStore,
) -> SearchRuntime:
    """Construct the SearchRuntime used across runtime-focused tests."""
    return SearchRuntime(
        mock_embedding_provider,
        vector_store,
        default_top_k=5,
        max_top_k=20,
        candidate_multiplier=5,
    )
