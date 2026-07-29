#!/usr/bin/env bash
# Build frontend and install Python deps into the application image.
# Sourced during Custom App Docker build: RUN . ./build-app.sh
# Also run locally before deploy: ./build-app.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
DIST="${ROOT}/frontend/dist/index.html"

chmod +x "${ROOT}/start-app.sh" "${ROOT}/build-app.sh" 2>/dev/null || true

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

if [[ ! -f "${ROOT}/backend/boot.py" ]]; then
  echo "ERROR: backend/boot.py missing — git pull the latest deploy fixes." >&2
  exit 1
fi

# Install ALL Python deps into the image (platform only installs lean requirements.txt).
for req in requirements.txt requirements-runtime.txt requirements-llm.txt; do
  if [[ -f "${ROOT}/${req}" ]]; then
    echo "Installing ${req} into application image…"
    python3 -m pip install --no-cache-dir -r "${ROOT}/${req}"
  fi
done

echo "Done — frontend/dist ready and Python deps installed."
