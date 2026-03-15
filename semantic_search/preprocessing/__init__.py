"""Preprocessing package for cleaning and chunking ingested records.

Exposes the three main classes used to build a preprocessing stage between
data source connectors and the embedding pipeline:

- :class:`TextCleaner` — strips HTML, normalizes Unicode and whitespace.
- :class:`TextChunker` — splits long text at word boundaries with overlap.
- :class:`PreprocessingPipeline` — composes cleaner + chunker over a stream
  of :class:`~semantic_search.ingestion.base.Record` objects.
"""

from .chunker import TextChunker
from .cleaner import TextCleaner
from .pipeline import PreprocessingPipeline

__all__ = [
    "TextCleaner",
    "TextChunker",
    "PreprocessingPipeline",
]
