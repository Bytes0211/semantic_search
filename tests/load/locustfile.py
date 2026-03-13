"""Locust load test for the semantic search ``/v1/search`` endpoint.

Configuration is supplied entirely via environment variables so the file can
be used without modification across CI and local runs.

Environment variables
---------------------
TARGET_HOST
    Base URL of the service under test, e.g. ``http://localhost:8000``.
    Falls back to ``http://localhost:8000`` when not set.
QUERY_BANK_FILE
    Path to a JSON file containing an array of query objects with at least a
    ``query_text`` field and an optional ``top_k`` field.  Defaults to the
    ``sample_queries.json`` shipped with the evaluation module.
TOP_K
    Default result count used when a query object does not supply ``top_k``.
    Defaults to ``10``.

Usage
-----
See ``tests/load/README.md`` for full run instructions.
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path
from typing import Any, Dict, List

from locust import HttpUser, between, events, task

# ──────────────────────────────────────────────────────────────────────────────
# Defaults
# ──────────────────────────────────────────────────────────────────────────────

_DEFAULT_HOST = "http://localhost:8000"
_DEFAULT_TOP_K = 10
_FALLBACK_QUERY_BANK = str(
    Path(__file__).parent.parent.parent
    / "semantic_search"
    / "evaluation"
    / "sample_queries.json"
)


# ──────────────────────────────────────────────────────────────────────────────
# Query bank helpers
# ──────────────────────────────────────────────────────────────────────────────


def _load_query_bank(path: str) -> List[Dict[str, Any]]:
    """Load and validate the query bank from *path*.

    Args:
        path: Filesystem path to the JSON query bank file.

    Returns:
        List of query dicts, each with at least a ``query_text`` key.

    Raises:
        FileNotFoundError: When *path* does not exist.
        ValueError: When the file is not a non-empty JSON array or individual
            entries are missing ``query_text``.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Query bank file not found: {path}")

    with file_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, list) or not data:
        raise ValueError(
            f"Query bank must be a non-empty JSON array; got: {type(data).__name__}"
        )

    for idx, entry in enumerate(data):
        if not isinstance(entry, dict) or "query_text" not in entry:
            raise ValueError(
                f"Entry {idx} in query bank is missing required field 'query_text'."
            )

    return data  # type: ignore[return-value]


# ──────────────────────────────────────────────────────────────────────────────
# Shared state populated at test-start
# ──────────────────────────────────────────────────────────────────────────────

_query_bank: List[Dict[str, Any]] = []
_default_top_k: int = _DEFAULT_TOP_K


@events.test_start.add_listener
def on_test_start(environment, **_kwargs: Any) -> None:  # type: ignore[no-untyped-def]
    """Load the query bank once before the first user spawns.

    Args:
        environment: Locust environment (not used directly).
        **_kwargs: Additional keyword arguments passed by Locust (ignored).
    """
    global _query_bank, _default_top_k

    bank_path = os.environ.get("QUERY_BANK_FILE", _FALLBACK_QUERY_BANK)
    _default_top_k = int(os.environ.get("TOP_K", str(_DEFAULT_TOP_K)))

    try:
        _query_bank = _load_query_bank(bank_path)
        print(
            f"[locust] Loaded {len(_query_bank)} queries from {bank_path} "
            f"(default top_k={_default_top_k})."
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"[locust] WARNING: Could not load query bank — {exc}")
        # Fall back to a single synthetic query so the test can still run.
        _query_bank = [{"query_text": "semantic search test query", "top_k": 10}]


# ──────────────────────────────────────────────────────────────────────────────
# Locust user
# ──────────────────────────────────────────────────────────────────────────────


class SearchUser(HttpUser):
    """Simulated user that continuously submits search queries.

    Wait time is randomised between 0.5 s and 2 s to produce a realistic
    arrival pattern without hammering the service.
    """

    host = os.environ.get("TARGET_HOST", _DEFAULT_HOST)
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        """Validate that the service is healthy before issuing queries.

        Performs a single GET ``/healthz`` probe.  If the probe fails, Locust
        logs a warning but does not abort the run — the failure will be counted
        in the task failure statistics.
        """
        with self.client.get(
            "/healthz",
            name="/healthz (on_start)",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"Health check failed with status {response.status_code}."
                )

    @task
    def search_task(self) -> None:
        """POST a randomly selected query to ``/v1/search``.

        A query is chosen at random from the loaded bank.  The ``top_k``
        field from the bank entry is used when present; otherwise
        ``TOP_K`` (or ``10``) is used.

        Responses with a non-2xx status code are explicitly marked as
        failures so Locust counts them in its error metrics.
        """
        if not _query_bank:
            return

        entry = random.choice(_query_bank)
        payload: Dict[str, Any] = {
            "query": entry["query_text"],
            "top_k": entry.get("top_k", _default_top_k),
        }

        with self.client.post(
            "/v1/search",
            json=payload,
            name="/v1/search",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(
                    f"/v1/search returned status {response.status_code}: "
                    f"{response.text[:200]}"
                )
