#!/usr/bin/env bash
# Run the DataRobot scoring pipeline locally, so repeated local restarts
# (uvicorn --reload, manual testing) skip re-running the batch prediction job.
#
# NOTE: this cache is excluded from the deploy bundle (see EXCLUDE_PATTERNS in
# infra/infra/explainability_app.py) so it does not affect deployed cold-start
# time — only local iteration speed.
#
# Populates backend/.prediction_dataset_cache.json + backend/.batch_output_cache.csv.
# pipeline.py only reuses that cache when DEPLOYMENT_ID / SCORING_DATASET_ID /
# ROW_ID_COL in .env match what generated it — rerun this after changing any
# of those, or after the scoring dataset's contents change even if its ID didn't.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"

if [[ -f "${ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/.env"
  set +a
fi

cd "${ROOT}/backend"
python3 -c "
from config import get_settings
from pipeline import build_tables

settings = get_settings()
scored_pop, expl_long, prediction_col = build_tables(settings)
print(f'scored_population={scored_pop.shape}  explanation_long={expl_long.shape}  prediction_col={prediction_col}')
"

echo "Cache populated — backend/.prediction_dataset_cache.json and backend/.batch_output_cache.csv are ready."
