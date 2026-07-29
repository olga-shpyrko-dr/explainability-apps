#!/usr/bin/env bash
# Recommended way to test in a DataRobot Codespace.
# Builds the frontend once, then serves API + static UI on a single port (:8080).
# Open the port-8080 link in the Codespace UI — no Vite sub-path issues.
#
# Keep this terminal open while testing — closing it stops the server.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
elif [[ -f backend/.env ]]; then
  set -a
  # shellcheck disable=SC1091
  source backend/.env
  set +a
fi

chmod +x build-app.sh
./build-app.sh

if [[ ! -d frontend/dist ]]; then
  echo "ERROR: frontend/dist missing after build." >&2
  exit 1
fi

echo ""
echo "Installing Python dependencies…"
if [[ -x .venv/bin/pip ]]; then
  .venv/bin/pip install -q -r requirements.txt
elif command -v uv >/dev/null 2>&1; then
  uv pip install -r requirements.txt
else
  python3 -m pip install -q -r requirements.txt
fi

echo ""
echo "Starting backend on 0.0.0.0:8080 (API + built frontend)…"
echo "Wait until you see:  Uvicorn running on http://0.0.0.0:8080"
echo "Then open the port-8080 link in the Codespace UI."
echo "Keep this terminal open — closing it stops the server."
echo ""

cd backend
if [[ -x ../.venv/bin/uvicorn ]]; then
  exec ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8080 --reload
fi
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
