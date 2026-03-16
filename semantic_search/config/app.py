"""Application-level configuration — tier, embedding, server settings.

Reads ``config/app.yaml`` (or a path provided via the ``CONFIG_DIR``
environment variable) and merges it with environment-variable overrides.
Precedence: **env var > YAML value > built-in default**.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from semantic_search.config.models import ModelPresetError, resolve_dimension

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tier enum and feature matrix
# ---------------------------------------------------------------------------


class Tier(str, Enum):
    """Client subscription tier.

    Each tier unlocks a progressively larger feature set:

    * **basic** — search only.
    * **standard** — adds drill-down detail and metadata filters.
    * **premium** — adds the analytics sidebar.
    """

    BASIC = "basic"
    STANDARD = "standard"
    PREMIUM = "premium"


TIER_FEATURES: Dict[Tier, Dict[str, bool]] = {
    Tier.BASIC: {
        "detail_enabled": False,
        "filters_enabled": False,
        "analytics_enabled": False,
    },
    Tier.STANDARD: {
        "detail_enabled": True,
        "filters_enabled": True,
        "analytics_enabled": False,
    },
    Tier.PREMIUM: {
        "detail_enabled": True,
        "filters_enabled": True,
        "analytics_enabled": True,
    },
}


class AppConfigError(ValueError):
    """Raised when application configuration is invalid."""


# ---------------------------------------------------------------------------
# Embedding sub-config
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    """Embedding provider settings.

    Attributes:
        backend: Provider key (``bedrock``, ``spot``, ``sagemaker``).
        model: Model identifier.
        dimension: Resolved vector dimensionality.
        config: Extra provider-specific options forwarded to the factory.
    """

    backend: str = "spot"
    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    dimension: int = 384
    config: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Server sub-config
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ServerConfig:
    """Server / runtime settings.

    Attributes:
        host: Bind address.
        port: Bind port.
        log_level: Uvicorn log level.
        cors_origins: Allowed CORS origins.
        search_top_k: Default number of results returned by ``/v1/search``.
    """

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    cors_origins: str = "*"
    search_top_k: int = 10


# ---------------------------------------------------------------------------
# Top-level AppConfig
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Root application configuration.

    Attributes:
        tier: Client subscription tier.
        embedding: Embedding provider configuration.
        server: Server / runtime configuration.
        detail_enabled: Whether drill-down detail is active.
        filters_enabled: Whether metadata filters are active.
        analytics_enabled: Whether the analytics sidebar is active.
    """

    tier: Tier = Tier.STANDARD
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    detail_enabled: bool = True
    filters_enabled: bool = True
    analytics_enabled: bool = False

    def feature_flags(self) -> Dict[str, bool]:
        """Return the feature-flag dict for this configuration.

        Returns:
            Dict with ``detail_enabled``, ``filters_enabled``, and
            ``analytics_enabled`` keys.
        """
        return {
            "detail_enabled": self.detail_enabled,
            "filters_enabled": self.filters_enabled,
            "analytics_enabled": self.analytics_enabled,
        }


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def load_app_config(config_dir: Optional[Path] = None) -> AppConfig:
    """Load and merge the application configuration.

    Resolution order:

    1. Read ``config/app.yaml`` (or *config_dir* ``/app.yaml``).
    2. Apply environment-variable overrides.
    3. Auto-resolve embedding dimension from model presets.
    4. Map tier to feature flags.

    Backward compatibility: if ``ANALYTICS_ENABLED=true`` is set and no
    ``TIER`` env var is present, the tier is upgraded to ``premium``.

    Args:
        config_dir: Optional path to the configuration directory.
            Defaults to ``CONFIG_DIR`` env var, then ``./config``.

    Returns:
        A fully resolved :class:`AppConfig`.

    Raises:
        AppConfigError: If the YAML is malformed or values are invalid.
    """
    config_dir = _resolve_config_dir(config_dir)
    raw = _load_yaml(config_dir / "app.yaml")

    # -- Tier ---------------------------------------------------------------
    tier = _resolve_tier(raw)

    # -- Embedding ----------------------------------------------------------
    embedding = _resolve_embedding(raw)

    # -- Server -------------------------------------------------------------
    server = _resolve_server(raw)

    # -- Feature flags (tier-based, then overrides) -------------------------
    flags = dict(TIER_FEATURES[tier])
    # Env overrides for individual flags
    for key in ("detail_enabled", "filters_enabled", "analytics_enabled"):
        env_val = os.environ.get(key.upper())
        if env_val is not None:
            flags[key] = env_val.lower() in ("true", "1", "yes")

    return AppConfig(
        tier=tier,
        embedding=embedding,
        server=server,
        **flags,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_int(value: Any, label: str) -> int:
    """Coerce *value* to an integer, raising :class:`AppConfigError` on failure.

    Args:
        value: The value to coerce (string, int, or other).
        label: Human-readable config key name used in the error message.

    Returns:
        The integer value.

    Raises:
        AppConfigError: If *value* cannot be converted to an integer.
    """
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise AppConfigError(
            f"Invalid integer value for {label}: {value!r}."
        ) from exc


def _resolve_config_dir(config_dir: Optional[Path]) -> Path:
    """Determine the config directory.

    Args:
        config_dir: Explicit path, or ``None`` to fall back to env / default.

    Returns:
        Resolved directory path.
    """
    if config_dir is not None:
        return config_dir
    env = os.environ.get("CONFIG_DIR")
    if env:
        return Path(env)
    return Path("config")


def _load_yaml(path: Path) -> Dict[str, Any]:
    """Load a YAML file, returning an empty dict when the file is absent.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed YAML mapping, or an empty dict.
    """
    if not path.is_file():
        LOGGER.debug("Config file not found, using defaults: %s", path)
        return {}
    LOGGER.info("Loading app config from %s", path)
    with open(path) as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise AppConfigError(f"Expected a YAML mapping in {path}, got {type(data).__name__}.")
    return data


def _resolve_tier(raw: Dict[str, Any]) -> Tier:
    """Resolve the subscription tier from env or YAML.

    Args:
        raw: Parsed app YAML.

    Returns:
        The resolved :class:`Tier`.

    Raises:
        AppConfigError: If the tier string is not recognised.
    """
    tier_str = os.environ.get("TIER") or raw.get("tier")

    # Backward compat: ANALYTICS_ENABLED=true → premium
    if tier_str is None:
        analytics_env = os.environ.get("ANALYTICS_ENABLED", "").lower()
        if analytics_env in ("true", "1", "yes"):
            return Tier.PREMIUM
        return Tier.STANDARD  # default

    try:
        return Tier(str(tier_str).lower())
    except ValueError as exc:
        valid = ", ".join(t.value for t in Tier)
        raise AppConfigError(
            f"Invalid tier '{tier_str}'.  Valid tiers: {valid}."
        ) from exc


def _resolve_embedding(raw: Dict[str, Any]) -> EmbeddingConfig:
    """Resolve embedding config from env overrides merged with YAML.

    Args:
        raw: Parsed app YAML.

    Returns:
        A resolved :class:`EmbeddingConfig`.

    Raises:
        AppConfigError: If the dimension is not a valid integer or the model
            is unknown and no explicit dimension is provided.
    """
    emb_raw = raw.get("embedding") or {}

    backend = os.environ.get("EMBEDDING_BACKEND") or emb_raw.get("backend", "spot")
    model = os.environ.get("EMBEDDING_MODEL") or emb_raw.get(
        "model", "sentence-transformers/all-MiniLM-L6-v2"
    )

    explicit_dim_str = os.environ.get("EMBEDDING_DIMENSION") or emb_raw.get("dimension")
    explicit_dim = (
        _parse_int(explicit_dim_str, "EMBEDDING_DIMENSION / embedding.dimension")
        if explicit_dim_str is not None
        else None
    )

    try:
        dimension = resolve_dimension(model, explicit_dim)
    except ModelPresetError as exc:
        raise AppConfigError(str(exc)) from exc
    extra_config = emb_raw.get("config") or {}

    return EmbeddingConfig(
        backend=backend,
        model=model,
        dimension=dimension,
        config=extra_config,
    )


def _resolve_server(raw: Dict[str, Any]) -> ServerConfig:
    """Resolve server settings from env overrides merged with YAML.

    Args:
        raw: Parsed app YAML.

    Returns:
        A resolved :class:`ServerConfig`.

    Raises:
        AppConfigError: If PORT or SEARCH_TOP_K cannot be parsed as integers.
    """
    srv_raw = raw.get("server") or {}

    return ServerConfig(
        host=os.environ.get("HOST") or srv_raw.get("host", "0.0.0.0"),
        port=_parse_int(
            os.environ.get("PORT") or srv_raw.get("port", 8000),
            "PORT / server.port",
        ),
        log_level=os.environ.get("LOG_LEVEL") or srv_raw.get("log_level", "info"),
        cors_origins=os.environ.get("CORS_ORIGINS") or srv_raw.get("cors_origins", "*"),
        search_top_k=_parse_int(
            os.environ.get("SEARCH_TOP_K") or srv_raw.get("search_top_k", 10),
            "SEARCH_TOP_K / server.search_top_k",
        ),
    )
