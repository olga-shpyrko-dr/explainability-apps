#!/usr/bin/env bash
# Build the React frontend before `dr run deploy`.
# The Custom Application container is Python-only — it cannot run npm.
set -euo pipefail
cd "$(dirname "$0")/frontend"

if [[ ! -f package-lock.json ]]; then
  echo "ERROR: package-lock.json missing — run 'npm install' in frontend/ first." >&2
  exit 1
fi

echo "Installing frontend dependencies…"
npm ci --no-audit --no-fund

echo "Building frontend…"
npm run build

echo "Done — frontend/dist is ready to bundle."
