"""Built-in model preset registry for embedding dimension auto-resolution.

Clients can specify just a model name in ``config/app.yaml`` and the correct
output dimension is resolved automatically from the preset registry.  An
explicit ``dimension`` in the YAML always overrides the preset.

Usage::

    from semantic_search.config.models import resolve_dimension

    dim = resolve_dimension("amazon.titan-embed-text-v1")        # → 1536
    dim = resolve_dimension("custom-model", explicit_dim=512)    # → 512
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


class ModelPresetError(ValueError):
    """Raised when a model's dimension cannot be resolved."""


@dataclass(frozen=True, slots=True)
class ModelPreset:
    """Metadata for a known embedding model.

    Attributes:
        dimension: Output vector dimensionality.
        backend: Recommended embedding backend for this model.
        description: Short human-readable description.
    """

    dimension: int
    backend: str
    description: str = ""


# ---------------------------------------------------------------------------
# Built-in presets — extend as new models are adopted.
# ---------------------------------------------------------------------------

MODEL_PRESETS: Dict[str, ModelPreset] = {
    # AWS Bedrock
    "amazon.titan-embed-text-v1": ModelPreset(
        dimension=1536,
        backend="bedrock",
        description="Amazon Titan Embeddings Text v1",
    ),
    "amazon.titan-embed-text-v2": ModelPreset(
        dimension=1024,
        backend="bedrock",
        description="Amazon Titan Embeddings Text v2",
    ),
    # Spot / SentenceTransformers
    "sentence-transformers/all-MiniLM-L6-v2": ModelPreset(
        dimension=384,
        backend="spot",
        description="MiniLM-L6-v2 (lightweight, 384-d)",
    ),
    "sentence-transformers/all-mpnet-base-v2": ModelPreset(
        dimension=768,
        backend="spot",
        description="MPNet base v2 (higher quality, 768-d)",
    ),
}


def resolve_dimension(
    model: str,
    explicit_dim: Optional[int] = None,
) -> int:
    """Resolve the embedding dimension for a model identifier.

    Args:
        model: Model identifier string (e.g. ``"amazon.titan-embed-text-v1"``).
        explicit_dim: Optional explicit dimension that overrides the preset.

    Returns:
        The resolved embedding dimension.

    Raises:
        ModelPresetError: If ``explicit_dim`` is ``None`` and the model is not
            found in :data:`MODEL_PRESETS`.
    """
    if explicit_dim is not None:
        if explicit_dim <= 0:
            raise ModelPresetError(
                f"Explicit dimension must be positive, got {explicit_dim}."
            )
        return explicit_dim

    preset = MODEL_PRESETS.get(model)
    if preset is not None:
        return preset.dimension

    raise ModelPresetError(
        f"Model '{model}' is not in the preset registry and no explicit "
        f"'dimension' was provided.  Either add 'dimension' to the embedding "
        f"config or register the model in semantic_search/config/models.py.  "
        f"Known models: {', '.join(sorted(MODEL_PRESETS))}."
    )


def get_preset(model: str) -> Optional[ModelPreset]:
    """Return the preset for a model, or ``None`` if unknown.

    Args:
        model: Model identifier string.

    Returns:
        The :class:`ModelPreset` if found, otherwise ``None``.
    """
    return MODEL_PRESETS.get(model)
