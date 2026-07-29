#!/usr/bin/env bash
# Codespace testing via vite preview (two-process: backend :8000 + preview :5173).
# Serves built dist/ — avoids Vite dev-server path issues with the DR port proxy.
# For a single-port setup, use ./start-codespace.sh (:8080) instead.
set -euo pipefail
cd "$(dirname "$0")"

DEV_PORT="${VITE_DEV_PORT:-5173}"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

chmod +x build-app.sh
./build-app.sh

echo "Starting backend on :8000…"
cd backend
if [[ -x ../.venv/bin/uvicorn ]]; then
  ../.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
else
  python3 -m uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
fi
BACKEND_PID=$!
cd ..

echo "Starting vite preview on :${DEV_PORT}…"
echo "Open the port-${DEV_PORT} link in the Codespace UI."
cd frontend
npm run preview -- --host 0.0.0.0 --port "${DEV_PORT}" &
PREVIEW_PID=$!
cd ..

echo "Backend PID: $BACKEND_PID   Preview PID: $PREVIEW_PID"
wait
