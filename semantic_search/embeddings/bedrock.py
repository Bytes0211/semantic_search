from __future__ import annotations

import json
import logging
from typing import Any, Dict, Mapping, Optional, Sequence

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from .base import EmbeddingInput, EmbeddingProvider, EmbeddingResult
from .factory import register_provider

LOGGER = logging.getLogger(__name__)


class BedrockInvocationError(RuntimeError):
    """Raised when an invocation to AWS Bedrock fails."""


class BedrockEmbeddingProvider(EmbeddingProvider):
    """Embedding provider backed by AWS Bedrock foundation models."""

    def __init__(
        self,
        *,
        region: str,
        model: str,
        profile_name: Optional[str] = None,
        session_kwargs: Optional[Mapping[str, Any]] = None,
        accept: str = "application/json",
        content_type: str = "application/json",
    ) -> None:
        """Initialise the Bedrock provider.

        Args:
            region: AWS region hosting the Bedrock runtime.
            model: Bedrock model identifier (e.g. ``amazon.titan-embed-text-v1``).
            profile_name: Optional AWS profile name used for credentials.
            session_kwargs: Additional keyword arguments forwarded to ``boto3.Session``.
            accept: Accept header value for Bedrock invocation.
            content_type: Content-Type header value for Bedrock invocation.
        """
        self._model = model
        self._accept = accept
        self._content_type = content_type

        session_parameters: Dict[str, Any] = {"region_name": region}
        if profile_name:
            session_parameters["profile_name"] = profile_name
        if session_kwargs:
            session_parameters.update(session_kwargs)

        session = boto3.Session(**session_parameters)
        self._client = session.client("bedrock-runtime")

    def generate(
        self,
        inputs: Sequence[EmbeddingInput],
        *,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Sequence[EmbeddingResult]:
        """Generate embeddings for the provided inputs via the Bedrock runtime.

        Args:
            inputs: Sequence of records to embed.
            model: Optional override to select a specific Bedrock model variant.
                Falls back to the model supplied at construction if omitted.
            **kwargs: Accepts an optional ``payload_overrides`` mapping whose
                keys are merged into each request body before serialisation.

        Returns:
            Sequence of :class:`~.base.EmbeddingResult` aligned with the input
            order.

        Raises:
            BedrockInvocationError: If the Bedrock API call fails, returns a
                missing or malformed body, or yields non-numeric vector values.
        """
        if not inputs:
            return []

        target_model = model or self._model
        payload_overrides: Mapping[str, Any] = kwargs.get("payload_overrides", {})  # type: ignore[assignment]

        results: list[EmbeddingResult] = []
        for item in inputs:
            body = self._build_payload(item, payload_overrides)
            response_payload = self._invoke_model(target_model, body)
            vector = self._extract_vector(response_payload)

            results.append(
                EmbeddingResult(
                    record_id=item.record_id,
                    vector=vector,
                    metadata={"model": target_model},
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
                before serialisation (e.g. model-specific parameters).

        Returns:
            UTF-8 encoded JSON bytes ready for the Bedrock invocation.
        """
        payload: Dict[str, Any] = {"inputText": item.text}
        if item.metadata:
            payload["metadata"] = dict(item.metadata)
        payload.update(overrides)
        return json.dumps(payload).encode("utf-8")

    def _invoke_model(self, model_id: str, body: bytes) -> Mapping[str, Any]:
        """Call the Bedrock runtime and return the decoded response payload.

        Args:
            model_id: Bedrock model identifier to invoke.
            body: Serialised JSON request payload bytes.

        Returns:
            Decoded JSON response mapping from Bedrock.

        Raises:
            BedrockInvocationError: On AWS client/service errors, a missing
                response body, or an unparseable JSON payload.
        """
        try:
            response = self._client.invoke_model(
                modelId=model_id,
                accept=self._accept,
                contentType=self._content_type,
                body=body,
            )
        except (ClientError, BotoCoreError) as exc:  # pragma: no cover - network
            LOGGER.exception("Bedrock invocation failed: %s", exc)
            raise BedrockInvocationError("Bedrock invocation failed") from exc

        raw_body = response.get("body")
        if raw_body is None:
            raise BedrockInvocationError("Bedrock response missing body")

        if hasattr(raw_body, "read"):
            raw_body = raw_body.read()
        if isinstance(raw_body, bytes):
            raw_body = raw_body.decode("utf-8")

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise BedrockInvocationError(
                "Unable to parse Bedrock response payload"
            ) from exc

        return payload

    def _extract_vector(self, payload: Mapping[str, Any]) -> list[float]:
        """Extract the embedding vector from a decoded Bedrock response.

        Handles both ``embedding`` (lowercase, Titan) and ``Embeddings``
        (capitalised, some foundation models) response keys.

        Args:
            payload: Decoded JSON response from the Bedrock invocation.

        Returns:
            A flat list of floats representing the embedding vector.

        Raises:
            BedrockInvocationError: If the expected key is absent, the value is
                not a list, or any element cannot be cast to float.
        """
        if "embedding" in payload:
            vector = payload["embedding"]
        elif "Embeddings" in payload:  # some models use capitalised fields
            vector = payload["Embeddings"]
        else:
            raise BedrockInvocationError("Bedrock response missing embedding vector")

        if not isinstance(vector, list):
            raise BedrockInvocationError("Embedding vector not returned as list")

        try:
            return [float(value) for value in vector]
        except (TypeError, ValueError) as exc:
            raise BedrockInvocationError(
                "Invalid embedding values in Bedrock response"
            ) from exc


@register_provider("bedrock", overwrite=True)
def _bedrock_factory(config: Mapping[str, Any]) -> BedrockEmbeddingProvider:
    """Factory used by the embedding provider registry."""
    required_keys = {"region", "model"}
    missing = required_keys - config.keys()
    if missing:
        raise ValueError(f"Missing Bedrock configuration keys: {sorted(missing)}")
    return BedrockEmbeddingProvider(
        region=str(config["region"]),
        model=str(config["model"]),
        profile_name=config.get("profile_name"),
        session_kwargs=config.get("session_kwargs"),
        accept=config.get("accept", "application/json"),
        content_type=config.get("content_type", "application/json"),
    )
