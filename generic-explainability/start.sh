#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "Tip: In a DataRobot Codespace, prefer ./start-codespace.sh (single port :8080, no Vite proxy issues)."
echo ""

# Backend
echo "Starting backend on :8000…"
cd backend
../.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ..

# Frontend
echo "Starting frontend on :5173…"
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo "Backend PID: $BACKEND_PID   Frontend PID: $FRONTEND_PID"
if [[ -n "${NOTEBOOK_ID:-}" ]]; then
  echo "Open: .../notebook-sessions/${NOTEBOOK_ID}/ports/5173/"
else
  echo "Open: http://localhost:5173"
fi

wait
