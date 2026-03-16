"""Generate a Spot-embedded vector index from one or more CSV files.

Extracts rows from the configured CSV path (supports glob patterns for
multiple files), embeds the concatenated text fields using the local Spot
provider (SentenceTransformers-compatible, no AWS required), and saves the
resulting NumpyVectorStore for local server validation.

The Spot provider in this codebase is a deterministic hash-based stub.  In
production it would call a containerised SentenceTransformers service on spot
capacity.  Index scores will not reflect true semantic similarity until the
production endpoint is wired in.

Usage::

    # Default: data/sample.csv, text=title+content, id=id, meta=category
    uv run python scripts/generate_csv_index.py

    # Custom CSV path and field mapping
    uv run python scripts/generate_csv_index.py \\
        --csv ./data/my_data.csv \\
        --text-fields title,body \\
        --id-field record_id \\
        --metadata-fields category,status \\
        --output ./my_csv_index

    # Glob pattern for multiple files
    uv run python scripts/generate_csv_index.py --csv './data/*.csv'

Detail fields and text fields may overlap intentionally.  A column such as
``content`` is a good embedding source (captured via ``--text-fields``) *and*
a useful drill-down field (captured via ``--detail-fields``).  When a field
appears in both, it is embedded into the vector **and** stored under ``_detail``
in the metadata — it will not appear as a visible tag on the search result
card unless the user expands the drill-down panel.  This keeps cards concise
while still surfacing the full text on demand.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from semantic_search.config.metadata import split_metadata
from semantic_search.embeddings.base import EmbeddingInput
from semantic_search.vectorstores.faiss_store import NumpyVectorStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults (match data/sample.csv column names)
# ---------------------------------------------------------------------------

DEFAULT_CSV = "./data/sample.csv"
DEFAULT_TEXT_FIELDS = "title,content"
DEFAULT_ID_FIELD = "id"
DEFAULT_METADATA_FIELDS = "category,author"
DEFAULT_DETAIL_FIELDS = "content"
DEFAULT_OUTPUT = "./csv_spot_index"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIM = 384


def extract_inputs(
    csv_path: str,
    text_fields: List[str],
    id_field: Optional[str],
    metadata_fields: List[str],
    detail_fields: Optional[List[str]] = None,
) -> List[EmbeddingInput]:
    """Extract records from CSV files and convert to EmbeddingInputs.

    Args:
        csv_path: Path or glob pattern to one or more CSV files.
        text_fields: Ordered list of column names to concatenate as the
            embeddable text payload.
        id_field: Column used as the record identifier.  When ``None`` the
            connector generates a fallback ID from filename and row index.
        metadata_fields: Columns stored as filterable metadata.
        detail_fields: Optional columns stored under ``_detail`` in metadata
            for drill-down display.

    Returns:
        List of EmbeddingInput objects ready for the embedding pipeline.

    Raises:
        SystemExit: If the connector cannot read the CSV or finds no records.
    """
    from semantic_search.ingestion import DataSourceError, get_connector

    detail_fields = detail_fields or []
    detail_field_set: Set[str] = set(detail_fields)
    # Pass combined list to the connector so all fields are extracted.
    all_metadata_fields = metadata_fields + [
        f for f in detail_fields if f not in metadata_fields
    ]

    LOGGER.info("Extracting from CSV: %s", csv_path)
    config: dict = {
        "path": csv_path,
        "text_fields": text_fields,
        "metadata_fields": all_metadata_fields,
    }
    if id_field:
        config["id_field"] = id_field

    try:
        connector = get_connector("csv", config)
        records = list(connector.extract())
    except DataSourceError as exc:
        LOGGER.critical("Failed to extract from CSV: %s", exc)
        raise SystemExit(1) from exc

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


def build_csv_spot_index(
    csv_path: str,
    text_fields: List[str],
    id_field: Optional[str],
    metadata_fields: List[str],
    detail_fields: Optional[List[str]] = None,
    model_name: str = DEFAULT_MODEL,
    dimension: int = DEFAULT_DIM,
) -> NumpyVectorStore:
    """Extract CSV records and embed them using the Spot provider.

    Args:
        csv_path: Path or glob pattern to one or more CSV files.
        text_fields: Columns concatenated to produce embeddable text.
        id_field: Column used as record identifier (``None`` for auto-ID).
        metadata_fields: Columns stored as filterable metadata.
        detail_fields: Optional columns stored under ``_detail`` in metadata
            for drill-down display.
        model_name: Logical model identifier reported in result metadata.
        dimension: Embedding vector dimensionality (must match the model).

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
        csv_path, text_fields, id_field, metadata_fields, detail_fields
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
        description="Generate a Spot-embedded FAISS index from CSV file(s)."
    )
    parser.add_argument(
        "--csv",
        default=None,
        help=f"Path or glob to CSV file(s) (default: {DEFAULT_CSV!r})",
    )
    parser.add_argument(
        "--text-fields",
        default=None,
        help=f"Comma-separated text columns (default: {DEFAULT_TEXT_FIELDS!r})",
    )
    parser.add_argument(
        "--id-field",
        default=None,
        help=f"Column used as record ID (default: {DEFAULT_ID_FIELD!r})",
    )
    parser.add_argument(
        "--metadata-fields",
        default=None,
        help=f"Comma-separated metadata columns (default: {DEFAULT_METADATA_FIELDS!r})",
    )
    parser.add_argument(
        "--detail-fields",
        default=None,
        help=(
            f"Comma-separated columns stored under _detail for drill-down display "
            f"(default: {DEFAULT_DETAIL_FIELDS!r}). "
            "May overlap with --text-fields: overlapping columns are embedded into "
            "the vector AND stored in _detail, so they won't appear as visible "
            "metadata tags unless the user expands the drill-down panel."
        ),
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
        help="Path to a source YAML config file (e.g. config/sources/sample_csv.yaml)",
    )
    parser.add_argument(
        "--app-config",
        default=None,
        help="Path to config directory containing app.yaml (e.g. ./config)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the CSV Spot index generator.

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
    csv_path = args.csv or (
        src_cfg.connector.config["path"]
        if src_cfg and src_cfg.connector.config.get("path")
        else DEFAULT_CSV
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

    detail_fields_raw = args.detail_fields or (
        ",".join(src_cfg.detail_fields) if src_cfg and src_cfg.detail_fields else DEFAULT_DETAIL_FIELDS
    )
    detail_fields = [f.strip() for f in detail_fields_raw.split(",") if f.strip()]

    id_field = (
        args.id_field
        or (src_cfg.id_field if src_cfg and src_cfg.id_field else DEFAULT_ID_FIELD)
    ) or None

    model_name = args.model_name or (app_cfg.embedding.model if app_cfg else DEFAULT_MODEL)

    dimension = args.dimension
    if dimension is None:
        if app_cfg:
            dimension = app_cfg.embedding.dimension
        elif src_cfg is None:
            dimension = DEFAULT_DIM
        else:
            from semantic_search.config.models import resolve_dimension

            dimension = resolve_dimension(model_name, None)

    store = build_csv_spot_index(
        csv_path=csv_path,
        text_fields=text_fields,
        id_field=id_field,
        metadata_fields=metadata_fields,
        detail_fields=detail_fields,
        model_name=model_name,
        dimension=dimension,
    )
    store.save(args.output)
    LOGGER.info("Saved %d records to %r", len(store._vectors), args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
