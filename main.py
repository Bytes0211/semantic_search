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
CORS_ORIGINS
    Comma-separated list of allowed CORS origins for the web UI.  Defaults
    to ``"http://localhost:5173,http://localhost:4173"`` (Vite dev and
    preview ports).  Set to ``"*"`` to allow all origins (dev only) or to
    the CloudFront distribution URL in production.
ENABLE_UI
    Set to ``"true"`` (case-insensitive) to mount the pre-built React SPA from
    ``frontend/dist/`` at ``/ui``.  Requires ``npm run build`` in ``frontend/``
    to have been run first.  Defaults to ``"false"``.
ANALYTICS_ENABLED
    Set to ``"true"`` (case-insensitive) to enable the Premium-tier query
    analytics panel in the React web UI.  Defaults to ``"false"``.
SEARCH_TOP_K
    Maximum number of results the React UI requests per query.  Returned
    via ``GET /v1/config`` so the frontend never has a hard-coded ceiling.
    Must be an integer between 1 and 200.  Defaults to ``50``.
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

Local validation with a saved index (Premium analytics enabled)::

    VECTOR_STORE_PATH=./my_index ANALYTICS_ENABLED=true uv run python main.py
    # -> React UI at http://localhost:5173 (run `npm run dev` in frontend/)
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
        len(store),
    )
    return SearchRuntime(provider, store)


def build_app() -> Any:
    """Construct and return the FastAPI application, configured from environment.

    Loads ``config/app.yaml`` and ``config/sources/*.yaml`` when a config
    directory is available (``CONFIG_DIR`` env var or ``./config``).  Falls
    back to legacy env-var-only behaviour when no config directory is found,
    ensuring backward compatibility with existing deployments.

    Returns:
        Configured :class:`~fastapi.FastAPI` application instance.
    """
    from pathlib import Path
    from semantic_search.runtime.api import create_app

    # -- Load configuration (YAML + env overrides) --------------------------
    app_config = None
    display_configs = None
    config_dir = Path(os.environ.get("CONFIG_DIR", "./config"))

    if (config_dir / "app.yaml").is_file() or (config_dir / "sources").is_dir():
        from semantic_search.config.app import load_app_config
        from semantic_search.config.source import load_source_configs

        try:
            app_config = load_app_config(config_dir)
            source_cfgs = load_source_configs(config_dir / "sources")
        except Exception as exc:
            LOGGER.critical("Failed to load configuration: %s", exc)
            raise SystemExit(1) from exc
        if source_cfgs:
            display_configs = {
                name: scfg.display for name, scfg in source_cfgs.items()
            }
        LOGGER.info(
            "Config loaded: tier=%s  backend=%s  model=%s  sources=%d",
            app_config.tier.value,
            app_config.embedding.backend,
            app_config.embedding.model,
            len(source_cfgs),
        )

    # -- Resolve runtime settings -------------------------------------------
    vector_store_path = os.environ.get("VECTOR_STORE_PATH", "")

    if app_config is not None:
        backend = app_config.embedding.backend
        cors_raw = app_config.server.cors_origins
    else:
        backend = os.environ.get("EMBEDDING_BACKEND", "spot")
        cors_raw = os.environ.get(
            "CORS_ORIGINS", "http://localhost:5173,http://localhost:4173"
        )

    cors_origins = [o.strip() for o in cors_raw.split(",") if o.strip()]
    provider_config_raw = os.environ.get("PROVIDER_CONFIG_JSON", "{}")

    # Legacy scalar fallbacks (used only when app_config is None)
    analytics_enabled = os.environ.get("ANALYTICS_ENABLED", "").lower() in (
        "true", "1", "yes",
    )
    try:
        search_top_k = max(1, min(200, int(os.environ.get("SEARCH_TOP_K", "50"))))
    except ValueError:
        LOGGER.warning("SEARCH_TOP_K is not a valid integer — using default of 50.")
        search_top_k = 50

    # -- Build runtime (if vector store path supplied) ----------------------
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

    # -- Create FastAPI app -------------------------------------------------
    app = create_app(
        runtime,
        cors_origins=cors_origins,
        analytics_enabled=analytics_enabled,
        search_top_k=search_top_k,
        app_config=app_config,
        display_configs=display_configs,
    )

    enable_ui = os.environ.get("ENABLE_UI", "").lower() in ("true", "1", "yes")
    if enable_ui:
        import pathlib
        from fastapi.staticfiles import StaticFiles as _StaticFiles
        dist = pathlib.Path("frontend/dist")
        if dist.is_dir():
            assets_dir = dist / "assets"
            if assets_dir.is_dir():
                app.mount(
                    "/assets",
                    _StaticFiles(directory=str(assets_dir)),
                    name="ui-assets",
                )
            app.mount("/ui", _StaticFiles(directory=str(dist), html=True), name="ui")
            LOGGER.info("Web UI mounted at /ui (frontend/dist)")
        else:
            LOGGER.warning(
                "ENABLE_UI=true but frontend/dist/ was not found — UI not mounted. "
                "Run 'npm run build' in frontend/ to generate the build artifacts."
            )

    return app


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
