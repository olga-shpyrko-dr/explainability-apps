#!/usr/bin/env bash
# Production entry point for DataRobot Custom Applications.
# Frontend MUST be pre-built (./build-app.sh or ./deploy.sh) before deploy.
set -euo pipefail
cd "$(dirname "$0")"

# Local .env (Codespace); in Custom Apps runtime parameters are injected as env vars.
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

# Map MLOPS_RUNTIME_PARAM_* → app env vars (Custom Application convention).
_runtime_keys=(
  DATA_SOURCE CSV_PATH DATAROBOT_ENDPOINT
  DEPLOYMENT_ID PROJECT_ID MODEL_ID
  SCORING_DATASET_ID TRAINING_DATASET_ID DEFAULT_USE_CASE_ID
  ROW_ID_COL PREDICTION_COL OUTCOME_COL MAX_EXPLANATIONS
  APP_TITLE APP_SUBTITLE DATASET_DISPLAY_NAME
  DR_GATEWAY_MODEL DR_LLM_DEPLOYMENT_ID
  AZURE_OPENAI_API_BASE AZURE_OPENAI_API_VERSION AZURE_OPENAI_DEPLOYMENT_NAME
  ANTHROPIC_MODEL
)
for key in "${_runtime_keys[@]}"; do
  mlops_var="MLOPS_RUNTIME_PARAM_${key}"
  if [[ -n "${!mlops_var:-}" ]]; then
    export "${key}=${!mlops_var}"
  fi
done

if [[ ! -f frontend/dist/index.html ]]; then
  echo "ERROR: frontend/dist/index.html not found." >&2
  echo "Run ./build-app.sh (or ./deploy.sh) before dr run deploy." >&2
  exit 1
fi

_ensure_python_deps() {
  if python3 -c "import fastapi, uvicorn; from datarobot_asgi_middleware import DataRobotASGIMiddleware" 2>/dev/null; then
    return 0
  fi
  echo "WARNING: core Python imports failed — installing from requirements.txt…" >&2
  python3 -m pip install --no-cache-dir -r requirements.txt
  if [[ -f requirements-llm.txt ]]; then
    python3 -m pip install --no-cache-dir -r requirements-llm.txt
  fi
  python3 -c "import fastapi, uvicorn; from datarobot_asgi_middleware import DataRobotASGIMiddleware"
}

echo "Python $(python3 --version 2>&1)"
echo "Starting explainability API on 0.0.0.0:8080…"
export PYTHONUNBUFFERED=1

_ensure_python_deps || {
  echo "ERROR: Python imports failed — check Docker build log for pip install errors." >&2
  exit 1
}

cd backend
python3 -c "import main" || {
  echo "ERROR: failed to import backend/main.py:" >&2
  python3 -c "import traceback; traceback.print_exc()" 2>&1 || true
  exit 1
}

exec python3 -m uvicorn main:app \
  --host 0.0.0.0 \
  --port 8080 \
  --proxy-headers \
  --timeout-keep-alive 300
