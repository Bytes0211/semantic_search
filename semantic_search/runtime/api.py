from __future__ import annotations

from logging import getLogger
from time import perf_counter
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Union

try:
    from fastapi import Depends, FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
except (
    ModuleNotFoundError
) as exc:  # pragma: no cover - ensures clear guidance when dependency missing.
    raise RuntimeError(
        "FastAPI is required to use the semantic search runtime API. "
        "Install it with `pip install fastapi[standard]` or add it to your project dependencies."
    ) from exc

try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError as exc:  # pragma: no cover
    raise RuntimeError(
        "Pydantic is required to use the semantic search runtime API. "
        "Install it with `pip install pydantic`."
    ) from exc

from starlette.requests import Request as StarletteRequest

from semantic_search.embeddings.base import EmbeddingInput, EmbeddingProvider
from semantic_search.vectorstores.faiss_store import NumpyVectorStore, QueryResult

LOGGER = getLogger(__name__)

FilterValue = Union[str, Sequence[str]]


class SearchRequest(BaseModel):
    """Payload submitted to the semantic search endpoint."""

    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language query to execute.",
    )
    top_k: int = Field(
        10,
        ge=1,
        le=200,
        description="Maximum number of results to return.",
    )
    filters: Optional[Dict[str, FilterValue]] = Field(
        default=None,
        description=(
            "Optional metadata filters applied to search results. "
            "Specify as a mapping of field name to either a string or list of acceptable values."
        ),
    )
    roles: Optional[List[str]] = Field(
        default=None,
        description=(
            "Caller's roles for access-control filtering (dev/testing). "
            "Ignored when access control is disabled. In production, roles "
            "are derived from JWT claims (Phase B)."
        ),
    )


class SearchResultItem(BaseModel):
    """Single search hit returned to clients."""

    record_id: str = Field(..., description="Identifier of the matched record.")
    score: float = Field(..., description="Similarity score for the match.")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Metadata associated with the record.",
    )
    detail: Dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Detail fields for drill-down display. Extracted from the "
            "reserved '_detail' key in stored metadata at query time."
        ),
    )


class SearchResponse(BaseModel):
    """Structured response describing search outcomes."""

    query: str = Field(..., description="Original query string.")
    top_k: int = Field(..., description="Requested result count.")
    elapsed_ms: float = Field(..., description="End-to-end latency for the query.")
    embedding_model: Optional[str] = Field(
        default=None,
        description="Embedding model used to vectorise the query, when available.",
    )
    embedding_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider-specific metadata attached to the query embedding.",
    )
    query_vector: List[float] = Field(
        ...,
        description="Numerical embedding derived from the query (primarily for debugging).",
    )
    results: List[SearchResultItem] = Field(
        default_factory=list,
        description="Ranked list of semantic matches.",
    )
    total_results: int = Field(
        ...,
        description="Number of results returned after filtering.",
    )


class SearchRuntime:
    """Coordinates embedding generation and vector store lookup for semantic search."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: NumpyVectorStore,
        *,
        default_top_k: int = 10,
        max_top_k: int = 200,
        candidate_multiplier: int = 3,
        access_control_enabled: bool = False,
        access_control_roles_field: str = "allowed_roles",
        access_control_overfetch_multiplier: int = 3,
    ) -> None:
        """Initialise the runtime.

        Args:
            embedding_provider: Provider used to convert natural-language queries into vectors.
            vector_store: Backing vector index queried for nearest neighbours.
            default_top_k: Fallback result count when a request omits `top_k`.
            max_top_k: Maximum result count permitted per request.
            candidate_multiplier: Multiplier applied to `top_k` to broaden the candidate
                pool prior to filter application. Must be >= 1.
            access_control_enabled: When ``True``, results are post-filtered by
                comparing the caller's roles against each record's roles metadata.
            access_control_roles_field: Metadata key holding the list of allowed
                roles on each record.
            access_control_overfetch_multiplier: Additional multiplier applied to
                ``top_k`` when access control is active.  Must be >= 1.

        Raises:
            ValueError: If configuration values are invalid.
        """
        if default_top_k <= 0:
            raise ValueError("default_top_k must be positive.")
        if max_top_k < default_top_k:
            raise ValueError(
                "max_top_k must be greater than or equal to default_top_k."
            )
        if candidate_multiplier < 1:
            raise ValueError("candidate_multiplier must be at least 1.")
        if access_control_overfetch_multiplier < 1:
            raise ValueError("access_control_overfetch_multiplier must be at least 1.")

        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._default_top_k = default_top_k
        self._max_top_k = max_top_k
        self._candidate_multiplier = candidate_multiplier
        self._ac_enabled = access_control_enabled
        self._ac_roles_field = access_control_roles_field
        self._ac_overfetch_multiplier = access_control_overfetch_multiplier

    def search(self, request: SearchRequest) -> SearchResponse:
        """Execute a semantic search request.

        Args:
            request: Parsed search payload.

        Returns:
            Response payload containing ranked results.

        Raises:
            ValueError: If the request is invalid.
            RuntimeError: If the embedding provider fails to return a query vector.
        """
        query = request.query.strip()
        if not query:
            raise ValueError(
                "Query must contain at least one non-whitespace character."
            )

        top_k = request.top_k or self._default_top_k
        if top_k > self._max_top_k:
            raise ValueError(
                f"Requested top_k={top_k} exceeds maximum supported value of {self._max_top_k}."
            )

        start = perf_counter()
        embedding_inputs = [EmbeddingInput(record_id="__query__", text=query)]
        embeddings = list(self._embedding_provider.generate(embedding_inputs))
        if not embeddings:
            raise RuntimeError(
                "Embedding provider returned no results for the supplied query."
            )

        embedding = embeddings[0]
        query_vector = list(embedding.vector)

        filter_fn = self._build_filter_fn(request.filters)
        candidate_count = max(top_k, top_k * self._candidate_multiplier)

        # Widen the candidate pool when access control is active so that
        # post-filter removal doesn't starve the result set.  The AC
        # multiplier is applied on top of candidate_multiplier.
        ac_active = self._ac_enabled
        if ac_active:
            candidate_count = max(
                candidate_count,
                top_k * self._candidate_multiplier * self._ac_overfetch_multiplier,
            )

        matches = self._vector_store.query(
            query_vector,
            k=candidate_count,
            filter_fn=filter_fn,
        )

        # --- Access-control post-filter -----------------------------------
        if ac_active:
            caller_roles = set(request.roles) if request.roles is not None else set()
            filtered: list[QueryResult] = []
            for m in matches:
                record_roles = m.metadata.get(self._ac_roles_field) if m.metadata else None
                if record_roles is None:
                    # No roles field → open access (visible to everyone)
                    filtered.append(m)
                elif isinstance(record_roles, (list, set, tuple)):
                    if caller_roles & set(record_roles):
                        filtered.append(m)
                else:
                    # Single string value
                    if str(record_roles) in caller_roles:
                        filtered.append(m)
            matches = filtered

        matches = matches[:top_k]

        elapsed_ms = (perf_counter() - start) * 1000.0

        results = []
        for match in matches:
            meta = dict(match.metadata)
            raw_detail = meta.pop("_detail", None)
            if ac_active:
                meta.pop(self._ac_roles_field, None)  # don't expose ACL to callers
            detail = raw_detail if isinstance(raw_detail, dict) else {}
            results.append(
                SearchResultItem(
                    record_id=match.record_id,
                    score=match.score,
                    metadata=meta,
                    detail=detail,
                )
            )

        return SearchResponse(
            query=query,
            top_k=top_k,
            elapsed_ms=elapsed_ms,
            embedding_model=self._resolve_model_name(embedding.metadata),
            embedding_metadata=dict(embedding.metadata),
            query_vector=query_vector,
            results=results,
            total_results=len(results),
        )

    @staticmethod
    def _resolve_model_name(metadata: Mapping[str, Any] | None) -> Optional[str]:
        """Extract the embedding model identifier from provider metadata, if present."""
        if not metadata:
            return None
        model = metadata.get("model")
        if model:
            return str(model)
        return None

    @staticmethod
    def _normalise_filter_values(raw_value: FilterValue) -> List[str]:
        """Convert an incoming filter value into a list of string tokens."""
        if isinstance(raw_value, str):
            return [raw_value]
        if isinstance(raw_value, Sequence):
            return [
                str(item)
                for item in raw_value
                if isinstance(item, (str, int, float, bool))
            ]
        raise ValueError(
            "Filter values must be strings or sequences of primitive values."
        )

    def _build_filter_fn(
        self,
        filters: Optional[Dict[str, FilterValue]],
    ) -> Optional[Callable[[QueryResult], bool]]:
        """Construct a predicate for metadata filtering."""
        if not filters:
            return None

        normalised: Dict[str, set[str]] = {}
        for key, value in filters.items():
            try:
                normalised[str(key)] = set(self._normalise_filter_values(value))
            except ValueError as exc:
                raise ValueError(f"Invalid filter for key '{key}': {exc}") from exc

        def predicate(result: QueryResult) -> bool:
            metadata = result.metadata or {}
            for key, allowed in normalised.items():
                if key not in metadata:
                    return False

                candidate_value = metadata[key]
                if isinstance(candidate_value, Sequence) and not isinstance(
                    candidate_value, str
                ):
                    candidate_tokens = {str(item) for item in candidate_value}
                else:
                    candidate_tokens = {str(candidate_value)}

                if allowed.isdisjoint(candidate_tokens):
                    return False
            return True

        return predicate


def create_app(
    runtime: Optional[SearchRuntime] = None,
    *,
    cors_origins: list[str] | None = None,
    analytics_enabled: bool = False,
    search_top_k: int = 50,
    app_config: Optional[Any] = None,
    display_configs: Optional[Dict[str, Any]] = None,
    jwt_enabled: bool = False,
) -> FastAPI:
    """Configure and return the FastAPI application serving semantic search.

    Args:
        runtime: Optional pre-configured :class:`SearchRuntime`.  When
            ``None`` the application starts without a runtime; the
            ``/readyz`` probe will return ``503`` until one is attached
            via ``app.state.runtime``.
        cors_origins: List of allowed CORS origins (e.g.
            ``["http://localhost:5173"]`` for the Vite dev server, or
            ``["*"]`` to allow all origins).  When ``None`` or empty, no
            CORS middleware is added.
        analytics_enabled: When ``True``, the ``GET /v1/config`` response
            advertises that the query analytics panel is available.  Set
            via the ``ANALYTICS_ENABLED`` environment variable for the
            Premium tier.  Defaults to ``False`` (ignored when
            *app_config* is supplied).
        search_top_k: Maximum number of results the React UI will request
            per query.  Returned via ``GET /v1/config`` so the frontend
            never has a hard-coded ceiling.  Defaults to ``50`` (ignored
            when *app_config* is supplied).
        app_config: Optional :class:`~semantic_search.config.app.AppConfig`
            instance.  When supplied, tier, feature flags, and
            ``search_top_k`` are derived from it, overriding the legacy
            scalar parameters.
        display_configs: Optional mapping of source name →
            :class:`~semantic_search.config.display.DisplayConfig`.  When
            supplied, the ``/v1/config`` response includes a ``display``
            block keyed by source name.
    """
    # -- Resolve effective config values ------------------------------------
    if app_config is not None:
        _tier = app_config.tier.value
        _detail_enabled = app_config.detail_enabled
        _filters_enabled = app_config.filters_enabled
        _analytics_enabled = app_config.analytics_enabled
        _search_top_k = app_config.server.search_top_k
    else:
        _tier = "premium" if analytics_enabled else "standard"
        _detail_enabled = True
        _filters_enabled = True
        _analytics_enabled = analytics_enabled
        _search_top_k = search_top_k

    _display_map: Dict[str, Any] = {}
    if display_configs:
        for source_name, dcfg in display_configs.items():
            _display_map[source_name] = (
                dcfg.to_dict() if hasattr(dcfg, "to_dict") else dcfg
            )

    app = FastAPI(
        title="Semantic Search Runtime",
        version="0.1.0",
        description="REST API for semantic search queries backed by vector embeddings.",
    )
    app.state.runtime = runtime
    app.state.jwt_enabled = jwt_enabled

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Authorization"],
        )

    def get_runtime() -> SearchRuntime:
        runtime_instance = getattr(app.state, "runtime", None)
        if runtime_instance is None:
            raise HTTPException(
                status_code=503,
                detail="Search runtime not initialised. Configure runtime before serving requests.",
            )
        return runtime_instance

    @app.get("/healthz", summary="Liveness probe")
    def healthcheck() -> Dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", summary="Readiness probe")
    def readiness() -> Dict[str, str]:
        _ = get_runtime()
        return {"status": "ready"}

    @app.post(
        "/v1/search",
        response_model=SearchResponse,
        summary="Execute a semantic search query.",
    )
    def search_endpoint(
        request: SearchRequest,
        raw_request: StarletteRequest,
        runtime_service: SearchRuntime = Depends(get_runtime),
    ) -> SearchResponse:
        # When JWT middleware is active, prefer token-derived roles.
        if app.state.jwt_enabled:
            jwt_roles = getattr(raw_request.state, "roles", None)
            if jwt_roles is not None:
                if request.roles is not None:
                    LOGGER.warning(
                        "request.roles supplied while JWT auth is active — "
                        "ignoring request body roles in favour of JWT-derived roles."
                    )
                request.roles = jwt_roles  # type: ignore[misc]
        try:
            return runtime_service.search(request)
        except ValueError as exc:
            LOGGER.debug("Bad search request rejected: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            LOGGER.exception("Search runtime encountered an error: %s", exc)
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/config", summary="Frontend feature configuration.")
    def config_endpoint() -> Dict[str, Any]:
        """Return tier, feature flags, and display configuration.

        The response drives the React web UI — which columns to render,
        whether drill-down and analytics are enabled, and how many results
        to request per query.  Values are set at startup and do not change
        during the lifetime of the process.
        """
        payload: Dict[str, Any] = {
            "tier": _tier,
            "detail_enabled": _detail_enabled,
            "filters_enabled": _filters_enabled,
            "analytics_enabled": _analytics_enabled,
            "search_top_k": _search_top_k,
        }
        if _display_map:
            payload["display"] = _display_map
        return payload

    return app


__all__ = [
    "SearchRequest",
    "SearchResponse",
    "SearchResultItem",
    "SearchRuntime",
    "create_app",
    "CORSMiddleware",
]
