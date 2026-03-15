"""Unit tests for the MongoDB data source connector.

Uses ``mongomock`` to simulate a real MongoDB server so no live instance is
required.  ``pymongo.MongoClient`` is patched with the mongomock client for
each test via ``unittest.mock.patch``.
"""

from __future__ import annotations

import sys
from typing import Any, Dict, List
from unittest.mock import patch

import mongomock
import pytest

from semantic_search.ingestion import DataSourceError, get_connector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

URI = "mongodb://localhost:27017"
DB = "test_db"


def _make_client(docs_by_collection: Dict[str, List[Dict[str, Any]]]) -> mongomock.MongoClient:
    """Build a seeded mongomock client.

    Args:
        docs_by_collection: Mapping of collection name to list of documents to
            insert.

    Returns:
        A mongomock MongoClient with the specified collections seeded.
    """
    client = mongomock.MongoClient()
    db = client[DB]
    for collection, docs in docs_by_collection.items():
        if docs:
            db[collection].insert_many(docs)
    return client


def _extract(config: Dict[str, Any], client: mongomock.MongoClient) -> list:
    """Create a connector and extract records using a patched MongoClient.

    Args:
        config: Connector configuration dict.
        client: Pre-seeded mongomock client to inject.

    Returns:
        List of extracted :class:`~semantic_search.ingestion.base.Record`
        objects.
    """
    connector = get_connector("mongodb", config)
    with patch("pymongo.MongoClient", return_value=client):
        return list(connector.extract())


# ---------------------------------------------------------------------------
# Basic extraction
# ---------------------------------------------------------------------------


def test_basic_extraction_text_and_source() -> None:
    """Records are extracted with correct text concatenation and source tag."""
    client = _make_client({"tickets": [
        {"_id": 1, "title": "Login issue", "body": "User cannot login"},
        {"_id": 2, "title": "Slow search", "body": "Results take 10 seconds"},
    ]})

    records = _extract(
        {
            "uri": URI, "database": DB, "collection": "tickets",
            "text_fields": ["title", "body"],
        },
        client,
    )

    assert len(records) == 2
    assert records[0].text == "Login issue | User cannot login"
    assert records[1].text == "Slow search | Results take 10 seconds"
    assert all(r.source == "mongodb" for r in records)


def test_objectid_converted_to_string() -> None:
    """The default ``_id`` ObjectId is coerced to a string record_id."""
    client = _make_client({"items": [
        {"_id": 42, "title": "Test record"},
    ]})

    records = _extract(
        {"uri": URI, "database": DB, "collection": "items", "text_fields": ["title"]},
        client,
    )

    assert records[0].record_id == "42"


def test_custom_id_field() -> None:
    """A non-``_id`` field can be used as the record identifier."""
    client = _make_client({"candidates": [
        {"_id": 1, "slug": "alice-okonkwo", "name": "Alice Okonkwo", "bio": "Data engineer"},
    ]})

    records = _extract(
        {
            "uri": URI, "database": DB, "collection": "candidates",
            "text_fields": ["name", "bio"],
            "id_field": "slug",
        },
        client,
    )

    assert records[0].record_id == "alice-okonkwo"


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_metadata_fields_populated() -> None:
    """Specified metadata fields are extracted and stored correctly."""
    client = _make_client({"tickets": [
        {"_id": 1, "title": "Export broken", "body": "CSV fails",
         "category": "export", "priority": "high", "status": "open"},
    ]})

    records = _extract(
        {
            "uri": URI, "database": DB, "collection": "tickets",
            "text_fields": ["title", "body"],
            "metadata_fields": ["category", "priority", "status"],
        },
        client,
    )

    assert records[0].metadata == {
        "category": "export",
        "priority": "high",
        "status": "open",
    }


def test_missing_metadata_field_is_omitted() -> None:
    """Metadata fields absent from a document are silently omitted."""
    client = _make_client({"tickets": [
        {"_id": 1, "title": "Minimal record"},
    ]})

    records = _extract(
        {
            "uri": URI, "database": DB, "collection": "tickets",
            "text_fields": ["title"],
            "metadata_fields": ["category", "priority"],
        },
        client,
    )

    assert records[0].metadata == {}


def test_null_metadata_value_is_omitted() -> None:
    """Metadata fields with a ``None`` value are excluded from the record."""
    client = _make_client({"tickets": [
        {"_id": 1, "title": "Partial", "category": None, "priority": "low"},
    ]})

    records = _extract(
        {
            "uri": URI, "database": DB, "collection": "tickets",
            "text_fields": ["title"],
            "metadata_fields": ["category", "priority"],
        },
        client,
    )

    assert "category" not in records[0].metadata
    assert records[0].metadata["priority"] == "low"


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------


def test_filter_restricts_results() -> None:
    """A MongoDB query filter reduces the number of documents returned."""
    client = _make_client({"tickets": [
        {"_id": 1, "title": "A", "body": "open high",   "status": "open"},
        {"_id": 2, "title": "B", "body": "closed low",  "status": "closed"},
        {"_id": 3, "title": "C", "body": "open medium", "status": "open"},
    ]})

    records = _extract(
        {
            "uri": URI, "database": DB, "collection": "tickets",
            "text_fields": ["title", "body"],
            "filter": {"status": "open"},
        },
        client,
    )

    assert len(records) == 2
    assert {r.record_id for r in records} == {"1", "3"}


# ---------------------------------------------------------------------------
# Empty collection
# ---------------------------------------------------------------------------


def test_empty_collection_returns_no_records() -> None:
    """An empty collection yields zero records without error."""
    client = _make_client({"empty": []})

    records = _extract(
        {"uri": URI, "database": DB, "collection": "empty", "text_fields": ["title"]},
        client,
    )

    assert records == []


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_missing_id_field_raises() -> None:
    """A document without the configured id field raises DataSourceError."""
    client = _make_client({"items": [
        {"_id": 1, "title": "No custom id"},
    ]})

    connector = get_connector("mongodb", {
        "uri": URI, "database": DB, "collection": "items",
        "text_fields": ["title"],
        "id_field": "slug",  # not present in document
    })
    with patch("pymongo.MongoClient", return_value=client):
        with pytest.raises(DataSourceError, match="slug"):
            list(connector.extract())


def test_missing_text_field_raises() -> None:
    """A document missing an expected text field raises DataSourceError."""
    client = _make_client({"items": [
        {"_id": 1, "title": "Only title"},
    ]})

    connector = get_connector("mongodb", {
        "uri": URI, "database": DB, "collection": "items",
        "text_fields": ["title", "body"],  # body not in document
    })
    with patch("pymongo.MongoClient", return_value=client):
        with pytest.raises(DataSourceError, match="body"):
            list(connector.extract())


def test_pymongo_not_installed_raises() -> None:
    """A helpful DataSourceError is raised when pymongo is not importable."""
    connector = get_connector("mongodb", {
        "uri": URI, "database": DB, "collection": "items",
        "text_fields": ["title"],
    })
    with patch.dict(sys.modules, {"pymongo": None}):
        with pytest.raises(DataSourceError, match="pymongo is required"):
            list(connector.extract())


def test_missing_required_config_key_raises() -> None:
    """Omitting a required config key (e.g. uri) raises DataSourceError."""
    with pytest.raises(DataSourceError, match="uri"):
        get_connector("mongodb", {
            "database": DB, "collection": "items", "text_fields": ["title"],
        })


def test_invalid_text_fields_type_raises() -> None:
    """Passing a string instead of a list for text_fields raises DataSourceError."""
    with pytest.raises(DataSourceError):
        get_connector("mongodb", {
            "uri": URI, "database": DB, "collection": "items",
            "text_fields": "title",  # should be a list
        })
