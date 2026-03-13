"""Tests for the SageMaker embedding provider."""

from __future__ import annotations

import json
import types
from typing import Any, Dict

import pytest

from semantic_search.embeddings.base import EmbeddingInput
from semantic_search.embeddings.factory import get_provider
from semantic_search.embeddings.sagemaker import (
    SageMakerEmbeddingProvider,
    SageMakerInvocationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session(response_body: Any) -> type:
    """Return a mock boto3.Session class that yields the given response body."""

    class MockClient:
        def __init__(self, body: Any) -> None:
            self._body = body

        def invoke_endpoint(
            self,
            *,
            EndpointName: str,
            ContentType: str,
            Accept: str,
            Body: bytes,
        ) -> Dict[str, Any]:
            encoded = (
                json.dumps(self._body).encode()
                if not isinstance(self._body, bytes)
                else self._body
            )
            return {"Body": types.SimpleNamespace(read=lambda: encoded)}

    class MockSession:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def client(self, service_name: str, **kwargs: Any) -> MockClient:
            assert service_name == "sagemaker-runtime"
            return MockClient(response_body)

    return MockSession


# ---------------------------------------------------------------------------
# Response shape tests
# ---------------------------------------------------------------------------


def test_huggingface_nested_list_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """HuggingFace containers return [[float, ...]] — outer list must be unwrapped."""
    expected = [0.1, 0.2, 0.3]
    monkeypatch.setattr(
        "semantic_search.embeddings.sagemaker.boto3.Session",
        _make_mock_session([expected]),
    )

    provider = SageMakerEmbeddingProvider(endpoint_name="hf-endpoint")
    results = provider.generate([EmbeddingInput(record_id="r1", text="hello")])

    assert len(results) == 1
    assert results[0].record_id == "r1"
    assert results[0].vector == pytest.approx(expected)
    assert results[0].metadata["endpoint"] == "hf-endpoint"


def test_flat_list_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Some containers return a flat [float, ...] list directly."""
    expected = [0.4, 0.5, 0.6]
    monkeypatch.setattr(
        "semantic_search.embeddings.sagemaker.boto3.Session",
        _make_mock_session(expected),
    )

    provider = SageMakerEmbeddingProvider(endpoint_name="flat-endpoint")
    results = provider.generate([EmbeddingInput(record_id="r2", text="world")])

    assert results[0].vector == pytest.approx(expected)


def test_dict_embedding_key_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Containers that return {\"embedding\": [...]} should be handled."""
    expected = [0.7, 0.8]
    monkeypatch.setattr(
        "semantic_search.embeddings.sagemaker.boto3.Session",
        _make_mock_session({"embedding": expected}),
    )

    provider = SageMakerEmbeddingProvider(endpoint_name="dict-endpoint")
    results = provider.generate([EmbeddingInput(record_id="r3", text="test")])

    assert results[0].vector == pytest.approx(expected)


def test_dict_embeddings_plural_key_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Containers that return {\"embeddings\": [[...]]} should use first element."""
    expected = [0.9, 1.0]
    monkeypatch.setattr(
        "semantic_search.embeddings.sagemaker.boto3.Session",
        _make_mock_session({"embeddings": [expected]}),
    )

    provider = SageMakerEmbeddingProvider(endpoint_name="plural-endpoint")
    results = provider.generate([EmbeddingInput(record_id="r4", text="test")])

    assert results[0].vector == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_missing_body_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """A response with no Body key should raise SageMakerInvocationError."""

    class MockClient:
        def invoke_endpoint(self, **kwargs: Any) -> Dict[str, Any]:
            return {}  # no "Body" key

    class MockSession:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def client(self, service_name: str, **kwargs: Any) -> MockClient:
            return MockClient()

    monkeypatch.setattr(
        "semantic_search.embeddings.sagemaker.boto3.Session", MockSession
    )

    provider = SageMakerEmbeddingProvider(endpoint_name="missing-body")
    with pytest.raises(SageMakerInvocationError, match="missing Body"):
        provider.generate([EmbeddingInput(record_id="r5", text="boom")])


def test_unparseable_json_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-JSON response body should raise SageMakerInvocationError."""

    class MockClient:
        def invoke_endpoint(self, **kwargs: Any) -> Dict[str, Any]:
            return {"Body": types.SimpleNamespace(read=lambda: b"not-json")}

    class MockSession:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def client(self, service_name: str, **kwargs: Any) -> MockClient:
            return MockClient()

    monkeypatch.setattr(
        "semantic_search.embeddings.sagemaker.boto3.Session", MockSession
    )

    provider = SageMakerEmbeddingProvider(endpoint_name="bad-json")
    with pytest.raises(SageMakerInvocationError, match="Unable to parse"):
        provider.generate([EmbeddingInput(record_id="r6", text="boom")])


def test_empty_embeddings_list_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty 'embeddings' list should raise immediately with a clear error."""
    monkeypatch.setattr(
        "semantic_search.embeddings.sagemaker.boto3.Session",
        _make_mock_session({"embeddings": []}),
    )

    provider = SageMakerEmbeddingProvider(endpoint_name="empty-embeddings")
    with pytest.raises(SageMakerInvocationError, match="empty 'embeddings' list"):
        provider.generate([EmbeddingInput(record_id="r-empty", text="test")])


def test_unknown_dict_keys_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dict response without 'embedding' or 'embeddings' should raise."""
    monkeypatch.setattr(
        "semantic_search.embeddings.sagemaker.boto3.Session",
        _make_mock_session({"result": [1.0, 2.0]}),
    )

    provider = SageMakerEmbeddingProvider(endpoint_name="unknown-key")
    with pytest.raises(SageMakerInvocationError, match="missing"):
        provider.generate([EmbeddingInput(record_id="r7", text="boom")])


def test_empty_input_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Passing an empty sequence should return an empty list without calling the endpoint."""
    called = []

    class MockClient:
        def invoke_endpoint(self, **kwargs: Any) -> Dict[str, Any]:
            called.append(True)
            return {}

    class MockSession:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def client(self, service_name: str, **kwargs: Any) -> MockClient:
            return MockClient()

    monkeypatch.setattr(
        "semantic_search.embeddings.sagemaker.boto3.Session", MockSession
    )

    provider = SageMakerEmbeddingProvider(endpoint_name="empty-test")
    results = provider.generate([])

    assert results == []
    assert not called


# ---------------------------------------------------------------------------
# Factory / registry
# ---------------------------------------------------------------------------


def test_factory_requires_endpoint_name() -> None:
    with pytest.raises(ValueError, match="endpoint_name"):
        get_provider("sagemaker", {})


def test_factory_creates_provider() -> None:
    provider = get_provider("sagemaker", {"endpoint_name": "my-ep", "region": "us-west-2"})
    assert isinstance(provider, SageMakerEmbeddingProvider)
