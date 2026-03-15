"""Ingestion package exposing data source connector abstractions and factory utilities."""

from .base import DataSourceConnector, DataSourceError, Record
from .factory import (
    get_connector,
    list_registered_connectors,
    register_connector,
)

__all__ = [
    "DataSourceConnector",
    "DataSourceError",
    "Record",
    "get_connector",
    "list_registered_connectors",
    "register_connector",
]

from . import (
    api_connector,  # noqa: F401
    csv_connector,  # noqa: F401
    json_connector,  # noqa: F401
    mongodb_connector,  # noqa: F401
    sql_connector,  # noqa: F401
    xml_connector,  # noqa: F401
)
