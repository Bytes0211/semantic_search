"""Unified index builder — config-driven multi-source index generation.

Reads ``config/app.yaml`` and all ``config/sources/*.yaml`` files (or paths
specified via CLI), iterates over each enabled source, and produces a combined
vector index using the configured embedding backend and model.

Usage::

    # Default: reads config/ directory, builds index at ./vector_index
    uv run python scripts/generate_index.py

    # Custom config directory and output
    uv run python scripts/generate_index.py --config-dir ./my_config --output ./my_index

    # Single source only
    uv run python scripts/generate_index.py --source sample_csv

    # Override embedding backend from the command line
    uv run python scripts/generate_index.py --backend spot --model sentence-transformers/all-MiniLM-L6-v2
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from semantic_search.config.app import load_app_config, AppConfig
from semantic_search.config.metadata import split_metadata
from semantic_search.config.source import SourceConfig, load_source_configs
from semantic_search.embeddings.base import EmbeddingInput
from semantic_search.vectorstores.faiss_store import NumpyVectorStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract_from_source(source: SourceConfig) -> List[EmbeddingInput]:
    """Extract records from a single data source and convert to EmbeddingInputs.

    Args:
        source: Source configuration loaded from YAML.

    Returns:
        List of EmbeddingInput objects ready for embedding.

    Raises:
        SystemExit: If the connector fails to extract records.
    """
    from semantic_search.ingestion import DataSourceError, get_connector

    detail_field_set: Set[str] = set(source.detail_fields)
    all_metadata_fields = source.metadata_fields + [
        f for f in source.detail_fields if f not in source.metadata_fields
    ]

    connector_config: Dict[str, Any] = dict(source.connector.config)
    # Inject text_fields, id_field, metadata_fields if the connector supports them
    if source.text_fields:
        connector_config.setdefault("text_fields", source.text_fields)
    if source.id_field:
        connector_config.setdefault("id_field", source.id_field)
    if all_metadata_fields:
        connector_config.setdefault("metadata_fields", all_metadata_fields)

    LOGGER.info("Extracting from source '%s' (connector: %s)", source.name, source.connector.type)
    try:
        connector = get_connector(source.connector.type, connector_config)
        records = list(connector.extract())
    except DataSourceError as exc:
        LOGGER.critical("Failed to extract from '%s': %s", source.name, exc)
        raise SystemExit(1) from exc

    prefix = source.id_prefix or source.name
    inputs = [
        EmbeddingInput(
            record_id=f"{prefix}-{r.record_id}" if source.id_prefix else r.record_id,
            text=r.text,
            metadata={
                **split_metadata(dict(r.metadata), detail_field_set),
                "source": source.name,
            },
        )
        for r in records
    ]
    LOGGER.info("  Extracted %d records from '%s'", len(inputs), source.name)
    return inputs


# ---------------------------------------------------------------------------
# Index building
# ---------------------------------------------------------------------------


def build_index(
    app_cfg: AppConfig,
    sources: List[SourceConfig],
) -> NumpyVectorStore:
    """Build a combined vector index from multiple data sources.

    Args:
        app_cfg: Application configuration with embedding settings.
        sources: List of source configurations to process.

    Returns:
        A populated NumpyVectorStore with embedded vectors from all sources.

    Raises:
        SystemExit: On provider init failure or if no records are extracted.
    """
    backend = app_cfg.embedding.backend
    model = app_cfg.embedding.model
    dimension = app_cfg.embedding.dimension
    extra_config = app_cfg.embedding.config

    # Register and instantiate the embedding provider
    _register_backend(backend)
    from semantic_search.embeddings.factory import get_provider
    from semantic_search.pipeline.embedding_pipeline import EmbeddingPipeline

    provider_config: Dict[str, Any] = {"model_name": model, "dimension": dimension}
    if backend == "bedrock":
        provider_config = {"model": model, "region": extra_config.get("region", "us-east-1")}
    elif backend == "sagemaker":
        provider_config = {
            "endpoint_name": extra_config.get("endpoint_name", ""),
            "region": extra_config.get("region", "us-east-1"),
            "dimension": dimension,
        }
    # spot uses model_name + dimension

    LOGGER.info(
        "Initialising %s provider: model=%s  dimension=%d", backend, model, dimension
    )
    try:
        provider = get_provider(backend, provider_config)
    except Exception as exc:  # noqa: BLE001
        LOGGER.critical("Failed to initialise %s provider: %s", backend, exc)
        raise SystemExit(1) from exc

    # Extract records from all sources
    all_inputs: List[EmbeddingInput] = []
    for source in sources:
        all_inputs.extend(extract_from_source(source))

    if not all_inputs:
        LOGGER.critical("No records extracted from any source — nothing to embed.")
        raise SystemExit(1)

    # Build the vector store
    store = NumpyVectorStore(dimension=dimension, metric="cosine")
    pipeline = EmbeddingPipeline(provider, store, batch_size=50)

    LOGGER.info("Embedding %d records via %s ...", len(all_inputs), backend)
    result = pipeline.run(all_inputs)
    LOGGER.info(
        "Embedding complete: %d succeeded, %d failed.",
        result.succeeded,
        result.failed,
    )
    if result.failed:
        LOGGER.warning("Failed record IDs: %s", result.failed_ids)

    return store


def _register_backend(backend: str) -> None:
    """Import the backend module to register its factory.

    Args:
        backend: Backend identifier (``spot``, ``bedrock``, ``sagemaker``).
    """
    if backend == "spot":
        import semantic_search.embeddings.spot  # noqa: F401
    elif backend == "bedrock":
        import semantic_search.embeddings.bedrock  # noqa: F401
    elif backend == "sagemaker":
        import semantic_search.embeddings.sagemaker  # noqa: F401
    else:
        LOGGER.warning("Unknown backend '%s' — attempting direct factory lookup.", backend)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        Parsed :class:`argparse.Namespace`.
    """
    parser = argparse.ArgumentParser(
        description="Unified config-driven index builder for all data sources."
    )
    parser.add_argument(
        "--config-dir",
        default="./config",
        help="Path to config directory containing app.yaml and sources/ (default: ./config)",
    )
    parser.add_argument(
        "--source",
        default=None,
        help="Process a single source only (by name). Omit to process all sources.",
    )
    parser.add_argument(
        "--output",
        default="./vector_index",
        help="Output directory for the combined index (default: ./vector_index)",
    )
    parser.add_argument(
        "--backend",
        default=None,
        help="Override embedding backend (spot, bedrock, sagemaker)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Override embedding model identifier",
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=None,
        help="Override embedding vector dimensionality",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the unified index builder.

    Args:
        argv: Argument list forwarded to :func:`parse_args`.

    Returns:
        Exit code (0 on success, 1 on error).
    """
    args = parse_args(argv)
    config_dir = Path(args.config_dir)

    # Load configuration
    app_cfg = load_app_config(config_dir)
    source_configs = load_source_configs(config_dir / "sources")

    if not source_configs:
        LOGGER.critical("No source configs found in %s/sources/", config_dir)
        raise SystemExit(1)

    # CLI overrides for embedding settings
    if args.backend or args.model or args.dimension is not None:
        from semantic_search.config.app import EmbeddingConfig
        from semantic_search.config.models import resolve_dimension

        backend = args.backend or app_cfg.embedding.backend
        model = args.model or app_cfg.embedding.model
        dim = resolve_dimension(model, args.dimension) if args.dimension else app_cfg.embedding.dimension
        app_cfg = AppConfig(
            tier=app_cfg.tier,
            embedding=EmbeddingConfig(
                backend=backend,
                model=model,
                dimension=dim,
                config=app_cfg.embedding.config,
            ),
            server=app_cfg.server,
            detail_enabled=app_cfg.detail_enabled,
            filters_enabled=app_cfg.filters_enabled,
            analytics_enabled=app_cfg.analytics_enabled,
        )

    # Filter to a single source if requested
    if args.source:
        if args.source not in source_configs:
            LOGGER.critical(
                "Source '%s' not found.  Available: %s",
                args.source,
                ", ".join(sorted(source_configs)),
            )
            raise SystemExit(1)
        sources = [source_configs[args.source]]
    else:
        sources = list(source_configs.values())

    LOGGER.info(
        "Building index: %d source(s), backend=%s, model=%s, dimension=%d",
        len(sources),
        app_cfg.embedding.backend,
        app_cfg.embedding.model,
        app_cfg.embedding.dimension,
    )

    store = build_index(app_cfg, sources)
    store.save(args.output)
    LOGGER.info("Saved %d records to %r", len(store._vectors), args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
