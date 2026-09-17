# Generic Explainability App

A DataRobot-hosted app that turns row-level SHAP prediction explanations into
business-readable insight: filter the scored population into cohorts, see
SHAP impact rolled up into named feature groups, and generate an AI narrative
explaining what's driving a cohort's predicted score.

Works with any DataRobot binary classification or regression deployment that
has SHAP prediction explanations enabled — nothing domain-specific is
hardcoded; a deployment is adapted via the three JSON files in `backend/`.

For the full write-up (architecture, API reference, config schema,
compatibility matrix) see [`docs/README.md`](docs/README.md).

## What's included

| Path | What it is |
|---|---|
| `backend/` | FastAPI app — data pipeline, cohort/SHAP aggregation, LLM narrative |
| `frontend/` | React + Vite UI (cohort filters, group SHAP chart, waterfall, narrative panel) |
| `data/` | Example scoring/training CSVs — motor claim fraud (classification) and manufacturing RUL (regression) |
| `manufacturing_rul_source/` | Full source data + scripts to retrain the manufacturing RUL model and regenerate its subsamples in `data/` |
| `infra/` | Pulumi module wiring env vars into a DataRobot Custom Application |
| `scripts/` | Helpers for building a scoring dataset and warming the local cache |
| `docs/` | Full README, spec, and codespace deployment guide |

## Running it

**Inside a DataRobot Codespace (recommended for testing):**

```bash
cp backend/.env.template backend/.env   # fill in DEPLOYMENT_ID, SCORING_DATASET_ID, etc.
./start-codespace.sh
```

Runs as a local test process within the Codespace session — builds the
frontend once, then serves API + UI together on one port (`$APP_PORT`,
default `8501`). This is not yet a persistent deployment; see below for that.

**Custom Application deployment:**

```bash
uvx copier copy https://github.com/datarobot-community/af-component-base .
dr dotenv setup && dr dotenv validate
./deploy.sh
```

`deploy.sh` builds the frontend, sanity-checks the backend, then runs
`dr run deploy`.

See [`docs/codespaces-guide.md`](docs/codespaces-guide.md) for the detailed
step-by-step version of both paths.

## Example configurations

The app ships with one **active** config at a time (`backend/.env` plus the
three JSON files in `backend/`). Two ready-made examples are included as
`-example` reference files you copy over the active ones — no code changes
required. Full details, data provenance, and a known-limitation writeup are
in [`docs/examples.md`](docs/examples.md).

| Example | Target type | Files |
|---|---|---|
| Motor claim fraud detection | Binary classification | `backend/.env.fraud-example` |
| Manufacturing — Remaining Useful Life (RUL) | Regression (numeric target) | `backend/.env.manufacturing-example` + matching `feature_group_mapping` / `profile_config` / `narrative_config` `.manufacturing-example.json` files |

### Manufacturing — Remaining Useful Life (RUL)

Predictive-maintenance use case: predicts **`rul_days`**, the number of days
until a piece of heavy equipment (synthetic Caterpillar-style fleet —
excavators, dozers, mining trucks, engines) fails, from its sensor telemetry
(oil pressure, coolant temp, vibration, hydraulic pressure, etc.).

The model is a fresh Quick-Autopilot regression project trained on a 30k-row
sample of synthetic telemetry. See
[`manufacturing_rul_source/`](manufacturing_rul_source/README.md) to retrain
it or regenerate the subsamples:

- **Project**: `6a7488275a589c879326e74d`
- **Model**: `6a748a955bd1af802e86f383` — LightGBM Regressor w/ Early Stopping, validation RMSE 4.09 (target range 0–30 days)
- **Deployment**: `6a748b20ddc31eeea5d9c1a1`

The bundled `data/manufacturing_rul_scoring_sample.csv` (1,657 rows) is
already scored with real SHAP prediction explanations, so this example runs
fully self-contained in CSV mode — no live DataRobot connection needed.

**Run it locally:**

```bash
# 1. Activate the example config (overwrites the currently-active config)
cp backend/.env.manufacturing-example backend/.env
cp backend/feature_group_mapping.manufacturing-example.json backend/feature_group_mapping.json
cp backend/profile_config.manufacturing-example.json backend/profile_config.json
cp backend/narrative_config.manufacturing-example.json backend/narrative_config.json

# 2. Backend (terminal 1) — must run from inside backend/, since CSV_PATH
#    in the .env is relative to it (see docs/examples.md for why)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-runtime.txt
cd backend && uvicorn main:app --reload --port 8000

# 3. Frontend (terminal 2)
cd frontend
npm install   # first time only
VITE_API_URL=http://localhost:8000/ npm run dev
```

Open the printed Vite URL (typically `http://localhost:5173`). No LLM
provider is configured by default, so everything works except the "AI
Summary" narrative — uncomment one provider in `backend/.env` to enable it.

To switch back to the fraud example afterward:

```bash
cp backend/.env.fraud-example backend/.env
git checkout -- backend/feature_group_mapping.json backend/profile_config.json backend/narrative_config.json
```
