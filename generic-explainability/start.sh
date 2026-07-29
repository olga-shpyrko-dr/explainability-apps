#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

DEV_PORT="${VITE_DEV_PORT:-5173}"

# ---------------------------------------------------------------------------
# Vite dev through DR port proxy REQUIRES the notebook session base path.
# Without NOTEBOOK_ID, modules 404 at app.*.datarobot.com/src/... (blank page).
# ---------------------------------------------------------------------------
if [[ -z "${NOTEBOOK_ID:-}" ]]; then
  for candidate in /etc/datarobot/notebook_id /run/datarobot/notebook_id; do
    if [[ -f "$candidate" ]]; then
      NOTEBOOK_ID="$(tr -d '[:space:]' < "$candidate")"
      break
    fi
  done
fi
export NOTEBOOK_ID

if [[ -n "${NOTEBOOK_ID:-}" ]]; then
  export VITE_DEV_BASE="/notebook-sessions/${NOTEBOOK_ID}/ports/${DEV_PORT}/"
  echo "Codespace detected — Vite base: ${VITE_DEV_BASE}"
else
  echo ""
  echo "WARNING: NOTEBOOK_ID is not set."
  echo "  Vite dev will show a BLANK PAGE through the DR port-5173 link."
  echo "  Recommended: ./start-codespace.sh  (single port :8080, always works)"
  echo ""
  echo "  Or set NOTEBOOK_ID from your browser URL, then restart:"
  echo "    export NOTEBOOK_ID=6a69b27ea228f57f1b3012aa   # example from .../notebook-sessions/THIS_ID/ports/5173/"
  echo ""
fi

# Backend
echo "Starting backend on :8000…"
cd backend
../.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Frontend
echo "Starting frontend on :${DEV_PORT}…"
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo "Backend PID: $BACKEND_PID   Frontend PID: $FRONTEND_PID"
if [[ -n "${NOTEBOOK_ID:-}" ]]; then
  echo "Open: .../notebook-sessions/${NOTEBOOK_ID}/ports/${DEV_PORT}/"
else
  echo "Open: http://localhost:${DEV_PORT}  (only works in-terminal, not via DR port link)"
fi

wait
