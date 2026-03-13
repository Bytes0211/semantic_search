import numpy as np
import pytest

from semantic_search.embeddings.base import EmbeddingInput
from semantic_search.embeddings.spot import SpotEmbeddingProvider


def test_spot_provider_produces_deterministic_embeddings() -> None:
    provider = SpotEmbeddingProvider(dimension=12, salt="deterministic", normalize=True)

    inputs = [
        EmbeddingInput(record_id="a", text="semantic search"),
        EmbeddingInput(record_id="b", text="semantic search"),
        EmbeddingInput(record_id="c", text="different text"),
    ]

    result1 = provider.generate(inputs)
    result2 = provider.generate(inputs)

    for first, second in zip(result1, result2):
        assert np.allclose(first.vector, second.vector, atol=1e-9)


def test_spot_provider_respects_normalize_flag() -> None:
    provider = SpotEmbeddingProvider(dimension=8, normalize=True, salt="norm")

    embedding = provider.generate([EmbeddingInput(record_id="x", text="normalize me")])[
        0
    ]
    assert np.isclose(np.linalg.norm(embedding.vector), 1.0, atol=1e-6)

    provider_non_norm = SpotEmbeddingProvider(dimension=8, normalize=False, salt="norm")
    raw_embedding = provider_non_norm.generate(
        [EmbeddingInput(record_id="x", text="normalize me")]
    )[0]
    assert not np.isclose(np.linalg.norm(raw_embedding.vector), 1.0, atol=1e-6)


def test_spot_provider_salt_changes_output() -> None:
    inputs = [EmbeddingInput(record_id="doc", text="salty hash")]
    provider_a = SpotEmbeddingProvider(dimension=6, salt="alpha")
    provider_b = SpotEmbeddingProvider(dimension=6, salt="beta")

    vec_a = provider_a.generate(inputs)[0].vector
    vec_b = provider_b.generate(inputs)[0].vector

    assert not np.allclose(vec_a, vec_b, atol=1e-9)


def test_spot_provider_metadata_fields_take_precedence() -> None:
    """Provider-set 'model' and 'backend' keys must not be overwritten by caller metadata."""
    provider = SpotEmbeddingProvider(
        model_name="my-model", dimension=6, salt="meta-test"
    )
    inputs = [
        EmbeddingInput(
            record_id="doc",
            text="text",
            metadata={"model": "overridden", "backend": "overridden", "custom": "kept"},
        )
    ]
    result = provider.generate(inputs)[0]

    assert result.metadata["model"] == "my-model"
    assert result.metadata["backend"] == "spot"
    assert result.metadata["custom"] == "kept"  # caller fields not in namespace are preserved


def test_spot_provider_rejects_non_positive_dimension() -> None:
    with pytest.raises(ValueError):
        SpotEmbeddingProvider(dimension=0)

    with pytest.raises(ValueError):
        SpotEmbeddingProvider(dimension=-5)
