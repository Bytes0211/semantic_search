"""Preprocessing pipeline that wires TextCleaner and TextChunker over Records.

:class:`PreprocessingPipeline` sits between the ingestion connectors and the
embedding pipeline.  It consumes :class:`~semantic_search.ingestion.base.Record`
objects, cleans and optionally chunks their text, and re-emits canonical
:class:`~semantic_search.ingestion.base.Record` objects ready for embedding.
"""

from __future__ import annotations

import logging
from typing import Iterable, Iterator, Optional

from ..ingestion.base import Record
from .chunker import TextChunker
from .cleaner import TextCleaner

__all__ = ["PreprocessingPipeline"]

LOGGER = logging.getLogger(__name__)


class PreprocessingPipeline:
    """Applies cleaning and optional chunking to a stream of :class:`Record` objects.

    Both the cleaner and the chunker are optional.  When neither is supplied,
    records pass through unchanged (useful for testing or when the source data
    is already clean and short enough for the embedding provider).

    Chunking behaviour:

    - Records whose text fits within ``chunk_size`` are emitted unchanged.
    - Records that are split produce N child records with IDs of the form
      ``{original_id}#chunk-{index}`` (zero-based).  Each child record's
      metadata is enriched with ``chunk_index``, ``chunk_count``, and
      ``original_id`` keys.

    Records that produce empty text after cleaning are dropped and logged
    at WARNING level.

    Args:
        cleaner: Optional :class:`TextCleaner` to apply before chunking.
        chunker: Optional :class:`TextChunker` to apply after cleaning.

    Example:
        >>> from semantic_search.ingestion.base import Record
        >>> cleaner = TextCleaner()
        >>> chunker = TextChunker(chunk_size=100, overlap=20)
        >>> pipeline = PreprocessingPipeline(cleaner=cleaner, chunker=chunker)
        >>> records = [Record("r1", "<p>Hello world</p>", {}, "csv")]
        >>> list(pipeline.process(records))
        [Record(record_id='r1', text='Hello world', metadata={}, source='csv')]
    """

    def __init__(
        self,
        *,
        cleaner: Optional[TextCleaner] = None,
        chunker: Optional[TextChunker] = None,
    ) -> None:
        self._cleaner = cleaner
        self._chunker = chunker

    def process(self, records: Iterable[Record]) -> Iterator[Record]:
        """Yield preprocessed records from *records*.

        Args:
            records: Iterable of :class:`Record` objects from any connector.

        Yields:
            Cleaned and optionally chunked :class:`Record` instances.
            Records that become empty after cleaning are silently dropped
            (a WARNING is logged for each).
        """
        for record in records:
            text = record.text

            if self._cleaner is not None:
                text = self._cleaner.clean(text)

            if not text:
                LOGGER.warning(
                    "PreprocessingPipeline: record_id=%r produced empty text "
                    "after cleaning; dropping.",
                    record.record_id,
                )
                continue

            if self._chunker is not None:
                chunks = self._chunker.chunk(text)
                if not chunks:
                    LOGGER.warning(
                        "PreprocessingPipeline: record_id=%r produced no chunks "
                        "after chunking; dropping.",
                        record.record_id,
                    )
                    continue
            else:
                chunks = [text]

            if len(chunks) == 1:
                yield Record(
                    record_id=record.record_id,
                    text=chunks[0],
                    metadata=record.metadata,
                    source=record.source,
                )
            else:
                for index, chunk_text in enumerate(chunks):
                    yield Record(
                        record_id=f"{record.record_id}#chunk-{index}",
                        text=chunk_text,
                        metadata={
                            **record.metadata,
                            "chunk_index": index,
                            "chunk_count": len(chunks),
                            "original_id": record.record_id,
                        },
                        source=record.source,
                    )
