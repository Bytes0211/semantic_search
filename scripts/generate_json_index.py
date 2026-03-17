"""Generate a Spot-embedded vector index from one or more JSON/JSONL files.

Extracts records from JSON files using the ``JsonConnector``, embeds the
concatenated text fields using the local Spot provider, and saves the
resulting NumpyVectorStore for local server validation.

Usage::

    # Default: data/sample_products.json
    uv run python scripts/generate_json_index.py

    # Custom path, fields, and detail
    uv run python scripts/generate_json_index.py \\
        --json ./data/my_data.json \\
        --text-fields name,description \\
        --id-field id \\
        --metadata-fields category,brand \\
        --detail-fields description \\
        --output ./my_json_index

    # With jq-style filter for nested arrays
    uv run python scripts/generate_json_index.py \\
        --json ./data/nested.json --jq-filter .data.items
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from semantic_search.config.app import PreprocessingConfig, build_preprocessing_pipeline
from semantic_search.config.metadata import split_metadata
from semantic_search.embeddings.base import EmbeddingInput
from semantic_search.vectorstores.faiss_store import NumpyVectorStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (match data/sample_products.json)
# ---------------------------------------------------------------------------

DEFAULT_JSON = "./data/sample_products.json"
DEFAULT_TEXT_FIELDS = "name,description"
DEFAULT_ID_FIELD = "id"
DEFAULT_METADATA_FIELDS = "category,brand"
DEFAULT_DETAIL_FIELDS = "description"
DEFAULT_OUTPUT = "./json_spot_index"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIM = 384


def extract_inputs(
    json_path: str,
    text_fields: List[str],
    id_field: str,
    metadata_fields: List[str],
    detail_fields: Optional[List[str]] = None,
    jq_filter: Optional[str] = None,
    preprocessing_pipeline: Optional[Any] = None,
) -> List[EmbeddingInput]:
    """Extract records from JSON files and convert to EmbeddingInputs.

    Args:
        json_path: Path or glob pattern to one or more JSON/JSONL files.
        text_fields: Ordered list of field names to concatenate as the
            embeddable text payload.
        id_field: Field used as the record identifier.
        metadata_fields: Fields stored as filterable metadata.
        detail_fields: Optional fields stored under ``_detail`` in metadata
            for drill-down display.
        jq_filter: Optional jq-style dotted path to extract record arrays
            from nested JSON structures.
        preprocessing_pipeline: Optional pipeline to clean/chunk records
            before embedding.

    Returns:
        List of EmbeddingInput objects ready for the embedding pipeline.

    Raises:
        SystemExit: If the connector cannot read the JSON or finds no records.
    """
    from semantic_search.ingestion import DataSourceError, get_connector

    detail_fields = detail_fields or []
    detail_field_set: Set[str] = set(detail_fields)
    all_metadata_fields = metadata_fields + [
        f for f in detail_fields if f not in metadata_fields
    ]

    LOGGER.info("Extracting from JSON: %s", json_path)
    config: dict = {
        "path": json_path,
        "text_fields": text_fields,
        "id_field": id_field,
        "metadata_fields": all_metadata_fields,
    }
    if jq_filter:
        config["jq_filter"] = jq_filter

    try:
        connector = get_connector("json", config)
        records = list(connector.extract())
    except DataSourceError as exc:
        LOGGER.critical("Failed to extract from JSON: %s", exc)
        raise SystemExit(1) from exc

    if preprocessing_pipeline is not None:
        records = list(preprocessing_pipeline.process(records))
        LOGGER.info("  After preprocessing: %d records", len(records))

    inputs = [
        EmbeddingInput(
            record_id=r.record_id,
            text=r.text,
            metadata=split_metadata(dict(r.metadata), detail_field_set),
        )
        for r in records
    ]
    LOGGER.info("  Extracted %d records", len(inputs))
    return inputs


def build_json_spot_index(
    json_path: str,
    text_fields: List[str],
    id_field: str,
    metadata_fields: List[str],
    detail_fields: Optional[List[str]] = None,
    jq_filter: Optional[str] = None,
    model_name: str = DEFAULT_MODEL,
    dimension: int = DEFAULT_DIM,
    preprocessing_pipeline: Optional[Any] = None,
) -> NumpyVectorStore:
    """Extract JSON records and embed them using the Spot provider.

    Args:
        json_path: Path or glob pattern to one or more JSON/JSONL files.
        text_fields: Fields concatenated to produce embeddable text.
        id_field: Field used as record identifier.
        metadata_fields: Fields stored as filterable metadata.
        detail_fields: Optional fields stored under ``_detail`` in metadata
            for drill-down display.
        jq_filter: Optional jq-style dotted path to extract record arrays.
        model_name: Logical model identifier reported in result metadata.
        dimension: Embedding vector dimensionality (must match the model).
        preprocessing_pipeline: Optional pipeline to clean/chunk records
            before embedding.

    Returns:
        A populated NumpyVectorStore ready to be saved and served.

    Raises:
        SystemExit: On provider initialisation failure or if no records are
            found to embed.
    """
    import semantic_search.embeddings.spot  # noqa: F401 — registers 'spot' factory
    from semantic_search.embeddings.factory import get_provider
    from semantic_search.pipeline.embedding_pipeline import EmbeddingPipeline

    LOGGER.info(
        "Initialising Spot provider: model=%s  dimension=%d", model_name, dimension
    )
    try:
        provider = get_provider(
            "spot", {"model_name": model_name, "dimension": dimension}
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.critical("Failed to initialise Spot provider: %s", exc)
        raise SystemExit(1) from exc

    inputs = extract_inputs(
        json_path, text_fields, id_field, metadata_fields, detail_fields, jq_filter,
        preprocessing_pipeline=preprocessing_pipeline,
    )
    if not inputs:
        LOGGER.critical("No records extracted — nothing to embed.")
        raise SystemExit(1)

    store = NumpyVectorStore(dimension=dimension, metric="cosine")
    pipeline = EmbeddingPipeline(provider, store, batch_size=50)

    LOGGER.info("Embedding %d records via Spot ...", len(inputs))
    result = pipeline.run(inputs)
    LOGGER.info(
        "Embedding complete: %d succeeded, %d failed.",
        result.succeeded,
        result.failed,
    )
    if result.failed:
        LOGGER.warning("Failed record IDs: %s", result.failed_ids)

    return store


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        Parsed :class:`argparse.Namespace`.
    """
    parser = argparse.ArgumentParser(
        description="Generate a Spot-embedded FAISS index from JSON/JSONL file(s)."
    )
    parser.add_argument(
        "--json",
        default=None,
        help=f"Path or glob to JSON/JSONL file(s) (default: {DEFAULT_JSON!r})",
    )
    parser.add_argument(
        "--text-fields",
        default=None,
        help=f"Comma-separated text columns (default: {DEFAULT_TEXT_FIELDS!r})",
    )
    parser.add_argument(
        "--id-field",
        default=None,
        help=f"Field used as record ID (default: {DEFAULT_ID_FIELD!r})",
    )
    parser.add_argument(
        "--metadata-fields",
        default=None,
        help=f"Comma-separated metadata fields (default: {DEFAULT_METADATA_FIELDS!r})",
    )
    parser.add_argument(
        "--detail-fields",
        default=None,
        help=f"Comma-separated detail fields for drill-down display (default: {DEFAULT_DETAIL_FIELDS!r})",
    )
    parser.add_argument(
        "--jq-filter",
        default=None,
        help="Optional jq-style dotted path to extract records (e.g. '.data.items')",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output directory for the index (default: {DEFAULT_OUTPUT!r})",
    )
    parser.add_argument(
        "--model-name",
        default=None,
        help=f"Spot model identifier reported in metadata (default: {DEFAULT_MODEL!r})",
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=None,
        help=f"Embedding vector dimensionality (default: {DEFAULT_DIM})",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to a source YAML config file (e.g. config/sources/products.yaml)",
    )
    parser.add_argument(
        "--app-config",
        default=None,
        help="Path to config directory containing app.yaml (e.g. ./config)",
    )
    parser.add_argument(
        "--no-preprocessing",
        action="store_true",
        default=False,
        help="Disable all preprocessing (cleaning and chunking) regardless of config.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the JSON Spot index generator.

    Args:
        argv: Argument list forwarded to :func:`parse_args`.

    Returns:
        Exit code (0 on success, 1 on error).
    """
    args = parse_args(argv)

    # --- Optional YAML config loading --------------------------------------
    src_cfg = None
    app_cfg = None
    if args.config:
        import yaml
        from semantic_search.config.source import parse_source_config

        with open(args.config) as fh:
            try:
                raw = yaml.safe_load(fh)
            except yaml.YAMLError as exc:
                LOGGER.critical("Failed to parse YAML config %s: %s", args.config, exc)
                raise SystemExit(1) from exc
        src_cfg = parse_source_config(Path(args.config).stem, raw)
        LOGGER.info("Loaded source config: %s", args.config)

    if args.app_config:
        from semantic_search.config.app import load_app_config

        app_cfg = load_app_config(Path(args.app_config))
        LOGGER.info("Loaded app config from: %s", args.app_config)

    # --- Resolve fields: CLI > source YAML > defaults ----------------------
    json_path = args.json or (
        src_cfg.connector.config["path"]
        if src_cfg and src_cfg.connector.config.get("path")
        else DEFAULT_JSON
    )

    text_fields_raw = args.text_fields or (
        ",".join(src_cfg.text_fields) if src_cfg and src_cfg.text_fields else DEFAULT_TEXT_FIELDS
    )
    text_fields = [f.strip() for f in text_fields_raw.split(",") if f.strip()]

    metadata_fields_raw = args.metadata_fields or (
        ",".join(src_cfg.metadata_fields)
        if src_cfg and src_cfg.metadata_fields
        else DEFAULT_METADATA_FIELDS
    )
    metadata_fields = [f.strip() for f in metadata_fields_raw.split(",") if f.strip()]

    if args.detail_fields is not None:
        detail_fields = [f.strip() for f in args.detail_fields.split(",") if f.strip()]
    elif src_cfg is not None:
        detail_fields = list(src_cfg.detail_fields)  # honours explicit empty []
    else:
        detail_fields = [f.strip() for f in DEFAULT_DETAIL_FIELDS.split(",") if f.strip()]

    id_field = args.id_field or (src_cfg.id_field if src_cfg and src_cfg.id_field else DEFAULT_ID_FIELD)

    model_name = args.model_name or (app_cfg.embedding.model if app_cfg else DEFAULT_MODEL)

    dimension = args.dimension
    if dimension is None:
        if app_cfg:
            dimension = app_cfg.embedding.dimension
        elif src_cfg is None:
            dimension = DEFAULT_DIM
        else:
            from semantic_search.config.models import resolve_dimension

            try:
                dimension = resolve_dimension(model_name, None)
            except Exception as exc:  # ModelPresetError
                LOGGER.critical("Cannot resolve dimension for model '%s': %s", model_name, exc)
                raise SystemExit(1) from exc

    # Build preprocessing pipeline (CLI flag > app config > built-in defaults)
    preprocessing_pipeline = None
    if not args.no_preprocessing:
        pp_cfg = app_cfg.preprocessing if app_cfg else PreprocessingConfig()
        preprocessing_pipeline = build_preprocessing_pipeline(pp_cfg)
        if preprocessing_pipeline is not None:
            LOGGER.info(
                "Preprocessing enabled: clean=%s  chunk=%s  chunk_size=%d  overlap=%d",
                pp_cfg.clean, pp_cfg.chunk, pp_cfg.chunk_size, pp_cfg.overlap,
            )

    store = build_json_spot_index(
        json_path=json_path,
        text_fields=text_fields,
        id_field=id_field,
        metadata_fields=metadata_fields,
        detail_fields=detail_fields,
        jq_filter=args.jq_filter,
        model_name=model_name,
        dimension=dimension,
        preprocessing_pipeline=preprocessing_pipeline,
    )
    store.save(args.output)
    LOGGER.info("Saved %d records to %r", len(store), args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
