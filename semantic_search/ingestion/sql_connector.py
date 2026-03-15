from __future__ import annotations

import contextlib
from typing import Iterator, Mapping, Sequence

import sqlalchemy
from sqlalchemy.engine import Result
from sqlalchemy.sql import text

from .base import DataSourceConnector, DataSourceError, Record
from .factory import register_connector


class SqlConnector(DataSourceConnector):
    """Connector that extracts records from an SQL database via SQLAlchemy."""

    def __init__(
        self,
        *,
        connection_string: str,
        query: str,
        text_fields: Sequence[str],
        id_field: str,
        metadata_fields: Sequence[str] | None = None,
        batch_size: int = 1000,
    ) -> None:
        if not connection_string:
            raise DataSourceError("SQL connector requires a connection_string.")
        if not query:
            raise DataSourceError("SQL connector requires a query.")
        if not text_fields:
            raise DataSourceError("SQL connector requires at least one text field.")
        if not id_field:
            raise DataSourceError("SQL connector requires an id_field.")

        self._connection_string = connection_string
        self._query = query
        self._text_fields = list(text_fields)
        self._id_field = id_field
        self._metadata_fields = list(metadata_fields or [])
        self._batch_size = max(1, batch_size)

    def extract(self) -> Iterator[Record]:
        try:
            engine = sqlalchemy.create_engine(self._connection_string)
        except Exception as exc:  # pragma: no cover - engine creation failures
            raise DataSourceError(f"Failed to create SQL engine: {exc}") from exc

        try:
            with engine.connect() as connection:
                if self._batch_size > 0:
                    result = connection.execution_options(
                        stream_results=True, max_row_buffer=self._batch_size
                    ).execute(text(self._query))
                else:
                    result = connection.execute(text(self._query))

                with contextlib.closing(result):
                    yield from self._iter_rows(result)
        finally:
            engine.dispose()

    def _iter_rows(self, result: Result) -> Iterator[Record]:
        for row in result.mappings():
            row_dict = dict(row)

            missing_text = [
                column for column in self._text_fields if column not in row_dict
            ]
            if missing_text:
                raise DataSourceError(
                    f"Row is missing expected text column(s): {missing_text}"
                )
            if self._id_field not in row_dict:
                raise DataSourceError(
                    f"Row is missing required id column: {self._id_field}"
                )

            record_id = str(row_dict[self._id_field])

            text_parts = [
                str(row_dict[column]).strip()
                for column in self._text_fields
                if row_dict.get(column) not in (None, "")
            ]
            metadata = {
                column: row_dict[column]
                for column in self._metadata_fields
                if column in row_dict and row_dict[column] not in (None, "")
            }

            yield Record(
                record_id=record_id,
                text=" | ".join(text_parts),
                metadata=metadata,
                source="sql",
            )


@register_connector("sql")
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

    try:
        return SqlConnector(
            connection_string=str(config["connection_string"]),
            query=str(config["query"]),
            text_fields=_sequence("text_fields"),
            id_field=str(config["id_field"]),
            metadata_fields=_sequence("metadata_fields"),
            batch_size=int(config.get("batch_size", 1000)),
        )
    except KeyError as exc:
        raise DataSourceError(f"Missing required SQL config key: {exc}") from exc
    except ValueError as exc:
        raise DataSourceError(f"Invalid SQL connector configuration: {exc}") from exc
