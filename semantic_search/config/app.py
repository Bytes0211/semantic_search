"""Application-level configuration — tier, embedding, server, preprocessing, and model settings.

Reads ``config/app.yaml`` (or a path provided via the ``CONFIG_DIR``
environment variable) and merges it with environment-variable overrides.
Precedence: **env var > YAML value > built-in default**.

Custom embedding models can be declared in the ``models:`` block of
``config/app.yaml`` without editing Python source.  They are merged with the
built-in :data:`~semantic_search.config.models.MODEL_PRESETS` and stored on
:attr:`AppConfig.models` for downstream use.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from semantic_search.config.models import (
    MODEL_PRESETS,
    ModelPreset,
    ModelPresetError,
    load_model_presets,
    resolve_dimension,
)

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
# Preprocessing sub-config
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PreprocessingConfig:
    """Text preprocessing settings applied between ingestion and embedding.

    Controls the :class:`~semantic_search.preprocessing.PreprocessingPipeline`
    that cleans and optionally chunks records before they reach the embedding
    provider.  Chunking is disabled by default to avoid unexpected cost
    increases from inflating record counts.

    Attributes:
        enabled: When ``False`` the pipeline is a pass-through (no cleaning or
            chunking).  Defaults to ``True``.
        clean: Apply :class:`~semantic_search.preprocessing.TextCleaner`
            (HTML stripping, Unicode normalisation, whitespace collapsing).
            Defaults to ``True``.
        chunk: Apply :class:`~semantic_search.preprocessing.TextChunker` to
            split long records.  Defaults to ``False``.
        chunk_size: Maximum character length per chunk.  Only used when
            ``chunk`` is ``True``.  Defaults to ``512``.
        overlap: Overlap in characters between consecutive chunks.  Only used
            when ``chunk`` is ``True``.  Defaults to ``64``.
    """

    enabled: bool = True
    clean: bool = True
    chunk: bool = False
    chunk_size: int = 512
    overlap: int = 64


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
        preprocessing: Text preprocessing configuration.
        models: Merged model preset registry (built-ins + YAML overrides).
            User-defined presets from the ``models:`` block of ``config/app.yaml``
            take precedence over built-in presets.
        detail_enabled: Whether drill-down detail is active.
        filters_enabled: Whether metadata filters are active.
        analytics_enabled: Whether the analytics sidebar is active.
    """

    tier: Tier = Tier.STANDARD
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    preprocessing: PreprocessingConfig = field(default_factory=PreprocessingConfig)
    models: Dict[str, ModelPreset] = field(
        default_factory=lambda: dict(MODEL_PRESETS),
        repr=False,
    )
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
# Pipeline factory
# ---------------------------------------------------------------------------


def build_preprocessing_pipeline(cfg: PreprocessingConfig) -> Optional[Any]:
    """Construct a :class:`~semantic_search.preprocessing.PreprocessingPipeline`.

    Returns ``None`` when preprocessing is disabled or when neither cleaning
    nor chunking are enabled, so callers can skip the pipeline entirely with
    a simple ``if pipeline is not None:`` check.

    Args:
        cfg: Resolved :class:`PreprocessingConfig`.

    Returns:
        A configured pipeline, or ``None`` when preprocessing is a no-op.
    """
    if not cfg.enabled:
        return None

    # Lazy import avoids a hard dependency between the config and preprocessing
    # packages at module load time.
    from semantic_search.preprocessing import (  # noqa: PLC0415
        PreprocessingPipeline,
        TextCleaner,
        TextChunker,
    )

    cleaner = TextCleaner() if cfg.clean else None
    chunker = (
        TextChunker(chunk_size=cfg.chunk_size, overlap=cfg.overlap)
        if cfg.chunk
        else None
    )
    if cleaner is None and chunker is None:
        return None
    return PreprocessingPipeline(cleaner=cleaner, chunker=chunker)


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

    # -- Models (must be resolved before embedding) -------------------------
    models = _resolve_models(raw)

    # -- Embedding ----------------------------------------------------------
    embedding = _resolve_embedding(raw, models)

    # -- Server -------------------------------------------------------------
    server = _resolve_server(raw)

    # -- Feature flags (tier-based, then overrides) -------------------------
    flags = dict(TIER_FEATURES[tier])
    # Env overrides for individual flags
    for key in ("detail_enabled", "filters_enabled", "analytics_enabled"):
        env_val = os.environ.get(key.upper())
        if env_val is not None:
            flags[key] = env_val.lower() in ("true", "1", "yes")

    preprocessing = _resolve_preprocessing(raw)

    return AppConfig(
        tier=tier,
        embedding=embedding,
        server=server,
        preprocessing=preprocessing,
        models=models,
        **flags,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_models(raw: Dict[str, Any]) -> Dict[str, ModelPreset]:
    """Resolve the merged model preset registry from the ``models:`` YAML block.

    Wraps :func:`~semantic_search.config.models.load_model_presets` and
    re-raises :class:`~semantic_search.config.models.ModelPresetError` as
    :class:`AppConfigError` to keep error types consistent for callers.

    Args:
        raw: Parsed app YAML.

    Returns:
        A merged ``Dict[str, ModelPreset]`` (built-ins + user overrides).

    Raises:
        AppConfigError: If any user-defined model entry is invalid.
    """
    try:
        return load_model_presets(raw.get("models"))
    except ModelPresetError as exc:
        raise AppConfigError(str(exc)) from exc


def _resolve_preprocessing(raw: Dict[str, Any]) -> PreprocessingConfig:
    """Resolve preprocessing settings from env overrides merged with YAML.

    Env override mapping:

    * ``PREPROCESSING_ENABLED`` — ``"true"``/``"false"``
    * ``PREPROCESSING_CLEAN``   — ``"true"``/``"false"``
    * ``PREPROCESSING_CHUNK``   — ``"true"``/``"false"``
    * ``PREPROCESSING_CHUNK_SIZE`` — integer
    * ``PREPROCESSING_OVERLAP``    — integer

    Args:
        raw: Parsed app YAML.

    Returns:
        A resolved :class:`PreprocessingConfig`.

    Raises:
        AppConfigError: If chunk_size or overlap cannot be parsed as integers.
    """
    pp_raw = raw.get("preprocessing") or {}

    def _bool_env(env_key: str, yaml_key: str, default: bool) -> bool:
        val = os.environ.get(env_key)
        if val is not None:
            return val.lower() in ("true", "1", "yes")
        return bool(pp_raw.get(yaml_key, default))

    enabled = _bool_env("PREPROCESSING_ENABLED", "enabled", True)
    clean = _bool_env("PREPROCESSING_CLEAN", "clean", True)
    chunk = _bool_env("PREPROCESSING_CHUNK", "chunk", False)

    chunk_size = _parse_int(
        os.environ.get("PREPROCESSING_CHUNK_SIZE") or pp_raw.get("chunk_size", 512),
        "PREPROCESSING_CHUNK_SIZE / preprocessing.chunk_size",
    )
    overlap = _parse_int(
        os.environ.get("PREPROCESSING_OVERLAP") or pp_raw.get("overlap", 64),
        "PREPROCESSING_OVERLAP / preprocessing.overlap",
    )

    if chunk_size <= 0:
        raise AppConfigError(
            f"preprocessing.chunk_size must be a positive integer, got {chunk_size}."
        )
    if overlap < 0:
        raise AppConfigError(
            f"preprocessing.overlap must be non-negative, got {overlap}."
        )
    if chunk and overlap >= chunk_size:
        raise AppConfigError(
            f"preprocessing.overlap ({overlap}) must be less than "
            f"preprocessing.chunk_size ({chunk_size})."
        )

    return PreprocessingConfig(
        enabled=enabled,
        clean=clean,
        chunk=chunk,
        chunk_size=chunk_size,
        overlap=overlap,
    )


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


def _normalise_cors_origins(value: Any) -> str:
    """Coerce *value* to a comma-separated origins string.

    Accepts a YAML list (``["http://a", "http://b"]``) or a plain string
    (``"http://a,http://b"``).  Prevents ``AttributeError`` when YAML authors
    use a sequence instead of a comma-separated string.

    Args:
        value: Raw value from the YAML file or environment variable.

    Returns:
        Comma-separated string of origins.
    """
    if isinstance(value, list):
        return ",".join(str(o) for o in value)
    return str(value)


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
        try:
            data = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise AppConfigError(f"Failed to parse YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise AppConfigError(f"Expected a YAML mapping in {path}, got {type(data).__name__}.")
    return data


def _resolve_tier(raw: Dict[str, Any]) -> Tier:
    """Resolve the subscription tier from env or YAML.

    When ``tier_locked: true`` is set in the YAML, the ``TIER`` environment
    variable is ignored and the YAML value is always used.  This prevents
    clients from escalating their tier after deployment.

    Args:
        raw: Parsed app YAML.

    Returns:
        The resolved :class:`Tier`.

    Raises:
        AppConfigError: If the tier string is not recognised.
    """
    tier_locked = bool(raw.get("tier_locked", False))
    yaml_tier_str = raw.get("tier")

    if tier_locked:
        if yaml_tier_str is None:
            raise AppConfigError(
                "tier_locked is true but no 'tier' value is set in app.yaml."
            )
        env_tier = os.environ.get("TIER")
        if env_tier:
            LOGGER.warning(
                "tier_locked is enabled — ignoring TIER env var ('%s'); "
                "using locked tier '%s'.",
                env_tier,
                yaml_tier_str,
            )
        tier_str = yaml_tier_str
    else:
        tier_str = os.environ.get("TIER") or yaml_tier_str

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


def _resolve_embedding(
    raw: Dict[str, Any],
    registry: Optional[Dict[str, ModelPreset]] = None,
) -> EmbeddingConfig:
    """Resolve embedding config from env overrides merged with YAML.

    Args:
        raw: Parsed app YAML.
        registry: Merged model preset registry (built-ins + user overrides)
            used to auto-resolve the embedding dimension.  Defaults to the
            built-in presets when ``None``.

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
        dimension = resolve_dimension(model, explicit_dim, registry=registry)
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
        cors_origins=_normalise_cors_origins(
            os.environ.get("CORS_ORIGINS") or srv_raw.get("cors_origins", "*")
        ),
        search_top_k=_parse_int(
            os.environ.get("SEARCH_TOP_K") or srv_raw.get("search_top_k", 10),
            "SEARCH_TOP_K / server.search_top_k",
        ),
    )
