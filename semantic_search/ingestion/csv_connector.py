from __future__ import annotations

import csv
import glob
import os
from typing import Iterator, List, Mapping, Sequence

from .base import DataSourceConnector, DataSourceError, Record
from .factory import register_connector


class CsvConnector(DataSourceConnector):
    """Connector that reads one or more CSV files and emits canonical records.

    The connector streams rows from every matched CSV file, concatenates the
    configured text fields into the `Record.text` payload, and exposes any
    additional metadata columns requested.

    Args:
        path: Absolute or relative file path / glob pattern matching CSV files.
        text_fields: Ordered sequence of column names to concatenate into the
            semantic text payload.
        id_field: Optional column providing a stable record identifier. When
            omitted, the connector generates deterministic identifiers using the
            file name and row index.
        metadata_fields: Optional list of column names to copy verbatim into the
            record metadata mapping.
        delimiter: Optional CSV delimiter (defaults to comma).
        encoding: Optional file encoding (defaults to UTF-8).
    """

    def __init__(
        self,
        *,
        path: str,
        text_fields: Sequence[str],
        id_field: str | None = None,
        metadata_fields: Sequence[str] | None = None,
        delimiter: str = ",",
        encoding: str = "utf-8",
    ) -> None:
        if not path:
            raise DataSourceError("CSV connector requires a non-empty 'path' value.")
        if not text_fields:
            raise DataSourceError("CSV connector requires at least one text field.")
        self._path = path
        self._text_fields = list(text_fields)
        self._id_field = id_field
        self._metadata_fields = list(metadata_fields or [])
        self._delimiter = delimiter
        self._encoding = encoding

    def extract(self) -> Iterator[Record]:
        """Yield normalised records from every CSV file matching the path."""
        file_paths = sorted(glob.glob(self._path))
        if not file_paths:
            raise DataSourceError(
                f"CSV connector did not match any files for pattern: {self._path!r}"
            )

        for file_path in file_paths:
            try:
                with open(
                    file_path, "r", encoding=self._encoding, newline=""
                ) as handle:
                    reader = csv.DictReader(handle, delimiter=self._delimiter)
                    self._validate_fields(reader.fieldnames, file_path)
                    for row_index, row in enumerate(reader, start=1):
                        try:
                            yield self._build_record(file_path, row_index, row)
                        except DataSourceError:
                            raise
                        except Exception as exc:  # defensive: unexpected row issues
                            raise DataSourceError(
                                f"Failed to normalise row {row_index} in {file_path}: {exc}"
                            ) from exc
            except OSError as exc:
                raise DataSourceError(
                    f"Unable to read CSV file '{file_path}': {exc}"
                ) from exc

    def _validate_fields(self, header: Sequence[str] | None, file_path: str) -> None:
        if header is None:
            raise DataSourceError(
                f"CSV file '{file_path}' is missing a header row required for DictReader."
            )
        missing = [
            field
            for field in (*self._text_fields, *(self._metadata_fields or []))
            if field not in header
        ]
        if self._id_field and self._id_field not in header:
            missing.append(self._id_field)
        if missing:
            raise DataSourceError(
                f"CSV file '{file_path}' is missing expected column(s): {missing}"
            )

    def _build_record(
        self, file_path: str, row_index: int, row: Mapping[str, object]
    ) -> Record:
        record_id = (
            str(row[self._id_field])
            if self._id_field is not None
            else self._generate_fallback_id(file_path, row_index)
        )

        text_parts: List[str] = []
        for column in self._text_fields:
            value = row.get(column)
            if value not in (None, ""):
                text_parts.append(str(value).strip())

        metadata = {
            key: row.get(key)
            for key in self._metadata_fields
            if key in row and row.get(key) not in (None, "")
        }

        return Record(
            record_id=record_id,
            text=" | ".join(text_parts),
            metadata=metadata,
            source="csv",
        )

    @staticmethod
    def _generate_fallback_id(file_path: str, row_index: int) -> str:
        filename = os.path.basename(file_path)
        return f"{filename}:{row_index}"


@register_connector("csv")
def _build_connector(config: Mapping[str, object]) -> DataSourceConnector:
    """Factory used by the connector registry to instantiate CSV connectors."""
    try:
        return CsvConnector(
            path=str(config["path"]),
            text_fields=_coerce_sequence(config.get("text_fields")),
            id_field=str(config.get("id_field"))
            if config.get("id_field") is not None
            else None,
            metadata_fields=_coerce_sequence(config.get("metadata_fields")),
            delimiter=str(config.get("delimiter")) if config.get("delimiter") else ",",
            encoding=str(config.get("encoding")) if config.get("encoding") else "utf-8",
        )
    except KeyError as exc:
        raise DataSourceError(f"Missing required CSV config key: {exc}") from exc


def _coerce_sequence(value: object | None) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    raise DataSourceError(
        f"Expected a list for sequence configuration, got {type(value).__name__}"
    )
