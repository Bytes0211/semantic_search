"""S3 presigned URL generation for document links (ABAC Phase C).

Inspects the URI scheme of a ``doc_link`` value and conditionally generates
a time-limited presigned ``GetObject`` URL for ``s3://`` URIs.  Other schemes
(``https://``, server-relative paths) are passed through unchanged.

The module exposes two entry points:

* :func:`presign_url` — stateless, accepts an explicit boto3 client.
* :func:`create_presigner` — returns a closure that captures a cached
  client and TTL, suitable for injection into :class:`SearchRuntime`.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

LOGGER = logging.getLogger(__name__)


def presign_url(
    raw_link: Optional[str],
    *,
    ttl_seconds: int = 900,
    s3_client: Any = None,
) -> Optional[str]:
    """Convert a raw document link to a browser-accessible URL.

    Args:
        raw_link: Document link value from record metadata.
        ttl_seconds: Presigned URL lifetime in seconds (only for ``s3://``).
        s3_client: A ``boto3`` S3 client.  Required only when *raw_link*
            uses the ``s3://`` scheme.

    Returns:
        A presigned URL for ``s3://`` links, the original value for
        ``https://``/``http://``/server-relative links, or ``None`` for
        empty/``n/a``/missing values.
    """
    if not raw_link or raw_link.strip().lower() in ("n/a", "no document found"):
        return None

    link = raw_link.strip()

    # Pass through HTTP(S) URLs and server-relative paths.
    if link.startswith(("https://", "http://", "/")):
        return link

    # Presign S3 URIs.
    if link.startswith("s3://"):
        return _presign_s3(link, ttl_seconds=ttl_seconds, s3_client=s3_client)

    # Unrecognised scheme — return as-is rather than hiding it.
    return link


def _presign_s3(
    s3_uri: str,
    *,
    ttl_seconds: int,
    s3_client: Any,
) -> Optional[str]:
    """Generate a presigned GetObject URL from an ``s3://`` URI.

    Args:
        s3_uri: Full S3 URI (``s3://bucket/key``).
        ttl_seconds: URL lifetime in seconds.
        s3_client: boto3 S3 client.

    Returns:
        Presigned HTTPS URL, or ``None`` on error.
    """
    if s3_client is None:
        LOGGER.warning("Cannot presign '%s': no S3 client configured.", s3_uri)
        return None

    try:
        # Parse s3://bucket/key
        without_scheme = s3_uri[5:]  # strip "s3://"
        slash_idx = without_scheme.find("/")
        if slash_idx == -1:
            LOGGER.warning("Malformed S3 URI (missing key): '%s'", s3_uri)
            return None
        if slash_idx == 0:
            LOGGER.warning("Malformed S3 URI (empty bucket): '%s'", s3_uri)
            return None
        bucket = without_scheme[:slash_idx]
        key = without_scheme[slash_idx + 1:]
        if not key:
            LOGGER.warning("Malformed S3 URI (empty key): '%s'", s3_uri)
            return None

        url: str = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )
        return url
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Failed to presign '%s': %s", s3_uri, exc)
        return None


def create_presigner(
    ttl_seconds: int = 900,
    s3_region: Optional[str] = None,
) -> Callable[[Optional[str]], Optional[str]]:
    """Build a presigner closure with a cached boto3 S3 client.

    The returned callable has the signature
    ``(raw_link: str | None) -> str | None`` and is suitable for injection
    into :class:`~semantic_search.runtime.api.SearchRuntime`.

    Args:
        ttl_seconds: Default TTL for presigned URLs.
        s3_region: AWS region for the S3 client.

    Returns:
        A callable that presigns ``s3://`` links and passes through others.
    """
    import boto3  # noqa: PLC0415

    client_kwargs: dict = {}
    if s3_region:
        client_kwargs["region_name"] = s3_region
    client = boto3.client("s3", **client_kwargs)

    def _presign(raw_link: Optional[str]) -> Optional[str]:
        return presign_url(raw_link, ttl_seconds=ttl_seconds, s3_client=client)

    return _presign
