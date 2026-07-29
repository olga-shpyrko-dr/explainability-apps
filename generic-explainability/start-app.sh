#!/usr/bin/env bash
# Production entry point for DataRobot Custom Applications.
# Frontend MUST be pre-built (./build-app.sh or ./deploy.sh) before deploy.
set -euo pipefail
cd "$(dirname "$0")"

echo "=== start-app.sh ===" >&2
echo "PWD=$(pwd)" >&2
echo "Python: $(command -v python3) ($(python3 --version 2>&1))" >&2

# Local .env (Codespace); in Custom Apps runtime parameters are injected as env vars.
# Preserve a platform-injected DATAROBOT_API_TOKEN across the sourcing below so an
# empty placeholder line in a copied .env.template can't silently blank it out.
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

if [[ ! -f backend/boot.py ]]; then
  echo "ERROR: backend/boot.py not found — run 'git pull' for the latest deploy fixes." >&2
  exit 1
fi

export PYTHONUNBUFFERED=1
echo "Starting uvicorn boot:app on 0.0.0.0:8080…" >&2

cd backend
exec python3 -m uvicorn boot:app \
  --host 0.0.0.0 \
  --port 8080 \
  --proxy-headers \
  --timeout-keep-alive 300
