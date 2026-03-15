from __future__ import annotations

import glob as _glob
import json
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Sequence

from .base import DataSourceConnector, DataSourceError, Record
from .factory import register_connector


class JsonConnector(DataSourceConnector):
    """Connector that reads JSON/JSONL files and emits canonical records."""

    def __init__(
        self,
        *,
        path: str,
        text_fields: Sequence[str],
        id_field: str,
        metadata_fields: Sequence[str] | None = None,
        jq_filter: str | None = None,
        encoding: str = "utf-8",
    ) -> None:
        if not path:
            raise DataSourceError("JSON connector requires a non-empty 'path'.")
        if not text_fields:
            raise DataSourceError("JSON connector requires at least one text field.")
        if not id_field:
            raise DataSourceError("JSON connector requires an 'id_field' value.")

        self._path = path
        self._text_fields = list(text_fields)
        self._id_field = id_field
        self._metadata_fields = list(metadata_fields or [])
        self._jq_filter = jq_filter
        self._encoding = encoding

    def extract(self) -> Iterator[Record]:
        matched_files = sorted(Path(p) for p in _glob.glob(self._path))
        if not matched_files:
            raise DataSourceError(
                f"JSON connector did not match any files for pattern: {self._path!r}"
            )

        for file_path in matched_files:
            try:
                yield from self._records_from_file(file_path)
            except DataSourceError:
                raise
            except Exception as exc:  # pragma: no cover - defensive path
                raise DataSourceError(
                    f"Failed to process JSON file '{file_path}': {exc}"
                ) from exc

    def _records_from_file(self, file_path: Path) -> Iterator[Record]:
        if file_path.suffix.lower() == ".jsonl":
            with file_path.open("r", encoding=self._encoding) as handle:
                for line_number, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise DataSourceError(
                            f"Invalid JSON on line {line_number} in {file_path}: {exc}"
                        ) from exc
                    yield self._build_record(payload, file_path, line_number)
        else:
            with file_path.open("r", encoding=self._encoding) as handle:
                payload = json.load(handle)

            records = self._apply_filter(payload)
            if not isinstance(records, list):
                raise DataSourceError(
                    f"Filtered JSON payload in {file_path} is not a list of records."
                )

            for index, item in enumerate(records, start=1):
                yield self._build_record(item, file_path, index)

    def _apply_filter(self, payload: Any) -> Any:
        if not self._jq_filter:
            return payload
        # Minimal jq-style dotted path support (e.g., ".data.items")
        path = self._jq_filter.lstrip(".")
        if not path:
            return payload
        current = payload
        for segment in path.split("."):
            if isinstance(current, dict) and segment in current:
                current = current[segment]
            else:
                raise DataSourceError(
                    f"jq_filter '{self._jq_filter}' could not be resolved in JSON document."
                )
        return current

    def _build_record(self, item: Any, file_path: Path, index: int) -> Record:
        if not isinstance(item, Mapping):
            raise DataSourceError(
                f"Record #{index} in {file_path} is not a JSON object."
            )

        if self._id_field not in item:
            raise DataSourceError(
                f"Record #{index} in {file_path} is missing id field '{self._id_field}'."
            )
        record_id = str(item[self._id_field])

        text_parts = [
            str(item[field]).strip()
            for field in self._text_fields
            if field in item and item[field] not in (None, "")
        ]

        metadata: Dict[str, Any] = {
            field: item[field]
            for field in self._metadata_fields
            if field in item and item[field] not in (None, "")
        }

        return Record(
            record_id=record_id,
            text=" | ".join(text_parts),
            metadata=metadata,
            source="json",
        )


@register_connector("json")
def _build_connector(config: Mapping[str, object]) -> DataSourceConnector:
    def _as_sequence(value: object | None) -> Sequence[str]:
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        raise DataSourceError(
            f"Expected list/tuple for sequence configuration, got {type(value).__name__}"
        )

    try:
        return JsonConnector(
            path=str(config["path"]),
            text_fields=_as_sequence(config.get("text_fields")),
            id_field=str(config["id_field"]),
            metadata_fields=_as_sequence(config.get("metadata_fields")),
            jq_filter=str(config.get("jq_filter")) if config.get("jq_filter") else None,
            encoding=str(config.get("encoding") or "utf-8"),
        )
    except KeyError as exc:
        raise DataSourceError(f"Missing required JSON config key: {exc}") from exc
