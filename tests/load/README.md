# Load Testing — Semantic Search `/v1/search`

Locust-based load tests for the semantic search runtime.  The test file
(`locustfile.py`) posts queries drawn from a JSON query bank to the
`/v1/search` endpoint and tracks throughput, latency, and error rates.

---

## Prerequisites

Install Locust into the project's dev environment:

```bash
uv sync --group dev
```

The service under test must be running and reachable before you start Locust.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TARGET_HOST` | `http://localhost:8000` | Base URL of the service under test. |
| `QUERY_BANK_FILE` | `semantic_search/evaluation/sample_queries.json` | Path to the JSON query bank. Each entry needs `query_text` and optionally `top_k`. |
| `TOP_K` | `10` | Fallback result count when a query entry does not supply `top_k`. |

---

## Running Locust

### Interactive / Web UI mode

```bash
TARGET_HOST=http://localhost:8000 \
  locust -f tests/load/locustfile.py
```

Open [http://localhost:8089](http://localhost:8089) in your browser, set the
number of users and spawn rate, then start the swarm.

### Headless / CI mode

Run for a fixed duration (e.g. 60 s), spawning 20 users at 5/s:

```bash
TARGET_HOST=http://localhost:8000 \
  QUERY_BANK_FILE=semantic_search/evaluation/sample_queries.json \
  locust -f tests/load/locustfile.py \
    --headless \
    --users 20 \
    --spawn-rate 5 \
    --run-time 60s \
    --html reports/load_report.html
```

Add `--csv reports/load_results` to produce CSV artefacts for later analysis.

### Against a deployed environment

```bash
TARGET_HOST=https://api.example.com \
  QUERY_BANK_FILE=/path/to/production_queries.json \
  locust -f tests/load/locustfile.py \
    --headless \
    --users 50 \
    --spawn-rate 10 \
    --run-time 5m
```

---

## Acceptance Criteria

A load test run **passes** when all of the following hold across a steady-state
window of at least 60 seconds at the target concurrency:

| Metric | Target |
|---|---|
| P95 end-to-end latency (`/v1/search`) | **≤ 1 000 ms** |
| Error rate (non-2xx responses) | **< 2 %** |
| Throughput | **≥ 10 RPS** (single-task baseline) |

These numbers are starting points; adjust per environment capacity and SLA.

---

## Query Bank Format

The query bank is a JSON array of objects.  Minimum schema:

```json
[
  {
    "query_text": "semantic search for internal docs",
    "top_k": 10
  }
]
```

The full evaluation schema (`EvalQuery`) also accepts `query_id` and
`relevant_ids`, but the load test only reads `query_text` and `top_k`.

---

## Reports

Locust writes results to `stdout` by default.  Use `--html` or `--csv` flags
to persist reports.  HTML reports include latency percentile charts and an
error table.

---

## Troubleshooting

**`FileNotFoundError: Query bank file not found`** — Set `QUERY_BANK_FILE`
to a valid path or let it fall back to the bundled `sample_queries.json`.

**`Connection refused` on start** — Ensure the service is running at
`TARGET_HOST` before spawning users.  The `on_start` health check will log
connection failures without aborting the run.

**High error rate** — Check the service logs; common causes are an
uninitialised vector store (503 from `/readyz`) or invalid request payloads.
Use Locust's built-in failure statistics (displayed in the web UI and
`--csv` output under `*_failures.csv`) to inspect failure counts and messages;
these cover both HTTP-level errors and network-level exceptions (timeouts,
connection resets).
