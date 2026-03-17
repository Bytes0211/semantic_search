"""Configuration package for the semantic search platform.

Public API
----------
- **App config:** :func:`load_app_config`, :class:`AppConfig`, :class:`Tier`
- **Source configs:** :func:`load_source_configs`, :class:`SourceConfig`
- **Display configs:** :class:`DisplayConfig`, :func:`parse_display_config`
- **Model presets:** :func:`resolve_dimension`, :data:`MODEL_PRESETS`
- **Metadata helper:** :func:`split_metadata`
"""

from semantic_search.config.app import (
    AppConfig,
    AppConfigError,
    EmbeddingConfig,
    ServerConfig,
    Tier,
    TIER_FEATURES,
    load_app_config,
)
from semantic_search.config.display import (
    ColumnConfig,
    DetailSectionConfig,
    DisplayConfig,
    DisplayConfigError,
    parse_display_config,
)
from semantic_search.config.metadata import split_metadata
from semantic_search.config.models import (
    MODEL_PRESETS,
    ModelPreset,
    ModelPresetError,
    get_preset,
    resolve_dimension,
)
from semantic_search.config.source import (
    ConnectorConfig,
    SourceConfig,
    SourceConfigError,
    load_source_configs,
    parse_source_config,
)

__all__ = [
    # app
    "AppConfig",
    "AppConfigError",
    "EmbeddingConfig",
    "ServerConfig",
    "Tier",
    "TIER_FEATURES",
    "load_app_config",
    # display
    "ColumnConfig",
    "DetailSectionConfig",
    "DisplayConfig",
    "DisplayConfigError",
    "parse_display_config",
    # metadata
    "split_metadata",
    # models
    "MODEL_PRESETS",
    "ModelPreset",
    "ModelPresetError",
    "get_preset",
    "resolve_dimension",
    # source
    "ConnectorConfig",
    "SourceConfig",
    "SourceConfigError",
    "load_source_configs",
    "parse_source_config",
]
