import types
from typing import Any, Dict, Mapping, Sequence

import numpy as np
import pytest

from semantic_search.embeddings.base import (
    EmbeddingInput,
    EmbeddingProvider,
    EmbeddingResult,
)
from semantic_search.embeddings.bedrock import BedrockEmbeddingProvider
from semantic_search.embeddings.factory import (
    ProviderRegistryError,
    get_provider,
    list_registered_backends,
    register_provider,
)
from semantic_search.embeddings.spot import SpotEmbeddingProvider
from semantic_search.embeddings.utils import hash_vector


class DummyProvider(EmbeddingProvider):
    """Minimal provider used for factory registration tests."""

    def __init__(self, multiplier: float = 1.0) -> None:
        self._multiplier = multiplier

    def generate(
        self,
        inputs: Sequence[EmbeddingInput],
        *,
        model: str | None = None,
        **_: Any,
    ) -> Sequence[EmbeddingResult]:
        return [
            EmbeddingResult(
                record_id=item.record_id,
                vector=[ord(c) * self._multiplier for c in item.text],
                metadata={"model": model or "dummy"},
            )
            for item in inputs
        ]


def test_register_provider_decorator(monkeypatch):
    """Providers should be discoverable through the factory once registered."""

    @register_provider("dummy-test", overwrite=True)
    def _factory(config: Mapping[str, Any]) -> EmbeddingProvider:
        return DummyProvider(multiplier=config.get("multiplier", 1.0))

    provider = get_provider("dummy-test", {"multiplier": 2.0})
    result = provider.generate([EmbeddingInput(record_id="1", text="ab")])
    assert isinstance(provider, DummyProvider)
    assert [vector.vector for vector in result] == [[194.0, 196.0]]

    # registry should show dummy-test backend
    assert "dummy-test" in list_registered_backends()

    # duplicate registration without overwrite should raise
    with pytest.raises(ProviderRegistryError):

        @register_provider("dummy-test")
        def _duplicate(_: Mapping[str, Any]) -> EmbeddingProvider:
            return DummyProvider()


def test_hash_vector_normalises_precision():
    vector = [0.1234567, 0.7654321]
    digest = hash_vector(vector, precision=4)
    assert digest == hash_vector([0.1234566, 0.7654322], precision=4)

    with pytest.raises(ValueError):
        hash_vector(vector, precision=-1)


def test_bedrock_embedding_provider(monkeypatch):
    """Verify Bedrock provider interaction with the mocked boto3 client."""
    calls: Dict[str, Any] = {}

    class MockClient:
        def __init__(self, model_response: str):
            self._response = model_response

        def invoke_model(self, modelId: str, body: bytes, **kwargs: Any) -> Dict[str, Any]:
            calls["modelId"] = modelId
            calls["body"] = body.decode("utf-8")
            return {"body": types.SimpleNamespace(read=lambda: self._response.encode())}

    class MockSession:
        def __init__(self, **kwargs: Any) -> None:
            calls["session_kwargs"] = kwargs

        def client(self, service_name: str) -> MockClient:
            assert service_name == "bedrock-runtime"
            return MockClient('{"embedding": [0.1, 0.2, 0.3]}')

    monkeypatch.setattr("semantic_search.embeddings.bedrock.boto3.Session", MockSession)

    provider = BedrockEmbeddingProvider(region="us-east-1", model="test-model")
    inputs = [EmbeddingInput(record_id="doc-1", text="hello world")]
    results = provider.generate(inputs)

    assert calls["session_kwargs"]["region_name"] == "us-east-1"
    assert calls["modelId"] == "test-model"
    assert isinstance(results, list)
    assert results[0].record_id == "doc-1"
    assert results[0].vector == [0.1, 0.2, 0.3]
    assert results[0].metadata == {"model": "test-model"}


def test_bedrock_embedding_provider_raises_on_bad_response(monkeypatch):
    class MockClient:
        def invoke_model(self, modelId: str, body: bytes, **kwargs: Any) -> Dict[str, Any]:
            return {"body": types.SimpleNamespace(read=lambda: b"invalid-number")}

    class MockSession:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def client(self, service_name: str) -> MockClient:
            return MockClient()

    monkeypatch.setattr("semantic_search.embeddings.bedrock.boto3.Session", MockSession)

    provider = BedrockEmbeddingProvider(region="us-east-1", model="test-model")
    with pytest.raises(RuntimeError):
        provider.generate([EmbeddingInput(record_id="doc-1", text="text")])


def test_spot_embedding_provider_generates_deterministic_vectors():
    provider = SpotEmbeddingProvider(dimension=6, normalize=True, salt="unit-test")
    inputs = [EmbeddingInput(record_id="doc-1", text="hello world")]
    results = provider.generate(inputs)

    assert len(results) == 1
    vector = np.array(results[0].vector)
    assert vector.shape == (6,)
    assert np.isclose(np.linalg.norm(vector), 1.0, atol=1e-6)

    repeat = provider.generate(inputs)
    assert results[0].vector == repeat[0].vector


def test_spot_provider_available_via_factory():
    provider = get_provider(
        "spot", {"dimension": 5, "normalize": False, "salt": "factory"}
    )
    assert isinstance(provider, SpotEmbeddingProvider)

    inputs = [EmbeddingInput(record_id="doc-1", text="factory test")]
    vectors = provider.generate(inputs)
    assert len(vectors) == 1
    assert len(vectors[0].vector) == 5
