"""Tests for the lightweight validation UI served at /ui."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from semantic_search.runtime.api import create_app
from semantic_search.runtime.ui import _HTML_TEMPLATE, mount_ui


# ---------------------------------------------------------------------------
# mount_ui unit tests
# ---------------------------------------------------------------------------


def test_mount_ui_rejects_path_without_leading_slash() -> None:
    """mount_ui raises ValueError when path does not start with '/'."""
    app = create_app()
    with pytest.raises(ValueError, match="must start with '/'"):
        mount_ui(app, path="ui")


def test_mount_ui_custom_path() -> None:
    """mount_ui registers the route at the supplied custom path."""
    app = create_app()
    mount_ui(app, path="/search-ui")
    client = TestClient(app)

    resp = client.get("/search-ui")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# enable_ui=True — UI is accessible
# ---------------------------------------------------------------------------


@pytest.fixture()
def ui_client() -> TestClient:
    """TestClient for an app with enable_ui=True (no runtime attached)."""
    app = create_app(enable_ui=True)
    return TestClient(app)


def test_ui_returns_200(ui_client: TestClient) -> None:
    """GET /ui returns HTTP 200 when the UI is enabled."""
    resp = ui_client.get("/ui")
    assert resp.status_code == 200


def test_ui_content_type_is_html(ui_client: TestClient) -> None:
    """GET /ui sets Content-Type to text/html."""
    resp = ui_client.get("/ui")
    assert "text/html" in resp.headers["content-type"]


def test_ui_contains_title(ui_client: TestClient) -> None:
    """The UI page includes the expected page title."""
    resp = ui_client.get("/ui")
    assert "Semantic Search" in resp.text


def test_ui_contains_search_form(ui_client: TestClient) -> None:
    """The UI page contains the search form and query input."""
    resp = ui_client.get("/ui")
    body = resp.text
    assert "search-form" in body
    assert 'id="query"' in body
    assert 'id="top-k"' in body
    assert 'id="search-btn"' in body


def test_ui_references_search_endpoint(ui_client: TestClient) -> None:
    """The UI JavaScript targets the /v1/search API endpoint."""
    resp = ui_client.get("/ui")
    assert "/v1/search" in resp.text


def test_ui_contains_results_container(ui_client: TestClient) -> None:
    """The UI page has the results list container."""
    resp = ui_client.get("/ui")
    assert 'id="results"' in resp.text


def test_ui_excluded_from_openapi_schema(ui_client: TestClient) -> None:
    """The /ui route must not appear in the generated OpenAPI schema."""
    schema = ui_client.get("/openapi.json").json()
    paths = schema.get("paths", {})
    assert "/ui" not in paths


# ---------------------------------------------------------------------------
# enable_ui=False (default) — UI is not registered
# ---------------------------------------------------------------------------


def test_ui_not_registered_by_default() -> None:
    """GET /ui returns 404 when enable_ui is not set (default)."""
    app = create_app()
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/ui")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# HTML template content sanity checks
# ---------------------------------------------------------------------------


def test_html_template_is_valid_html() -> None:
    """The template starts and ends with the expected HTML document tags."""
    assert _HTML_TEMPLATE.strip().startswith("<!DOCTYPE html>")
    assert "</html>" in _HTML_TEMPLATE


def test_html_template_has_no_external_resources() -> None:
    """The UI template must not reference external CDN or remote script sources.

    All resources must be self-contained so the UI works in air-gapped
    environments without internet access.
    """
    lower = _HTML_TEMPLATE.lower()
    external_patterns = [
        "cdn.",
        "googleapis.com",
        "bootstrapcdn",
        "unpkg.com",
        "jsdelivr.net",
        "cloudflare.com",
    ]
    for pattern in external_patterns:
        assert pattern not in lower, (
            f"UI template must not reference external resource matching '{pattern}'"
        )
