"""Generate a Spot-embedded vector index from MongoDB collections.

Extracts records from the ``semantic_search_test`` database (``products`` and
``articles`` collections), embeds the concatenated text fields using the local
Spot provider, and saves the resulting NumpyVectorStore for local server
validation.

Prerequisites::

    uv run python scripts/seed_mongodb.py   # populate the database first

Usage::

    # Both collections, default output to ./mongo_spot_index
    uv run python scripts/generate_mongo_index.py

    # Single collection
    uv run python scripts/generate_mongo_index.py --collection products

    # Custom URI / output
    uv run python scripts/generate_mongo_index.py --uri mongodb://localhost:27017 --output ./my_mongo_index
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

DEFAULT_URI = "mongodb://localhost:27017"
DATABASE = "semantic_search_test"
DEFAULT_OUTPUT = "./mongo_spot_index"
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DIM = 384

# ---------------------------------------------------------------------------
# Collection extraction configurations
# ---------------------------------------------------------------------------

COLLECTION_CONFIGS: Dict[str, Dict[str, Any]] = {
    "products": {
        "text_fields": ["name", "description"],
        "id_field": "id",
        "metadata_fields": ["category", "brand"],
        "detail_fields": ["description", "price"],
        "id_prefix": "product",
    },
    "articles": {
        "text_fields": ["title", "body"],
        "id_field": "article_id",
        "metadata_fields": ["title", "category", "author"],
        "detail_fields": ["body"],
        "id_prefix": "article",
    },
}


def extract_inputs(
    uri: str,
    collection: str,
    config: Dict[str, Any],
) -> List[EmbeddingInput]:
    """Extract records from a MongoDB collection and convert to EmbeddingInputs.

    Args:
        uri: MongoDB connection URI.
        collection: Collection name within the ``semantic_search_test`` database.
        config: Collection configuration dict containing text_fields, id_field,
            metadata_fields, detail_fields, and id_prefix keys.

    Returns:
        List of EmbeddingInput objects ready for the embedding pipeline.

    Raises:
        SystemExit: If the connector fails to connect or extract records.
    """
    from semantic_search.ingestion import DataSourceError, get_connector

    metadata_fields: List[str] = config.get("metadata_fields", [])
    detail_fields: List[str] = config.get("detail_fields", [])
    detail_field_set: Set[str] = set(detail_fields)
    all_metadata_fields = metadata_fields + [
        f for f in detail_fields if f not in metadata_fields
    ]

    LOGGER.info("Extracting from collection: %s.%s", DATABASE, collection)
    try:
        connector = get_connector(
            "mongodb",
            {
                "uri": uri,
                "database": DATABASE,
                "collection": collection,
                "text_fields": config["text_fields"],
                "id_field": config["id_field"],
                "metadata_fields": all_metadata_fields,
            },
        )
        records = list(connector.extract())
    except DataSourceError as exc:
        LOGGER.critical("Failed to extract from %s: %s", collection, exc)
        raise SystemExit(1) from exc

    prefix = config["id_prefix"]
    inputs = [
        EmbeddingInput(
            record_id=f"{prefix}-{r.record_id}",
            text=r.text,
            metadata={
                **split_metadata(dict(r.metadata), detail_field_set),
                "source_collection": collection,
            },
        )
        for r in records
    ]
    LOGGER.info("  Extracted %d records from %s", len(inputs), collection)
    return inputs


def build_mongo_spot_index(
    uri: str,
    collections: List[str],
    model_name: str = DEFAULT_MODEL,
    dimension: int = DEFAULT_DIM,
) -> NumpyVectorStore:
    """Extract records from MongoDB collections and embed them via Spot.

    Args:
        uri: MongoDB connection URI.
        collections: List of collection names to process (must be keys in
            COLLECTION_CONFIGS).
        model_name: Logical model identifier reported in result metadata.
        dimension: Embedding vector dimensionality (must match the model).

    Returns:
        A populated NumpyVectorStore with embedded vectors.

    Raises:
        SystemExit: On provider initialisation failure, extraction error, or if
            no records are available to embed.
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

    all_inputs: List[EmbeddingInput] = []
    for coll in collections:
        all_inputs.extend(extract_inputs(uri, coll, COLLECTION_CONFIGS[coll]))

    if not all_inputs:
        LOGGER.critical("No records extracted — nothing to embed.")
        raise SystemExit(1)

    store = NumpyVectorStore(dimension=dimension, metric="cosine")
    pipeline = EmbeddingPipeline(provider, store, batch_size=50)

    LOGGER.info("Embedding %d records via Spot ...", len(all_inputs))
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
            "Generate a Spot-embedded FAISS index from MongoDB collections "
            "in the semantic_search_test database."
        )
    )
    parser.add_argument(
        "--uri",
        default=DEFAULT_URI,
        help=f"MongoDB connection URI (default: {DEFAULT_URI!r})",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Local directory to write the index (default: {DEFAULT_OUTPUT!r})",
    )
    parser.add_argument(
        "--collection",
        choices=list(COLLECTION_CONFIGS.keys()),
        default=None,
        help="Process a single collection only. Omit to process all collections.",
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
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the MongoDB Spot index generator.

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
        model_name = args.model_name if args.model_name is not None else app_cfg.embedding.model
        dimension = args.dimension if args.dimension is not None else app_cfg.embedding.dimension
    else:
        model_name = args.model_name or DEFAULT_MODEL
        dimension = args.dimension if args.dimension is not None else DEFAULT_DIM

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
        coll_name = src_cfg.connector.config.get("collection", src_cfg.name)
        COLLECTION_CONFIGS[coll_name] = {
            "text_fields": src_cfg.text_fields,
            "id_field": src_cfg.id_field or "id",
            "metadata_fields": src_cfg.metadata_fields,
            "detail_fields": src_cfg.detail_fields,
            "id_prefix": src_cfg.id_prefix or coll_name,
        }

    collections = (
        [args.collection] if args.collection else list(COLLECTION_CONFIGS.keys())
    )

    store = build_mongo_spot_index(
        uri=args.uri,
        collections=collections,
        model_name=model_name,
        dimension=dimension,
    )
    store.save(args.output)
    LOGGER.info("Saved %d records to %r", len(store._vectors), args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
