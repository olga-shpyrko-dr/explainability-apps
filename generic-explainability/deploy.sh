#!/usr/bin/env bash
# Build frontend, verify bundle prerequisites, then deploy to DataRobot.
set -euo pipefail
cd "$(dirname "$0")"

chmod +x build-app.sh start-app.sh

echo "=== Building frontend ==="
./build-app.sh

if [[ ! -f frontend/dist/index.html ]]; then
  echo "ERROR: frontend/dist/index.html missing after build." >&2
  exit 1
fi

echo "=== Validating Python entrypoint ==="
python3 -c "import ast; ast.parse(open('backend/main.py').read())"

echo "=== Deploying to DataRobot ==="
# Allow long first-start (pip install in image + container boot + health probe).
export DATAROBOT_TIMEOUT_MINUTES="${DATAROBOT_TIMEOUT_MINUTES:-60}"
export PULUMI_SKIP_UPDATE_CHECK="${PULUMI_SKIP_UPDATE_CHECK:-1}"
echo "DATAROBOT_TIMEOUT_MINUTES=${DATAROBOT_TIMEOUT_MINUTES}"
dr run deploy
