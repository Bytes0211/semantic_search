"""Tests for semantic_search.runtime.presign — S3 presigned URL generation."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from semantic_search.runtime.presign import presign_url


class TestPresignPassthrough:
    """Non-S3 links should be passed through or returned as None."""

    def test_https_url_passed_through(self) -> None:
        """HTTPS URLs are returned unchanged."""
        url = "https://example.com/doc.pdf"
        assert presign_url(url) == url

    def test_http_url_passed_through(self) -> None:
        """HTTP URLs are returned unchanged."""
        url = "http://internal.corp/report.html"
        assert presign_url(url) == url

    def test_server_relative_path_passed_through(self) -> None:
        """Server-relative paths (e.g. /data/test_doc.txt) are returned unchanged."""
        path = "/data/test_doc.txt"
        assert presign_url(path) == path

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        assert presign_url(None) is None

    def test_empty_string_returns_none(self) -> None:
        """Empty string returns None."""
        assert presign_url("") is None

    def test_na_returns_none(self) -> None:
        """'n/a' returns None (case-insensitive)."""
        assert presign_url("n/a") is None
        assert presign_url("N/A") is None

    def test_no_document_found_returns_none(self) -> None:
        """'No Document Found' returns None."""
        assert presign_url("No Document Found") is None

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped."""
        assert presign_url("  https://example.com/doc.pdf  ") == "https://example.com/doc.pdf"

    def test_unrecognised_scheme_returned_as_is(self) -> None:
        """Unknown scheme is returned as-is (not hidden)."""
        assert presign_url("ftp://host/file") == "ftp://host/file"


class TestPresignS3:
    """S3 URIs should be presigned via boto3."""

    def test_s3_uri_presigned(self) -> None:
        """s3://bucket/key generates a presigned URL via the S3 client."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://bucket.s3.amazonaws.com/key?sig=abc"

        result = presign_url(
            "s3://my-bucket/docs/report.pdf",
            ttl_seconds=300,
            s3_client=mock_client,
        )
        assert result == "https://bucket.s3.amazonaws.com/key?sig=abc"
        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-bucket", "Key": "docs/report.pdf"},
            ExpiresIn=300,
        )

    def test_ttl_forwarded_to_boto3(self) -> None:
        """TTL parameter is forwarded as ExpiresIn."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://presigned"

        presign_url("s3://b/k", ttl_seconds=60, s3_client=mock_client)
        call_kwargs = mock_client.generate_presigned_url.call_args
        assert call_kwargs.kwargs.get("ExpiresIn") == 60 or call_kwargs[1].get("ExpiresIn") == 60

    def test_s3_no_client_returns_none(self) -> None:
        """s3:// URI without a client returns None."""
        assert presign_url("s3://bucket/key") is None

    def test_s3_client_error_returns_none(self) -> None:
        """boto3 error returns None, not an exception."""
        mock_client = MagicMock()
        mock_client.generate_presigned_url.side_effect = Exception("AccessDenied")

        result = presign_url("s3://bucket/key", s3_client=mock_client)
        assert result is None

    def test_s3_malformed_uri_no_key(self) -> None:
        """s3://bucket (no key) returns None."""
        mock_client = MagicMock()
        assert presign_url("s3://bucket", s3_client=mock_client) is None
        mock_client.generate_presigned_url.assert_not_called()

    def test_s3_malformed_uri_empty_key(self) -> None:
        """s3://bucket/ (empty key) returns None."""
        mock_client = MagicMock()
        assert presign_url("s3://bucket/", s3_client=mock_client) is None
        mock_client.generate_presigned_url.assert_not_called()
