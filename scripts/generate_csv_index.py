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
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
DEFAULT_OUTPUT = "./csv_spot_index"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIM = 384


def extract_inputs(
    csv_path: str,
    text_fields: List[str],
    id_field: Optional[str],
    metadata_fields: List[str],
) -> List[EmbeddingInput]:
    """Extract records from CSV files and convert to EmbeddingInputs.

    Args:
        csv_path: Path or glob pattern to one or more CSV files.
        text_fields: Ordered list of column names to concatenate as the
            embeddable text payload.
        id_field: Column used as the record identifier.  When ``None`` the
            connector generates a fallback ID from filename and row index.
        metadata_fields: Columns stored as filterable metadata.

    Returns:
        List of EmbeddingInput objects ready for the embedding pipeline.

    Raises:
        SystemExit: If the connector cannot read the CSV or finds no records.
    """
    from semantic_search.ingestion import DataSourceError, get_connector

    LOGGER.info("Extracting from CSV: %s", csv_path)
    config: dict = {
        "path": csv_path,
        "text_fields": text_fields,
        "metadata_fields": metadata_fields,
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
            metadata=r.metadata,
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
    model_name: str = DEFAULT_MODEL,
    dimension: int = DEFAULT_DIM,
) -> NumpyVectorStore:
    """Extract CSV records and embed them using the Spot provider.

    Args:
        csv_path: Path or glob pattern to one or more CSV files.
        text_fields: Columns concatenated to produce embeddable text.
        id_field: Column used as record identifier (``None`` for auto-ID).
        metadata_fields: Columns stored as filterable metadata.
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

    inputs = extract_inputs(csv_path, text_fields, id_field, metadata_fields)
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
        default=DEFAULT_CSV,
        help=f"Path or glob to CSV file(s) (default: {DEFAULT_CSV!r})",
    )
    parser.add_argument(
        "--text-fields",
        default=DEFAULT_TEXT_FIELDS,
        help=f"Comma-separated text columns (default: {DEFAULT_TEXT_FIELDS!r})",
    )
    parser.add_argument(
        "--id-field",
        default=DEFAULT_ID_FIELD,
        help=f"Column used as record ID (default: {DEFAULT_ID_FIELD!r})",
    )
    parser.add_argument(
        "--metadata-fields",
        default=DEFAULT_METADATA_FIELDS,
        help=f"Comma-separated metadata columns (default: {DEFAULT_METADATA_FIELDS!r})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output directory for the index (default: {DEFAULT_OUTPUT!r})",
    )
    parser.add_argument(
        "--model-name",
        default=DEFAULT_MODEL,
        help=f"Spot model identifier reported in metadata (default: {DEFAULT_MODEL!r})",
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=DEFAULT_DIM,
        help=f"Embedding vector dimensionality (default: {DEFAULT_DIM})",
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

    text_fields = [f.strip() for f in args.text_fields.split(",") if f.strip()]
    metadata_fields = [f.strip() for f in args.metadata_fields.split(",") if f.strip()]
    id_field = args.id_field or None

    store = build_csv_spot_index(
        csv_path=args.csv,
        text_fields=text_fields,
        id_field=id_field,
        metadata_fields=metadata_fields,
        model_name=args.model_name,
        dimension=args.dimension,
    )
    store.save(args.output)
    LOGGER.info("Saved %d records to %r", len(store._vectors), args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
