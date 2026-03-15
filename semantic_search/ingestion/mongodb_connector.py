"""MongoDB data source connector for the semantic search ingestion pipeline.

Extracts documents from a MongoDB collection and normalises them into the
canonical :class:`~semantic_search.ingestion.base.Record` schema.

Requires the ``pymongo`` package.  It is imported lazily so the rest of the
ingestion package can be used without ``pymongo`` installed.

Example configuration::

    {
        "uri":        "mongodb://localhost:27017",
        "database":   "my_db",
        "collection": "support_tickets",
        "text_fields":     ["title", "body"],
        "id_field":        "_id",               # default; any top-level field
        "metadata_fields": ["category", "priority", "status"],
        "filter":     {"status": "open"},        # optional MongoDB query filter
        "batch_size": 500,                        # cursor batch size
    }
"""

from __future__ import annotations

from typing import Any, Iterator, Mapping, Sequence

from .base import DataSourceConnector, DataSourceError, Record
from .factory import register_connector


class MongoDbConnector(DataSourceConnector):
    """Connector that extracts records from a MongoDB collection.

    Attributes:
        _uri: MongoDB connection URI.
        _database: Name of the database to query.
        _collection: Name of the collection to query.
        _text_fields: Ordered list of top-level fields whose values are
            concatenated (with `` | `` separator) to form the embeddable text.
        _id_field: Top-level field used as the canonical record identifier.
            Defaults to ``_id``; the raw value is always coerced to ``str``.
        _metadata_fields: Top-level fields stored as filterable metadata.
        _filter: MongoDB query filter dict passed to ``collection.find()``.
        _batch_size: Number of documents fetched per network round-trip.
    """

    def __init__(
        self,
        *,
        uri: str,
        database: str,
        collection: str,
        text_fields: Sequence[str],
        id_field: str = "_id",
        metadata_fields: Sequence[str] | None = None,
        filter: Mapping[str, Any] | None = None,
        batch_size: int = 1000,
    ) -> None:
        """Initialise and validate connector configuration.

        Args:
            uri: MongoDB connection URI (e.g. ``"mongodb://localhost:27017"``).
            database: Database name.
            collection: Collection name.
            text_fields: One or more top-level fields whose values are joined
                to produce the text sent to the embedding provider.
            id_field: Top-level field used as the record identifier.
                Defaults to ``"_id"``.
            metadata_fields: Additional top-level fields stored alongside the
                vector for filtering and result display.
            filter: Optional MongoDB query filter applied to ``collection.find()``.
            batch_size: Cursor batch size (default 1000).

        Raises:
            DataSourceError: If any required configuration value is missing or
                invalid.
        """
        if not uri:
            raise DataSourceError("MongoDB connector requires a uri.")
        if not database:
            raise DataSourceError("MongoDB connector requires a database.")
        if not collection:
            raise DataSourceError("MongoDB connector requires a collection.")
        if not text_fields:
            raise DataSourceError(
                "MongoDB connector requires at least one text_field."
            )

        self._uri = uri
        self._database = database
        self._collection = collection
        self._text_fields = list(text_fields)
        self._id_field = id_field
        self._metadata_fields = list(metadata_fields or [])
        self._filter: dict[str, Any] = dict(filter) if filter else {}
        self._batch_size = max(1, batch_size)

    def extract(self) -> Iterator[Record]:
        """Yield canonical records from the configured MongoDB collection.

        Opens a connection to MongoDB, runs ``collection.find(filter)``, and
        streams documents through :meth:`_iter_docs`.  The connection is always
        closed on exit, even on failure.

        Yields:
            Normalised :class:`Record` instances.

        Raises:
            DataSourceError: If ``pymongo`` is not installed, the connection
                fails, or a document cannot be normalised.
        """
        try:
            import pymongo
        except ImportError as exc:
            raise DataSourceError(
                "pymongo is required for the MongoDB connector. "
                "Install it with: pip install pymongo"
            ) from exc

        try:
            client = pymongo.MongoClient(self._uri, serverSelectionTimeoutMS=5000)
        except Exception as exc:
            raise DataSourceError(
                f"Failed to create MongoDB client: {exc}"
            ) from exc

        try:
            coll = client[self._database][self._collection]
            cursor = coll.find(self._filter, batch_size=self._batch_size)
            yield from self._iter_docs(cursor)
        except DataSourceError:
            raise
        except Exception as exc:
            raise DataSourceError(f"Failed to query MongoDB: {exc}") from exc
        finally:
            client.close()

    def _iter_docs(self, cursor: Any) -> Iterator[Record]:
        """Normalise raw MongoDB documents into :class:`Record` objects.

        Args:
            cursor: A pymongo (or compatible) cursor over the result set.

        Yields:
            One :class:`Record` per document.

        Raises:
            DataSourceError: If a document is missing the id field or an
                expected text field.
        """
        for doc in cursor:
            if self._id_field not in doc:
                raise DataSourceError(
                    f"Document is missing required id field: {self._id_field!r}"
                )

            record_id = str(doc[self._id_field])

            missing_text = [
                f for f in self._text_fields if f not in doc
            ]
            if missing_text:
                raise DataSourceError(
                    f"Document is missing expected text field(s): {missing_text}"
                )

            text_parts = [
                str(doc[f]).strip()
                for f in self._text_fields
                if doc.get(f) not in (None, "")
            ]

            metadata = {
                f: doc[f]
                for f in self._metadata_fields
                if f in doc and doc[f] is not None
            }

            yield Record(
                record_id=record_id,
                text=" | ".join(text_parts),
                metadata=metadata,
                source="mongodb",
            )


@register_connector("mongodb")
def _build_connector(config: Mapping[str, object]) -> DataSourceConnector:
    """Factory function registered under the ``"mongodb"`` connector key.

    Args:
        config: Connector configuration mapping.  Required keys: ``uri``,
            ``database``, ``collection``, ``text_fields``.

    Returns:
        A configured :class:`MongoDbConnector` instance.

    Raises:
        DataSourceError: If a required key is absent or a value has the wrong
            type.
    """

    def _sequence(name: str) -> Sequence[str]:
        """Extract a list/tuple config value as a sequence of strings."""
        value = config.get(name)
        if value is None:
            return []
        if isinstance(value, (list, tuple)):
            return [str(item) for item in value]
        raise DataSourceError(
            f"Expected list/tuple for '{name}', got {type(value).__name__}"
        )

    try:
        return MongoDbConnector(
            uri=str(config["uri"]),
            database=str(config["database"]),
            collection=str(config["collection"]),
            text_fields=_sequence("text_fields"),
            id_field=str(config.get("id_field", "_id")),
            metadata_fields=_sequence("metadata_fields"),
            filter=config.get("filter"),  # type: ignore[arg-type]
            batch_size=int(config.get("batch_size", 1000)),
        )
    except KeyError as exc:
        raise DataSourceError(
            f"Missing required MongoDB config key: {exc}"
        ) from exc
    except ValueError as exc:
        raise DataSourceError(
            f"Invalid MongoDB connector configuration: {exc}"
        ) from exc
