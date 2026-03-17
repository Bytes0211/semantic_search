"""Tests for semantic_search.config.models."""

from __future__ import annotations

import pytest

from semantic_search.config.models import (
    MODEL_PRESETS,
    ModelPreset,
    ModelPresetError,
    get_preset,
    load_model_presets,
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


class TestLoadModelPresets:
    """Verify load_model_presets merging and validation logic."""

    def test_none_returns_builtin_copy(self) -> None:
        registry = load_model_presets(None)
        assert registry == MODEL_PRESETS
        # Ensure it is a copy, not the same object
        assert registry is not MODEL_PRESETS

    def test_empty_dict_returns_builtin_copy(self) -> None:
        registry = load_model_presets({})
        assert registry == MODEL_PRESETS

    def test_custom_model_added(self) -> None:
        registry = load_model_presets({"my-model": {"dimension": 512, "backend": "bedrock"}})
        assert "my-model" in registry
        assert registry["my-model"].dimension == 512
        assert registry["my-model"].backend == "bedrock"

    def test_custom_model_description_defaults_to_empty(self) -> None:
        registry = load_model_presets({"my-model": {"dimension": 256}})
        assert registry["my-model"].description == ""

    def test_custom_model_backend_defaults_to_spot(self) -> None:
        registry = load_model_presets({"my-model": {"dimension": 256}})
        assert registry["my-model"].backend == "spot"

    def test_builtin_presets_still_present(self) -> None:
        registry = load_model_presets({"new-model": {"dimension": 128}})
        assert "amazon.titan-embed-text-v1" in registry
        assert "sentence-transformers/all-MiniLM-L6-v2" in registry

    def test_user_entry_overrides_builtin(self) -> None:
        registry = load_model_presets(
            {"amazon.titan-embed-text-v1": {"dimension": 512, "backend": "bedrock"}}
        )
        assert registry["amazon.titan-embed-text-v1"].dimension == 512

    def test_missing_dimension_raises(self) -> None:
        with pytest.raises(ModelPresetError, match="missing required field 'dimension'"):
            load_model_presets({"my-model": {"backend": "spot"}})

    def test_invalid_dimension_string_raises(self) -> None:
        with pytest.raises(ModelPresetError, match="invalid dimension"):
            load_model_presets({"my-model": {"dimension": "big"}})

    def test_zero_dimension_raises(self) -> None:
        with pytest.raises(ModelPresetError, match="positive"):
            load_model_presets({"my-model": {"dimension": 0}})

    def test_negative_dimension_raises(self) -> None:
        with pytest.raises(ModelPresetError, match="positive"):
            load_model_presets({"my-model": {"dimension": -128}})

    def test_non_mapping_entry_raises(self) -> None:
        with pytest.raises(ModelPresetError, match="YAML mapping"):
            load_model_presets({"my-model": 512})

    def test_invalid_backend_raises(self) -> None:
        with pytest.raises(ModelPresetError, match="invalid backend"):
            load_model_presets({"my-model": {"dimension": 512, "backend": "sagemaaker"}})

    def test_non_dict_top_level_raises(self) -> None:
        """models: 0 or models: [] must raise, not silently return built-ins."""
        with pytest.raises(ModelPresetError, match="'models:' must be a YAML mapping"):
            load_model_presets(0)  # type: ignore[arg-type]

    def test_list_top_level_raises(self) -> None:
        with pytest.raises(ModelPresetError, match="'models:' must be a YAML mapping"):
            load_model_presets(["item"])  # type: ignore[arg-type]

    def test_resolve_dimension_uses_custom_registry(self) -> None:
        registry = load_model_presets({"custom/model": {"dimension": 768}})
        assert resolve_dimension("custom/model", registry=registry) == 768


class TestGetPreset:
    """Verify get_preset helper."""

    def test_known_model_returns_preset(self) -> None:
        result = get_preset("amazon.titan-embed-text-v1")
        assert isinstance(result, ModelPreset)
        assert result.dimension == 1536

    def test_unknown_model_returns_none(self) -> None:
        assert get_preset("unknown-model") is None
