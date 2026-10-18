#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/.venv/bin/python"

if [[ ! -x "$PYTHON" ]]; then
    echo "Missing Python environment: $PYTHON" >&2
    exit 1
fi

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

wait_for_url() {
    local url="$1"
    for _ in {1..50}; do
        if curl --fail --silent --show-error "$url" >/dev/null; then
            return
        fi
        sleep 0.2
    done
    echo "Server did not become ready: $url" >&2
    exit 1
}

# Restart both local services together so the dashboard never points at a
# stale backend process.
stop_listener 8010
stop_listener 8000

(cd "$ROOT/backend" && exec "$PYTHON" -m uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1) \
    >/tmp/exectuthon26-fastapi.log 2>&1 &
backend_pid=$!

(cd "$ROOT/hardware/live_ui" && exec "$PYTHON" dashboard_server.py) \
    >/tmp/exectuthon26-dashboard.log 2>&1 &
dashboard_pid=$!

wait_for_url http://127.0.0.1:8000/health
wait_for_url http://127.0.0.1:8010/

echo "FastAPI:  http://127.0.0.1:8000 (pid $backend_pid)"
echo "Dashboard: http://127.0.0.1:8010 (pid $dashboard_pid)"
