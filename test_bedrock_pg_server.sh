#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PROVIDER_CONFIG_JSON:-}" ]]; then
  export PROVIDER_CONFIG_JSON='{"region":"us-east-1","model":"amazon.titan-embed-text-v1"}'
fi

###############################################################################
# test_bedrock_pg_server.sh
#
# Builds a Bedrock-embedded vector index from the semantic_search_test
# PostgreSQL database and validates the local search server against it.
#
# Tables indexed:
#   • support_tickets  (title + body → text; category, priority, status → metadata)
#   • candidates       (full_name + summary + skills → text;
#                       location, years_experience, availability → metadata)
#
# Prerequisites
# -------------
#   1. PROVIDER_CONFIG_JSON exported with Bedrock credentials + config:
#        export PROVIDER_CONFIG_JSON='{"region":"us-east-1","model":"amazon.titan-embed-text-v1"}'
#   2. PostgreSQL running locally with semantic_search_test seeded:
#        psql -f developer/sql/seed_semantic_search_test.sql semantic_search_test
###############################################################################

# ------------------------------- UI Helpers -------------------------------- #

SPINNER_PID=""
SERVER_PID=""
TAIL_PID=""

start_spinner() {
  local msg="$1"
  printf "  %s" "$msg"
  (
    local sp='|/-\'
    local i=0
    while true; do
      printf "\r  %s %s" "$msg" "${sp:i++%${#sp}:1}"
      sleep 0.1
    done
  ) &
  SPINNER_PID=$!
  disown
}

stop_spinner() {
  if [[ -n "$SPINNER_PID" ]] && kill -0 "$SPINNER_PID" 2>/dev/null; then
    kill "$SPINNER_PID" 2>/dev/null || true
  fi
  SPINNER_PID=""
  printf "\r  %s ✓\n" "$1"
}

pause() {
  local seconds="${1:-2}"
  sleep "$seconds"
}

kill_port_occupant() {
  local port="${1:-8000}"
  local pids
  pids="$(lsof -ti :"$port" 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    start_spinner "Stopping existing server on port $port"
    echo "$pids" | xargs kill 2>/dev/null || true
    sleep 2
    pids="$(lsof -ti :"$port" 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      echo "$pids" | xargs kill -9 2>/dev/null || true
      sleep 0.5
    fi
    stop_spinner "Stopping existing server on port $port"
  fi
}

banner() {
  cat <<'EOF'
╔══════════════════════════════════════════════════════════════════╗
║  Semantic Search :: PostgreSQL × Bedrock Local Validation Runner ║
╚══════════════════════════════════════════════════════════════════╝
EOF
  echo
}

INDEX_DIR="./pg_bedrock_index"
SELECTED_BACKEND="bedrock"
ENABLE_UI_FLAG=false
READY_STATUS=1

# ------------------------------ Validations -------------------------------- #

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: '$cmd' is required but not on PATH."
    exit 1
  fi
}

ensure_repo_root() {
  if [[ ! -f "pyproject.toml" || ! -d "semantic_search" ]]; then
    echo "Error: run this script from the project root (semantic_search/)."
    exit 1
  fi
}

parse_args() {
  for arg in "$@"; do
    case "$arg" in
      --ui) ENABLE_UI_FLAG=true ;;
      *) ;;
    esac
  done
}

ensure_bedrock_config() {
  if [[ -z "${PROVIDER_CONFIG_JSON:-}" ]]; then
    echo "Error: PROVIDER_CONFIG_JSON is not set."
    echo "  Export your Bedrock configuration before running:"
    echo "  export PROVIDER_CONFIG_JSON='{\"region\":\"us-east-1\",\"model\":\"amazon.titan-embed-text-v1\"}'"
    exit 1
  fi
}

check_postgres() {
  start_spinner "Verifying PostgreSQL connectivity (semantic_search_test)"
  if ! psql -d semantic_search_test -c "SELECT 1" >/dev/null 2>&1; then
    stop_spinner "Verifying PostgreSQL connectivity (semantic_search_test)"
    echo "  Error: Cannot connect to the 'semantic_search_test' database."
    echo "    Ensure PostgreSQL is running and the DB is seeded:"
    echo "    psql -f developer/sql/seed_semantic_search_test.sql semantic_search_test"
    exit 1
  fi
  stop_spinner "Verifying PostgreSQL connectivity (semantic_search_test)"
}

# ------------------------------ Main Tasks --------------------------------- #

generate_pg_bedrock_index() {
  local region="us-east-1"
  local extracted_region
  extracted_region="$(uv run python -c "import json,sys; print(json.loads(sys.stdin.read()).get('region',''),end='')" <<<"${PROVIDER_CONFIG_JSON}" 2>/dev/null || true)"
  if [[ -n "$extracted_region" ]]; then
    region="$extracted_region"
  fi

  start_spinner "Extracting from PostgreSQL and embedding via Bedrock (region: $region)"
  if uv run python scripts/generate_pg_index.py \
      --region "$region" \
      --output "$INDEX_DIR" >/tmp/pg_bedrock_index.log 2>&1; then
    stop_spinner "Extracting from PostgreSQL and embedding via Bedrock (region: $region)"
  else
    stop_spinner "Extracting from PostgreSQL and embedding via Bedrock (region: $region)"
    echo "  Failed to build index. Full log:"
    sed 's/^/    /' /tmp/pg_bedrock_index.log
    exit 1
  fi
}

inspect_index() {
  start_spinner "Inspecting generated index"
  INDEX_DIR="$INDEX_DIR" uv run python - <<'EOF' >/tmp/index_inspect.log 2>&1 || true
import os
from semantic_search.vectorstores.faiss_store import NumpyVectorStore

path = os.environ.get("INDEX_DIR", "./pg_bedrock_index")
try:
    store = NumpyVectorStore.load(path)
except Exception as exc:
    raise SystemExit(f"Could not load index at {path!r}: {exc}") from exc

print(f"Index   : {path}")
print(f"Records : {len(store._vectors)}")
print(f"Dimension: {store.dimension}")
print(f"Metric  : {store._metric_name}")

tables: dict = {}
for meta in store._metadata.values():
    t = meta.get("source_table", "unknown")
    tables[t] = tables.get(t, 0) + 1
print("By table:")
for table, count in sorted(tables.items()):
    print(f"  {table}: {count} records")

print("Sample records:")
for record_id, meta in list(store._metadata.items())[:4]:
    print(f"  [{record_id}] {meta}")
EOF
  stop_spinner "Inspecting generated index"
  sed 's/^/    /' /tmp/index_inspect.log
}

launch_server() {
  if [[ ! -d "$INDEX_DIR" ]]; then
    echo "Error: Index directory '$INDEX_DIR' not found — did index generation succeed?"
    exit 1
  fi

  kill_port_occupant 8000

  if [[ "$ENABLE_UI_FLAG" == "true" ]]; then
    export ENABLE_UI=true
  fi

  export VECTOR_STORE_PATH="$INDEX_DIR"
  export EMBEDDING_BACKEND="$SELECTED_BACKEND"

  : > /tmp/server.log
  start_spinner "Starting local server"
  uv run python main.py >/tmp/server.log 2>&1 &
  SERVER_PID=$!
  sleep 3  # allow uvicorn to bind
  stop_spinner "Starting local server"
}

verify_endpoints() {
  local base_url="http://localhost:8000"

  start_spinner "Checking /healthz"
  local health_status=1
  for _ in {1..10}; do
    if curl -sSf "$base_url/healthz" >/tmp/healthz.log 2>&1; then
      health_status=0
      break
    fi
    sleep 1
  done
  if [[ $health_status -eq 0 ]]; then
    stop_spinner "Checking /healthz"
  else
    stop_spinner "Checking /healthz"
    echo "    /healthz did not return 200 within timeout. See /tmp/healthz.log."
  fi

  start_spinner "Checking /readyz"
  READY_STATUS=1
  for _ in {1..10}; do
    if curl -sSf "$base_url/readyz" >/tmp/readyz.log 2>&1; then
      READY_STATUS=0
      break
    fi
    sleep 1
  done
  if [[ $READY_STATUS -eq 0 ]]; then
    stop_spinner "Checking /readyz"
  else
    stop_spinner "Checking /readyz"
    echo "    /readyz did not return 200 within timeout. See /tmp/readyz.log."
  fi
}

teardown_server() {
  if [[ -n "${TAIL_PID:-}" ]]; then
    kill "$TAIL_PID" >/dev/null 2>&1 || true
    wait "$TAIL_PID" 2>/dev/null || true
    TAIL_PID=""
  fi
  if [[ -n "${SERVER_PID:-}" ]]; then
    if kill -0 "$SERVER_PID" 2>/dev/null; then
      start_spinner "Stopping local server"
      kill "$SERVER_PID" >/dev/null 2>&1 || true
      wait "$SERVER_PID" 2>/dev/null || true
      stop_spinner "Stopping local server"
    else
      wait "$SERVER_PID" 2>/dev/null || true
    fi
    SERVER_PID=""
  fi
}

open_browser() {
  local url="$1"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 &
  elif command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 &
  else
    echo "  Open your browser at: $url"
  fi
}

run_query_loop() {
  local base_url="http://localhost:8000"
  echo
  printf '%s\n' "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Interactive Search  —  top 5 results per query  ('q' to quit)"
  printf '%s\n' "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  while true; do
    echo
    printf "  Query> "
    local query
    read -r query
    [[ "$query" == "q" || "$query" == "quit" ]] && break
    [[ -z "$query" ]] && continue

    local json_body
    json_body="$(uv run python -c "
import json, sys
print(json.dumps({'query': sys.argv[1], 'top_k': 5}))
" "$query" 2>/dev/null)"

    if [[ -z "$json_body" ]]; then
      echo "  Error: could not build request body."
      continue
    fi

    local response
    response="$(curl -s -X POST "$base_url/v1/search" \
      -H "Content-Type: application/json" \
      -d "$json_body" 2>/dev/null)"

    if [[ -z "$response" ]]; then
      echo "  No response from server — is it still running?"
      continue
    fi

    printf '%s' "$response" | uv run python -c "
import json, sys
try:
    data = json.load(sys.stdin)
except json.JSONDecodeError:
    print('  Error: could not parse server response.')
    sys.exit(1)
results = data.get('results', [])
elapsed = data.get('elapsed_ms', 0)
if not results:
    print(f'  No results  [{elapsed:.1f} ms]')
    sys.exit(0)
print(f'  {len(results)} result(s)  [{elapsed:.1f} ms]')
print()
for i, r in enumerate(results, 1):
    meta = r.get('metadata', {})
    table = meta.get('source_table', '')
    label = f'[{table}]  ' if table else ''
    score = r['score']
    rid = r['record_id']
    title = next((str(meta[k]) for k in ['title', 'full_name', 'name'] if k in meta), rid)
    print(f'  {i}. {label}{title}  (score: {score:.4f})')
    skip = {'source_table', 'title', 'full_name', 'name'}
    meta_parts = [f'{k}: {v}' for k, v in meta.items() if k not in skip]
    if meta_parts:
        print('     ' + '  |  '.join(meta_parts))
" 2>/dev/null || echo "  Error: failed to parse response."
  done
}

# ------------------------------- Entrypoint -------------------------------- #

main() {
  parse_args "$@"
  banner
  ensure_repo_root
  ensure_bedrock_config
  require_command uv
  require_command curl
  require_command psql

  echo "Preparing environment..."
  pause 1

  check_postgres
  pause 1

  generate_pg_bedrock_index
  pause 1

  inspect_index
  pause 1

  launch_server
  pause 1

  verify_endpoints

  echo
  echo "  Server : http://localhost:8000  |  Backend: $SELECTED_BACKEND"
  echo "  Index  : $VECTOR_STORE_PATH"
  echo "  Logs   : /tmp/server.log"

  if [[ "$ENABLE_UI_FLAG" == "true" && $READY_STATUS -eq 0 ]]; then
    echo "  UI     : http://localhost:8000/ui  (opening browser...)"
    open_browser "http://localhost:8000/ui"
  fi

  if [[ $READY_STATUS -eq 0 ]]; then
    run_query_loop
  else
    echo
    echo "  /readyz did not pass — index may not be loaded."
    echo "  Press Enter to stop the server."
    read -r
  fi

  teardown_server

  cat <<EOF

✅ PostgreSQL × Bedrock validation complete
  • Source  : semantic_search_test (support_tickets, candidates)
  • Index   : $INDEX_DIR
  • Backend : $SELECTED_BACKEND
  • /healthz and /readyz probed

Refer to developer/guides/data-and-testing-guide.md for subsequent steps.
EOF
}

trap teardown_server EXIT
main "$@"
