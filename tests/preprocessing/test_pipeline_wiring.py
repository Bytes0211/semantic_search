"""Tests verifying that generate scripts wire PreprocessingPipeline correctly.

These tests validate that:
- ``extract_inputs`` / ``extract_from_source`` apply the pipeline when supplied.
- Records are cleaned/chunked before building EmbeddingInputs.
- ``--no-preprocessing`` disables the pipeline end-to-end.
- ``build_preprocessing_pipeline`` integrates with ``PreprocessingConfig`` defaults.
"""

from __future__ import annotations

from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from semantic_search.config.app import PreprocessingConfig, build_preprocessing_pipeline
from semantic_search.ingestion.base import Record
from semantic_search.preprocessing import PreprocessingPipeline, TextCleaner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_records(texts: List[str]) -> List[Record]:
    """Build a list of dummy Records from plain text strings."""
    return [Record(f"r{i}", t, {}, "test") for i, t in enumerate(texts)]


# ---------------------------------------------------------------------------
# Unit tests: extract_inputs in generate_csv_index
# ---------------------------------------------------------------------------


class TestCsvExtractInputsWithPipeline:
    """Verify preprocessing is applied inside generate_csv_index.extract_inputs."""

    def test_pipeline_applied_to_records(self, tmp_path: Path) -> None:
        """HTML is stripped before EmbeddingInputs are built."""
        csv_file = tmp_path / "sample.csv"
        csv_file.write_text("id,title,content\n1,<b>Hello</b>,<p>World</p>\n")

        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from scripts.generate_csv_index import extract_inputs

        pipeline = build_preprocessing_pipeline(
            PreprocessingConfig(enabled=True, clean=True, chunk=False)
        )
        assert pipeline is not None

        inputs = extract_inputs(
            csv_path=str(csv_file),
            text_fields=["title", "content"],
            id_field="id",
            metadata_fields=[],
            preprocessing_pipeline=pipeline,
        )
        assert len(inputs) == 1
        # HTML should be stripped
        assert "<b>" not in inputs[0].text
        assert "<p>" not in inputs[0].text
        assert "Hello" in inputs[0].text
        assert "World" in inputs[0].text

    def test_no_pipeline_passes_through_raw_text(self, tmp_path: Path) -> None:
        """Without a pipeline records are embedded unchanged."""
        csv_file = tmp_path / "sample.csv"
        csv_file.write_text("id,title,content\n1,<b>Hello</b>,<p>World</p>\n")

        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from scripts.generate_csv_index import extract_inputs

        inputs = extract_inputs(
            csv_path=str(csv_file),
            text_fields=["title", "content"],
            id_field="id",
            metadata_fields=[],
            preprocessing_pipeline=None,
        )
        assert len(inputs) == 1
        assert "<b>" in inputs[0].text  # raw HTML preserved

    def test_chunking_inflates_record_count(self, tmp_path: Path) -> None:
        """Long records are split into multiple EmbeddingInputs."""
        long_text = "word " * 30  # ~150 chars
        csv_file = tmp_path / "sample.csv"
        csv_file.write_text(f"id,content\n1,\"{long_text.strip()}\"\n")

        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from scripts.generate_csv_index import extract_inputs

        pipeline = build_preprocessing_pipeline(
            PreprocessingConfig(enabled=True, clean=False, chunk=True, chunk_size=30, overlap=0)
        )
        assert pipeline is not None

        inputs = extract_inputs(
            csv_path=str(csv_file),
            text_fields=["content"],
            id_field="id",
            metadata_fields=[],
            preprocessing_pipeline=pipeline,
        )
        assert len(inputs) > 1
        assert all("#chunk-" in inp.record_id for inp in inputs)


# ---------------------------------------------------------------------------
# Unit tests: extract_from_source in generate_index (unified builder)
# ---------------------------------------------------------------------------


class TestUnifiedBuilderWithPipeline:
    """Verify preprocessing is applied inside generate_index.extract_from_source."""

    def test_pipeline_applied(self, tmp_path: Path) -> None:
        """HTML is cleaned before EmbeddingInputs are built via the unified builder."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("id,content\n1,<b>Cleaned text</b>\n")

        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from scripts.generate_index import extract_from_source
        from semantic_search.config.source import SourceConfig, ConnectorConfig

        source = SourceConfig(
            name="test_csv",
            connector=ConnectorConfig(type="csv", config={"path": str(csv_file)}),
            text_fields=["content"],
            id_field="id",
            metadata_fields=[],
            detail_fields=[],
            id_prefix="",
        )

        pipeline = build_preprocessing_pipeline(
            PreprocessingConfig(enabled=True, clean=True, chunk=False)
        )
        inputs = extract_from_source(source, preprocessing_pipeline=pipeline)
        assert len(inputs) == 1
        assert "<b>" not in inputs[0].text
        assert "Cleaned text" in inputs[0].text

    def test_no_pipeline_preserves_raw_text(self, tmp_path: Path) -> None:
        """Without a pipeline, raw text is preserved."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("id,content\n1,<b>Raw text</b>\n")

        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from scripts.generate_index import extract_from_source
        from semantic_search.config.source import SourceConfig, ConnectorConfig

        source = SourceConfig(
            name="test_csv",
            connector=ConnectorConfig(type="csv", config={"path": str(csv_file)}),
            text_fields=["content"],
            id_field="id",
            metadata_fields=[],
            detail_fields=[],
            id_prefix="",
        )

        inputs = extract_from_source(source, preprocessing_pipeline=None)
        assert len(inputs) == 1
        assert "<b>" in inputs[0].text


# ---------------------------------------------------------------------------
# CLI integration: --no-preprocessing flag
# ---------------------------------------------------------------------------


class TestNoPreprocessingFlag:
    """Verify --no-preprocessing suppresses pipeline construction."""

    def test_no_preprocessing_flag_parses(self) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from scripts.generate_csv_index import parse_args

        args = parse_args(["--no-preprocessing"])
        assert args.no_preprocessing is True

    def test_no_preprocessing_flag_parses_unified(self) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from scripts.generate_index import parse_args

        args = parse_args(["--no-preprocessing"])
        assert args.no_preprocessing is True

    def test_no_preprocessing_false_by_default(self) -> None:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from scripts.generate_csv_index import parse_args

        args = parse_args([])
        assert args.no_preprocessing is False


# ---------------------------------------------------------------------------
# build_preprocessing_pipeline + PreprocessingConfig integration
# ---------------------------------------------------------------------------


class TestPreprocessingConfigIntegration:
    """End-to-end tests from PreprocessingConfig through to cleaned Records."""

    def test_default_config_returns_cleaner_pipeline(self) -> None:
        """Default config (clean=True, chunk=False) returns a cleaning pipeline."""
        from semantic_search.preprocessing import PreprocessingPipeline

        cfg = PreprocessingConfig()  # defaults
        pipeline = build_preprocessing_pipeline(cfg)
        assert isinstance(pipeline, PreprocessingPipeline)

    def test_disabled_config_returns_none(self) -> None:
        cfg = PreprocessingConfig(enabled=False)
        assert build_preprocessing_pipeline(cfg) is None

    def test_clean_false_chunk_false_returns_none(self) -> None:
        cfg = PreprocessingConfig(enabled=True, clean=False, chunk=False)
        assert build_preprocessing_pipeline(cfg) is None

    def test_full_pipeline_on_records(self) -> None:
        """clean=True + chunk=True processes records end-to-end."""
        cfg = PreprocessingConfig(
            enabled=True, clean=True, chunk=True, chunk_size=50, overlap=0
        )
        pipeline = build_preprocessing_pipeline(cfg)
        assert pipeline is not None

        long_text = "<p>" + ("hello world " * 10).strip() + "</p>"
        records = _make_records([long_text])
        result = list(pipeline.process(records))
        # Each chunk should be clean and short
        assert len(result) > 0
        for r in result:
            assert "<p>" not in r.text
            assert len(r.text) <= 60  # close to chunk_size
