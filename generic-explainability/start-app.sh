#!/usr/bin/env bash
# Production entry point for DataRobot Custom Applications.
# Frontend MUST be pre-built (./build-app.sh) before deploy.
# Python deps are installed automatically from requirements.txt by the platform.
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

if [[ ! -d frontend/dist ]]; then
  echo "ERROR: frontend/dist not found. Run ./build-app.sh before deploying." >&2
  exit 1
fi

echo "Installing Python dependencies…"
python3 -m pip install --quiet -r requirements.txt

echo "Starting explainability API on 0.0.0.0:8080…"
cd backend
exec python3 -m uvicorn main:app \
  --host 0.0.0.0 \
  --port 8080 \
  --proxy-headers \
  --timeout-keep-alive 300
