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
   ./build-app.sh
   ```

4. Configure **all** app parameters interactively:

   ```bash
   dr dotenv setup
   ```

   Prompts come from:
   - `.datarobot/cli/base.yml` — Pulumi passphrase, default use case, OTEL
   - `.datarobot/cli/explainability-app.yaml` — scoring, columns, LLM, metadata
   - `.env.template` — variable discovery for `dr dotenv validate`

5. Deploy:

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

### "Custom Application is not ready: application failed to create"

1. **Test startup locally in the Codespace** (fastest way to see the real error):

   ```bash
   ./build-app.sh
   bash -x ./start-app.sh
   ```

2. **Check Custom Application logs** in DataRobot UI:
   Registry → Custom Applications → your app → **Logs**

3. **Common causes:**
   - `frontend/dist` missing → run `./build-app.sh` before `dr run deploy`
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
