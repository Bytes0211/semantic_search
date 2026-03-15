"""PostgreSQL integration tests for the SQL data source connector.

These tests run against a live ``semantic_search_test`` PostgreSQL database
seeded with two tables: ``support_tickets`` and ``candidates``.

Prerequisites
-------------
- PostgreSQL 16 running locally on port 5432.
- Database ``semantic_search_test`` created and accessible to the OS user
  running the tests (peer authentication via Unix socket).
- Tables and data provisioned by ``developer/sql/seed_semantic_search_test.sql``
  (or the setup instructions in ``developer/pluggable_data_sources.md``).

Run only these tests::

    uv run pytest tests/ingestion/test_sql_pg_connector.py -v -m integration
"""

from __future__ import annotations

import pytest

from semantic_search.ingestion import DataSourceError, get_connector

# ---------------------------------------------------------------------------
# Shared connection string — peer auth over Unix socket, no password needed.
# ---------------------------------------------------------------------------
CONN = "postgresql+psycopg2:///semantic_search_test"


# ---------------------------------------------------------------------------
# support_tickets tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_support_tickets_basic_extraction() -> None:
    """All 10 seeded tickets are returned with correct text and source."""
    connector = get_connector(
        "sql",
        {
            "connection_string": CONN,
            "query": "SELECT id, title, body, category, priority, status, created_at FROM support_tickets ORDER BY id",
            "text_fields": ["title", "body"],
            "id_field": "id",
        },
    )

    records = list(connector.extract())

    assert len(records) == 10
    assert all(r.source == "sql" for r in records)
    # First record — canonical text concatenation
    assert records[0].text == (
        "Cannot log in after password reset | "
        "User reports being locked out after resetting password via email link. Error code 403."
    )
    assert records[0].record_id == "1"


@pytest.mark.integration
def test_support_tickets_metadata_fields() -> None:
    """Metadata fields are correctly populated and exclude text/id columns."""
    connector = get_connector(
        "sql",
        {
            "connection_string": CONN,
            "query": "SELECT id, title, body, category, priority, status FROM support_tickets ORDER BY id",
            "text_fields": ["title", "body"],
            "id_field": "id",
            "metadata_fields": ["category", "priority", "status"],
        },
    )

    records = list(connector.extract())

    assert records[0].metadata == {
        "category": "auth",
        "priority": "high",
        "status": "open",
    }
    # Resolved tickets appear with status=resolved
    resolved = [r for r in records if r.metadata.get("status") == "resolved"]
    assert len(resolved) == 2


@pytest.mark.integration
def test_support_tickets_filtered_query() -> None:
    """Only open high-priority tickets are returned when query filters the data."""
    connector = get_connector(
        "sql",
        {
            "connection_string": CONN,
            "query": (
                "SELECT id, title, body, category FROM support_tickets "
                "WHERE priority = 'high' AND status = 'open' ORDER BY id"
            ),
            "text_fields": ["title", "body"],
            "id_field": "id",
            "metadata_fields": ["category"],
        },
    )

    records = list(connector.extract())

    assert len(records) == 4
    categories = {r.metadata["category"] for r in records}
    assert "auth" in categories
    assert "performance" in categories


@pytest.mark.integration
def test_support_tickets_batch_size_streaming() -> None:
    """batch_size=2 streams correctly and yields all rows."""
    connector = get_connector(
        "sql",
        {
            "connection_string": CONN,
            "query": "SELECT id, title, body FROM support_tickets ORDER BY id",
            "text_fields": ["title", "body"],
            "id_field": "id",
            "batch_size": 2,
        },
    )

    records = list(connector.extract())
    assert len(records) == 10
    # IDs are sequential strings
    assert [r.record_id for r in records] == [str(i) for i in range(1, 11)]


@pytest.mark.integration
def test_support_tickets_category_search_pattern() -> None:
    """Text field concatenation produces embeddable content suitable for search."""
    connector = get_connector(
        "sql",
        {
            "connection_string": CONN,
            "query": "SELECT id, title, body FROM support_tickets WHERE category = 'auth' ORDER BY id",
            "text_fields": ["title", "body"],
            "id_field": "id",
        },
    )

    records = list(connector.extract())

    assert len(records) == 2
    texts = [r.text for r in records]
    assert any("password" in t.lower() for t in texts)
    assert any("authenticator" in t.lower() for t in texts)


# ---------------------------------------------------------------------------
# candidates tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_candidates_basic_extraction() -> None:
    """All 8 seeded candidates are returned with name + summary + skills in text."""
    connector = get_connector(
        "sql",
        {
            "connection_string": CONN,
            "query": (
                "SELECT id, full_name, summary, skills, location, years_experience, availability "
                "FROM candidates ORDER BY id"
            ),
            "text_fields": ["full_name", "summary", "skills"],
            "id_field": "id",
        },
    )

    records = list(connector.extract())

    assert len(records) == 8
    alice = records[0]
    assert alice.text == (
        "Alice Okonkwo | "
        "Senior data engineer with deep experience in ELT pipelines and cloud data warehouses. | "
        "Python, dbt, Snowflake, Airflow, AWS"
    )


@pytest.mark.integration
def test_candidates_metadata_fields() -> None:
    """Location, years_experience, and availability are stored as filterable metadata."""
    connector = get_connector(
        "sql",
        {
            "connection_string": CONN,
            "query": (
                "SELECT id, full_name, summary, skills, location, years_experience, availability "
                "FROM candidates ORDER BY id"
            ),
            "text_fields": ["full_name", "summary", "skills"],
            "id_field": "id",
            "metadata_fields": ["location", "years_experience", "availability"],
        },
    )

    records = list(connector.extract())

    alice = records[0]
    assert alice.metadata["location"] == "New York, NY"
    assert alice.metadata["years_experience"] == 8
    assert alice.metadata["availability"] == "immediate"

    # Remote candidates
    remote = [r for r in records if r.metadata.get("location") == "Remote"]
    assert len(remote) == 2


@pytest.mark.integration
def test_candidates_filtered_by_availability() -> None:
    """Filtering for immediately available candidates returns correct subset."""
    connector = get_connector(
        "sql",
        {
            "connection_string": CONN,
            "query": (
                "SELECT id, full_name, summary, skills, location FROM candidates "
                "WHERE availability = 'immediate' ORDER BY id"
            ),
            "text_fields": ["full_name", "summary", "skills"],
            "id_field": "id",
            "metadata_fields": ["location"],
        },
    )

    records = list(connector.extract())

    assert len(records) == 4
    names = [r.text.split(" | ")[0] for r in records]
    assert "Alice Okonkwo" in names
    assert "Esme Oduya" in names


@pytest.mark.integration
def test_candidates_senior_engineers_search_pattern() -> None:
    """Records for senior engineers contain M&A and vector search keywords."""
    connector = get_connector(
        "sql",
        {
            "connection_string": CONN,
            "query": (
                "SELECT id, full_name, summary, skills FROM candidates "
                "WHERE years_experience >= 8 ORDER BY id"
            ),
            "text_fields": ["full_name", "summary", "skills"],
            "id_field": "id",
        },
    )

    records = list(connector.extract())

    assert len(records) == 3
    combined_text = " ".join(r.text for r in records)
    assert "M&A" in combined_text
    assert "AWS" in combined_text


# ---------------------------------------------------------------------------
# Error / edge-case tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_missing_column_raises_datasource_error() -> None:
    """Querying a column that does not exist raises DataSourceError."""
    connector = get_connector(
        "sql",
        {
            "connection_string": CONN,
            "query": "SELECT id, title FROM support_tickets ORDER BY id",
            "text_fields": ["title", "nonexistent_column"],
            "id_field": "id",
        },
    )

    with pytest.raises(DataSourceError, match="nonexistent_column"):
        list(connector.extract())


@pytest.mark.integration
def test_bad_connection_string_raises_datasource_error() -> None:
    """An unreachable host raises DataSourceError during extract()."""
    connector = get_connector(
        "sql",
        {
            "connection_string": "postgresql+psycopg2://invalid_host/no_db",
            "query": "SELECT 1 AS id, 'test' AS title",
            "text_fields": ["title"],
            "id_field": "id",
        },
    )

    with pytest.raises((DataSourceError, Exception)):
        list(connector.extract())


@pytest.mark.integration
def test_empty_result_set_returns_no_records() -> None:
    """A query that matches zero rows yields an empty iterator without error."""
    connector = get_connector(
        "sql",
        {
            "connection_string": CONN,
            "query": "SELECT id, title, body FROM support_tickets WHERE category = 'nonexistent'",
            "text_fields": ["title", "body"],
            "id_field": "id",
        },
    )

    records = list(connector.extract())
    assert records == []
