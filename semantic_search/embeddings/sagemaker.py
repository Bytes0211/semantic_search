"""SageMaker-hosted embedding provider implementation."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .base import EmbeddingInput, EmbeddingProvider, EmbeddingResult
from .factory import register_provider

LOGGER = logging.getLogger(__name__)


class SageMakerInvocationError(RuntimeError):
    """Raised when an invocation to a SageMaker endpoint fails."""


class SageMakerEmbeddingProvider(EmbeddingProvider):
    """Embedding provider backed by a SageMaker real-time inference endpoint.

    Sends each input record to a SageMaker endpoint that hosts an embedding
    model (e.g., a HuggingFace SentenceTransformers container or a custom
    fine-tuned variant) and retrieves the resulting embedding vectors.

    Supports the following common response shapes returned by SageMaker
    containers:

    - ``[[float, ...]]`` — HuggingFace embedding container (outer list unwrapped)
    - ``[float, ...]`` — Flat list of floats
    - ``{"embedding": [...]}`` — Named embedding field
    - ``{"embeddings": [[...]]}`` — Plural embeddings field (first element used)
    """

    def __init__(
        self,
        *,
        endpoint_name: str,
        region: Optional[str] = None,
        profile_name: Optional[str] = None,
        content_type: str = "application/json",
        accept: str = "application/json",
        client_kwargs: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Initialise the SageMaker provider.

        Args:
            endpoint_name: Name of the SageMaker real-time inference endpoint.
            region: AWS region where the endpoint is deployed. Defaults to
                the region resolved by the boto3 credential chain.
            profile_name: Optional AWS credentials profile name.
            content_type: MIME type for the request payload sent to the
                endpoint. Defaults to ``application/json``.
            accept: MIME type expected in the endpoint response. Defaults to
                ``application/json``.
            client_kwargs: Additional keyword arguments forwarded to
                ``boto3.Session.client``.
        """
        self._endpoint_name = endpoint_name
        self._content_type = content_type
        self._accept = accept

        session_params: Dict[str, Any] = {}
        if region:
            session_params["region_name"] = region
        if profile_name:
            session_params["profile_name"] = profile_name

        session = boto3.Session(**session_params)
        self._client = session.client(
            "sagemaker-runtime", **dict(client_kwargs or {})
        )

    def generate(
        self,
        inputs: Sequence[EmbeddingInput],
        *,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Sequence[EmbeddingResult]:
        """Generate embeddings by invoking the SageMaker endpoint.

        Each input is sent as a separate request. The ``model`` parameter is
        ignored because the deployed endpoint determines the model.

        Args:
            inputs: Sequence of records to embed.
            model: Unused for SageMaker; the endpoint determines the model.
            **kwargs: Accepts an optional ``payload_overrides`` mapping whose
                keys are merged into each request body before serialisation.

        Returns:
            Sequence of :class:`~.base.EmbeddingResult` aligned with the input
            order.

        Raises:
            SageMakerInvocationError: If the endpoint call fails or returns an
                unrecognised response structure.
        """
        if not inputs:
            return []

        payload_overrides: Mapping[str, Any] = kwargs.get("payload_overrides", {})  # type: ignore[assignment]

        results: List[EmbeddingResult] = []
        for item in inputs:
            body = self._build_payload(item, payload_overrides)
            response_payload = self._invoke_endpoint(body)
            vector = self._extract_vector(response_payload)
            results.append(
                EmbeddingResult(
                    record_id=item.record_id,
                    vector=vector,
                    metadata={"endpoint": self._endpoint_name},
                )
            )
        return results

    def _build_payload(
        self, item: EmbeddingInput, overrides: Mapping[str, Any]
    ) -> bytes:
        """Serialise an embedding input into a JSON request body.

        Args:
            item: The embedding input record.
            overrides: Additional top-level fields merged into the payload
                before serialisation.

        Returns:
            UTF-8 encoded JSON bytes ready for the endpoint invocation.
        """
        payload: Dict[str, Any] = {"inputs": item.text}
        if item.metadata:
            payload["parameters"] = dict(item.metadata)
        payload.update(overrides)
        return json.dumps(payload).encode("utf-8")

    def _invoke_endpoint(
        self, body: bytes
    ) -> Union[Mapping[str, Any], List[Any]]:
        """Call the SageMaker runtime endpoint and decode the response.

        Args:
            body: Serialised request payload bytes.

        Returns:
            Decoded JSON response; either a dict or a list depending on
            the container's output format.

        Raises:
            SageMakerInvocationError: On network or service errors, a missing
                response body, or an unparseable JSON payload.
        """
        try:
            response = self._client.invoke_endpoint(
                EndpointName=self._endpoint_name,
                ContentType=self._content_type,
                Accept=self._accept,
                Body=body,
            )
        except (ClientError, BotoCoreError) as exc:  # pragma: no cover - network
            LOGGER.exception("SageMaker endpoint invocation failed: %s", exc)
            raise SageMakerInvocationError(
                "SageMaker endpoint invocation failed"
            ) from exc

        raw_body = response.get("Body")
        if raw_body is None:
            raise SageMakerInvocationError("SageMaker response missing Body")

        if hasattr(raw_body, "read"):
            raw_body = raw_body.read()
        if isinstance(raw_body, bytes):
            raw_body = raw_body.decode("utf-8")

        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise SageMakerInvocationError(
                "Unable to parse SageMaker response payload"
            ) from exc

    def _extract_vector(
        self, payload: Union[Mapping[str, Any], List[Any]]
    ) -> List[float]:
        """Extract the embedding vector from a decoded SageMaker response.

        Handles common response shapes returned by HuggingFace and custom
        SageMaker containers:

        - ``[[float, ...]]``: HuggingFace container — outer list unwrapped.
        - ``[float, ...]``: Flat list of floats returned directly.
        - ``{"embedding": [...]}`` : Named singular embedding field.
        - ``{"embeddings": [[...]]}`` : Named plural embeddings field;
          the first element is used.

        Args:
            payload: Decoded JSON response from the endpoint.

        Returns:
            A flat list of floats representing the embedding vector.

        Raises:
            SageMakerInvocationError: If the embedding cannot be extracted or
                contains non-numeric values.
        """
        if isinstance(payload, list):
            if not payload:
                raise SageMakerInvocationError(
                    "SageMaker returned empty response list"
                )
            inner = payload[0]
            if isinstance(inner, list):
                # HuggingFace shape: [[float, ...]]
                vector: Any = inner
            elif isinstance(inner, (int, float)):
                # Flat list shape: [float, ...]
                vector = payload
            else:
                raise SageMakerInvocationError(
                    f"Unexpected response list element type: {type(inner).__name__}"
                )
        elif isinstance(payload, dict):
            if "embedding" in payload:
                vector = payload["embedding"]
            elif "embeddings" in payload:
                emb = payload["embeddings"]
                vector = emb[0] if isinstance(emb, list) and emb else emb
            else:
                raise SageMakerInvocationError(
                    "SageMaker response dict missing 'embedding' or 'embeddings' key"
                )
        else:
            raise SageMakerInvocationError(
                f"Unexpected SageMaker response type: {type(payload).__name__}"
            )

        if not isinstance(vector, list):
            raise SageMakerInvocationError("Embedding vector is not a list")

        try:
            return [float(v) for v in vector]
        except (TypeError, ValueError) as exc:
            raise SageMakerInvocationError(
                "Invalid embedding values in SageMaker response"
            ) from exc


@register_provider("sagemaker", overwrite=True)
def _sagemaker_factory(config: Mapping[str, Any]) -> SageMakerEmbeddingProvider:
    """Factory hook for the provider registry.

    Args:
        config: Configuration mapping. Must contain ``endpoint_name``. Optional
            keys: ``region``, ``profile_name``, ``content_type``, ``accept``,
            ``client_kwargs``.

    Returns:
        A configured :class:`SageMakerEmbeddingProvider` instance.

    Raises:
        ValueError: If ``endpoint_name`` is absent from ``config``.
    """
    endpoint = config.get("endpoint_name")
    if not endpoint:
        raise ValueError("SageMaker provider requires 'endpoint_name' configuration")

    return SageMakerEmbeddingProvider(
        endpoint_name=str(endpoint),
        region=config.get("region"),
        profile_name=config.get("profile_name"),
        content_type=config.get("content_type", "application/json"),
        accept=config.get("accept", "application/json"),
        client_kwargs=config.get("client_kwargs"),
    )
