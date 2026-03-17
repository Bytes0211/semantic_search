"""Built-in model preset registry for embedding dimension auto-resolution.

Clients can specify just a model name in ``config/app.yaml`` and the correct
output dimension is resolved automatically from the preset registry.  An
explicit ``dimension`` in the YAML always overrides the preset.

Custom models can be registered via the ``models:`` block in ``config/app.yaml``
without editing Python source.  User-defined presets take precedence over
built-in ones, so existing models can also be overridden this way.

Usage::

    from semantic_search.config.models import resolve_dimension, load_model_presets

    dim = resolve_dimension("amazon.titan-embed-text-v1")        # → 1536
    dim = resolve_dimension("custom-model", explicit_dim=512)    # → 512

    # Merge built-ins with YAML-defined models
    registry = load_model_presets({"my-model": {"dimension": 768, "backend": "sagemaker"}})
    dim = resolve_dimension("my-model", registry=registry)        # → 768
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


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


def load_model_presets(
    raw_models: Optional[Dict[str, Any]] = None,
) -> Dict[str, ModelPreset]:
    """Build a merged model preset registry from built-ins and YAML overrides.

    Starts from a copy of :data:`MODEL_PRESETS` and overlays any user-defined
    entries from the ``models:`` block in ``config/app.yaml``.  User entries
    take precedence, so built-in presets can be overridden as well as extended.

    Args:
        raw_models: The parsed ``models:`` mapping from ``app.yaml``, where
            each key is a model identifier and each value is a dict with at
            least a ``dimension`` field.  ``None`` or an empty dict returns a
            copy of the built-in registry unchanged.

    Returns:
        A merged ``Dict[str, ModelPreset]`` containing all built-in presets
        plus any user-defined overrides.

    Raises:
        ModelPresetError: If a user-defined entry is missing ``dimension``,
            has a non-integer or non-positive ``dimension``, or is not a
            YAML mapping.
    """
    registry: Dict[str, ModelPreset] = dict(MODEL_PRESETS)
    if not raw_models:
        return registry

    for model_id, entry in raw_models.items():
        if not isinstance(entry, dict):
            raise ModelPresetError(
                f"Model entry '{model_id}' must be a YAML mapping, "
                f"got {type(entry).__name__}."
            )
        raw_dim = entry.get("dimension")
        if raw_dim is None:
            raise ModelPresetError(
                f"Model '{model_id}' is missing required field 'dimension'."
            )
        try:
            dim = int(raw_dim)
        except (TypeError, ValueError) as exc:
            raise ModelPresetError(
                f"Model '{model_id}' has invalid dimension {raw_dim!r}: "
                f"must be a positive integer."
            ) from exc
        if dim <= 0:
            raise ModelPresetError(
                f"Model '{model_id}' dimension must be positive, got {dim}."
            )
        registry[model_id] = ModelPreset(
            dimension=dim,
            backend=str(entry.get("backend", "spot")),
            description=str(entry.get("description", "")),
        )

    return registry


def resolve_dimension(
    model: str,
    explicit_dim: Optional[int] = None,
    registry: Optional[Dict[str, ModelPreset]] = None,
) -> int:
    """Resolve the embedding dimension for a model identifier.

    Args:
        model: Model identifier string (e.g. ``"amazon.titan-embed-text-v1"``).
        explicit_dim: Optional explicit dimension that overrides the preset.
        registry: Optional merged model registry to look up.  Defaults to
            the built-in :data:`MODEL_PRESETS` when ``None``.

    Returns:
        The resolved embedding dimension.

    Raises:
        ModelPresetError: If ``explicit_dim`` is ``None`` and the model is not
            found in the effective registry.
    """
    if explicit_dim is not None:
        if explicit_dim <= 0:
            raise ModelPresetError(
                f"Explicit dimension must be positive, got {explicit_dim}."
            )
        return explicit_dim

    effective = registry if registry is not None else MODEL_PRESETS
    preset = effective.get(model)
    if preset is not None:
        return preset.dimension

    raise ModelPresetError(
        f"Model '{model}' is not in the preset registry and no explicit "
        f"'dimension' was provided.  Either add 'dimension' to the embedding "
        f"config, register the model in the 'models:' block of config/app.yaml, "
        f"or add it to semantic_search/config/models.py.  "
        f"Known models: {', '.join(sorted(effective))}."
    )


def get_preset(model: str) -> Optional[ModelPreset]:
    """Return the preset for a model, or ``None`` if unknown.

    Args:
        model: Model identifier string.

    Returns:
        The :class:`ModelPreset` if found, otherwise ``None``.
    """
    return MODEL_PRESETS.get(model)
