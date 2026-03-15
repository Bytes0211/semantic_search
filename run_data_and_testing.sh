#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${PROVIDER_CONFIG_JSON:-}" ]]; then
  export PROVIDER_CONFIG_JSON='{"region":"us-east-1","model":"amazon.titan-embed-text-v1"}'
fi


###############################################################################
# run_data_and_testing.sh
#
# Automates Sections 1.1 – 2.2 of developer/guides/data_and_testing_guide.md:
#   1.1 Generate random test index
#   1.2 Generate Bedrock-backed index (if configuration is present)
#   1.4 Inspect saved index contents
#   2.1 Launch local server with generated index
#   2.2 Verify /healthz and /readyz endpoints
#
# The script provides animated feedback, sleeps between major stages,
# and reports a concise summary at the end.
###############################################################################

# ------------------------------- UI Helpers -------------------------------- #

SPINNER_PID=""

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
    kill "$SPINNER_PID" >/dev/null 2>&1 || true
    wait "$SPINNER_PID" 2>/dev/null || true
  fi
  SPINNER_PID=""
  TAIL_PID=""
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

# ------------------------------ Main Tasks --------------------------------- #

generate_random_index() {
  start_spinner "Generating random test index (Section 1.1)"
  uv run python scripts/generate_test_index.py >/tmp/random_index.log 2>&1
  stop_spinner "Generating random test index (Section 1.1)"
  if [[ -z "$SELECTED_VECTOR_PATH" ]]; then
    SELECTED_VECTOR_PATH="$INDEX_DIR_RANDOM"
  fi
}

generate_bedrock_index() {
  local output_dir="$INDEX_DIR_BEDROCK"
  local config="${PROVIDER_CONFIG_JSON:-}"
  if [[ -z "$config" ]]; then
    echo "  Skipping Bedrock index (Section 1.2): PROVIDER_CONFIG_JSON not set."
    echo "    Export e.g. PROVIDER_CONFIG_JSON='{\"region\":\"us-east-1\",\"model\":\"amazon.titan-embed-text-v1\"}'"
    SELECTED_BACKEND="spot"
    return
  fi
`
  start_spinner "Generating Bedrock-backed index (Section 1.2)"
  if uv run python scripts/generate_test_index.py \
      --backend bedrock \
      --region "$(jq -r '.region' <<<"$config" 2>/dev/null || echo us-east-1)" \
      --output "$output_dir" >/tmp/bedrock_index.log 2>&1; then
    stop_spinner "Generating Bedrock-backed index (Section 1.2)"
    SELECTED_BACKEND="bedrock"
    SELECTED_VECTOR_PATH="$INDEX_DIR_BEDROCK"
  else
    stop_spinner "Generating Bedrock-backed index (Section 1.2)"
    echo "    Failed to build Bedrock index. Inspect /tmp/bedrock_index.log for details."
    SELECTED_BACKEND="spot"
  fi
}

inspect_index() {
  start_spinner "Inspecting generated index (Section 1.4)"
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
  stop_spinner "Inspecting generated index (Section 1.4)"
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
    echo "Error: PROVIDER_CONFIG_JSON must be set to launch the server with the bedrock backend (Section 2.1)."
    echo "       Export e.g. PROVIDER_CONFIG_JSON='{\"region\":\"us-east-1\",\"model\":\"amazon.titan-embed-text-v1\"}'"
    exit 1
  fi

  export VECTOR_STORE_PATH="$vector_path"
  export EMBEDDING_BACKEND="$SELECTED_BACKEND"

  : > /tmp/server.log
  start_spinner "Starting local server (Section 2.1)"
  uv run python main.py >/tmp/server.log 2>&1 &
  SERVER_PID=$!
  sleep 3  # allow uvicorn to boot
  stop_spinner "Starting local server (Section 2.1)"
}

verify_endpoints() {
  local base_url="http://localhost:8000"

  start_spinner "Checking /healthz (Section 2.2)"
  if curl -sSf "$base_url/healthz" >/tmp/healthz.log 2>&1; then
    stop_spinner "Checking /healthz (Section 2.2)"
  else
    stop_spinner "Checking /healthz (Section 2.2)"
    echo "    /healthz check failed:"
    sed 's/^/      /' /tmp/healthz.log
  fi

  start_spinner "Checking /readyz (Section 2.2)"
  local ready_status=1
  for _ in {1..10}; do
    if curl -sSf "$base_url/readyz" >/tmp/readyz.log 2>&1; then
      ready_status=0
      break
    fi
    sleep 1
  done

  if [[ $ready_status -eq 0 ]]; then
    stop_spinner "Checking /readyz (Section 2.2)"
  else
    stop_spinner "Checking /readyz (Section 2.2)"
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

# ------------------------------- Entrypoint -------------------------------- #

main() {
  banner
  ensure_repo_root
  require_command uv
  require_command curl
  require_command jq

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
  echo "Local server is running at http://localhost:8000."
  echo "Backend: $SELECTED_BACKEND | Index: $VECTOR_STORE_PATH"
  echo "Streaming server logs from /tmp/server.log (press Enter to stop the server and continue...)"
  tail -f /tmp/server.log &
  TAIL_PID=$!
  read -r

  teardown_server

  cat <<EOF

✅ Completed Sections 1.1 – 2.2
  • Random test index generated ($INDEX_DIR_RANDOM)
  • Active backend: $SELECTED_BACKEND
  • Active index: $VECTOR_STORE_PATH
  • Local server launched with generated index
  • /healthz and /readyz probed

Refer to developer/guides/data_and_testing_guide.md for subsequent steps.
EOF
}

trap teardown_server EXIT
main "$@"
