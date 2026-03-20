"""Tests for semantic_search.runtime.audit — structured AC audit logging."""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import pytest

from semantic_search.runtime.audit import AuditLogger


@pytest.fixture()
def audit_records(caplog: pytest.LogCaptureFixture):
    """Capture audit log records from the 'semantic_search.audit' logger."""
    with caplog.at_level(logging.INFO, logger="semantic_search.audit"):
        yield caplog


class TestAuditDisabled:
    """When disabled, no log entries should be emitted."""

    def test_filter_noop(self, audit_records: pytest.LogCaptureFixture) -> None:
        """log_filter is a no-op when disabled."""
        logger = AuditLogger(enabled=False)
        logger.log_filter("rec-1", ["admin"], ["viewer"])
        assert len(audit_records.records) == 0

    def test_grant_noop(self, audit_records: pytest.LogCaptureFixture) -> None:
        """log_grant is a no-op when disabled."""
        logger = AuditLogger(enabled=False, log_grants=True)
        logger.log_grant("rec-1", ["viewer"])
        assert len(audit_records.records) == 0

    def test_auth_failure_noop(self, audit_records: pytest.LogCaptureFixture) -> None:
        """log_auth_failure is a no-op when disabled."""
        logger = AuditLogger(enabled=False)
        logger.log_auth_failure(path="/v1/search", error_type="ExpiredSignatureError")
        assert len(audit_records.records) == 0


class TestAuditFilterEvent:
    """ac.filter events should be emitted for removed records."""

    def test_filter_emits_event(self, audit_records: pytest.LogCaptureFixture) -> None:
        """log_filter emits a structured JSON entry with correct fields."""
        logger = AuditLogger(enabled=True)
        logger.log_filter(
            "rec-42",
            ["admin", "editor"],
            ["viewer"],
            user_id="user-abc",
        )
        assert len(audit_records.records) == 1
        payload = json.loads(audit_records.records[0].message)
        assert payload["event"] == "ac.filter"
        assert payload["record_id"] == "rec-42"
        assert payload["security_tags"] == ["admin", "editor"]
        assert payload["caller_roles"] == ["viewer"]
        assert payload["user_id"] == "user-abc"
        assert "timestamp" in payload

    def test_filter_without_user_id(self, audit_records: pytest.LogCaptureFixture) -> None:
        """user_id defaults to None when not provided."""
        logger = AuditLogger(enabled=True)
        logger.log_filter("rec-1", None, ["analyst"])
        payload = json.loads(audit_records.records[0].message)
        assert payload["user_id"] is None


class TestAuditGrantEvent:
    """ac.grant events should be gated by log_grants flag."""

    def test_grant_emitted_when_enabled(self, audit_records: pytest.LogCaptureFixture) -> None:
        """log_grant emits when log_grants=True with default grant_reason."""
        logger = AuditLogger(enabled=True, log_grants=True)
        logger.log_grant("rec-7", ["admin"], user_id="user-xyz")
        assert len(audit_records.records) == 1
        payload = json.loads(audit_records.records[0].message)
        assert payload["event"] == "ac.grant"
        assert payload["record_id"] == "rec-7"
        assert payload["user_id"] == "user-xyz"
        assert payload["grant_reason"] == "role_match"

    def test_grant_reason_open_access(self, audit_records: pytest.LogCaptureFixture) -> None:
        """grant_reason='open_access' is preserved in the emitted payload."""
        logger = AuditLogger(enabled=True, log_grants=True)
        logger.log_grant("rec-open", [], grant_reason="open_access")
        payload = json.loads(audit_records.records[0].message)
        assert payload["grant_reason"] == "open_access"

    def test_grant_suppressed_when_disabled(self, audit_records: pytest.LogCaptureFixture) -> None:
        """log_grant is a no-op when log_grants=False."""
        logger = AuditLogger(enabled=True, log_grants=False)
        logger.log_grant("rec-7", ["admin"])
        assert len(audit_records.records) == 0


class TestAuditAuthFailure:
    """ac.auth_failure events for JWT validation failures."""

    def test_auth_failure_emits_event(self, audit_records: pytest.LogCaptureFixture) -> None:
        """log_auth_failure emits structured JSON."""
        logger = AuditLogger(enabled=True)
        logger.log_auth_failure(
            path="/v1/search",
            error_type="ExpiredSignatureError",
            user_id=None,
        )
        assert len(audit_records.records) == 1
        payload = json.loads(audit_records.records[0].message)
        assert payload["event"] == "ac.auth_failure"
        assert payload["path"] == "/v1/search"
        assert payload["error_type"] == "ExpiredSignatureError"
        assert "timestamp" in payload
