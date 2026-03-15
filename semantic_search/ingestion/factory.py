"""Factory utilities for pluggable data source connectors."""

from __future__ import annotations

from typing import Callable, Dict, Mapping, MutableMapping

from .base import DataSourceConnector, DataSourceError

FactoryFn = Callable[[Mapping[str, object]], DataSourceConnector]

__all__ = [
    "register_connector",
    "get_connector",
    "list_registered_connectors",
]


class _ConnectorRegistry:
    """Internal registry maintaining backend → factory mappings."""

    def __init__(self) -> None:
        self._factories: MutableMapping[str, FactoryFn] = {}

    def register(
        self, backend: str, factory: FactoryFn, *, overwrite: bool = False
    ) -> None:
        key = backend.lower()
        if not overwrite and key in self._factories:
            raise DataSourceError(
                f"Data source connector backend '{backend}' is already registered."
            )
        self._factories[key] = factory

    def create(self, backend: str, config: Mapping[str, object]) -> DataSourceConnector:
        key = backend.lower()
        if key not in self._factories:
            raise DataSourceError(
                f"Data source connector backend '{backend}' is not registered."
            )
        return self._factories[key](config)

    def available(self) -> Dict[str, FactoryFn]:
        return dict(self._factories)


_registry = _ConnectorRegistry()


def register_connector(
    backend: str,
    *,
    overwrite: bool = False,
) -> Callable[[FactoryFn], FactoryFn]:
    """Decorator used by connectors to register their factory callable.

    Example:
        @register_connector("csv")
        def build_csv(config: Mapping[str, object]) -> DataSourceConnector:
            return CsvConnector(**config)

    Args:
        backend: Logical backend identifier (case insensitive).
        overwrite: When True, replaces any existing registration.

    Returns:
        The original factory function to support decorator usage.
    """

    def decorator(factory: FactoryFn) -> FactoryFn:
        _registry.register(backend, factory, overwrite=overwrite)
        return factory

    return decorator


def get_connector(
    backend: str,
    config: Mapping[str, object] | None = None,
) -> DataSourceConnector:
    """Instantiate a connector for the requested backend."""
    return _registry.create(backend, config or {})


def list_registered_connectors() -> Dict[str, FactoryFn]:
    """Expose the currently registered connector factories."""
    return _registry.available()
