"""Tests for semantic_search.config.app."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from semantic_search.config.app import (
    AppConfig,
    AppConfigError,
    EmbeddingConfig,
    PreprocessingConfig,
    ServerConfig,
    Tier,
    TIER_FEATURES,
    build_preprocessing_pipeline,
    load_app_config,
)


class TestTier:
    """Verify tier enum and feature matrix."""

    def test_basic_features(self) -> None:
        flags = TIER_FEATURES[Tier.BASIC]
        assert flags["detail_enabled"] is False
        assert flags["filters_enabled"] is False
        assert flags["analytics_enabled"] is False

    def test_standard_features(self) -> None:
        flags = TIER_FEATURES[Tier.STANDARD]
        assert flags["detail_enabled"] is True
        assert flags["filters_enabled"] is True
        assert flags["analytics_enabled"] is False

    def test_premium_features(self) -> None:
        flags = TIER_FEATURES[Tier.PREMIUM]
        assert flags["analytics_enabled"] is True


class TestAppConfig:
    """Verify AppConfig dataclass defaults and feature_flags()."""

    def test_defaults(self) -> None:
        cfg = AppConfig()
        assert cfg.tier == Tier.STANDARD
        assert cfg.detail_enabled is True
        assert cfg.analytics_enabled is False

    def test_feature_flags(self) -> None:
        cfg = AppConfig(analytics_enabled=True)
        flags = cfg.feature_flags()
        assert flags["analytics_enabled"] is True


class TestLoadAppConfig:
    """Verify YAML loading, env overrides, and backward compat."""

    def test_no_yaml_returns_defaults(self, tmp_path: Path) -> None:
        cfg = load_app_config(tmp_path)
        assert cfg.tier == Tier.STANDARD
        assert cfg.embedding.backend == "spot"

    def test_reads_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(
            yaml.dump({
                "tier": "premium",
                "embedding": {
                    "backend": "bedrock",
                    "model": "amazon.titan-embed-text-v1",
                },
                "server": {"port": 9000},
            })
        )
        cfg = load_app_config(tmp_path)
        assert cfg.tier == Tier.PREMIUM
        assert cfg.embedding.backend == "bedrock"
        assert cfg.embedding.dimension == 1536  # auto-resolved
        assert cfg.server.port == 9000
        assert cfg.analytics_enabled is True  # premium tier

    def test_env_tier_overrides_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "app.yaml").write_text(yaml.dump({"tier": "basic"}))
        monkeypatch.setenv("TIER", "premium")
        cfg = load_app_config(tmp_path)
        assert cfg.tier == Tier.PREMIUM

    def test_analytics_enabled_backward_compat(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANALYTICS_ENABLED", "true")
        cfg = load_app_config(tmp_path)
        assert cfg.tier == Tier.PREMIUM

    def test_invalid_tier_raises(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(yaml.dump({"tier": "gold"}))
        with pytest.raises(AppConfigError, match="Invalid tier"):
            load_app_config(tmp_path)

    def test_env_embedding_overrides(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMBEDDING_BACKEND", "bedrock")
        monkeypatch.setenv("EMBEDDING_MODEL", "amazon.titan-embed-text-v2")
        cfg = load_app_config(tmp_path)
        assert cfg.embedding.backend == "bedrock"
        assert cfg.embedding.model == "amazon.titan-embed-text-v2"
        assert cfg.embedding.dimension == 1024

    def test_explicit_dimension_override(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(
            yaml.dump({"embedding": {"model": "custom-model", "dimension": 512}})
        )
        cfg = load_app_config(tmp_path)
        assert cfg.embedding.dimension == 512

    def test_env_flag_overrides_tier(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        (tmp_path / "app.yaml").write_text(yaml.dump({"tier": "basic"}))
        monkeypatch.setenv("DETAIL_ENABLED", "true")
        cfg = load_app_config(tmp_path)
        assert cfg.tier == Tier.BASIC
        # Basic normally has detail_enabled=False, but env override flips it
        assert cfg.detail_enabled is True

    def test_malformed_yaml_raises(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text("just a string")
        with pytest.raises(AppConfigError, match="YAML mapping"):
            load_app_config(tmp_path)

    def test_syntax_error_yaml_raises(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text("key: [unclosed")
        with pytest.raises(AppConfigError, match="Failed to parse YAML"):
            load_app_config(tmp_path)

    def test_cors_origins_yaml_list_normalised(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(
            yaml.dump({"server": {"cors_origins": ["http://localhost:5173", "http://localhost:4173"]}})
        )
        cfg = load_app_config(tmp_path)
        assert cfg.server.cors_origins == "http://localhost:5173,http://localhost:4173"

    def test_invalid_port_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PORT", "not-a-port")
        with pytest.raises(AppConfigError, match="PORT / server.port"):
            load_app_config(tmp_path)

    def test_invalid_search_top_k_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEARCH_TOP_K", "many")
        with pytest.raises(AppConfigError, match="SEARCH_TOP_K / server.search_top_k"):
            load_app_config(tmp_path)

    def test_unknown_model_without_dimension_raises(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(
            yaml.dump({"embedding": {"model": "unknown/custom-model"}})
        )
        with pytest.raises(AppConfigError, match="not in the preset registry"):
            load_app_config(tmp_path)

    def test_custom_model_via_yaml_resolves_dimension(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(
            yaml.dump({
                "models": {"my-custom-model": {"dimension": 768, "backend": "sagemaker"}},
                "embedding": {"model": "my-custom-model"},
            })
        )
        cfg = load_app_config(tmp_path)
        assert cfg.embedding.dimension == 768
        assert cfg.embedding.model == "my-custom-model"
        assert "my-custom-model" in cfg.models

    def test_custom_model_overrides_builtin(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(
            yaml.dump({
                "models": {"amazon.titan-embed-text-v1": {"dimension": 512, "backend": "bedrock"}},
                "embedding": {"model": "amazon.titan-embed-text-v1"},
            })
        )
        cfg = load_app_config(tmp_path)
        assert cfg.embedding.dimension == 512  # user override wins over built-in 1536

    def test_models_registry_contains_builtins(self, tmp_path: Path) -> None:
        cfg = load_app_config(tmp_path)
        assert "amazon.titan-embed-text-v1" in cfg.models
        assert "sentence-transformers/all-MiniLM-L6-v2" in cfg.models

    def test_invalid_custom_model_dimension_raises(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(
            yaml.dump({"models": {"my-model": {"dimension": -1}}})
        )
        with pytest.raises(AppConfigError, match="positive"):
            load_app_config(tmp_path)

    def test_custom_model_missing_dimension_raises(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(
            yaml.dump({"models": {"my-model": {"backend": "spot"}}})
        )
        with pytest.raises(AppConfigError, match="missing required field"):
            load_app_config(tmp_path)

    def test_invalid_embedding_dimension_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EMBEDDING_DIMENSION", "big")
        with pytest.raises(AppConfigError, match="EMBEDDING_DIMENSION"):
            load_app_config(tmp_path)

    def test_preprocessing_defaults(self, tmp_path: Path) -> None:
        cfg = load_app_config(tmp_path)
        assert cfg.preprocessing.enabled is True
        assert cfg.preprocessing.clean is True
        assert cfg.preprocessing.chunk is False
        assert cfg.preprocessing.chunk_size == 512
        assert cfg.preprocessing.overlap == 64

    def test_preprocessing_from_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(
            yaml.dump({
                "preprocessing": {
                    "enabled": True,
                    "clean": False,
                    "chunk": True,
                    "chunk_size": 256,
                    "overlap": 32,
                }
            })
        )
        cfg = load_app_config(tmp_path)
        assert cfg.preprocessing.clean is False
        assert cfg.preprocessing.chunk is True
        assert cfg.preprocessing.chunk_size == 256
        assert cfg.preprocessing.overlap == 32

    def test_preprocessing_disabled_via_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(
            yaml.dump({"preprocessing": {"enabled": False}})
        )
        cfg = load_app_config(tmp_path)
        assert cfg.preprocessing.enabled is False

    def test_preprocessing_env_overrides(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PREPROCESSING_ENABLED", "false")
        monkeypatch.setenv("PREPROCESSING_CHUNK", "true")
        monkeypatch.setenv("PREPROCESSING_CHUNK_SIZE", "1024")
        monkeypatch.setenv("PREPROCESSING_OVERLAP", "128")
        cfg = load_app_config(tmp_path)
        assert cfg.preprocessing.enabled is False
        assert cfg.preprocessing.chunk is True
        assert cfg.preprocessing.chunk_size == 1024
        assert cfg.preprocessing.overlap == 128

    def test_preprocessing_invalid_chunk_size_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PREPROCESSING_CHUNK_SIZE", "big")
        with pytest.raises(AppConfigError, match="PREPROCESSING_CHUNK_SIZE"):
            load_app_config(tmp_path)

    def test_preprocessing_overlap_gte_chunk_size_raises(self, tmp_path: Path) -> None:
        (tmp_path / "app.yaml").write_text(
            yaml.dump({"preprocessing": {"chunk": True, "chunk_size": 100, "overlap": 100}})
        )
        with pytest.raises(AppConfigError, match="overlap"):
            load_app_config(tmp_path)

    def test_preprocessing_overlap_gte_chunk_size_allowed_when_chunk_disabled(
        self, tmp_path: Path
    ) -> None:
        """overlap >= chunk_size is permitted when chunking is disabled."""
        (tmp_path / "app.yaml").write_text(
            yaml.dump({"preprocessing": {"chunk": False, "chunk_size": 100, "overlap": 100}})
        )
        cfg = load_app_config(tmp_path)  # must not raise
        assert cfg.preprocessing.chunk is False
        assert cfg.preprocessing.overlap == 100


class TestBuildPreprocessingPipeline:
    """Verify build_preprocessing_pipeline constructs pipelines correctly."""

    def test_disabled_returns_none(self) -> None:
        cfg = PreprocessingConfig(enabled=False)
        assert build_preprocessing_pipeline(cfg) is None

    def test_clean_only_returns_pipeline(self) -> None:
        from semantic_search.preprocessing import PreprocessingPipeline

        cfg = PreprocessingConfig(enabled=True, clean=True, chunk=False)
        pipeline = build_preprocessing_pipeline(cfg)
        assert isinstance(pipeline, PreprocessingPipeline)

    def test_neither_clean_nor_chunk_returns_none(self) -> None:
        cfg = PreprocessingConfig(enabled=True, clean=False, chunk=False)
        assert build_preprocessing_pipeline(cfg) is None

    def test_chunk_enabled_returns_pipeline(self) -> None:
        from semantic_search.preprocessing import PreprocessingPipeline

        cfg = PreprocessingConfig(enabled=True, clean=False, chunk=True, chunk_size=100, overlap=10)
        pipeline = build_preprocessing_pipeline(cfg)
        assert isinstance(pipeline, PreprocessingPipeline)

    def test_pipeline_cleans_html(self) -> None:
        from semantic_search.ingestion.base import Record

        cfg = PreprocessingConfig(enabled=True, clean=True, chunk=False)
        pipeline = build_preprocessing_pipeline(cfg)
        assert pipeline is not None
        records = [Record("r1", "<p>Hello   World</p>", {}, "test")]
        result = list(pipeline.process(records))
        assert len(result) == 1
        assert result[0].text == "Hello World"

    def test_pipeline_chunks_long_text(self) -> None:
        from semantic_search.ingestion.base import Record

        cfg = PreprocessingConfig(
            enabled=True, clean=False, chunk=True, chunk_size=20, overlap=0
        )
        pipeline = build_preprocessing_pipeline(cfg)
        assert pipeline is not None
        long_text = "word " * 20  # 100 chars > chunk_size=20
        records = [Record("r1", long_text.strip(), {}, "test")]
        result = list(pipeline.process(records))
        assert len(result) > 1
        assert all(r.record_id.startswith("r1#chunk-") for r in result)
