"""Seed a local MongoDB instance with sample data for semantic search testing.

Loads ``data/sample_products.json`` into the ``semantic_search_test`` database
under two collections:

- ``products``  — the full 20-record product catalogue
- ``articles``  — a small set of knowledge-base articles (inline)

Usage::

    uv run python scripts/seed_mongodb.py

    # Custom URI
    uv run python scripts/seed_mongodb.py --uri mongodb://localhost:27017
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
LOGGER = logging.getLogger(__name__)

DEFAULT_URI = "mongodb://localhost:27017"
DATABASE = "semantic_search_test"
PRODUCTS_JSON = Path(__file__).resolve().parent.parent / "data" / "sample_products.json"

# Inline articles — small enough to embed directly rather than a separate file.
ARTICLES: List[Dict[str, Any]] = [
    {
        "article_id": "kb-001",
        "title": "Getting Started with Semantic Search",
        "body": "Semantic search uses vector embeddings to match queries by meaning rather than keywords. Upload your data, generate embeddings, and start querying in minutes.",
        "category": "guide",
        "author": "engineering",
    },
    {
        "article_id": "kb-002",
        "title": "Choosing an Embedding Provider",
        "body": "AWS Bedrock offers managed Titan and Claude models with no infrastructure to maintain. Spot-hosted open-source models like MiniLM are cost-effective for high-volume workloads. SageMaker provides full control for custom fine-tuned models.",
        "category": "guide",
        "author": "engineering",
    },
    {
        "article_id": "kb-003",
        "title": "Troubleshooting Slow Search Queries",
        "body": "Check the vector store size — queries over millions of records may benefit from index partitioning. Verify that the embedding dimension matches between the provider and the stored vectors. Enable CloudWatch latency alarms to catch regressions early.",
        "category": "troubleshooting",
        "author": "devops",
    },
    {
        "article_id": "kb-004",
        "title": "Data Ingestion Best Practices",
        "body": "Use the batch ingestion mode for initial loads and schedule periodic re-indexes. Enable streaming mode only for near-real-time requirements. Validate connector configs in dev before deploying to production.",
        "category": "guide",
        "author": "engineering",
    },
    {
        "article_id": "kb-005",
        "title": "Understanding Cosine Similarity Scores",
        "body": "Cosine distance ranges from 0 (identical direction) to 2 (opposite). Lower scores indicate stronger semantic matches. Scores above 0.5 typically indicate weak relevance for normalised embeddings.",
        "category": "reference",
        "author": "engineering",
    },
    {
        "article_id": "kb-006",
        "title": "Configuring Metadata Filters",
        "body": "Metadata filters narrow search results without re-embedding. Store filterable fields like category, status, or date in the metadata dict at index time. Filters are applied after the vector search candidate pool is retrieved.",
        "category": "guide",
        "author": "engineering",
    },
    {
        "article_id": "kb-007",
        "title": "Deploying to AWS Fargate",
        "body": "The search service runs as a containerised FastAPI application on ECS Fargate. Set VECTOR_STORE_PATH to the S3 prefix containing the index. Health probes at /healthz and /readyz verify container and index readiness.",
        "category": "deployment",
        "author": "devops",
    },
    {
        "article_id": "kb-008",
        "title": "Security and Access Control",
        "body": "All data stays within the client AWS account. IAM roles follow least-privilege principles. Secrets are stored in AWS Secrets Manager with automatic rotation. API access is restricted via IAM-authenticated API Gateway or ALB with mTLS.",
        "category": "security",
        "author": "security",
    },
    {
        "article_id": "kb-009",
        "title": "Cost Optimisation Strategies",
        "body": "Use spot capacity for embedding generation jobs. Right-size Fargate tasks via CPU and memory Terraform variables. Enable S3 lifecycle rules to move older embeddings to Infrequent Access. Schedule provisioned concurrency only during business hours.",
        "category": "guide",
        "author": "finance",
    },
    {
        "article_id": "kb-010",
        "title": "Running the Relevance Evaluation Suite",
        "body": "The semantic-search-eval CLI runs ground-truth queries against a live index and reports hit rate, MRR, precision at K, and nDCG at K. Exit code 1 indicates the hit rate fell below the configured threshold.",
        "category": "testing",
        "author": "engineering",
    },
]


def seed(uri: str) -> None:
    """Connect to MongoDB and insert sample data.

    Args:
        uri: MongoDB connection URI.

    Raises:
        SystemExit: On connection or insertion failure.
    """
    try:
        import pymongo
    except ImportError:
        LOGGER.critical("pymongo is required. Install with: pip install pymongo")
        raise SystemExit(1)

    try:
        client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except Exception as exc:
        LOGGER.critical("Failed to connect to MongoDB at %s: %s", uri, exc)
        raise SystemExit(1) from exc

    db = client[DATABASE]

    # --- products collection ---
    products_data = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))
    db.products.drop()
    db.products.insert_many(products_data)
    LOGGER.info("Inserted %d documents into %s.products", len(products_data), DATABASE)

    # --- articles collection ---
    db.articles.drop()
    db.articles.insert_many(ARTICLES)
    LOGGER.info("Inserted %d documents into %s.articles", len(ARTICLES), DATABASE)

    client.close()
    LOGGER.info("MongoDB seed complete.")


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the MongoDB seed script.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).

    Returns:
        Exit code (0 on success, 1 on error).
    """
    parser = argparse.ArgumentParser(
        description="Seed a local MongoDB with sample data for semantic search testing."
    )
    parser.add_argument(
        "--uri",
        default=DEFAULT_URI,
        help=f"MongoDB connection URI (default: {DEFAULT_URI!r})",
    )
    args = parser.parse_args(argv)
    seed(args.uri)
    return 0


if __name__ == "__main__":
    sys.exit(main())
