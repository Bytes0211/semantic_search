"""Tests for semantic_search.config.source."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from semantic_search.config.source import (
    SourceConfig,
    SourceConfigError,
    load_source_configs,
    parse_source_config,
)


class TestParseSourceConfig:
    """Verify source YAML parsing."""

    def test_minimal_valid(self) -> None:
        raw = {"connector": {"type": "csv", "config": {"path": "data.csv"}}}
        cfg = parse_source_config("test", raw)
        assert cfg.name == "test"
        assert cfg.connector.type == "csv"
        assert cfg.connector.config["path"] == "data.csv"

    def test_full_config(self) -> None:
        raw = {
            "connector": {"type": "sql", "config": {"query": "SELECT 1"}},
            "text_fields": ["title", "body"],
            "id_field": "id",
            "metadata_fields": ["status"],
            "detail_fields": ["body"],
            "id_prefix": "ticket",
            "display": {
                "result_card": {"title_field": "title", "columns": ["status"]},
                "record_detail": {"sections": ["body"]},
            },
        }
        cfg = parse_source_config("tickets", raw)
        assert cfg.text_fields == ["title", "body"]
        assert cfg.id_prefix == "ticket"
        assert cfg.display.title_field == "title"

    def test_empty_raw_raises(self) -> None:
        with pytest.raises(SourceConfigError, match="non-empty"):
            parse_source_config("bad", {})

    def test_missing_connector_raises(self) -> None:
        with pytest.raises(SourceConfigError, match="connector"):
            parse_source_config("bad", {"text_fields": ["a"]})

    def test_missing_connector_type_raises(self) -> None:
        with pytest.raises(SourceConfigError, match="type"):
            parse_source_config("bad", {"connector": {"config": {}}})

    def test_comma_string_text_fields(self) -> None:
        raw = {
            "connector": {"type": "csv", "config": {}},
            "text_fields": "title,body",
        }
        cfg = parse_source_config("test", raw)
        assert cfg.text_fields == ["title", "body"]


class TestLoadSourceConfigs:
    """Verify directory-based source config loading."""

    def test_loads_yaml_files(self, tmp_path: Path) -> None:
        src_dir = tmp_path / "sources"
        src_dir.mkdir()
        (src_dir / "alpha.yaml").write_text(
            yaml.dump({"connector": {"type": "csv", "config": {"path": "a.csv"}}})
        )
        (src_dir / "beta.yml").write_text(
            yaml.dump({"connector": {"type": "json", "config": {"path": "b.json"}}})
        )
        # Non-YAML file should be ignored
        (src_dir / "readme.txt").write_text("ignore me")

        configs = load_source_configs(src_dir)
        assert len(configs) == 2
        assert "alpha" in configs
        assert "beta" in configs
        assert configs["alpha"].connector.type == "csv"

    def test_nonexistent_dir_returns_empty(self, tmp_path: Path) -> None:
        configs = load_source_configs(tmp_path / "nope")
        assert configs == {}
