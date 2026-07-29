#!/usr/bin/env bash
# Build the React frontend before `dr run deploy`.
# Safe to source during the Custom App Docker build (RUN . ./build-app.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
DIST="${ROOT}/frontend/dist/index.html"

if [[ -f "${DIST}" ]]; then
  echo "frontend/dist already present — skipping build."
  exit 0
fi

cd "${ROOT}/frontend"

if [[ ! -f package-lock.json ]]; then
  echo "ERROR: package-lock.json missing — run 'npm install' in frontend/ first." >&2
  exit 1
fi

echo "Installing frontend dependencies…"
npm ci --no-audit --no-fund

echo "Building frontend…"
npm run build

echo "Done — frontend/dist is ready to bundle."
