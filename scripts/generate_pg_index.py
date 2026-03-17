"""Generate a Bedrock-embedded vector index from the semantic_search_test PostgreSQL database.

Extracts records from ``support_tickets`` and ``candidates`` tables, embeds
the concatenated text fields via AWS Bedrock Titan embed-text-v1, and saves
the resulting NumpyVectorStore for local server validation.

Usage::

    # Both tables, us-east-1, output to ./pg_bedrock_index
    uv run python scripts/generate_pg_index.py

    # Custom region / output directory
    uv run python scripts/generate_pg_index.py --region us-west-2 --output ./my_pg_index

    # Single table only
    uv run python scripts/generate_pg_index.py --table support_tickets
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
# Constants
# ---------------------------------------------------------------------------

CONN = "postgresql+psycopg2:///semantic_search_test"
DIM = 1536  # Bedrock Titan embed-text-v1 output dimension
BEDROCK_MODEL = "amazon.titan-embed-text-v1"
DEFAULT_OUTPUT = "./pg_bedrock_index"

# ---------------------------------------------------------------------------
# Table extraction configurations
# ---------------------------------------------------------------------------

TABLE_CONFIGS: Dict[str, Dict] = {
    "support_tickets": {
        "query": (
            "SELECT id, title, body, category, priority, status "
            "FROM support_tickets ORDER BY id"
        ),
        "text_fields": ["title", "body"],
        "id_field": "id",
        "metadata_fields": ["title", "priority", "status"],
        "detail_fields": ["body"],
        "id_prefix": "ticket",
    },
    "candidates": {
        "query": (
            "SELECT id, full_name, summary, skills, location, years_experience, availability "
            "FROM candidates ORDER BY id"
        ),
        "text_fields": ["full_name", "summary", "skills"],
        "id_field": "id",
        "metadata_fields": ["full_name", "location", "years_experience"],
        "detail_fields": ["summary", "skills"],
        "id_prefix": "candidate",
    },
}


def extract_inputs(table: str, config: Dict) -> List[EmbeddingInput]:
    """Extract records from a PostgreSQL table and convert to EmbeddingInputs.

    Args:
        table: Table name, stored as ``source_table`` in each record's metadata.
        config: Connector configuration dict containing query, text_fields,
            id_field, metadata_fields, detail_fields, and id_prefix keys.

    Returns:
        List of EmbeddingInput objects ready for the embedding pipeline.

    Raises:
        SystemExit: If the connector fails to connect or extract records.
    """
    from semantic_search.ingestion import DataSourceError, get_connector

    metadata_fields: List[str] = config.get("metadata_fields", [])
    detail_fields: List[str] = config.get("detail_fields", [])
    detail_field_set: Set[str] = set(detail_fields)
    # Pass combined list to the connector so all fields are extracted.
    all_metadata_fields = metadata_fields + [
        f for f in detail_fields if f not in metadata_fields
    ]

    LOGGER.info("Extracting from table: %s", table)
    try:
        connector = get_connector(
            "sql",
            {
                "connection_string": CONN,
                "query": config["query"],
                "text_fields": config["text_fields"],
                "id_field": config["id_field"],
                "metadata_fields": all_metadata_fields,
            },
        )
        records = list(connector.extract())
    except DataSourceError as exc:
        LOGGER.critical("Failed to extract from %s: %s", table, exc)
        raise SystemExit(1) from exc

    prefix = config["id_prefix"]
    inputs = [
        EmbeddingInput(
            record_id=f"{prefix}-{r.record_id}",
            text=r.text,
            metadata={
                **split_metadata(dict(r.metadata), detail_field_set),
                "source_table": table,
            },
        )
        for r in records
    ]
    LOGGER.info("  Extracted %d records from %s", len(inputs), table)
    return inputs


def build_pg_bedrock_index(
    tables: List[str],
    region: str,
    model: str = BEDROCK_MODEL,
) -> NumpyVectorStore:
    """Extract records from PostgreSQL tables and embed them via AWS Bedrock.

    Args:
        tables: List of table names to process (must be keys in TABLE_CONFIGS).
        region: AWS region string for the Bedrock runtime (e.g. ``"us-east-1"``).
        model: Bedrock model ID (default: Titan embed-text-v1).

    Returns:
        A populated NumpyVectorStore with real semantic embedding vectors.

    Raises:
        SystemExit: On provider initialisation failure, extraction error, or if
            no records are available to embed.
    """
    import semantic_search.embeddings.bedrock  # noqa: F401 — registers 'bedrock' factory
    from semantic_search.embeddings.factory import get_provider
    from semantic_search.pipeline.embedding_pipeline import EmbeddingPipeline

    LOGGER.info("Initialising Bedrock provider: region=%s  model=%s", region, model)
    try:
        provider = get_provider("bedrock", {"region": region, "model": model})
    except Exception as exc:  # noqa: BLE001
        LOGGER.critical("Failed to initialise Bedrock provider: %s", exc)
        raise SystemExit(1) from exc

    all_inputs: List[EmbeddingInput] = []
    for table in tables:
        all_inputs.extend(extract_inputs(table, TABLE_CONFIGS[table]))

    if not all_inputs:
        LOGGER.critical("No records extracted — nothing to embed.")
        raise SystemExit(1)

    store = NumpyVectorStore(dimension=DIM, metric="cosine")
    pipeline = EmbeddingPipeline(provider, store, batch_size=10)

    LOGGER.info("Embedding %d records via Bedrock ...", len(all_inputs))
    result = pipeline.run(all_inputs)
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
        description=(
            "Generate a Bedrock-embedded FAISS index from the "
            "semantic_search_test PostgreSQL database."
        )
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Local directory to write the index (default: {DEFAULT_OUTPUT!r})",
    )
    parser.add_argument(
        "--region",
        default=None,
        help="AWS region for Bedrock (default: us-east-1)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=f"Bedrock model ID (default: {BEDROCK_MODEL!r})",
    )
    parser.add_argument(
        "--table",
        choices=list(TABLE_CONFIGS.keys()),
        default=None,
        help="Process a single table only. Omit to process all tables.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to a source YAML config file (e.g. config/sources/support_tickets.yaml)",
    )
    parser.add_argument(
        "--app-config",
        default=None,
        help="Path to config directory containing app.yaml (e.g. ./config)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the PostgreSQL Bedrock index generator.

    Args:
        argv: Argument list forwarded to :func:`parse_args`.

    Returns:
        Exit code (0 on success, 1 on error).
    """
    args = parse_args(argv)

    # --- Optional YAML config loading --------------------------------------
    if args.app_config:
        from semantic_search.config.app import load_app_config

        app_cfg = load_app_config(Path(args.app_config))
        LOGGER.info("Loaded app config from: %s", args.app_config)
        model = args.model if args.model is not None else app_cfg.embedding.model
        region = args.region if args.region is not None else app_cfg.embedding.config.get("region", "us-east-1")
    else:
        model = args.model or BEDROCK_MODEL
        region = args.region or "us-east-1"

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
        # Override TABLE_CONFIGS with source YAML if the table matches
        table_name = src_cfg.name
        TABLE_CONFIGS[table_name] = {
            "query": src_cfg.connector.config.get("query", ""),
            "text_fields": src_cfg.text_fields,
            "id_field": src_cfg.id_field or "id",
            "metadata_fields": src_cfg.metadata_fields,
            "detail_fields": src_cfg.detail_fields,
            "id_prefix": src_cfg.id_prefix or table_name,
        }

    tables = [args.table] if args.table else list(TABLE_CONFIGS.keys())

    store = build_pg_bedrock_index(tables, region=region, model=model)
    store.save(args.output)
    LOGGER.info("Saved %d records to %r", len(store), args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
