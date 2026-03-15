from __future__ import annotations

import glob as _glob
from pathlib import Path
from typing import Dict, Iterator, Mapping, Sequence
from xml.etree import ElementTree as ET

from .base import DataSourceConnector, DataSourceError, Record
from .factory import register_connector


class XmlConnector(DataSourceConnector):
    """Connector that parses XML documents and emits canonical records."""

    def __init__(
        self,
        *,
        path: str,
        record_xpath: str,
        text_fields: Sequence[str],
        id_field: str,
        metadata_fields: Sequence[str] | None = None,
        encoding: str = "utf-8",
        namespace: Mapping[str, str] | None = None,
    ) -> None:
        if not path:
            raise DataSourceError("XML connector requires a non-empty 'path'.")
        if not record_xpath:
            raise DataSourceError("XML connector requires 'record_xpath'.")
        if not text_fields:
            raise DataSourceError("XML connector requires at least one text field.")
        if not id_field:
            raise DataSourceError("XML connector requires an 'id_field' value.")

        self._path = path
        self._record_xpath = record_xpath
        self._text_fields = list(text_fields)
        self._id_field = id_field
        self._metadata_fields = list(metadata_fields or [])
        self._encoding = encoding
        self._namespaces: Dict[str, str] | None = dict(namespace) if namespace else None

    def extract(self) -> Iterator[Record]:
        matched_files = sorted(Path(p) for p in _glob.glob(self._path))
        if not matched_files:
            raise DataSourceError(
                f"XML connector did not match any files for pattern: {self._path!r}"
            )

        for file_path in matched_files:
            try:
                tree = ET.parse(file_path)
            except (ET.ParseError, OSError) as exc:
                raise DataSourceError(
                    f"Unable to parse XML file '{file_path}': {exc}"
                ) from exc

            root = tree.getroot()
            records = root.findall(self._record_xpath, namespaces=self._namespaces)
            if not records:
                raise DataSourceError(
                    f"No elements matched record_xpath '{self._record_xpath}' in {file_path}"
                )

            for index, element in enumerate(records, start=1):
                yield self._build_record(element, file_path, index)

    def _build_record(self, element: ET.Element, file_path: Path, index: int) -> Record:
        record_id = self._resolve_value(element, self._id_field)
        if record_id in (None, ""):
            raise DataSourceError(
                f"Record #{index} in {file_path} is missing id field '{self._id_field}'."
            )

        text_parts = [
            value.strip()
            for value in (
                self._resolve_value(element, field) for field in self._text_fields
            )
            if value not in (None, "")
        ]

        metadata = {
            field: value
            for field in self._metadata_fields
            if (value := self._resolve_value(element, field)) not in (None, "")
        }

        return Record(
            record_id=str(record_id),
            text=" | ".join(text_parts),
            metadata=metadata,
            source="xml",
        )

    def _resolve_value(self, element: ET.Element, path: str | None) -> str | None:
        if not path:
            return None
        if path.startswith("@"):
            return element.get(path[1:])
        if path.startswith("text()"):
            return element.text or None
        node = element.find(path, namespaces=self._namespaces)
        if node is None:
            return None
        if len(node):
            return (node.text or "").strip() or None
        return node.text or None


@register_connector("xml")
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

    def _namespace(value: object | None) -> Mapping[str, str] | None:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return {str(k): str(v) for k, v in value.items()}
        raise DataSourceError(
            f"Expected mapping for 'namespace', got {type(value).__name__}"
        )

    try:
        return XmlConnector(
            path=str(config["path"]),
            record_xpath=str(config["record_xpath"]),
            text_fields=_sequence("text_fields"),
            id_field=str(config["id_field"]),
            metadata_fields=_sequence("metadata_fields"),
            encoding=str(config.get("encoding") or "utf-8"),
            namespace=_namespace(config.get("namespace")),
        )
    except KeyError as exc:
        raise DataSourceError(f"Missing required XML config key: {exc}") from exc
