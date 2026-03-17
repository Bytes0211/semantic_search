"""Tests for semantic_search.config.display."""

from __future__ import annotations

import pytest

from semantic_search.config.display import (
    ColumnConfig,
    DetailSectionConfig,
    DisplayConfig,
    DisplayConfigError,
    parse_display_config,
)


class TestColumnConfig:
    """Verify ColumnConfig dataclass."""

    def test_auto_label(self) -> None:
        col = ColumnConfig(field="first_name")
        assert col.label == "First Name"

    def test_explicit_label(self) -> None:
        col = ColumnConfig(field="name", label="Full Name")
        assert col.label == "Full Name"

    def test_empty_field_raises(self) -> None:
        with pytest.raises(DisplayConfigError, match="non-empty"):
            ColumnConfig(field="")


class TestDetailSectionConfig:
    """Verify DetailSectionConfig dataclass."""

    def test_auto_label(self) -> None:
        sec = DetailSectionConfig(field="body_text")
        assert sec.label == "Body Text"

    def test_empty_field_raises(self) -> None:
        with pytest.raises(DisplayConfigError, match="non-empty"):
            DetailSectionConfig(field="")


class TestDisplayConfig:
    """Verify DisplayConfig dataclass and to_dict serialisation."""

    def test_to_dict(self) -> None:
        cfg = DisplayConfig(
            title_field="name",
            columns=[ColumnConfig(field="category", label="Cat")],
            detail_sections=[DetailSectionConfig(field="body", label="Body")],
        )
        d = cfg.to_dict()
        assert d["title_field"] == "name"
        assert len(d["columns"]) == 1
        assert d["columns"][0] == {"field": "category", "label": "Cat"}
        assert d["detail_sections"][0] == {"field": "body", "label": "Body"}

    def test_empty_config_to_dict(self) -> None:
        d = DisplayConfig().to_dict()
        assert d["title_field"] is None
        assert d["columns"] == []
        assert d["detail_sections"] == []


class TestParseDisplayConfig:
    """Verify YAML display block parsing."""

    def test_empty_raw_returns_default(self) -> None:
        result = parse_display_config({})
        assert result.title_field is None
        assert result.columns == []

    def test_none_raw_returns_default(self) -> None:
        result = parse_display_config(None)
        assert isinstance(result, DisplayConfig)

    def test_full_parse(self) -> None:
        raw = {
            "result_card": {
                "title_field": "title",
                "columns": [
                    {"field": "category", "label": "Category"},
                    "author",
                ],
            },
            "record_detail": {
                "sections": [
                    {"field": "content", "label": "Content"},
                ],
            },
        }
        result = parse_display_config(raw)
        assert result.title_field == "title"
        assert len(result.columns) == 2
        assert result.columns[0].label == "Category"
        assert result.columns[1].label == "Author"
        assert len(result.detail_sections) == 1
        assert result.detail_sections[0].label == "Content"

    def test_invalid_column_type_raises(self) -> None:
        raw = {"result_card": {"columns": [123]}}
        with pytest.raises(DisplayConfigError, match="Invalid column entry"):
            parse_display_config(raw)

    def test_string_only_columns(self) -> None:
        raw = {"result_card": {"columns": ["a", "b"]}}
        result = parse_display_config(raw)
        assert result.columns[0].field == "a"
        assert result.columns[0].label == "A"
