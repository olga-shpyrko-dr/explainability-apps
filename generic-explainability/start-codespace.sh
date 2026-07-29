#!/usr/bin/env bash
# Recommended way to test in a DataRobot Codespace.
# Builds the frontend once, then serves API + static UI on a single port (:8080).
# Open the port-8080 link in the Codespace UI — no Vite sub-path issues.
set -euo pipefail
cd "$(dirname "$0")"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

chmod +x build-app.sh
./build-app.sh

echo ""
echo "Starting backend on :8080 (API + built frontend)…"
echo "In the Codespace UI, open the forwarded link for port 8080."
echo ""

cd backend
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8080 --reload
