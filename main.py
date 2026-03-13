"""Application entry point for the semantic search REST service.

Launches a :mod:`uvicorn` server hosting the FastAPI application defined in
:mod:`semantic_search.runtime.api`.  Configuration is supplied entirely through
environment variables so the same image works across dev, staging, and
production without code changes.

Environment variables
---------------------
EMBEDDING_BACKEND
    Embedding provider to use (``"spot"``, ``"bedrock"``, ``"sagemaker"``).  Required
    when ``VECTOR_STORE_PATH`` is supplied.  Defaults to ``"spot"``.
PROVIDER_CONFIG_JSON
    Optional JSON string passed verbatim to the provider factory as its
    configuration mapping (e.g. ``'{"dimension": 768}'``).
VECTOR_STORE_PATH
    Filesystem path to a saved :class:`~semantic_search.vectorstores.faiss_store.NumpyVectorStore`
    directory (``vectors.npy`` + ``metadata.json``).  When absent the server
    starts without a runtime; ``/readyz`` returns 503 until a runtime is
    injected via ``app.state.runtime``.
ENABLE_UI
    Set to ``"true"`` (case-insensitive) to mount the lightweight validation
    UI at ``/ui``.  Disabled by default.
HOST
    Bind address for uvicorn.  Defaults to ``"0.0.0.0"``.
PORT
    Port for uvicorn.  Defaults to ``8000``.
LOG_LEVEL
    Uvicorn log level (``"debug"``, ``"info"``, ``"warning"``, ``"error"``,
    ``"critical"``).  Defaults to ``"info"``.

Examples
--------
Local demo (no real vector store needed)::

    uv run python main.py
    # -> GET /healthz returns {"status": "ok"}
    # -> GET /readyz  returns 503 (no runtime configured)

Local validation with a saved index and the built-in UI::

    VECTOR_STORE_PATH=./my_index ENABLE_UI=true uv run python main.py
    # -> open http://localhost:8000/ui
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Mapping

LOGGER = logging.getLogger(__name__)


def _build_runtime(
    backend: str,
    provider_config: Mapping[str, Any],
    vector_store_path: str,
) -> Any:
    """Construct a SearchRuntime from environment-supplied configuration.

    Args:
        backend: Embedding provider identifier (e.g. ``"spot"``).
        provider_config: Provider-specific configuration mapping.
        vector_store_path: Path to a saved NumpyVectorStore directory.

    Returns:
        A configured :class:`~semantic_search.runtime.api.SearchRuntime`.

    Raises:
        SystemExit: If the backend or vector store cannot be loaded.
    """
    # Import provider modules so they self-register with the factory.
    import semantic_search.embeddings.bedrock as _b  # noqa: F401
    import semantic_search.embeddings.sagemaker as _sm  # noqa: F401
    import semantic_search.embeddings.spot as _sp  # noqa: F401

    from semantic_search.embeddings.factory import get_provider
    from semantic_search.runtime.api import SearchRuntime
    from semantic_search.vectorstores.faiss_store import NumpyVectorStore, VectorStoreError

    try:
        provider = get_provider(backend, provider_config)
    except Exception as exc:  # noqa: BLE001
        LOGGER.critical("Failed to initialise embedding provider '%s': %s", backend, exc)
        raise SystemExit(1) from exc

    try:
        store = NumpyVectorStore.load(vector_store_path)
    except VectorStoreError as exc:
        LOGGER.critical("Failed to load vector store from '%s': %s", vector_store_path, exc)
        raise SystemExit(1) from exc

    LOGGER.info(
        "Runtime initialised: backend=%s  store=%s  records=%d",
        backend,
        vector_store_path,
        len(store._vectors),
    )
    return SearchRuntime(provider, store)


def build_app() -> Any:
    """Construct and return the FastAPI application, configured from environment.

    Returns:
        Configured :class:`~fastapi.FastAPI` application instance.
    """
    from semantic_search.runtime.api import create_app

    enable_ui = os.environ.get("ENABLE_UI", "").lower() in ("true", "1", "yes")
    vector_store_path = os.environ.get("VECTOR_STORE_PATH", "")
    backend = os.environ.get("EMBEDDING_BACKEND", "spot")
    provider_config_raw = os.environ.get("PROVIDER_CONFIG_JSON", "{}")

    runtime = None
    if vector_store_path:
        try:
            provider_config = json.loads(provider_config_raw)
        except json.JSONDecodeError:
            LOGGER.warning(
                "PROVIDER_CONFIG_JSON is not valid JSON — ignoring; using empty config."
            )
            provider_config = {}
        runtime = _build_runtime(backend, provider_config, vector_store_path)
    else:
        LOGGER.warning(
            "VECTOR_STORE_PATH not set — starting without a runtime. "
            "/readyz will return 503 until app.state.runtime is set."
        )

    return create_app(runtime, enable_ui=enable_ui)


# Module-level ``app`` so uvicorn can reference it as ``main:app``.
app = build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
        log_level=os.environ.get("LOG_LEVEL", "info"),
        reload=False,
    )
