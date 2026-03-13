"""Public exports for embedding provider interfaces and factories."""

from .base import EmbeddingInput, EmbeddingProvider, EmbeddingResult
from .bedrock import BedrockEmbeddingProvider
from .factory import get_provider, list_registered_backends, register_provider
from .sagemaker import SageMakerEmbeddingProvider
from .spot import SpotEmbeddingProvider

__all__ = [
    "EmbeddingInput",
    "EmbeddingProvider",
    "EmbeddingResult",
    "BedrockEmbeddingProvider",
    "SpotEmbeddingProvider",
    "SageMakerEmbeddingProvider",
    "get_provider",
    "list_registered_backends",
    "register_provider",
]
