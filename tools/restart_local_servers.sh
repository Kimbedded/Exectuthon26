#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"
READINESS_TIMEOUT="${READINESS_TIMEOUT:-60}"
READINESS_INTERVAL="${READINESS_INTERVAL:-0.5}"

if [[ ! -x "$PYTHON" ]]; then
    echo "Missing Python environment: $PYTHON" >&2
    exit 1
fi

backend_pid=""
dashboard_pid=""

stop_listener() {
    local port="$1"
    local pids
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN || true)"
    if [[ -z "$pids" ]]; then
        return
    fi

    echo "Stopping port $port: $pids"
    kill $pids
    for _ in {1..50}; do
        if ! lsof -tiTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
            return
        fi
        sleep 0.1
    done
    echo "Timed out stopping port $port" >&2
    exit 1
}

http_get() {
    local url="$1"
    local response

    response="$(curl --silent --show-error --max-time 3 \
        --write-out $'\n%{http_code}' "$url" 2>/dev/null || true)"
    HTTP_BODY="${response%$'\n'*}"
    HTTP_STATUS="${response##*$'\n'}"
}

state_is_ready() {
    "$PYTHON" -c '
import json
import sys

try:
    state = json.loads(sys.stdin.read())
except (TypeError, ValueError):
    raise SystemExit(1)

allowed_statuses = {"idle", "starting", "recording", "ready", "clarifying"}
ready = (
    state.get("model_status") == "ready"
    and state.get("status") in allowed_statuses
    and not state.get("error")
)
raise SystemExit(0 if ready else 1)
' <<<"$1"
}

wait_for_backend() {
    local deadline=$((SECONDS + READINESS_TIMEOUT))
    local body=""

    while (( SECONDS < deadline )); do
        http_get "http://127.0.0.1:8000/health"
        body="$HTTP_BODY"
        if [[ "$HTTP_STATUS" == "200" ]] && "$PYTHON" -c '
import json
import sys
try:
    ok = json.load(sys.stdin).get("status") == "ok"
except (TypeError, ValueError):
    ok = False
raise SystemExit(0 if ok else 1)
' <<<"$body"; then
            return 0
        fi
        sleep "$READINESS_INTERVAL"
    done

    echo "FastAPI readiness failed: GET /health did not return HTTP 200 with {\"status\":\"ok\"} within ${READINESS_TIMEOUT}s." >&2
    [[ -n "$body" ]] && echo "Last /health response: $body" >&2
    return 1
}

wait_for_dashboard() {
    local deadline=$((SECONDS + READINESS_TIMEOUT))
    local root_body=""
    local state_body=""

    while (( SECONDS < deadline )); do
        http_get "http://127.0.0.1:8010/"
        root_body="$HTTP_BODY"
        local root_status="$HTTP_STATUS"

        http_get "http://127.0.0.1:8010/api/state"
        state_body="$HTTP_BODY"
        local state_status="$HTTP_STATUS"

        if [[ "$root_status" == "200" ]] &&
            grep -Fq '<title>IDK Button · Live</title>' <<<"$root_body" &&
            [[ "$state_status" == "200" ]] &&
            state_is_ready "$state_body"; then
            return 0
        fi
        sleep "$READINESS_INTERVAL"
    done

    if [[ "$root_status" == "200" ]] && [[ "$state_status" == "200" ]]; then
        echo "Dashboard HTTP is healthy, but application readiness failed: model initialization did not complete within ${READINESS_TIMEOUT}s." >&2
        "$PYTHON" -c '
import json
import sys
try:
    state = json.load(sys.stdin)
except (TypeError, ValueError):
    print("Last /api/state response was not valid JSON.", file=sys.stderr)
else:
    print("Dashboard state: status=%r stage=%r model_status=%r error=%r" % (
        state.get("status"), state.get("stage"), state.get("model_status"),
        state.get("error")), file=sys.stderr)
    if state.get("error"):
        print("The dashboard web server is up, but its internal model/board initialization is not ready.", file=sys.stderr)
' <<<"$state_body"
        if curl --fail --silent --show-error --max-time 3 \
            http://127.0.0.1:18181/v1/models >/dev/null 2>&1; then
            echo "Board model endpoint 127.0.0.1:18181 responds; inspect the dashboard error above (this is separate from HTTP server readiness)." >&2
        else
            echo "Board model endpoint 127.0.0.1:18181 is unavailable or refused the connection." >&2
        fi
    else
        echo "Dashboard readiness failed: / returned HTTP $root_status and /api/state returned HTTP $state_status." >&2
        [[ -n "$state_body" ]] && echo "Last /api/state response: $state_body" >&2
    fi
    return 1
}

cleanup_on_failure() {
    if [[ "$?" -ne 0 ]]; then
        [[ -n "$dashboard_pid" ]] && kill "$dashboard_pid" 2>/dev/null || true
        [[ -n "$backend_pid" ]] && kill "$backend_pid" 2>/dev/null || true
        echo "Local server restart failed; newly started processes were stopped." >&2
    fi
}
trap cleanup_on_failure EXIT

# Restart both local services together so the dashboard never points at a
# stale backend process.
stop_listener 8010
stop_listener 8000

(cd "$ROOT/backend" && exec "$PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1) \
    >/tmp/exectuthon26-fastapi.log 2>&1 &
backend_pid=$!

wait_for_backend

(cd "$ROOT/hardware/live_ui" && exec "$PYTHON" dashboard_server.py) \
    >/tmp/exectuthon26-dashboard.log 2>&1 &
dashboard_pid=$!

wait_for_dashboard

echo "FastAPI:  http://127.0.0.1:8000 (pid $backend_pid)"
echo "Dashboard: http://127.0.0.1:8010 (pid $dashboard_pid)"
echo "Readiness: /health, /, and /api/state passed; dashboard model_status=ready"
