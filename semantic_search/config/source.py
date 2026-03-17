"""Per-source configuration dataclass and YAML loader.

Each data source the system indexes (e.g. ``candidates``, ``support_tickets``,
``products``) has its own YAML file under ``config/sources/``.  This module
parses those files into :class:`SourceConfig` instances consumed by the
generate scripts and the unified index builder.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from semantic_search.config.display import DisplayConfig, parse_display_config

LOGGER = logging.getLogger(__name__)


class SourceConfigError(ValueError):
    """Raised when a source configuration file is invalid."""


@dataclass(frozen=True, slots=True)
class ConnectorConfig:
    """Connector wiring for a single data source.

    Attributes:
        type: Connector type key (``csv``, ``sql``, ``json``, ``api``,
            ``xml``, ``mongo``).
        config: Connector-specific parameters forwarded directly to
            :func:`semantic_search.ingestion.get_connector`.
    """

    type: str
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SourceConfig:
    """Complete configuration for a single data source.

    Attributes:
        name: Unique source identifier (derived from the YAML filename).
        connector: Connector wiring.
        text_fields: Columns concatenated for embedding.
        id_field: Column used as the record identifier.
        metadata_fields: Columns stored as filterable metadata.
        detail_fields: Columns stored under ``_detail`` for drill-down.
        id_prefix: Optional prefix prepended to record IDs.
        display: UI display configuration for this source.
    """

    name: str
    connector: ConnectorConfig
    text_fields: List[str] = field(default_factory=list)
    id_field: Optional[str] = None
    metadata_fields: List[str] = field(default_factory=list)
    detail_fields: List[str] = field(default_factory=list)
    id_prefix: Optional[str] = None
    display: DisplayConfig = field(default_factory=DisplayConfig)


def parse_source_config(name: str, raw: Dict[str, Any]) -> SourceConfig:
    """Parse a source YAML mapping into a :class:`SourceConfig`.

    Args:
        name: Source identifier (typically the YAML filename without
            extension).
        raw: Parsed YAML contents.

    Returns:
        A validated :class:`SourceConfig` instance.

    Raises:
        SourceConfigError: If required keys are missing or malformed.
    """
    if not raw or not isinstance(raw, dict):
        raise SourceConfigError(f"Source '{name}': config must be a non-empty mapping.")

    connector_raw = raw.get("connector")
    if not connector_raw or not isinstance(connector_raw, dict):
        raise SourceConfigError(f"Source '{name}': missing or invalid 'connector' block.")

    connector_type = connector_raw.get("type")
    if not connector_type:
        raise SourceConfigError(f"Source '{name}': connector must specify a 'type'.")

    connector = ConnectorConfig(
        type=connector_type,
        config=connector_raw.get("config") or {},
    )

    display = parse_display_config(raw.get("display") or {})

    return SourceConfig(
        name=name,
        connector=connector,
        text_fields=_as_str_list(raw.get("text_fields")),
        id_field=raw.get("id_field"),
        metadata_fields=_as_str_list(raw.get("metadata_fields")),
        detail_fields=_as_str_list(raw.get("detail_fields")),
        id_prefix=raw.get("id_prefix"),
        display=display,
    )


def load_source_configs(sources_dir: Path) -> Dict[str, SourceConfig]:
    """Load all ``*.yaml`` / ``*.yml`` files from *sources_dir*.

    Args:
        sources_dir: Directory containing per-source YAML files.

    Returns:
        Mapping from source name to :class:`SourceConfig`.

    Raises:
        SourceConfigError: If any individual file fails to parse or
            fails validation.
    """
    configs: Dict[str, SourceConfig] = {}
    if not sources_dir.is_dir():
        LOGGER.debug("Sources directory does not exist: %s", sources_dir)
        return configs

    for path in sorted(sources_dir.iterdir()):
        if path.suffix not in (".yaml", ".yml"):
            continue
        name = path.stem
        LOGGER.debug("Loading source config: %s", path)
        with open(path) as fh:
            try:
                raw = yaml.safe_load(fh)
            except yaml.YAMLError as exc:
                raise SourceConfigError(
                    f"Source '{name}': failed to parse YAML in {path}: {exc}"
                ) from exc
        configs[name] = parse_source_config(name, raw)

    LOGGER.info("Loaded %d source config(s) from %s", len(configs), sources_dir)
    return configs


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _as_str_list(value: Any) -> List[str]:
    """Coerce a value to a list of strings.

    Args:
        value: A string, list of strings, or ``None``.

    Returns:
        A list of strings (empty list when ``None``).
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]
