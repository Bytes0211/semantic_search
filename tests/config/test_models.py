"""Tests for semantic_search.config.models."""

from __future__ import annotations

import pytest

from semantic_search.config.models import (
    MODEL_PRESETS,
    ModelPreset,
    ModelPresetError,
    get_preset,
    resolve_dimension,
)


class TestModelPresets:
    """Verify the built-in model preset registry."""

    def test_titan_v1_preset(self) -> None:
        preset = MODEL_PRESETS["amazon.titan-embed-text-v1"]
        assert preset.dimension == 1536
        assert preset.backend == "bedrock"

    def test_titan_v2_preset(self) -> None:
        preset = MODEL_PRESETS["amazon.titan-embed-text-v2"]
        assert preset.dimension == 1024

    def test_minilm_preset(self) -> None:
        preset = MODEL_PRESETS["sentence-transformers/all-MiniLM-L6-v2"]
        assert preset.dimension == 384
        assert preset.backend == "spot"

    def test_mpnet_preset(self) -> None:
        preset = MODEL_PRESETS["sentence-transformers/all-mpnet-base-v2"]
        assert preset.dimension == 768


class TestResolveDimension:
    """Verify dimension auto-resolution logic."""

    def test_known_model_auto_resolves(self) -> None:
        assert resolve_dimension("amazon.titan-embed-text-v1") == 1536

    def test_explicit_dim_overrides_preset(self) -> None:
        assert resolve_dimension("amazon.titan-embed-text-v1", explicit_dim=512) == 512

    def test_unknown_model_without_dim_raises(self) -> None:
        with pytest.raises(ModelPresetError, match="not in the preset registry"):
            resolve_dimension("unknown-model")

    def test_unknown_model_with_explicit_dim_ok(self) -> None:
        assert resolve_dimension("unknown-model", explicit_dim=256) == 256

    def test_zero_explicit_dim_raises(self) -> None:
        with pytest.raises(ModelPresetError, match="positive"):
            resolve_dimension("amazon.titan-embed-text-v1", explicit_dim=0)

    def test_negative_explicit_dim_raises(self) -> None:
        with pytest.raises(ModelPresetError, match="positive"):
            resolve_dimension("amazon.titan-embed-text-v1", explicit_dim=-1)


class TestGetPreset:
    """Verify get_preset helper."""

    def test_known_model_returns_preset(self) -> None:
        result = get_preset("amazon.titan-embed-text-v1")
        assert isinstance(result, ModelPreset)
        assert result.dimension == 1536

    def test_unknown_model_returns_none(self) -> None:
        assert get_preset("unknown-model") is None
