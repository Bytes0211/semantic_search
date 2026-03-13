"""
Factory utilities for constructing embedding provider instances based on
configuration at runtime.

This module keeps the application decoupled from specific provider
implementations by centralising registration and instantiation logic.

Usage example
-------------

    from semantic_search.embeddings.factory import get_provider

    provider = get_provider(
        backend="bedrock",
        config={"region": "us-east-1", "model": "amazon.titan-text-lite-v1"},
    )
    embeddings = provider.generate(inputs)

Providers are registered via :func:`register_provider`. Implementations
should call the decorator at import time so they are discoverable by the
factory without additional wiring.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Mapping, MutableMapping, Optional, Type

from .base import EmbeddingProvider

# Type alias for callables that construct providers. They receive a configuration
# mapping and return an instantiated EmbeddingProvider.
FactoryFn = Callable[[Mapping[str, Any]], EmbeddingProvider]


class ProviderRegistryError(RuntimeError):
    """Raised when provider registration or lookup fails."""


class _ProviderRegistry:
    """Internal registry maintaining backend -> factory mappings."""

    def __init__(self) -> None:
        self._factories: MutableMapping[str, FactoryFn] = {}

    def register(
        self, backend: str, factory: FactoryFn, *, overwrite: bool = False
    ) -> None:
        """Add a factory for the given backend identifier."""
        key = backend.lower()
        if not overwrite and key in self._factories:
            raise ProviderRegistryError(
                f"Embedding provider backend '{backend}' is already registered."
            )
        self._factories[key] = factory

    def create(
        self, backend: str, config: Optional[Mapping[str, Any]] = None
    ) -> EmbeddingProvider:
        """Instantiate a provider for the specified backend."""
        key = backend.lower()
        if key not in self._factories:
            raise ProviderRegistryError(
                f"Embedding provider backend '{backend}' is not registered."
            )
        factory = self._factories[key]
        return factory(config or {})

    def available_backends(self) -> Dict[str, FactoryFn]:
        """Return a copy of the registered backend->factory map."""
        return dict(self._factories)


_registry = _ProviderRegistry()


def register_provider(
    backend: str,
    *,
    overwrite: bool = False,
) -> Callable[[FactoryFn], FactoryFn]:
    """Decorator to register an embedding provider factory.

    Example
    -------
        @register_provider("bedrock")
        def build_bedrock(config: Mapping[str, Any]) -> EmbeddingProvider:
            return BedrockEmbeddingProvider(**config)

    Args:
        backend: Unique identifier used in configuration (case-insensitive).
        overwrite: Allow replacing an existing registration when True.

    Returns:
        The original factory function (suitable for decorator usage).
    """

    def decorator(factory: FactoryFn) -> FactoryFn:
        _registry.register(backend, factory, overwrite=overwrite)
        return factory

    return decorator


def get_provider(
    backend: str,
    config: Optional[Mapping[str, Any]] = None,
) -> EmbeddingProvider:
    """Create an embedding provider for the requested backend.

    Args:
        backend: Backend identifier (e.g., ``\"bedrock\"``, ``\"spot\"``).
        config: Optional configuration mapping forwarded to the factory.

    Returns:
        An instantiated :class:`EmbeddingProvider`.
    """
    return _registry.create(backend, config)


def list_registered_backends() -> Dict[str, FactoryFn]:
    """Expose the currently registered provider factories."""
    return _registry.available_backends()
