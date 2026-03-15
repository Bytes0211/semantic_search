"""Tests for the ``GET /v1/config`` endpoint and CORS middleware.

Replaces ``test_ui.py`` (removed in Phase 6) with equivalent coverage of the
new :func:`~semantic_search.runtime.api.create_app` surface: the feature-flag
config endpoint and the opt-in CORS middleware.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from semantic_search.runtime.api import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    """Default app: no runtime, analytics disabled, no CORS."""
    return TestClient(create_app())


@pytest.fixture()
def analytics_client() -> TestClient:
    """App with analytics enabled."""
    return TestClient(create_app(analytics_enabled=True))


@pytest.fixture()
def cors_client() -> TestClient:
    """App with a single allowed CORS origin."""
    return TestClient(create_app(cors_origins=["http://localhost:5173"]))


_FRONTEND_ORIGIN = "http://localhost:5173"


# ---------------------------------------------------------------------------
# /v1/config — response body
# ---------------------------------------------------------------------------


def test_config_analytics_disabled_by_default(client: TestClient) -> None:
    """Config endpoint returns ``analytics_enabled=False`` when not configured."""
    resp = client.get("/v1/config")
    assert resp.status_code == 200
    assert resp.json()["analytics_enabled"] is False


def test_config_analytics_enabled_when_set(analytics_client: TestClient) -> None:
    """Config endpoint returns ``analytics_enabled=True`` when requested."""
    resp = analytics_client.get("/v1/config")
    assert resp.status_code == 200
    assert resp.json()["analytics_enabled"] is True


def test_config_analytics_false_explicit() -> None:
    """Passing ``analytics_enabled=False`` explicitly returns the correct value."""
    resp = TestClient(create_app(analytics_enabled=False)).get("/v1/config")
    assert resp.json()["analytics_enabled"] is False


def test_config_response_contains_expected_key(client: TestClient) -> None:
    """Config response body contains the ``analytics_enabled`` key."""
    assert "analytics_enabled" in client.get("/v1/config").json()


def test_config_accessible_without_runtime(client: TestClient) -> None:
    """/v1/config returns 200 even when no SearchRuntime is attached."""
    assert client.get("/v1/config").status_code == 200


def test_config_endpoint_in_openapi_schema(client: TestClient) -> None:
    """/v1/config is present in the generated OpenAPI schema."""
    schema = client.get("/openapi.json").json()
    assert "/v1/config" in schema["paths"]


# ---------------------------------------------------------------------------
# /v1/config — search_top_k
# ---------------------------------------------------------------------------


def test_config_search_top_k_default(client: TestClient) -> None:
    """Config endpoint returns search_top_k=50 by default."""
    resp = client.get("/v1/config")
    assert resp.status_code == 200
    assert resp.json()["search_top_k"] == 50


def test_config_search_top_k_custom() -> None:
    """Config endpoint reflects a custom search_top_k value."""
    resp = TestClient(create_app(search_top_k=100)).get("/v1/config")
    assert resp.json()["search_top_k"] == 100


def test_config_response_contains_search_top_k(client: TestClient) -> None:
    """Config response body contains the ``search_top_k`` key."""
    assert "search_top_k" in client.get("/v1/config").json()


# ---------------------------------------------------------------------------
# CORS middleware
# ---------------------------------------------------------------------------


def test_cors_headers_present_for_listed_origin(cors_client: TestClient) -> None:
    """CORS Allow-Origin header is returned for a configured origin."""
    resp = cors_client.get("/v1/config", headers={"Origin": _FRONTEND_ORIGIN})
    assert resp.headers.get("access-control-allow-origin") == _FRONTEND_ORIGIN


def test_cors_preflight_returns_ok(cors_client: TestClient) -> None:
    """OPTIONS preflight returns 200 with CORS headers for a listed origin."""
    resp = cors_client.options(
        "/v1/search",
        headers={
            "Origin": _FRONTEND_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert resp.status_code == 200
    assert "access-control-allow-origin" in resp.headers


def test_cors_wildcard_allows_any_origin() -> None:
    """Wildcard ``cors_origins=["*"]`` permits requests from arbitrary origins."""
    client = TestClient(create_app(cors_origins=["*"]))
    resp = client.get("/v1/config", headers={"Origin": "https://example.com"})
    # Starlette may echo the request origin or return the literal wildcard
    allow_origin = resp.headers.get("access-control-allow-origin", "")
    assert allow_origin in ("*", "https://example.com")


def test_cors_headers_absent_without_middleware(client: TestClient) -> None:
    """No CORS headers are emitted when ``cors_origins`` is not configured."""
    resp = client.get("/v1/config", headers={"Origin": _FRONTEND_ORIGIN})
    assert "access-control-allow-origin" not in resp.headers


def test_cors_unlisted_origin_not_reflected() -> None:
    """Unlisted origin does not receive an Allow-Origin header."""
    client = TestClient(create_app(cors_origins=["https://allowed.example.com"]))
    resp = client.get(
        "/v1/config", headers={"Origin": "https://evil.example.com"}
    )
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"


def test_ui_route_not_registered(client: TestClient) -> None:
    """GET /ui returns 404 — the legacy HTML UI is no longer mounted."""
    assert client.get("/ui").status_code == 404
