#!/usr/bin/env bash
set -euo pipefail

# Spot uses a local hash-based embedding stub — no AWS credentials required.
if [[ -z "${PROVIDER_CONFIG_JSON:-}" ]]; then
  export PROVIDER_CONFIG_JSON='{"dimension": 384}'
fi

###############################################################################
# test_spot_json_server.sh
#
# Builds a Spot-embedded vector index from a JSON file and validates the
# local search server against it.  No AWS credentials are required.
#
# NOTE: The Spot provider in this codebase is a deterministic hash-based
# stub.  Search scores will not reflect true semantic similarity until a
# real SentenceTransformers endpoint is wired in.
#
# Default JSON: data/sample_products.json (20-row product catalogue)
# Override:     JSON_PATH=./my_data.json ./test_spot_json_server.sh
#
# Usage:
#   ./test_spot_json_server.sh           # CLI query loop
#   ./test_spot_json_server.sh --ui      # + open React UI in browser
###############################################################################

# ------------------------------- UI Helpers -------------------------------- #

SPINNER_PID=""
SERVER_PID=""
TAIL_PID=""
ENABLE_UI_FLAG=false
READY_STATUS=1

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
║  Semantic Search :: JSON × Spot (Local) Validation Runner        ║
╚══════════════════════════════════════════════════════════════════╝
EOF
  echo
}

INDEX_DIR="./json_spot_index"
JSON_PATH="${JSON_PATH:-./data/sample_products.json}"
SELECTED_BACKEND="spot"

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

check_json() {
  start_spinner "Checking JSON source ($JSON_PATH)"
  if [[ ! -f "$JSON_PATH" ]]; then
    stop_spinner "Checking JSON source ($JSON_PATH)"
    echo "  Error: JSON file not found at: $JSON_PATH"
    echo "    Set JSON_PATH before running or place a JSON file at ./data/sample_products.json"
    exit 1
  fi
  local record_count
  record_count="$(uv run python -c "import json; print(len(json.load(open('$JSON_PATH'))))" 2>/dev/null || echo 0)"
  stop_spinner "Checking JSON source ($JSON_PATH)"
  echo "    Found $record_count record(s)"
}

# ------------------------------ Main Tasks --------------------------------- #

generate_json_spot_index() {
  start_spinner "Extracting from JSON and embedding via Spot"
  if uv run python scripts/generate_json_index.py \
      --json "$JSON_PATH" \
      --output "$INDEX_DIR" >/tmp/json_spot_index.log 2>&1; then
    stop_spinner "Extracting from JSON and embedding via Spot"
  else
    stop_spinner "Extracting from JSON and embedding via Spot"
    echo "  Failed to build index. Full log:"
    sed 's/^/    /' /tmp/json_spot_index.log
    exit 1
  fi
}

inspect_index() {
  start_spinner "Inspecting generated index"
  INDEX_DIR="$INDEX_DIR" uv run python - <<'EOF' >/tmp/index_inspect.log 2>&1 || true
import os
from semantic_search.vectorstores.faiss_store import NumpyVectorStore

path = os.environ.get("INDEX_DIR", "./json_spot_index")
try:
    store = NumpyVectorStore.load(path)
except Exception as exc:
    raise SystemExit(f"Could not load index at {path!r}: {exc}") from exc

print(f"Index    : {path}")
print(f"Records  : {len(store._vectors)}")
print(f"Dimension: {store.dimension}")
print(f"Metric   : {store._metric_name}")

categories: dict = {}
for meta in store._metadata.values():
    c = meta.get("category", "unknown")
    categories[c] = categories.get(c, 0) + 1
print("By category:")
for cat, count in sorted(categories.items()):
    print(f"  {cat}: {count} records")

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
  sleep 3
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
    score = r['score']
    rid = r['record_id']
    title = next((str(meta[k]) for k in ['title', 'full_name', 'name'] if k in meta), rid)
    print(f'  {i}. {title}  (score: {score:.4f})')
    skip = {'title', 'full_name', 'name'}
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
  require_command uv
  require_command curl

  echo "Preparing environment..."
  echo "  JSON   : $JSON_PATH"
  echo "  Backend: $SELECTED_BACKEND (local — no AWS required)"
  pause 1

  check_json
  pause 1

  generate_json_spot_index
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

✅ JSON × Spot validation complete
  • Source  : $JSON_PATH
  • Index   : $INDEX_DIR
  • Backend : $SELECTED_BACKEND (local stub — scores are hash-based)
  • /healthz and /readyz probed

Refer to developer/guides/data-and-testing-guide.md for subsequent steps.
EOF
}

trap teardown_server EXIT
main "$@"
