#!/usr/bin/env bash
# Production entry point for DataRobot Custom Applications.
# Builds the React frontend, installs Python deps, and serves FastAPI on :8080.
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

echo "Installing Python dependencies…"
if command -v uv >/dev/null 2>&1; then
  uv pip install -r requirements.txt --system 2>/dev/null || uv pip install -r requirements.txt
else
  pip install -r requirements.txt
fi

echo "Building React frontend…"
(
  cd frontend
  if [[ ! -d node_modules ]]; then
    npm ci --no-audit --no-fund
  fi
  npm run build
)

# Worker count for uvicorn (same heuristic as af-component-fastapi-backend)
if [[ -f /sys/fs/cgroup/cpu.max ]] && ! grep -q "max" /sys/fs/cgroup/cpu.max; then
  read -r max period < /sys/fs/cgroup/cpu.max
  workers=$((max / period))
else
  workers=$(nproc 2>/dev/null || echo 2)
fi
workers=$((workers * 2 + 1))
if [[ $workers -lt 2 ]]; then
  workers=2
fi

echo "Starting explainability API with ${workers} workers on :8080…"
cd backend
if command -v uv >/dev/null 2>&1; then
  exec uv run uvicorn main:app \
    --workers "$workers" \
    --host 0.0.0.0 \
    --port 8080 \
    --proxy-headers \
    --timeout-keep-alive 300
else
  exec uvicorn main:app \
    --workers "$workers" \
    --host 0.0.0.0 \
    --port 8080 \
    --proxy-headers \
    --timeout-keep-alive 300
fi
