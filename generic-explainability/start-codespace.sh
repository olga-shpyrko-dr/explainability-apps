#!/usr/bin/env bash
# Recommended way to test in a DataRobot Codespace.
# Builds the frontend once, then serves API + static UI on one port.
#
# NOTE: Port 8080 is reserved for Custom Application containers on DataRobot.
# The notebook-session port proxy often blocks 8080 even when uvicorn is running
# on 0.0.0.0:8080. Default to 8501 instead (override with APP_PORT=...).
#
# Keep this terminal open while testing — closing it stops the server.
set -euo pipefail
cd "$(dirname "$0")"

APP_PORT="${APP_PORT:-8501}"

# Preserve a platform-injected DATAROBOT_API_TOKEN (Codespaces auto-inject it) so
# an empty placeholder line in a copied .env.template can't silently blank it out.
_injected_token="${DATAROBOT_API_TOKEN:-}"

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

if [[ -z "${DATAROBOT_API_TOKEN:-}" && -n "$_injected_token" ]]; then
  export DATAROBOT_API_TOKEN="$_injected_token"
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
  .venv/bin/pip install -q -r requirements-runtime.txt
  [[ -f requirements-llm.txt ]] && .venv/bin/pip install -q -r requirements-llm.txt
elif command -v uv >/dev/null 2>&1; then
  uv pip install -r requirements.txt
  uv pip install -r requirements-runtime.txt
  [[ -f requirements-llm.txt ]] && uv pip install -r requirements-llm.txt
else
  python3 -m pip install -q -r requirements.txt
  python3 -m pip install -q -r requirements-runtime.txt
  [[ -f requirements-llm.txt ]] && python3 -m pip install -q -r requirements-llm.txt
fi

echo ""
echo "Starting backend on 0.0.0.0:${APP_PORT} (API + built frontend)…"
echo "Wait until you see:  Uvicorn running on http://0.0.0.0:${APP_PORT}"
echo "Then open the port-${APP_PORT} link in the Codespace sidebar (Ports panel)."
echo "Do NOT use the port-8080 link — DR blocks it at the notebook proxy layer."
echo "Keep this terminal open — closing it stops the server."
echo ""

cd backend
if [[ -x ../.venv/bin/uvicorn ]]; then
  exec ../.venv/bin/uvicorn boot:app --host 0.0.0.0 --port "${APP_PORT}"
fi
exec python3 -m uvicorn boot:app --host 0.0.0.0 --port "${APP_PORT}"
