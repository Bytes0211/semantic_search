"""Core abstractions for pluggable data source connectors.

This module defines the canonical ``Record`` schema emitted by all ingestion
connectors, along with the ``DataSourceConnector`` abstract base class that
each concrete implementation must extend.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterator, Mapping

__all__ = [
    "Record",
    "DataSourceError",
    "DataSourceConnector",
]


@dataclass(frozen=True)
class Record:
    """Canonical representation of a single item emitted by a data source.

    Attributes:
        record_id: Unique, stable identifier for the record. Should be
            deterministic so the same source row produces the same ID across
            runs.
        text: Concatenated natural-language content to embed. This is the only
            field considered during semantic ranking.
        metadata: Additional attributes stored alongside the vector for use in
            filters and result presentation.
        source: Logical backend identifier (e.g. ``"csv"``, ``"sql"``) that
            generated this record.
    """

    record_id: str
    text: str
    metadata: Mapping[str, Any]
    source: str


class DataSourceError(RuntimeError):
    """Raised when a connector cannot read or normalise records from its source."""


class DataSourceConnector(ABC):
    """Abstract base class for pluggable data source connectors."""

    @abstractmethod
    def extract(self) -> Iterator[Record]:
        """Yield canonical records from the underlying data source.

        Implementations should be safe to iterate multiple times and must not
        silently drop records—raise :class:`DataSourceError` when anomalies
        occur.

        Yields:
            Normalised :class:`Record` instances ready for the embedding
            pipeline.

        Raises:
            DataSourceError: If the source cannot be accessed or a record fails
                normalisation.
        """
        raise NotImplementedError
