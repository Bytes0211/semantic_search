"""
Pure NumPy-based vector store implementation that mimics a subset of FAISS behaviour.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import (
    Callable,
    Iterable,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Sequence,
    Tuple,
)

import numpy as np

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class VectorRecord:
    """A record stored in the vector index."""

    record_id: str
    vector: Sequence[float]
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class QueryResult:
    """A result returned from a similarity query."""

    record_id: str
    score: float
    metadata: Mapping[str, object]


class VectorStoreError(RuntimeError):
    """Base class for vector store related errors."""


class RecordNotFoundError(VectorStoreError):
    """Raised when attempting to update or delete a non-existent record."""


_METRIC_FUNCTIONS = {
    "l2": lambda a, b: np.linalg.norm(a - b, axis=1),
    "euclidean": lambda a, b: np.linalg.norm(a - b, axis=1),
    "cosine": lambda a, b: (
        1
        - np.sum(a * b, axis=1)
        / (np.linalg.norm(a, axis=1) * np.linalg.norm(b) + 1e-12)
    ),
    "inner_product": lambda a, b: -np.sum(a * b, axis=1),
    "ip": lambda a, b: -np.sum(a * b, axis=1),
}


class NumpyVectorStore:
    """In-memory vector store backed by NumPy arrays.

    The store keeps vectors and metadata in Python structures while exposing
    a FAISS-inspired API for add, upsert, delete, and query operations.
    Supports ``l2`` / ``euclidean``, ``cosine``, and ``inner_product`` /
    ``ip`` distance metrics.
    """

    def __init__(self, *, dimension: int, metric: str = "l2") -> None:
        """Initialise an empty vector store.

        Args:
            dimension: Expected dimensionality of all vectors stored in this
                index. Every vector passed to :meth:`add` or :meth:`upsert`
                must have exactly this many elements.
            metric: Distance metric used during similarity queries. Supported
                values are ``"l2"`` (or ``"euclidean"``), ``"cosine"``, and
                ``"inner_product"`` (or ``"ip"``). Defaults to ``"l2"``.

        Raises:
            ValueError: If ``metric`` is not one of the supported values.
        """
        self._dimension = dimension
        self._metric_name = metric.lower()
        if self._metric_name not in _METRIC_FUNCTIONS:
            raise ValueError(f"Unsupported metric '{metric}'")
        self._vectors: MutableMapping[str, np.ndarray] = {}
        self._metadata: MutableMapping[str, Mapping[str, object]] = {}

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def dimension(self) -> int:
        """Return the fixed vector dimensionality of this store."""
        return self._dimension

    def add(self, records: Iterable[VectorRecord]) -> None:
        """Insert records into the store, overwriting any duplicate IDs.

        Duplicate ``record_id`` values result in a warning and the existing
        vector and metadata are replaced. Use :meth:`upsert` when silent
        overwrites are the desired behaviour.

        Args:
            records: Iterable of :class:`VectorRecord` objects to insert.

        Raises:
            ValueError: If any vector's dimensionality does not match
                :attr:`dimension`.
        """
        for record in records:
            vector = self._coerce_vector(record.vector)
            if record.record_id in self._vectors:
                LOGGER.warning(
                    "Overwriting existing record %s in add()", record.record_id
                )
            self._vectors[record.record_id] = vector
            self._metadata[record.record_id] = dict(record.metadata)

    def upsert(self, records: Iterable[VectorRecord]) -> None:
        """Insert or update records in the store without warnings.

        Idempotent: calling upsert with the same ``record_id`` simply
        replaces the stored vector and metadata with the new values.

        Args:
            records: Iterable of :class:`VectorRecord` objects to upsert.

        Raises:
            ValueError: If any vector's dimensionality does not match
                :attr:`dimension`.
        """
        for record in records:
            vector = self._coerce_vector(record.vector)
            self._vectors[record.record_id] = vector
            self._metadata[record.record_id] = dict(record.metadata)

    def delete(self, record_ids: Iterable[str]) -> None:
        """Remove records from the store by ID.

        Non-existent IDs are silently ignored.

        Args:
            record_ids: Iterable of record identifiers to remove.
        """
        for record_id in record_ids:
            self._vectors.pop(record_id, None)
            self._metadata.pop(record_id, None)

    def query(
        self,
        vector: Sequence[float],
        *,
        k: int = 5,
        filter_fn: Optional[Callable[[QueryResult], bool]] = None,
    ) -> List[QueryResult]:
        """Return the ``k`` nearest records to the given query vector.

        Results are ordered by ascending distance (or descending similarity
        for ``inner_product`` / ``ip``).

        Args:
            vector: Query embedding of length :attr:`dimension`.
            k: Maximum number of results to return. Actual count may be
                smaller if the store contains fewer than ``k`` records or
                ``filter_fn`` eliminates candidates.
            filter_fn: Optional predicate applied to each candidate
                :class:`QueryResult`. Only results for which the function
                returns ``True`` are included in the output.

        Returns:
            List of :class:`QueryResult` ordered by closeness to the query.

        Raises:
            ValueError: If ``vector`` has wrong dimensionality.
        """
        if not self._vectors:
            return []
        query_vec = self._coerce_vector(vector)
        matrix = np.vstack(list(self._vectors.values()))
        ids = list(self._vectors.keys())

        scores = _METRIC_FUNCTIONS[self._metric_name](matrix, query_vec)
        if self._metric_name in {"l2", "euclidean", "cosine"}:
            indices = np.argsort(scores)[:k]
        else:  # inner product variants already negated for descending order
            indices = np.argsort(scores)[:k]

        results: List[QueryResult] = []
        for idx in indices:
            record_id = ids[int(idx)]
            score = float(scores[int(idx)])
            metadata = self._metadata.get(record_id, {})
            result = QueryResult(record_id=record_id, score=score, metadata=metadata)
            if filter_fn and not filter_fn(result):
                continue
            results.append(result)
        return results

    def save(self, path: str) -> None:
        """Persist the vector store to a local directory.

        Writes two files:

        - ``vectors.npy`` — Plain float32 matrix of shape ``(n, dimension)``.
          No pickle is used; the file contains only numeric data.
        - ``metadata.json`` — JSON file containing record IDs (in row order),
          record metadata, the dimension, and the metric name.

        Args:
            path: Directory path to write files into. Created if absent.
        """
        os.makedirs(path, exist_ok=True)
        vectors_path = os.path.join(path, "vectors.npy")
        meta_path = os.path.join(path, "metadata.json")

        ids = list(self._vectors.keys())
        matrix = (
            np.vstack(list(self._vectors.values()))
            if self._vectors
            else np.empty((0, self._dimension), dtype=np.float32)
        )
        np.save(vectors_path, matrix)
        with open(meta_path, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "ids": ids,
                    "metadata": self._metadata,
                    "dimension": self._dimension,
                    "metric": self._metric_name,
                },
                handle,
            )

    @classmethod
    def load(cls, path: str) -> "NumpyVectorStore":
        """Restore a vector store previously saved with :meth:`save`.

        Args:
            path: Directory path containing ``vectors.npy`` and
                ``metadata.json`` produced by :meth:`save`.

        Returns:
            A :class:`NumpyVectorStore` instance populated with the saved
            vectors and metadata.

        Raises:
            VectorStoreError: If either required file is missing in ``path``.
        """
        vectors_path = os.path.join(path, "vectors.npy")
        meta_path = os.path.join(path, "metadata.json")

        if not os.path.exists(vectors_path) or not os.path.exists(meta_path):
            raise VectorStoreError(f"Missing vector store files in {path!r}")

        matrix = np.load(vectors_path, allow_pickle=False)
        with open(meta_path, "r", encoding="utf-8") as handle:
            metadata_blob = json.load(handle)

        dimension = metadata_blob["dimension"]
        metric = metadata_blob["metric"]
        store = cls(dimension=dimension, metric=metric)

        ids = metadata_blob["ids"]
        for record_id, vector in zip(ids, matrix):
            store._vectors[str(record_id)] = np.asarray(vector, dtype=np.float32)
        store._metadata = {str(k): v for k, v in metadata_blob["metadata"].items()}
        return store

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _coerce_vector(self, vector: Sequence[float]) -> np.ndarray:
        """Validate and convert a vector sequence to a fixed-dtype NumPy array.

        Args:
            vector: Sequence of numeric values to convert.

        Returns:
            A 1-D ``float32`` NumPy array of shape ``(dimension,)``.

        Raises:
            ValueError: If the resulting array shape does not match
                ``(dimension,)``.
        """
        arr = np.asarray(vector, dtype=np.float32)
        if arr.shape != (self._dimension,):
            raise ValueError(
                f"Vector dimensionality mismatch: expected ({self._dimension},) got {arr.shape}"
            )
        return arr
