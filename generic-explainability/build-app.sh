#!/usr/bin/env bash
# Build frontend and install Python deps into the application image.
# Sourced during Custom App Docker build: RUN . ./build-app.sh
# Also run locally before deploy: ./build-app.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
DIST="${ROOT}/frontend/dist/index.html"

if [[ ! -f "${DIST}" ]]; then
  cd "${ROOT}/frontend"
  if [[ ! -f package-lock.json ]]; then
    echo "ERROR: package-lock.json missing — run 'npm install' in frontend/ first." >&2
    exit 1
  fi
  echo "Installing frontend dependencies…"
  npm ci --no-audit --no-fund
  echo "Building frontend…"
  npm run build
else
  echo "frontend/dist already present — skipping frontend build."
fi

if [[ ! -f "${DIST}" ]]; then
  echo "ERROR: frontend/dist/index.html missing after build." >&2
  exit 1
fi

# Install Python deps during Docker image build so container startup does not
# spend minutes on pip install before the /health probe (af-component pattern).
if [[ -f "${ROOT}/requirements.txt" ]]; then
  echo "Installing Python dependencies into application image…"
  python3 -m pip install --no-cache-dir -r "${ROOT}/requirements.txt"
  if [[ -f "${ROOT}/requirements-llm.txt" ]]; then
    python3 -m pip install --no-cache-dir -r "${ROOT}/requirements-llm.txt"
  fi
fi

echo "Done — frontend/dist ready and Python deps installed."
