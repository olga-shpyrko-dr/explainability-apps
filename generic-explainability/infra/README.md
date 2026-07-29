# App Framework infra — explainability Custom Application

This directory is consumed by the Pulumi project created when you scaffold with
`af-component-base`. The file `infra/explainability_app.py` is a **drop-in module**
that wires all explainability app environment variables into the Custom Application
as runtime parameters (not just the barebones Pulumi params from base).

## Setup

1. Scaffold App Framework base (one-time):

   ```bash
   cd generic-explainability
   uvx copier copy https://github.com/datarobot-community/af-component-base .
   ```

2. Copy or merge `infra/infra/explainability_app.py` into the generated
   `infra/infra/` package (this repo already includes the file — skip if present).

3. Build the frontend **before** deploying (the Custom App container is Python-only):

   ```bash
   ./deploy.sh
   ```

   Or manually: `./build-app.sh` then `dr run deploy`.

4. Configure **all** app parameters interactively:

   ```bash
   dr dotenv setup
   ```

   Prompts come from:
   - `.datarobot/cli/base.yml` — Pulumi passphrase, default use case, OTEL
   - `.datarobot/cli/explainability-app.yaml` — scoring, columns, LLM, metadata
   - `.env.template` — variable discovery for `dr dotenv validate`

5. Deploy (if you did not use `./deploy.sh` in step 3):

   ```bash
   dr run deploy
   ```

## Required variables (datarobot mode)

| Variable | Required | Notes |
|----------|----------|-------|
| `DATAROBOT_API_TOKEN` | yes | Auto-filled when `dr auth login` is active |
| `DATAROBOT_ENDPOINT` | yes | Region-specific API URL |
| `SCORING_DATASET_ID` | yes | AI Catalog dataset to score |
| `ROW_ID_COL` | yes | Unique row ID column in the dataset |
| `DEPLOYMENT_ID` | recommended | Preferred batch-prediction path |
| `PROJECT_ID` + `MODEL_ID` | fallback | Only when `DEPLOYMENT_ID` is unset |
| `DR_GATEWAY_MODEL` | recommended | At least one LLM provider for AI narrative |

See `.datarobot/cli/explainability-app.yaml` for the full list and help text.

## Troubleshooting deploy failures

### Pulumi fails but UI shows "Initializing…"

The first deploy can take **5–10 minutes** (Docker image build + pip install + container
boot). Pulumi may report failure while DataRobot is still starting the app in the
background.

1. **Wait** — refresh **Registry → Applications**; status should move from
   `Initializing` → `Running`.
2. **Open the app URL** once Running (batch scoring then takes another 2–5 min on first load).
3. **Sync Pulumi** after the app is Running:

   ```bash
   export DATAROBOT_TIMEOUT_MINUTES=60
   dr run infra:refresh -- -y
   ```

4. **Redeploy with longer timeout** (included in `./deploy.sh`):

   ```bash
   export DATAROBOT_TIMEOUT_MINUTES=60
   ./deploy.sh
   ```

### "Custom Application is not ready: application failed to create"

The platform health probe must get HTTP 200 from `/health` within ~2–3 minutes.
Heavy imports (pandas, datarobot) used to block uvicorn from binding in time.

**Fix:** `start-app.sh` runs `uvicorn boot:app` — a lightweight probe server that
responds on `/health` immediately while `main.py` loads in the background.

1. **Test startup locally in the Codespace** (fastest way to see the real error):

   ```bash
   ./build-app.sh
   bash -x ./start-app.sh
   ```

2. **Check Custom Application logs** in DataRobot UI:
   Registry → Custom Applications → your app → **Logs**

3. **Common causes:**
   - `frontend/dist` missing → run `./deploy.sh` (builds frontend then deploys)
   - Redundant `pip install` in `start-app.sh` → removed; platform installs `requirements.txt`
   - `pyodbc` / SQL deps in `requirements.txt` → use lean `requirements.txt` only
   - Missing env vars → run `dr dotenv validate`

4. **Refresh a stuck stack:**

   ```bash
   dr run infra:refresh -- -y
   dr run deploy
   ```

## Keeping prompts in sync

When adding a new field to `backend/config.py`:

1. Add it to `backend/.env.template` and root `.env.template`
2. Add a prompt entry to `.datarobot/cli/explainability-app.yaml`
3. Add the env var name to `STRING_RUNTIME_ENV_VARS` or `SECRET_RUNTIME_ENV_VARS`
   in `infra/infra/explainability_app.py`

Then re-run `dr dotenv setup` and `dr run deploy`.
