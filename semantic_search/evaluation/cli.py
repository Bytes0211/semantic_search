"""Command-line interface for the relevance evaluation suite.

Typical usage (text report)::

    semantic-search-eval queries.json --store /path/to/store.npy

JSON output suitable for CI gates::

    semantic-search-eval queries.json --store /path/to/store.npy --format json

Override the pass threshold::

    semantic-search-eval queries.json --store /path/to/store.npy --threshold 0.85

Exit codes
----------
* ``0`` — evaluation completed and hit rate meets the threshold.
* ``1`` — evaluation completed but hit rate is **below** the threshold.
* ``2`` — fatal error (missing file, bad JSON, runtime initialisation failure).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

from semantic_search.evaluation.evaluator import RelevanceEvaluator
from semantic_search.evaluation.schema import EvalQuery, EvalReport


def _load_queries(path: str) -> List[EvalQuery]:
    """Load evaluation queries from a JSON file.

    The file must contain a JSON array of objects with the following fields:

    * ``query_id`` (str) – unique identifier.
    * ``query_text`` (str) – natural-language query.
    * ``relevant_ids`` (list[str]) – ground-truth record IDs.
    * ``top_k`` (int, optional) – result count; defaults to ``10``.

    Args:
        path: Filesystem path to the JSON query file.

    Returns:
        List of :class:`~schema.EvalQuery` objects.

    Raises:
        SystemExit: On file-not-found, JSON parse error, or schema violation.
    """
    if not os.path.isfile(path):
        print(f"ERROR: query file not found: {path}", file=sys.stderr)
        sys.exit(2)

    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    if not isinstance(data, list):
        print(
            f"ERROR: {path} must contain a JSON array of query objects.",
            file=sys.stderr,
        )
        sys.exit(2)

    queries: List[EvalQuery] = []
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            print(
                f"ERROR: item {idx} in {path} is not an object.", file=sys.stderr
            )
            sys.exit(2)
        try:
            queries.append(
                EvalQuery(
                    query_id=str(item["query_id"]),
                    query_text=str(item["query_text"]),
                    relevant_ids=[str(r) for r in item["relevant_ids"]],
                    top_k=int(item.get("top_k", 10)),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            print(
                f"ERROR: item {idx} in {path} is malformed: {exc}", file=sys.stderr
            )
            sys.exit(2)

    return queries


def _build_runtime(store_path: str):  # type: ignore[return]
    """Construct a :class:`~semantic_search.runtime.api.SearchRuntime`.

    Embedding backend is selected via the ``EMBEDDING_BACKEND`` environment
    variable (``hash`` by default for local testing).

    Args:
        store_path: Path to the serialised ``NumpyVectorStore`` file.

    Returns:
        Configured :class:`~semantic_search.runtime.api.SearchRuntime`.

    Raises:
        SystemExit: On import errors or initialisation failures.
    """
    try:
        from semantic_search.runtime.api import SearchRuntime
        from semantic_search.vectorstores.faiss_store import NumpyVectorStore
    except ImportError as exc:
        print(f"ERROR: missing dependencies — {exc}", file=sys.stderr)
        sys.exit(2)

    backend = os.environ.get("EMBEDDING_BACKEND", "hash").lower()

    try:
        if backend == "bedrock":
            from semantic_search.embeddings.bedrock import BedrockEmbeddingProvider

            provider = BedrockEmbeddingProvider()
        elif backend == "sagemaker":
            from semantic_search.embeddings.sagemaker import SageMakerEmbeddingProvider

            endpoint = os.environ.get("SAGEMAKER_ENDPOINT_NAME", "")
            if not endpoint:
                print(
                    "ERROR: SAGEMAKER_ENDPOINT_NAME must be set when EMBEDDING_BACKEND=sagemaker.",
                    file=sys.stderr,
                )
                sys.exit(2)
            provider = SageMakerEmbeddingProvider(endpoint_name=endpoint)
        else:
            # Default: hash-based deterministic provider for local / CI use.
            from semantic_search.embeddings.hash_provider import HashEmbeddingProvider

            provider = HashEmbeddingProvider()
    except ImportError as exc:
        print(
            f"ERROR: could not load embedding provider for backend={backend!r}: {exc}",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        store = NumpyVectorStore.load(store_path)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to load vector store from {store_path!r}: {exc}", file=sys.stderr)
        sys.exit(2)

    return SearchRuntime(embedding_provider=provider, vector_store=store)


def _print_text(report: EvalReport, threshold: float) -> None:
    """Render the evaluation report as human-readable text.

    Args:
        report: Completed evaluation report.
        threshold: Pass/fail threshold used for the status indicator.
    """
    status = "PASS" if report.passes_threshold(threshold) else "FAIL"
    print(f"\n{'=' * 60}")
    print(f"  Relevance Evaluation Report  [{status}]")
    print(f"{'=' * 60}")
    print(f"  Queries evaluated : {report.num_queries}")
    print(f"  Hit Rate (Recall@K): {report.hit_rate:.1%}  (target >= {threshold:.0%})")
    print(f"  Mean Reciprocal Rank (MRR) : {report.mean_reciprocal_rank:.4f}")
    print(f"  Mean Precision@K           : {report.mean_precision_at_k:.4f}")
    print(f"  Mean nDCG@K                : {report.mean_ndcg_at_k:.4f}")
    print(f"  Mean Latency               : {report.mean_latency_ms:.1f} ms")
    print(f"{'=' * 60}\n")

    if report.results:
        print("  Per-query breakdown:")
        print(f"  {'ID':<20} {'Hit':<5} {'RR':>6} {'P@K':>6} {'nDCG':>6} {'ms':>8}")
        print(f"  {'-' * 58}")
        for r in report.results:
            hit_str = "Y" if r.hit else "N"
            print(
                f"  {r.query_id:<20} {hit_str:<5} {r.reciprocal_rank:>6.3f} "
                f"{r.precision_at_k:>6.3f} {r.ndcg_at_k:>6.3f} {r.elapsed_ms:>8.1f}"
            )
        print()


def _report_to_dict(report: EvalReport, threshold: float) -> Dict[str, Any]:
    """Serialise a report to a plain dictionary for JSON output.

    Args:
        report: Completed evaluation report.
        threshold: Pass/fail threshold.

    Returns:
        JSON-serialisable dictionary.
    """
    return {
        "passed": report.passes_threshold(threshold),
        "threshold": threshold,
        "num_queries": report.num_queries,
        "hit_rate": report.hit_rate,
        "mean_reciprocal_rank": report.mean_reciprocal_rank,
        "mean_precision_at_k": report.mean_precision_at_k,
        "mean_ndcg_at_k": report.mean_ndcg_at_k,
        "mean_latency_ms": report.mean_latency_ms,
        "results": [
            {
                "query_id": r.query_id,
                "query_text": r.query_text,
                "top_k": r.top_k,
                "hit": r.hit,
                "reciprocal_rank": r.reciprocal_rank,
                "precision_at_k": r.precision_at_k,
                "ndcg_at_k": r.ndcg_at_k,
                "elapsed_ms": r.elapsed_ms,
                "returned_ids": r.returned_ids,
                "relevant_ids": r.relevant_ids,
            }
            for r in report.results
        ],
    }


def _build_parser() -> argparse.ArgumentParser:
    """Create and return the argument parser.

    Returns:
        Configured :class:`argparse.ArgumentParser`.
    """
    parser = argparse.ArgumentParser(
        prog="semantic-search-eval",
        description=(
            "Evaluate semantic search relevance against a labelled query set. "
            "Exits with code 0 when the hit rate meets the threshold, 1 otherwise."
        ),
    )
    parser.add_argument(
        "query_file",
        metavar="QUERY_FILE",
        help="Path to the JSON file containing labeled evaluation queries.",
    )
    parser.add_argument(
        "--store",
        metavar="STORE_PATH",
        default=os.environ.get("VECTOR_STORE_PATH", ""),
        help=(
            "Path to the serialised NumpyVectorStore.  "
            "Overrides the VECTOR_STORE_PATH environment variable."
        ),
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.90,
        metavar="FLOAT",
        help="Minimum hit rate required to pass (default: 0.90).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        dest="output_format",
        help="Output format: 'text' (default) or 'json'.",
    )
    return parser


def main(argv: List[str] | None = None) -> None:
    """Entry point for the ``semantic-search-eval`` CLI.

    Args:
        argv: Argument list (defaults to ``sys.argv[1:]`` when ``None``).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.store:
        print(
            "ERROR: --store / VECTOR_STORE_PATH is required.",
            file=sys.stderr,
        )
        sys.exit(2)

    if not 0.0 <= args.threshold <= 1.0:
        print(
            f"ERROR: --threshold must be in [0.0, 1.0]; got {args.threshold}",
            file=sys.stderr,
        )
        sys.exit(2)

    queries = _load_queries(args.query_file)
    runtime = _build_runtime(args.store)
    evaluator = RelevanceEvaluator(runtime, hit_rate_threshold=args.threshold)
    report = evaluator.run(queries)

    if args.output_format == "json":
        print(json.dumps(_report_to_dict(report, args.threshold), indent=2))
    else:
        _print_text(report, args.threshold)

    sys.exit(0 if report.passes_threshold(args.threshold) else 1)


if __name__ == "__main__":
    main()
