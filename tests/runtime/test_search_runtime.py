from __future__ import annotations

import math
from typing import List

import pytest
from fastapi.testclient import TestClient

try:
    from semantic_search.runtime.api import (
        SearchRequest,
        SearchRuntime,
        create_app,
    )
except RuntimeError as exc:  # pragma: no cover - dependency missing
    pytest.skip(str(exc), allow_module_level=True)

from semantic_search.embeddings.base import EmbeddingResult


def _unit_vector(index: int, dimension: int) -> List[float]:
    """Return a unit vector with 1.0 at ``index``."""
    return [1.0 if i == index else 0.0 for i in range(dimension)]


def _normalized_vector(indices: List[int], dimension: int) -> List[float]:
    """Return a normalised vector with 1.0 contributions for each given index."""
    vector = [0.0] * dimension
    for idx in indices:
        vector[idx] += 1.0
    norm = math.sqrt(sum(component * component for component in vector))
    return [component / norm for component in vector]


def _patch_provider_generate(
    search_runtime: SearchRuntime, vector: List[float], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Patch the runtime's embedding provider to return the supplied vector."""

    def _fake_generate(inputs, *, model=None, **_):
        return [
            EmbeddingResult(
                record_id=item.record_id,
                vector=vector,
                metadata={"model": model or "unit-test"},
            )
            for item in inputs
        ]

    monkeypatch.setattr(search_runtime._embedding_provider, "generate", _fake_generate)  # type: ignore[attr-defined]


def test_search_runtime_returns_expected_result(
    search_runtime: SearchRuntime,
    embedding_dimension: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Semantic search returns the closest record when embeddings match."""
    _patch_provider_generate(
        search_runtime,
        _unit_vector(0, embedding_dimension),
        monkeypatch,
    )

    request = SearchRequest(query="alpha document", top_k=1)
    response = search_runtime.search(request)

    assert response.total_results == 1
    assert response.results[0].record_id == "alpha"
    assert response.embedding_model == "unit-test"
    assert len(response.query_vector) == embedding_dimension


def test_search_runtime_applies_metadata_filters(
    search_runtime: SearchRuntime,
    embedding_dimension: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Filtering removes results whose metadata does not match."""
    # Create an embedding that is equidistant between the first two records.
    _patch_provider_generate(
        search_runtime,
        _normalized_vector([0, 1], embedding_dimension),
        monkeypatch,
    )

    request = SearchRequest(
        query="mixed content",
        top_k=2,
        filters={"category": "documents", "region": "us-east-1"},
    )
    response = search_runtime.search(request)

    assert response.total_results == 1
    assert response.results[0].record_id == "alpha"
    assert all(item.metadata["category"] == "documents" for item in response.results)
    assert all(item.metadata["region"] == "us-east-1" for item in response.results)


def test_search_runtime_rejects_blank_query(search_runtime: SearchRuntime) -> None:
    """Whitespace-only search queries are rejected."""
    request = SearchRequest(query="   ", top_k=1)
    with pytest.raises(ValueError, match="non-whitespace"):
        search_runtime.search(request)


def test_fastapi_app_search_endpoint(
    search_runtime: SearchRuntime,
    embedding_dimension: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The FastAPI layer returns structured search results."""
    _patch_provider_generate(
        search_runtime,
        _unit_vector(0, embedding_dimension),
        monkeypatch,
    )
    app = create_app(search_runtime)
    client = TestClient(app)

    response = client.post(
        "/v1/search",
        json={"query": "find alpha", "top_k": 1},
    )
    assert response.status_code == 200

    payload = response.json()
    assert payload["query"] == "find alpha"
    assert payload["total_results"] == 1
    assert payload["results"][0]["record_id"] == "alpha"
    assert payload["embedding_model"] == "unit-test"


def test_fastapi_readiness_without_runtime() -> None:
    """Readiness endpoint returns 503 when no runtime is configured."""
    app = create_app()
    client = TestClient(app)

    health = client.get("/healthz")
    assert health.status_code == 200

    readiness = client.get("/readyz")
    assert readiness.status_code == 503
    assert readiness.json()["detail"].startswith("Search runtime not initialised")


def test_search_runtime_extracts_detail_from_metadata(
    search_runtime: SearchRuntime,
    embedding_dimension: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Records with _detail in metadata have it extracted into the detail field."""
    _patch_provider_generate(
        search_runtime,
        _unit_vector(0, embedding_dimension),
        monkeypatch,
    )

    request = SearchRequest(query="alpha document", top_k=1)
    response = search_runtime.search(request)

    assert response.total_results == 1
    result = response.results[0]
    assert result.record_id == "alpha"
    # _detail should be extracted into detail field
    assert result.detail == {"summary": "Alpha document content", "author": "Alice"}
    # _detail should not remain in metadata
    assert "_detail" not in result.metadata
    # Original metadata fields should still be present
    assert result.metadata["category"] == "documents"
    assert result.metadata["region"] == "us-east-1"


def test_search_runtime_empty_detail_when_no_detail_key(
    search_runtime: SearchRuntime,
    embedding_dimension: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Records without _detail produce an empty detail dict (backward compat)."""
    _patch_provider_generate(
        search_runtime,
        _unit_vector(1, embedding_dimension),
        monkeypatch,
    )

    request = SearchRequest(query="bravo ticket", top_k=1)
    response = search_runtime.search(request)

    assert response.total_results == 1
    result = response.results[0]
    assert result.record_id == "bravo"
    assert result.detail == {}
    assert "_detail" not in result.metadata


# ── Access Control Tests ──────────────────────────────────────────────────


def test_ac_disabled_returns_all_results(
    search_runtime: SearchRuntime,
    embedding_dimension: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With access control disabled, all results are returned regardless of roles."""
    _patch_provider_generate(
        search_runtime,
        _normalized_vector([0, 1, 2], embedding_dimension),
        monkeypatch,
    )
    request = SearchRequest(query="everything", top_k=10, roles=["viewer"])
    response = search_runtime.search(request)
    assert response.total_results == 3


def test_ac_enabled_matching_roles(
    ac_search_runtime: SearchRuntime,
    embedding_dimension: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Access control filters to records whose allowed_roles intersect caller roles."""
    _patch_provider_generate(
        ac_search_runtime,
        _normalized_vector([0, 1, 2], embedding_dimension),
        monkeypatch,
    )
    # 'analyst' matches alpha; charlie has no roles (open access); bravo requires 'admin'
    request = SearchRequest(query="search", top_k=10, roles=["analyst"])
    response = ac_search_runtime.search(request)
    ids = {r.record_id for r in response.results}
    assert "alpha" in ids    # analyst is in allowed_roles
    assert "charlie" in ids  # no allowed_roles → open access
    assert "bravo" not in ids  # requires admin


def test_ac_enabled_no_matching_roles(
    ac_search_runtime: SearchRuntime,
    embedding_dimension: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Caller with non-matching roles only sees open-access records."""
    _patch_provider_generate(
        ac_search_runtime,
        _normalized_vector([0, 1, 2], embedding_dimension),
        monkeypatch,
    )
    request = SearchRequest(query="search", top_k=10, roles=["intern"])
    response = ac_search_runtime.search(request)
    ids = {r.record_id for r in response.results}
    # Only charlie (open access) should be visible
    assert ids == {"charlie"}


def test_ac_enabled_admin_sees_all(
    ac_search_runtime: SearchRuntime,
    embedding_dimension: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Admin role matches all restricted records; open-access records also visible."""
    _patch_provider_generate(
        ac_search_runtime,
        _normalized_vector([0, 1, 2], embedding_dimension),
        monkeypatch,
    )
    request = SearchRequest(query="search", top_k=10, roles=["admin"])
    response = ac_search_runtime.search(request)
    ids = {r.record_id for r in response.results}
    assert ids == {"alpha", "bravo", "charlie"}


def test_ac_enabled_no_roles_in_request_returns_open_access_only(
    ac_search_runtime: SearchRuntime,
    embedding_dimension: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When roles is None, AC defaults to deny — only open-access records visible."""
    _patch_provider_generate(
        ac_search_runtime,
        _normalized_vector([0, 1, 2], embedding_dimension),
        monkeypatch,
    )
    request = SearchRequest(query="search", top_k=10)  # roles=None → empty set
    response = ac_search_runtime.search(request)
    ids = {r.record_id for r in response.results}
    # Only charlie (no allowed_roles → open access) should be visible
    assert ids == {"charlie"}


def test_ac_enabled_missing_roles_field_is_open_access(
    ac_search_runtime: SearchRuntime,
    embedding_dimension: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Records missing the roles_field are treated as open access."""
    _patch_provider_generate(
        ac_search_runtime,
        _unit_vector(2, embedding_dimension),  # points at charlie (no roles field)
        monkeypatch,
    )
    request = SearchRequest(query="open doc", top_k=1, roles=["any_role"])
    response = ac_search_runtime.search(request)
    assert response.total_results == 1
    assert response.results[0].record_id == "charlie"
