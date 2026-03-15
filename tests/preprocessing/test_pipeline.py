"""Unit tests for semantic_search.preprocessing.pipeline.PreprocessingPipeline."""

import pytest

from semantic_search.ingestion.base import Record
from semantic_search.preprocessing.chunker import TextChunker
from semantic_search.preprocessing.cleaner import TextCleaner
from semantic_search.preprocessing.pipeline import PreprocessingPipeline


def make_record(record_id: str, text: str, metadata: dict | None = None) -> Record:
    """Helper to construct a Record for testing."""
    return Record(record_id=record_id, text=text, metadata=metadata or {}, source="test")


class TestPreprocessingPipelinePassthrough:
    """Pipeline with no cleaner and no chunker passes records through unchanged."""

    def test_single_record_unchanged(self) -> None:
        pipeline = PreprocessingPipeline()
        record = make_record("r1", "hello world")
        result = list(pipeline.process([record]))
        assert result == [record]

    def test_multiple_records_unchanged(self) -> None:
        pipeline = PreprocessingPipeline()
        records = [make_record(f"r{i}", f"text {i}") for i in range(5)]
        result = list(pipeline.process(records))
        assert result == records

    def test_empty_input_yields_nothing(self) -> None:
        pipeline = PreprocessingPipeline()
        assert list(pipeline.process([])) == []


class TestPreprocessingPipelineCleanerOnly:
    """Pipeline with cleaner but no chunker."""

    def setup_method(self) -> None:
        self.pipeline = PreprocessingPipeline(cleaner=TextCleaner())

    def test_html_stripped_from_text(self) -> None:
        record = make_record("r1", "<p>Hello <b>world</b></p>")
        result = list(self.pipeline.process([record]))
        assert len(result) == 1
        assert result[0].text == "Hello world"
        assert result[0].record_id == "r1"

    def test_metadata_and_source_preserved(self) -> None:
        record = Record("r1", "<em>text</em>", {"key": "val"}, "csv")
        result = list(self.pipeline.process([record]))
        assert result[0].metadata == {"key": "val"}
        assert result[0].source == "csv"

    def test_empty_text_after_cleaning_drops_record(self) -> None:
        record = make_record("r1", "<br/><br/>")
        result = list(self.pipeline.process([record]))
        assert result == []

    def test_empty_text_after_cleaning_logs_warning(self, caplog) -> None:
        import logging
        record = make_record("drop-me", "   ")
        with caplog.at_level(logging.WARNING, logger="semantic_search.preprocessing.pipeline"):
            list(self.pipeline.process([record]))
        assert "drop-me" in caplog.text

    def test_mixed_records_some_dropped(self) -> None:
        records = [
            make_record("good", "hello world"),
            make_record("bad", "<br/>  "),
            make_record("also-good", "<p>text</p>"),
        ]
        result = list(self.pipeline.process(records))
        assert len(result) == 2
        assert result[0].record_id == "good"
        assert result[1].record_id == "also-good"


class TestPreprocessingPipelineChunkerOnly:
    """Pipeline with chunker but no cleaner."""

    def test_short_text_not_chunked(self) -> None:
        pipeline = PreprocessingPipeline(chunker=TextChunker(chunk_size=200, overlap=20))
        record = make_record("r1", "short text")
        result = list(pipeline.process([record]))
        assert len(result) == 1
        assert result[0].record_id == "r1"
        assert result[0].text == "short text"

    def test_long_text_produces_multiple_records(self) -> None:
        pipeline = PreprocessingPipeline(chunker=TextChunker(chunk_size=30, overlap=5))
        text = "word " * 30  # clearly longer than 30 chars
        record = make_record("r1", text.strip())
        result = list(pipeline.process([record]))
        assert len(result) > 1

    def test_chunk_ids_formatted_correctly(self) -> None:
        pipeline = PreprocessingPipeline(chunker=TextChunker(chunk_size=30, overlap=5))
        text = "word " * 30
        record = make_record("rec", text.strip())
        result = list(pipeline.process([record]))
        for i, r in enumerate(result):
            assert r.record_id == f"rec#chunk-{i}"

    def test_chunk_metadata_enriched(self) -> None:
        pipeline = PreprocessingPipeline(chunker=TextChunker(chunk_size=30, overlap=5))
        text = "word " * 30
        record = make_record("rec", text.strip(), {"category": "test"})
        result = list(pipeline.process([record]))
        assert len(result) > 1
        for i, r in enumerate(result):
            assert r.metadata["chunk_index"] == i
            assert r.metadata["chunk_count"] == len(result)
            assert r.metadata["original_id"] == "rec"
            assert r.metadata["category"] == "test"  # original metadata preserved

    def test_single_chunk_no_metadata_enrichment(self) -> None:
        pipeline = PreprocessingPipeline(chunker=TextChunker(chunk_size=500, overlap=20))
        record = make_record("r1", "short", {"key": "val"})
        result = list(pipeline.process([record]))
        assert len(result) == 1
        assert "chunk_index" not in result[0].metadata


class TestPreprocessingPipelineCombined:
    """Pipeline with both cleaner and chunker."""

    def test_cleans_then_chunks(self) -> None:
        cleaner = TextCleaner()
        chunker = TextChunker(chunk_size=30, overlap=5)
        pipeline = PreprocessingPipeline(cleaner=cleaner, chunker=chunker)
        html_text = "<p>" + " ".join(["word"] * 30) + "</p>"
        record = make_record("r1", html_text)
        result = list(pipeline.process([record]))
        # HTML stripped → chunked → multiple records, none containing <p>
        assert len(result) > 1
        for r in result:
            assert "<p>" not in r.text

    def test_generator_input_supported(self) -> None:
        """process() should work with generator inputs, not just lists."""
        pipeline = PreprocessingPipeline(cleaner=TextCleaner())

        def gen():
            yield make_record("r1", "<b>hello</b>")
            yield make_record("r2", "<i>world</i>")

        result = list(pipeline.process(gen()))
        assert len(result) == 2
        assert result[0].text == "hello"
        assert result[1].text == "world"
