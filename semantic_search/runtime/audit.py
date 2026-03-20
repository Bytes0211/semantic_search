"""Structured audit logging for access-control decisions (ABAC Phase D).

Emits structured JSON log entries via a dedicated ``semantic_search.audit``
logger so operators can route audit events to a separate CloudWatch log group
with different retention and access policies.

Events:
- ``ac.filter``  — record removed by the post-filter.
- ``ac.grant``   — record passed the filter (opt-in, high volume).
- ``ac.auth_failure`` — JWT validation failure.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional, Sequence

AUDIT_LOGGER = logging.getLogger("semantic_search.audit")


class AuditLogger:
    """Emits structured audit events for access-control decisions.

    Args:
        enabled: Master toggle. When ``False``, all methods are no-ops.
        log_grants: When ``True``, emit events for records that *pass*
            the filter in addition to filtered records.
    """

    def __init__(self, *, enabled: bool = False, log_grants: bool = False) -> None:
        """Initialise the audit logger.

        Args:
            enabled: Master toggle.
            log_grants: Also emit grant events.
        """
        self._enabled = enabled
        self._log_grants = log_grants

    @property
    def enabled(self) -> bool:
        """Whether audit logging is active."""
        return self._enabled

    def log_filter(
        self,
        record_id: str,
        security_tags: Any,
        caller_roles: Sequence[str],
        *,
        user_id: Optional[str] = None,
    ) -> None:
        """Emit an ``ac.filter`` event for a record removed by the post-filter.

        Args:
            record_id: Identifier of the filtered record.
            security_tags: The ``allowed_roles`` value from the record's metadata.
            caller_roles: Roles presented by the caller.
            user_id: JWT ``sub`` claim when available.
        """
        if not self._enabled:
            return
        self._emit({
            "event": "ac.filter",
            "record_id": record_id,
            "security_tags": _serialise(security_tags),
            "caller_roles": list(caller_roles),
            "user_id": user_id,
        })

    def log_grant(
        self,
        record_id: str,
        caller_roles: Sequence[str],
        *,
        user_id: Optional[str] = None,
    ) -> None:
        """Emit an ``ac.grant`` event for a record that passed the filter.

        Only emitted when ``log_grants`` is enabled.

        Args:
            record_id: Identifier of the granted record.
            caller_roles: Roles presented by the caller.
            user_id: JWT ``sub`` claim when available.
        """
        if not self._enabled or not self._log_grants:
            return
        self._emit({
            "event": "ac.grant",
            "record_id": record_id,
            "caller_roles": list(caller_roles),
            "user_id": user_id,
        })

    def log_auth_failure(
        self,
        *,
        path: str,
        error_type: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Emit an ``ac.auth_failure`` event for a JWT validation failure.

        Args:
            path: Request path that failed authentication.
            error_type: Exception class name.
            user_id: JWT ``sub`` claim if partially decoded.
        """
        if not self._enabled:
            return
        self._emit({
            "event": "ac.auth_failure",
            "path": path,
            "error_type": error_type,
            "user_id": user_id,
        })

    @staticmethod
    def _emit(payload: Dict[str, Any]) -> None:
        """Write a structured JSON log entry to the audit logger.

        Args:
            payload: Event fields to log.
        """
        entry = {**payload, "timestamp": time.time()}
        AUDIT_LOGGER.info(json.dumps(entry, default=str))


def _serialise(value: Any) -> Any:
    """Coerce a metadata value to a JSON-safe type.

    Args:
        value: Raw metadata value (list, set, string, etc.).

    Returns:
        A JSON-serialisable equivalent.
    """
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    if isinstance(value, set):
        return sorted(str(v) for v in value)
    if value is None:
        return None
    return str(value)
