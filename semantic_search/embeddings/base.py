from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

Vector = List[float]


@dataclass(frozen=True)
class EmbeddingInput:
    """Input payload for embedding generation.

    Attributes:
        record_id: Unique identifier for the source record.
        text: Canonical text to embed.
        metadata: Optional contextual metadata to forward to providers.
    """

    record_id: str
    text: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingResult:
    """Embedding output returned by an embedding provider.

    Attributes:
        record_id: Identifier matching the originating input record.
        vector: Numerical embedding representation.
        metadata: Optional provider-specific metadata (e.g., model name, token counts).
    """

    record_id: str
    vector: Vector
    metadata: Mapping[str, Any] = field(default_factory=dict)


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers.

    Concrete implementations should perform model-specific setup in ``__init__``
    and implement :meth:`generate` to transform input records into embeddings.
    """

    @abstractmethod
    def generate(
        self,
        inputs: Sequence[EmbeddingInput],
        *,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Sequence[EmbeddingResult]:
        """Generate embeddings for the provided inputs.

        Args:
            inputs: Sequence of records to embed.
            model: Optional override to select a specific model variant.
            **kwargs: Provider-specific control parameters (e.g., batching hints).

        Returns:
            Sequence of embedding results aligned with the input order.

        Raises:
            ValueError: If the provider cannot process the supplied inputs.
            RuntimeError: If the underlying service returns an error.
        """
        raise NotImplementedError
