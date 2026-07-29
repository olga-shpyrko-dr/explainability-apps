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
dr run deploy
