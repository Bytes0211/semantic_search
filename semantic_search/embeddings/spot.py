"""Spot-hosted (open-source) embedding provider implementation."""

from __future__ import annotations

import hashlib
import math
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .base import EmbeddingInput, EmbeddingProvider, EmbeddingResult
from .factory import register_provider


class SpotEmbeddingProvider(EmbeddingProvider):
    """Embedding provider that simulates open-source model inference on spot capacity.

    In production this class would call out to a containerised SentenceTransformers
    (or similar) service running on spot instances. For the purposes of the shared
    codebase and unit tests we provide a deterministic, dependency-light fallback
    that hashes the input text into a fixed-size embedding vector.
    """

    def __init__(
        self,
        *,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        dimension: int = 768,
        normalize: bool = True,
        salt: str = "semantic-search",
    ) -> None:
        """Initialise the spot-hosted embedding provider.

        Args:
            model_name: Logical model identifier reported in result metadata.
                In production this would correspond to the container image
                serving the SentenceTransformers model.
            dimension: Output embedding dimensionality. Must be a positive
                integer and must match the deployed model's output size.
            normalize: When ``True`` the output vector is L2-normalised to
                unit length before being returned.
            salt: Prefix string mixed into every token hash to namespace
                embeddings and prevent collisions across deployments.

        Raises:
            ValueError: If ``dimension`` is not a positive integer.
        """
        if dimension <= 0:
            raise ValueError("dimension must be a positive integer")
        self._model_name = model_name
        self._dimension = dimension
        self._normalize = normalize
        self._salt = salt

    def generate(
        self,
        inputs: Sequence[EmbeddingInput],
        *,
        model: Optional[str] = None,
        **_: Any,
    ) -> Sequence[EmbeddingResult]:
        if not inputs:
            return []

        target_model = model or self._model_name
        results: list[EmbeddingResult] = []
        for item in inputs:
            vector = self._hash_to_vector(item.text)
            # fix overwrite logic
            metadata = {"model": target_model, "backend": "spot"}
            if item.metadata:
                merged = dict(item.metadata)
                merged.update(metadata)  # provider fields win
                metadata = merged
            results.append(
                EmbeddingResult(
                    record_id=item.record_id,
                    vector=vector,
                    metadata=metadata,
                )
            )
        return results

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _hash_to_vector(self, text: str) -> list[float]:
        """Convert text to a deterministic embedding vector using hashing."""
        if not text:
            text = "<EMPTY>"

        vector = np.zeros(self._dimension, dtype=np.float32)
        # Tokenize on whitespace; for empty strings we already substituted.
        tokens = text.split()
        if not tokens:
            tokens = [text]

        for position, token in enumerate(tokens):
            digest = hashlib.sha256(f"{self._salt}:{token}:{position}".encode("utf-8"))
            chunk = digest.digest()

            # Iterate through the digest to produce pseudo-random floats in [-1, 1]
            for idx in range(self._dimension):
                byte_index = idx % len(chunk)
                value = chunk[byte_index] / 255.0  # scale to [0, 1]
                value = (value * 2.0) - 1.0  # scale to [-1, 1]
                vector[idx] += value

        if self._normalize:
            norm = np.linalg.norm(vector)
            if norm > 0:
                vector /= norm

        return vector.astype(np.float32).tolist()


@register_provider("spot", overwrite=True)
def _spot_factory(config: Mapping[str, Any]) -> SpotEmbeddingProvider:
    """Factory used by the embedding provider registry."""
    return SpotEmbeddingProvider(
        model_name=str(
            config.get("model_name", "sentence-transformers/all-MiniLM-L6-v2")
        ),
        dimension=int(config.get("dimension", 768)),
        normalize=bool(config.get("normalize", True)),
        salt=str(config.get("salt", "semantic-search")),
    )
