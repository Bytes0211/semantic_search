"""
Command-line interface for running semantic search queries against a local vector store.

This module allows operators to issue ad-hoc search queries using the same runtime
logic that powers the REST API. It is particularly useful for validating embeddings,
vector store contents, and filter behaviour without deploying the full service stack.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union

from pydantic import ValidationError

# Import provider modules to ensure their factories register with the global registry.
from semantic_search.embeddings import (  # noqa: F401
    bedrock as _bedrock_provider,
)
from semantic_search.embeddings import (
    sagemaker as _sagemaker_provider,
)
from semantic_search.embeddings import (
    spot as _spot_provider,
)
from semantic_search.embeddings.factory import get_provider, list_registered_backends
from semantic_search.runtime.api import SearchRequest, SearchResponse, SearchRuntime
from semantic_search.vectorstores.faiss_store import NumpyVectorStore

FilterDict = Dict[str, Union[str, List[str]]]


def _load_provider_config(path: Optional[str]) -> Mapping[str, Any]:
    """Load the embedding provider configuration from a JSON file if supplied.

    Args:
        path: Optional filesystem path to a JSON document containing provider
            configuration.

    Returns:
        Mapping sourced from the JSON document, or an empty dict when `path` is
        ``None``.

    Raises:
        ValueError: If the configuration file cannot be read or parsed.
    """
    if not path:
        return {}

    config_path = Path(path)
    if not config_path.exists():
        raise ValueError(f"Provider config file {config_path!s} does not exist.")
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive branch
        raise ValueError(
            f"Failed to parse provider config at {config_path!s}: {exc}"
        ) from exc


def _parse_filters(raw_filters: Iterable[str]) -> FilterDict:
    """Parse CLI filter arguments of the form ``field=value1,value2``.

    Args:
        raw_filters: Iterable of raw filter expressions.

    Returns:
        Dictionary mapping field names to either a single string value or a list
        of values when multiple options are supplied for the same key.

    Raises:
        ValueError: If a filter expression is malformed.
    """
    parsed: Dict[str, List[str]] = {}
    for expression in raw_filters:
        if "=" not in expression:
            raise ValueError(
                f"Filter '{expression}' is invalid; expected KEY=VALUE syntax."
            )
        key, value = expression.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Filter '{expression}' has an empty key.")
        values = [item.strip() for item in value.split(",") if item.strip()]
        if not values:
            raise ValueError(
                f"Filter '{expression}' must include at least one non-empty value."
            )
        parsed.setdefault(key, []).extend(values)

    result: FilterDict = {}
    for key, values in parsed.items():
        unique_values = list(dict.fromkeys(values))
        if len(unique_values) == 1:
            result[key] = unique_values[0]
        else:
            result[key] = unique_values
    return result


def _build_runtime(args: argparse.Namespace) -> SearchRuntime:
    """Construct the search runtime using CLI arguments.

    Args:
        args: Parsed namespace from ``argparse``.

    Returns:
        Configured :class:`SearchRuntime` instance.

    Raises:
        ValueError: If runtime dependencies cannot be initialised.
    """
    available_backends = list_registered_backends()
    if args.backend not in available_backends:
        raise ValueError(
            f"Embedding backend '{args.backend}' is not registered. "
            f"Available backends: {', '.join(sorted(available_backends)) or 'none'}."
        )

    provider_config = _load_provider_config(args.provider_config)
    provider = get_provider(args.backend, provider_config)

    if not args.vector_store:
        raise ValueError(
            "A vector store directory must be supplied via --vector-store."
        )
    vector_store_path = Path(args.vector_store)
    try:
        store = NumpyVectorStore.load(str(vector_store_path))
    except (
        Exception
    ) as exc:  # pragma: no cover - file system errors are environment specific
        raise ValueError(
            f"Failed to load vector store from {vector_store_path!s}: {exc}"
        ) from exc

    return SearchRuntime(
        provider,
        store,
        default_top_k=args.top_k,
        max_top_k=args.max_top_k,
        candidate_multiplier=args.candidate_multiplier,
    )


def _render_response(
    response: SearchResponse,
    *,
    show_metadata: bool,
    show_vector: bool,
    show_detail: bool = False,
    exclude_fields: Optional[frozenset[str]] = None,
) -> None:
    """Pretty-print the search response for terminal use.

    Args:
        response: Search response returned by :class:`SearchRuntime`.
        show_metadata: Whether to print record metadata blocks.
        show_vector: Whether to print the query embedding vector.
        show_detail: Whether to print detail fields below metadata.
        exclude_fields: Metadata keys to omit from CLI output (e.g.
            backing fields used only as link targets in the UI).
    """
    print(f"Query          : {response.query}")
    print(f"Top-K requested: {response.top_k}")
    print(f"Latency        : {response.elapsed_ms:.2f} ms")
    if response.embedding_model:
        print(f"Embedding model: {response.embedding_model}")
    if show_vector:
        print("Query vector   :")
        print(
            "  [" + ", ".join(f"{value:.6f}" for value in response.query_vector) + "]"
        )

    print(f"Results        : {response.total_results}")
    if not response.results:
        print("  (no matches)")
        return

    for index, item in enumerate(response.results, start=1):
        print(f"{index:>2}. {item.record_id}  score={item.score:.6f}")
        if show_metadata and item.metadata:
            for key, value in item.metadata.items():
                if exclude_fields and key in exclude_fields:
                    continue
                print(f"      {key}: {value}")
        if show_detail and item.detail:
            print("      --- detail ---")
            for key, value in item.detail.items():
                print(f"      {key}: {value}")


def _build_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Run semantic search queries against a saved vector store.",
    )
    parser.add_argument(
        "query",
        help="Natural-language query to execute.",
    )
    parser.add_argument(
        "--vector-store",
        metavar="PATH",
        required=True,
        help="Directory containing vectors.npy and metadata.json produced by the embedding pipeline.",
    )
    parser.add_argument(
        "--backend",
        default="spot",
        help=(
            "Embedding backend to use (default: spot). "
            "Available backends are dynamically registered; run with --list-backends to view the set."
        ),
    )
    parser.add_argument(
        "--provider-config",
        metavar="FILE",
        help="Optional JSON file providing embedding provider configuration.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Maximum number of results to return (default: 10).",
    )
    parser.add_argument(
        "--max-top-k",
        type=int,
        default=200,
        help="Hard limit for results per query (default: 200).",
    )
    parser.add_argument(
        "--candidate-multiplier",
        type=int,
        default=3,
        help=(
            "Multiplier applied to top_k to determine the intermediate candidate pool "
            "before filters (default: 3)."
        ),
    )
    parser.add_argument(
        "--filter",
        dest="filters",
        action="append",
        default=[],
        metavar="KEY=VALUE[,VALUE...]",
        help=(
            "Filter expression applied to result metadata. "
            "Repeat for multiple fields. Example: --filter status=active --filter region=us-east-1,eu-west-1"
        ),
    )
    parser.add_argument(
        "--hide-metadata",
        action="store_true",
        help="Suppress printing of record metadata in the output.",
    )
    parser.add_argument(
        "--show-vector",
        action="store_true",
        help="Print the query embedding vector for debugging.",
    )
    parser.add_argument(
        "--show-detail",
        action="store_true",
        help="Print record detail fields (stored under _detail at index time) below metadata.",
    )
    parser.add_argument(
        "--exclude-field",
        dest="exclude_fields",
        action="append",
        default=[],
        metavar="FIELD",
        help=(
            "Metadata field to hide from CLI output (e.g. backing fields used "
            "only as link targets in the UI). Repeat for multiple fields."
        ),
    )
    parser.add_argument(
        "--list-backends",
        action="store_true",
        help="List registered embedding backends and exit.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Program entrypoint invoked by ``python -m semantic_search.runtime.cli``."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list_backends:
        backends = sorted(list_registered_backends().keys())
        if backends:
            print("Registered embedding backends:")
            for backend in backends:
                print(f"  - {backend}")
        else:  # pragma: no cover - defensive branch
            print("No embedding backends are currently registered.")
        return 0

    try:
        filters = _parse_filters(args.filters)
    except ValueError as exc:
        print(f"Error parsing filters: {exc}", file=sys.stderr)
        return 1

    try:
        runtime = _build_runtime(args)
    except ValueError as exc:
        print(f"Runtime initialisation failed: {exc}", file=sys.stderr)
        return 2

    try:
        request = SearchRequest(
            query=args.query,
            top_k=args.top_k,
            filters=filters or None,
        )
    except ValidationError as exc:
        print(f"Search request validation failed: {exc}", file=sys.stderr)
        return 3

    try:
        response = runtime.search(request)
    except Exception as exc:  # pragma: no cover - runtime errors depend on environment
        print(f"Search execution failed: {exc}", file=sys.stderr)
        return 4

    _render_response(
        response,
        show_metadata=not args.hide_metadata,
        show_vector=args.show_vector,
        show_detail=args.show_detail,
        exclude_fields=frozenset(args.exclude_fields) if args.exclude_fields else None,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
