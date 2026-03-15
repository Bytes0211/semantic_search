import json
import textwrap
from pathlib import Path
from typing import Any, Dict, List

import pytest
import sqlalchemy

# Import connector modules to ensure registration side effects occur.
from semantic_search.ingestion import (  # noqa: F401
    DataSourceError,
    api_connector,
    csv_connector,
    get_connector,
    json_connector,
    list_registered_connectors,
    sql_connector,
    xml_connector,
)


def collect_texts(records):
    return [record.text for record in records]


def test_csv_connector_reads_multiple_files(tmp_path: Path) -> None:
    csv_content = textwrap.dedent(
        """\
        id,name,summary,skills,location
        1,Alice,Data engineer,python|sql,NYC
        2,Bob,ML engineer,pytorch|numpy,SF
        """
    )
    other_content = textwrap.dedent(
        """\
        id,name,summary,skills,location
        3,Carla,Platform engineer,kubernetes|terraform,Austin
        """
    )
    (tmp_path / "a.csv").write_text(csv_content, encoding="utf-8")
    (tmp_path / "b.csv").write_text(other_content, encoding="utf-8")

    connector = get_connector(
        "csv",
        {
            "path": str(tmp_path / "*.csv"),
            "text_fields": ["name", "summary", "skills"],
            "id_field": "id",
            "metadata_fields": ["location"],
        },
    )

    records = list(connector.extract())
    assert [record.record_id for record in records] == ["1", "2", "3"]
    assert collect_texts(records) == [
        "Alice | Data engineer | python|sql",
        "Bob | ML engineer | pytorch|numpy",
        "Carla | Platform engineer | kubernetes|terraform",
    ]
    assert [record.metadata["location"] for record in records] == [
        "NYC",
        "SF",
        "Austin",
    ]


def test_csv_connector_missing_columns_raises(tmp_path: Path) -> None:
    (tmp_path / "bad.csv").write_text("name\nAlice\n", encoding="utf-8")
    connector = get_connector(
        "csv",
        {"path": str(tmp_path / "bad.csv"), "text_fields": ["summary"]},
    )
    with pytest.raises(DataSourceError):
        list(connector.extract())


def test_sql_connector_streams_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "test.db"
    engine = sqlalchemy.create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        conn.execute(
            sqlalchemy.text(
                """
                CREATE TABLE support_tickets (
                    id INTEGER PRIMARY KEY,
                    title TEXT,
                    body TEXT,
                    category TEXT,
                    created_at TEXT
                )
                """
            )
        )
        conn.execute(
            sqlalchemy.text(
                """
                INSERT INTO support_tickets (title, body, category, created_at)
                VALUES
                  ('Login issue', 'User cannot login', 'auth', '2024-01-01'),
                  ('Search latency', 'Slow responses', 'performance', '2024-01-02')
                """
            )
        )

    connector = get_connector(
        "sql",
        {
            "connection_string": f"sqlite:///{db_path}",
            "query": "SELECT id, title, body, category, created_at FROM support_tickets",
            "text_fields": ["title", "body"],
            "id_field": "id",
            "metadata_fields": ["category", "created_at"],
            "batch_size": 1,
        },
    )

    records = list(connector.extract())
    assert len(records) == 2
    assert records[0].text == "Login issue | User cannot login"
    assert records[0].metadata == {"category": "auth", "created_at": "2024-01-01"}


def test_json_connector_supports_filter_and_metadata(tmp_path: Path) -> None:
    data = {
        "products": [
            {
                "sku": "abc",
                "name": "Vector Search Appliance",
                "description": "Enterprise ready",
                "tags": "vector,search",
                "category": "hardware",
                "price": 9999,
            }
        ]
    }
    json_path = tmp_path / "products.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    connector = get_connector(
        "json",
        {
            "path": str(json_path),
            "jq_filter": ".products",
            "text_fields": ["name", "description", "tags"],
            "id_field": "sku",
            "metadata_fields": ["category", "price"],
        },
    )

    records = list(connector.extract())
    assert len(records) == 1
    record = records[0]
    assert record.record_id == "abc"
    assert record.text == "Vector Search Appliance | Enterprise ready | vector,search"
    assert record.metadata == {"category": "hardware", "price": 9999}


def test_json_connector_handles_jsonl(tmp_path: Path) -> None:
    jsonl_path = tmp_path / "events.jsonl"
    jsonl_path.write_text(
        '{"id": 1, "title": "First", "body": "Hello"}\n'
        '{"id": 2, "title": "Second", "body": "World"}\n',
        encoding="utf-8",
    )

    connector = get_connector(
        "json",
        {
            "path": str(jsonl_path),
            "text_fields": ["title", "body"],
            "id_field": "id",
        },
    )

    records = list(connector.extract())
    assert [record.record_id for record in records] == ["1", "2"]


def test_xml_connector_extracts_records(tmp_path: Path) -> None:
    xml_content = textwrap.dedent(
        """\
        <catalog>
          <item id="001">
            <title>Neural Search</title>
            <description>All about neural search</description>
            <category>books</category>
          </item>
          <item id="002">
            <title>Vector Databases</title>
            <description>Indexing strategies</description>
            <category>books</category>
          </item>
        </catalog>
        """
    )
    xml_path = tmp_path / "catalog.xml"
    xml_path.write_text(xml_content, encoding="utf-8")

    connector = get_connector(
        "xml",
        {
            "path": str(xml_path),
            "record_xpath": "./item",
            "text_fields": ["title", "description"],
            "id_field": "@id",
            "metadata_fields": ["category"],
        },
    )

    records = list(connector.extract())
    assert [record.record_id for record in records] == ["001", "002"]
    assert records[0].text == "Neural Search | All about neural search"
    assert records[0].metadata == {"category": "books"}


def test_api_connector_cursor_pagination(monkeypatch) -> None:
    responses: List[Dict[str, Any]] = [
        {
            "data": [
                {"uuid": "1", "title": "First", "description": "Hello"},
                {"uuid": "2", "title": "Second", "description": "World"},
            ],
            "next": "cursor-2",
        },
        {
            "data": [
                {"uuid": "3", "title": "Third", "description": "Again"},
            ],
            "next": None,
        },
    ]

    class DummyResponse:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._payload = payload

        def json(self) -> Dict[str, Any]:
            return self._payload

        def raise_for_status(self) -> None:
            return None

    class DummyClient:
        def __init__(self, base_url: str, timeout: float) -> None:
            self.base_url = base_url
            self.timeout = timeout
            self.calls: List[Dict[str, Any]] = []

        def get(self, url: str, headers=None, params=None):
            self.calls.append({"url": url, "headers": headers, "params": params})
            if not responses:
                raise AssertionError("Unexpected extra API call")
            return DummyResponse(responses.pop(0))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr("httpx.Client", DummyClient)

    connector = get_connector(
        "api",
        {
            "base_url": "https://example.com",
            "endpoint": "/records",
            "text_fields": ["title", "description"],
            "id_field": "uuid",
        },
    )

    records = list(connector.extract())
    assert [record.record_id for record in records] == ["1", "2", "3"]
    assert records[0].text == "First | Hello"
    assert records[-1].text == "Third | Again"


def test_registered_connectors_include_expected_backends() -> None:
    available = list_registered_connectors()
    for backend in {"csv", "json", "xml", "sql", "api"}:
        assert backend in available, f"{backend} connector should be registered"
