#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PROVIDER_CONFIG_JSON:-}" ]]; then
  export PROVIDER_CONFIG_JSON='{"region":"us-east-1","model":"amazon.titan-embed-text-v1"}'
fi


###############################################################################
# test_bedrock_json_server.sh
#
# Automates Sections 2.1 – 3.2 of developer/guides/data-and-testing-guide.md:
#   2.1 Generate random test index
#   2.2 Generate Bedrock-backed index (if configuration is present)
#   2.4 Inspect saved index contents
#   3.1 Launch local server with generated index
#   3.2 Verify /healthz and /readyz endpoints
#
# The script provides animated feedback, sleeps between major stages,
# and reports a concise summary at the end.
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

banner() {
  cat <<'EOF'
╔══════════════════════════════════════════════════════════════════╗
║  Semantic Search :: Data Generation & Local Validation Runner    ║
╚══════════════════════════════════════════════════════════════════╝
EOF
  echo
}

INDEX_DIR_RANDOM="./test_index"
INDEX_DIR_BEDROCK="./bedrock_index"
SELECTED_VECTOR_PATH=""
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

# ------------------------------ Main Tasks --------------------------------- #

generate_random_index() {
  start_spinner "Generating random test index (Section 2.1)"
  uv run python scripts/generate_test_index.py >/tmp/random_index.log 2>&1
  stop_spinner "Generating random test index (Section 2.1)"
  if [[ -z "$SELECTED_VECTOR_PATH" ]]; then
    SELECTED_VECTOR_PATH="$INDEX_DIR_RANDOM"
  fi
}

generate_bedrock_index() {
  local output_dir="$INDEX_DIR_BEDROCK"
  local config="${PROVIDER_CONFIG_JSON:-}"
  # NOTE: this guard will not trigger while the default export at lines 4-6 is present;
  # remove that export if you want Bedrock generation to be skippable when no config is set.
  if [[ -z "$config" ]]; then
    echo "  Skipping Bedrock index (Section 2.2): PROVIDER_CONFIG_JSON not set."
    echo "    Export e.g. PROVIDER_CONFIG_JSON='{\"region\":\"us-east-1\",\"model\":\"amazon.titan-embed-text-v1\"}'"
    return
  fi
  local region="us-east-1"
  local extracted_region
  extracted_region="$(uv run python -c "import json,sys; print(json.loads(sys.stdin.read()).get('region',''),end='')" <<<"$config" 2>/dev/null || true)"
  if [[ -n "$extracted_region" ]]; then
    region="$extracted_region"
  fi

  start_spinner "Generating Bedrock-backed index (Section 2.2)"
  if uv run python scripts/generate_test_index.py \
      --backend bedrock \
      --region "$region" \
      --output "$output_dir" >/tmp/bedrock_index.log 2>&1; then
    stop_spinner "Generating Bedrock-backed index (Section 2.2)"
    SELECTED_BACKEND="bedrock"
    SELECTED_VECTOR_PATH="$INDEX_DIR_BEDROCK"
  else
    stop_spinner "Generating Bedrock-backed index (Section 2.2)"
    echo "    Failed to build Bedrock index. Inspect /tmp/bedrock_index.log for details."
  fi
}

inspect_index() {
  start_spinner "Inspecting generated index (Section 2.4)"
  SELECTED_VECTOR_PATH="$SELECTED_VECTOR_PATH" uv run python - <<'EOF' >/tmp/index_inspect.log 2>&1 || true
import os
from semantic_search.vectorstores.faiss_store import NumpyVectorStore

preferred = os.environ.get("SELECTED_VECTOR_PATH")
candidates = []
if preferred:
    candidates.append(preferred)
candidates.extend(["./bedrock_index", "./test_index"])

seen = set()
for path in candidates:
    if not path or path in seen:
        continue
    seen.add(path)
    try:
        store = NumpyVectorStore.load(path)
    except Exception:
        continue
    print(f"Index: {path}")
    print(f"  Records : {len(store._vectors)}")
    print(f"  Dimension: {store.dimension}")
    print(f"  Metric  : {store._metric_name}")
    for record_id, meta in list(store._metadata.items())[:3]:
        print(f"    {record_id}: {meta}")
    break
else:
    raise SystemExit("No index available to inspect.")
EOF
  stop_spinner "Inspecting generated index (Section 2.4)"
  sed 's/^/    /' /tmp/index_inspect.log
}

launch_server() {
  local vector_path="$SELECTED_VECTOR_PATH"
  if [[ -z "$vector_path" || ! -d "$vector_path" ]]; then
    if [[ "$SELECTED_BACKEND" == "bedrock" && -d "$INDEX_DIR_BEDROCK" ]]; then
      vector_path="$INDEX_DIR_BEDROCK"
    elif [[ -d "$INDEX_DIR_RANDOM" ]]; then
      vector_path="$INDEX_DIR_RANDOM"
    fi
  fi

  if [[ -z "$vector_path" || ! -d "$vector_path" ]]; then
    echo "Error: No vector store directory found (expected $INDEX_DIR_BEDROCK or $INDEX_DIR_RANDOM)."
    exit 1
  fi

  local config="${PROVIDER_CONFIG_JSON:-}"
  if [[ "$SELECTED_BACKEND" == "bedrock" && -z "$config" ]]; then
    echo "Error: PROVIDER_CONFIG_JSON must be set to launch the server with the bedrock backend (Section 3.1)."
    echo "       Export e.g. PROVIDER_CONFIG_JSON='{\"region\":\"us-east-1\",\"model\":\"amazon.titan-embed-text-v1\"}'"
    exit 1
  fi

  if [[ "$ENABLE_UI_FLAG" == "true" ]]; then
    export ENABLE_UI=true
  fi

  export VECTOR_STORE_PATH="$vector_path"
  export EMBEDDING_BACKEND="$SELECTED_BACKEND"

  : > /tmp/server.log
  start_spinner "Starting local server (Section 3.1)"
  uv run python main.py >/tmp/server.log 2>&1 &
  SERVER_PID=$!
  sleep 3  # allow uvicorn to boot
  stop_spinner "Starting local server (Section 3.1)"
}

verify_endpoints() {
  local base_url="http://localhost:8000"

  start_spinner "Checking /healthz (Section 3.2)"
  local health_status=1
  for _ in {1..10}; do
    if curl -sSf "$base_url/healthz" >/tmp/healthz.log 2>&1; then
      health_status=0
      break
    fi
    sleep 1
  done
  if [[ $health_status -eq 0 ]]; then
    stop_spinner "Checking /healthz (Section 3.2)"
  else
    stop_spinner "Checking /healthz (Section 3.2)"
    echo "    /healthz did not return 200 within timeout. See /tmp/healthz.log."
  fi

  start_spinner "Checking /readyz (Section 3.2)"
  READY_STATUS=1
  for _ in {1..10}; do
    if curl -sSf "$base_url/readyz" >/tmp/readyz.log 2>&1; then
      READY_STATUS=0
      break
    fi
    sleep 1
  done

  if [[ $READY_STATUS -eq 0 ]]; then
    stop_spinner "Checking /readyz (Section 3.2)"
  else
    stop_spinner "Checking /readyz (Section 3.2)"
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
  require_command uv
  require_command curl

  echo "Preparing environment..."
  pause 1

  generate_random_index
  pause 1

  generate_bedrock_index
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

✅ Completed Sections 2.1 – 3.2
  • Random test index generated ($INDEX_DIR_RANDOM)
  • Active backend: $SELECTED_BACKEND
  • Active index: $VECTOR_STORE_PATH
  • Local server launched with generated index
  • /healthz and /readyz probed

Refer to developer/guides/data-and-testing-guide.md for subsequent steps.
EOF
}

trap teardown_server EXIT
main "$@"
