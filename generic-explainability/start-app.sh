#!/usr/bin/env bash
# Production entry point for DataRobot Custom Applications.
# Frontend MUST be pre-built (./build-app.sh) before deploy — the Python
# Applications Base image does not include Node.js/npm.
set -euo pipefail
cd "$(dirname "$0")"

export UV_CACHE_DIR="${UV_CACHE_DIR:-.uv}"

# `dr dotenv setup` writes .env at the recipe root; backend/config.py also reads ../.env
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ ! -d frontend/dist ]]; then
  echo "ERROR: frontend/dist not found. Run ./build-app.sh before deploying." >&2
  exit 1
fi

echo "Installing Python dependencies…"
python3 -m pip install --quiet -r requirements.txt

echo "Starting explainability API on :8080 (single worker)…"
cd backend
exec python3 -m uvicorn main:app \
  --host 0.0.0.0 \
  --port 8080 \
  --proxy-headers \
  --timeout-keep-alive 300
