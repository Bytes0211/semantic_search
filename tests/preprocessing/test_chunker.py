"""Unit tests for semantic_search.preprocessing.chunker.TextChunker."""

import pytest

from semantic_search.preprocessing.chunker import TextChunker


class TestTextChunkerValidation:
    """Constructor validation."""

    def test_zero_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size"):
            TextChunker(chunk_size=0)

    def test_negative_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="chunk_size"):
            TextChunker(chunk_size=-1)

    def test_negative_overlap_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            TextChunker(chunk_size=100, overlap=-1)

    def test_overlap_equal_to_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            TextChunker(chunk_size=50, overlap=50)

    def test_overlap_greater_than_chunk_size_raises(self) -> None:
        with pytest.raises(ValueError, match="overlap"):
            TextChunker(chunk_size=50, overlap=60)


class TestTextChunkerShortText:
    """Text that fits within chunk_size is returned as a single chunk."""

    def setup_method(self) -> None:
        self.chunker = TextChunker(chunk_size=100, overlap=20)

    def test_short_text_single_chunk(self) -> None:
        text = "Hello world"
        chunks = self.chunker.chunk(text)
        assert chunks == [text]

    def test_text_exactly_chunk_size_single_chunk(self) -> None:
        text = "a" * 100
        chunks = self.chunker.chunk(text)
        assert chunks == [text]

    def test_empty_string_returns_single_empty_chunk(self) -> None:
        chunks = self.chunker.chunk("")
        assert chunks == [""]

    def test_single_word_shorter_than_chunk_size(self) -> None:
        chunks = self.chunker.chunk("word")
        assert chunks == ["word"]


class TestTextChunkerSplitting:
    """Text that exceeds chunk_size is split into multiple chunks."""

    def test_produces_multiple_chunks(self) -> None:
        chunker = TextChunker(chunk_size=20, overlap=0)
        text = "The quick brown fox jumps over the lazy dog"
        chunks = chunker.chunk(text)
        assert len(chunks) > 1

    def test_no_chunk_exceeds_chunk_size(self) -> None:
        chunker = TextChunker(chunk_size=30, overlap=5)
        text = " ".join(["word"] * 50)
        for chunk in chunker.chunk(text):
            assert len(chunk) <= 30

    def test_all_words_covered(self) -> None:
        """Every word in the original text should appear in at least one chunk."""
        chunker = TextChunker(chunk_size=20, overlap=5)
        words = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]
        text = " ".join(words)
        all_chunk_text = " ".join(chunker.chunk(text))
        for word in words:
            assert word in all_chunk_text

    def test_zero_overlap_no_repeated_words_at_boundaries(self) -> None:
        chunker = TextChunker(chunk_size=15, overlap=0)
        text = "aaa bbb ccc ddd eee fff"
        chunks = chunker.chunk(text)
        assert len(chunks) > 1
        # With zero overlap the concatenated chunks should contain each word exactly once
        combined_words = [w for chunk in chunks for w in chunk.split()]
        assert len(combined_words) == len(set(combined_words))

    def test_with_overlap_boundary_words_repeated(self) -> None:
        """Words near chunk boundaries should appear in consecutive chunks."""
        chunker = TextChunker(chunk_size=20, overlap=8)
        text = "alpha beta gamma delta epsilon zeta eta theta iota"
        chunks = chunker.chunk(text)
        assert len(chunks) > 1
        # The last word of chunk[0] should appear somewhere in chunk[1]
        last_word_of_first = chunks[0].split()[-1]
        assert last_word_of_first in chunks[1]

    def test_single_very_long_word_not_dropped(self) -> None:
        """A word longer than chunk_size must still be emitted as its own chunk."""
        chunker = TextChunker(chunk_size=5, overlap=0)
        text = "superlongword short"
        chunks = chunker.chunk(text)
        all_text = " ".join(chunks)
        assert "superlongword" in all_text

    def test_deterministic_output(self) -> None:
        chunker = TextChunker(chunk_size=25, overlap=10)
        text = "repeat " * 20
        assert chunker.chunk(text) == chunker.chunk(text)


class TestTextChunkerDefaults:
    """Smoke test with default parameters (chunk_size=512, overlap=50)."""

    def test_short_text_not_split(self) -> None:
        chunker = TextChunker()
        text = "A short piece of text."
        assert chunker.chunk(text) == [text]

    def test_long_text_split(self) -> None:
        chunker = TextChunker()
        # Build a text clearly larger than 512 chars
        text = ("This is a sentence that is of moderate length. " * 15).strip()
        assert len(text) > 512
        chunks = chunker.chunk(text)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 512
