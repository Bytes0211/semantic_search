"""Tests for semantic_search.config.app."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from semantic_search.config.app import (
    AppConfig,
    AppConfigError,
    EmbeddingConfig,
    ServerConfig,
    Tier,
    TIER_FEATURES,
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
