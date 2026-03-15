"""REST API data source connector for the semantic search ingestion pipeline.

Extracts records from a paginated REST API and normalises them into the
canonical :class:`~semantic_search.ingestion.base.Record` schema.

Requires the ``httpx`` package.  It is imported lazily inside
:meth:`ApiConnector.extract` so the rest of the ingestion package can be
used without ``httpx`` installed — consistent with how ``pymongo`` is
handled in :mod:`.mongodb_connector`.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Dict, Iterator, Mapping, MutableMapping, Optional, Sequence

if TYPE_CHECKING:
    import httpx

from .base import DataSourceConnector, DataSourceError, Record
from .factory import register_connector


class ApiConnector(DataSourceConnector):
    """Connector that fetches records from a paginated REST API."""

    def __init__(
        self,
        *,
        base_url: str,
        endpoint: str,
        text_fields: Sequence[str],
        id_field: str,
        metadata_fields: Sequence[str] | None = None,
        auth_header: str | None = None,
        auth_token_env: str | None = None,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, Any] | None = None,
        records_path: str | None = "data",
        pagination: str = "cursor",
        cursor_field: str = "next",
        cursor_param: str = "cursor",
        offset_param: str = "offset",
        limit_param: str = "limit",
        page_size: int = 100,
        max_retries: int = 3,
        timeout_seconds: float = 10.0,
    ) -> None:
        if not base_url:
            raise DataSourceError("API connector requires 'base_url'.")
        if not endpoint:
            raise DataSourceError("API connector requires 'endpoint'.")
        if not text_fields:
            raise DataSourceError("API connector requires at least one text field.")
        if not id_field:
            raise DataSourceError("API connector requires 'id_field'.")

        self._base_url = base_url.rstrip("/")
        self._endpoint = endpoint.lstrip("/")
        self._text_fields = list(text_fields)
        self._id_field = id_field
        self._metadata_fields = list(metadata_fields or [])
        self._headers: Dict[str, str] = dict(headers or {})

        if auth_header:
            token = os.getenv(auth_token_env or "", "")
            if not token:
                raise DataSourceError(
                    "API connector authentication requested but token environment "
                    f"variable '{auth_token_env}' is not set or empty."
                )
            self._headers[auth_header] = token

        self._params = dict(params or {})
        self._records_path = records_path
        self._pagination = pagination.lower()
        self._cursor_field = cursor_field
        self._cursor_param = cursor_param
        self._offset_param = offset_param
        self._limit_param = limit_param
        self._page_size = max(1, page_size)
        self._max_retries = max(0, max_retries)
        self._timeout = timeout_seconds

        if self._pagination not in {"cursor", "offset"}:
            raise DataSourceError(
                "API connector 'pagination' must be either 'cursor' or 'offset'."
            )

    def extract(self) -> Iterator[Record]:
        try:
            import httpx
        except ImportError as exc:
            raise DataSourceError(
                "httpx is required for the API connector. "
                "Install it with: pip install 'httpx>=0.27.0,<1.0'"
            ) from exc

        pagination_state: MutableMapping[str, Any] = {}

        if self._pagination == "offset":
            pagination_state[self._offset_param] = 0
            pagination_state[self._limit_param] = self._page_size

        with httpx.Client(base_url=self._base_url, timeout=self._timeout) as client:
            while True:
                response = self._request_with_retry(client, pagination_state)
                payload = response.json()

                records = self._extract_records(payload)
                if not records:
                    break

                for record_payload in records:
                    yield self._build_record(record_payload)

                if not self._advance_pagination(payload, pagination_state):
                    break

    def _request_with_retry(
        self, client: httpx.Client, pagination_state: Mapping[str, Any]
    ) -> httpx.Response:
        params = dict(self._params)
        params.update(pagination_state)

        url = f"/{self._endpoint}"
        last_exc: Optional[Exception] = None
        for attempt in range(self._max_retries + 1):
            try:
                response = client.get(url, headers=self._headers, params=params)
                response.raise_for_status()
                return response
            except Exception as exc:  # pragma: no cover - network dependent
                last_exc = exc
                if attempt == self._max_retries:
                    raise DataSourceError(
                        f"API request to '{url}' failed after {self._max_retries + 1} attempts: {exc}"
                    ) from exc
        raise DataSourceError(
            f"Unexpected failure issuing request to '{url}': {last_exc}"
        )

    def _extract_records(self, payload: Any) -> Sequence[Mapping[str, Any]]:
        if self._records_path:
            records = self._resolve_path(payload, self._records_path)
        else:
            records = payload
        if not isinstance(records, Sequence):
            raise DataSourceError(
                f"Expected records sequence at path '{self._records_path}', found {type(records).__name__}"
            )
        return records  # type: ignore[return-value]

    def _advance_pagination(
        self, payload: Mapping[str, Any], pagination_state: MutableMapping[str, Any]
    ) -> bool:
        if self._pagination == "cursor":
            next_cursor = self._resolve_path(payload, self._cursor_field, default=None)
            if not next_cursor:
                return False
            pagination_state[self._cursor_param] = next_cursor
            return True

        # offset pagination
        total_returned = len(self._resolve_path(payload, self._records_path))
        if total_returned < self._page_size:
            return False
        pagination_state[self._offset_param] = (
            pagination_state.get(self._offset_param, 0) + total_returned
        )
        pagination_state[self._limit_param] = self._page_size
        return True

    def _build_record(self, item: Mapping[str, Any]) -> Record:
        if self._id_field not in item:
            raise DataSourceError(f"API record missing id field '{self._id_field}'.")
        record_id = str(item[self._id_field])

        text_parts = [
            str(item[field]).strip()
            for field in self._text_fields
            if field in item and item[field] not in (None, "")
        ]
        metadata = {
            field: item[field]
            for field in self._metadata_fields
            if field in item and item[field] not in (None, "")
        }

        return Record(
            record_id=record_id,
            text=" | ".join(text_parts),
            metadata=metadata,
            source="api",
        )

    def _resolve_path(self, payload: Any, dotted_path: str, default: Any = None) -> Any:
        if dotted_path is None:
            return payload
        current = payload
        for segment in dotted_path.split("."):
            if isinstance(current, Mapping) and segment in current:
                current = current[segment]
            else:
                return default
        return current


@register_connector("api")
def _build_connector(config: Mapping[str, object]) -> DataSourceConnector:
    def _sequence(name: str) -> Sequence[str]:
        value = config.get(name)
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        raise DataSourceError(
            f"Expected list/tuple for '{name}', got {type(value).__name__}"
        )

    def _mapping(name: str) -> Mapping[str, Any] | None:
        value = config.get(name)
        if value is None:
            return None
        if isinstance(value, Mapping):
            return {str(k): v for k, v in value.items()}
        raise DataSourceError(
            f"Expected mapping for '{name}', got {type(value).__name__}"
        )

    try:
        return ApiConnector(
            base_url=str(config["base_url"]),
            endpoint=str(config["endpoint"]),
            text_fields=_sequence("text_fields"),
            id_field=str(config["id_field"]),
            metadata_fields=_sequence("metadata_fields"),
            auth_header=str(config.get("auth_header"))
            if config.get("auth_header")
            else None,
            auth_token_env=str(config.get("auth_token_env"))
            if config.get("auth_token_env")
            else None,
            headers=_mapping("headers"),
            params=_mapping("params"),
            records_path=str(config.get("records_path"))
            if config.get("records_path")
            else "data",
            pagination=str(config.get("pagination", "cursor")),
            cursor_field=str(config.get("cursor_field", "next")),
            cursor_param=str(config.get("cursor_param", "cursor")),
            offset_param=str(config.get("offset_param", "offset")),
            limit_param=str(config.get("limit_param", "limit")),
            page_size=int(config.get("page_size", 100)),
            max_retries=int(config.get("max_retries", 3)),
            timeout_seconds=float(config.get("timeout_seconds", 10.0)),
        )
    except KeyError as exc:
        raise DataSourceError(f"Missing required API config key: {exc}") from exc
    except ValueError as exc:
        raise DataSourceError(f"Invalid API connector configuration: {exc}") from exc
