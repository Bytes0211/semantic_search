"""Tests for semantic_search.config.metadata."""

from __future__ import annotations

from semantic_search.config.metadata import split_metadata


class TestSplitMetadata:
    """Verify shared split_metadata function."""

    def test_no_detail_fields(self) -> None:
        result = split_metadata({"a": 1, "b": 2}, set())
        assert result == {"a": 1, "b": 2}
        assert "_detail" not in result

    def test_all_detail_fields(self) -> None:
        result = split_metadata({"a": 1, "b": 2}, {"a", "b"})
        assert result == {"_detail": {"a": 1, "b": 2}}

    def test_partial_detail_fields(self) -> None:
        result = split_metadata({"a": 1, "b": 2, "c": 3}, {"b"})
        assert result == {"a": 1, "c": 3, "_detail": {"b": 2}}

    def test_empty_metadata(self) -> None:
        result = split_metadata({}, {"a"})
        assert result == {}

    def test_detail_field_not_present(self) -> None:
        result = split_metadata({"a": 1}, {"missing"})
        assert result == {"a": 1}
        assert "_detail" not in result
