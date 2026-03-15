"""Text chunking utilities for the preprocessing pipeline.

Provides :class:`TextChunker`, which splits long text into overlapping
character-bounded chunks at word boundaries, preventing embedding provider
token-limit failures on large documents.
"""

from __future__ import annotations

from typing import List

__all__ = ["TextChunker"]


class TextChunker:
    """Splits text into overlapping chunks at word boundaries.

    Each chunk is at most ``chunk_size`` characters long (measured after
    joining words with spaces).  Consecutive chunks share ``overlap``
    characters of context at their boundaries to preserve continuity across
    splits.

    Text shorter than or equal to ``chunk_size`` is returned as a single-
    element list without modification.

    Args:
        chunk_size: Maximum character length per chunk.  Defaults to 512.
        overlap: Number of characters to re-include at the start of each
            subsequent chunk.  Defaults to 50.  Must be less than
            ``chunk_size``.

    Raises:
        ValueError: If ``chunk_size`` is not a positive integer, ``overlap``
            is negative, or ``overlap`` is greater than or equal to
            ``chunk_size``.

    Example:
        >>> chunker = TextChunker(chunk_size=20, overlap=5)
        >>> chunks = chunker.chunk("The quick brown fox jumps over the lazy dog")
        >>> len(chunks) > 1
        True
    """

    def __init__(self, *, chunk_size: int = 512, overlap: int = 50) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be a positive integer")
        if overlap < 0:
            raise ValueError("overlap must be non-negative")
        if overlap >= chunk_size:
            raise ValueError("overlap must be less than chunk_size")
        self._chunk_size = chunk_size
        self._overlap = overlap

    def chunk(self, text: str) -> List[str]:
        """Split *text* into overlapping character-bounded chunks.

        Splitting occurs at word boundaries; a word that would exceed the
        chunk size is included in full to avoid truncating tokens.

        Args:
            text: Input string to split.

        Returns:
            A list of non-empty string chunks.  Returns ``[]`` when *text*
            is empty or contains only whitespace.  Returns ``[text]`` when
            ``len(text) <= chunk_size``.
        """
        if not text or not text.strip():
            return []
        if len(text) <= self._chunk_size:
            return [text]

        words = text.split()
        if not words:
            return []

        chunks: List[str] = []
        start = 0  # index into words[]

        while start < len(words):
            # Greedily consume words until the next one would exceed chunk_size.
            end = start
            char_count = 0
            while end < len(words):
                added = len(words[end]) + (1 if end > start else 0)  # +1 for space
                if char_count + added > self._chunk_size and end > start:
                    # Would overflow — stop here (but always take at least one
                    # word so we can't loop forever on a very long single word).
                    break
                char_count += added
                end += 1

            chunks.append(" ".join(words[start:end]))

            if end >= len(words):
                break

            # Roll back from `end` by roughly `overlap` characters to find
            # the start of the next chunk.  Skip entirely when overlap is 0
            # so consecutive chunks never share words.
            if self._overlap == 0:
                start = end
            else:
                back_chars = 0
                next_start = end  # default: no overlap
                for k in range(end - 1, start, -1):
                    back_chars += len(words[k]) + 1  # +1 for space
                    if back_chars >= self._overlap:
                        next_start = k
                        break

                # Always advance by at least one word to guarantee termination.
                start = max(next_start, start + 1)

        return chunks if chunks else []
