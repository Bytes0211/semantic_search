"""Runtime module exports for the semantic search service.

This package bundles the core runtime building blocks:

* :class:`SearchRuntime` — Orchestrates query embedding and similarity search.
* :func:`create_app` — FastAPI application factory exposing `/v1/search`.
* :func:`cli_main` — Command-line entry point mirroring the API behaviour.
* :class:`SearchRequest`, :class:`SearchResponse`, and :class:`SearchResultItem`
  — Typed payload models shared between the API and CLI layers.

Importing from ``semantic_search.runtime`` keeps downstream code decoupled from
the internal module layout:

    from semantic_search.runtime import SearchRuntime, create_app

These re-exports are safe for both ECS/Fargate and Lambda deployment profiles,
as documented in Phase 4 of the delivery plan.
"""

from .api import (
    SearchRequest,
    SearchResponse,
    SearchResultItem,
    SearchRuntime,
    create_app,
)
from .cli import main as cli_main
from .ui import mount_ui

__all__ = [
    "SearchRequest",
    "SearchResponse",
    "SearchResultItem",
    "SearchRuntime",
    "create_app",
    "cli_main",
    "mount_ui",
]
