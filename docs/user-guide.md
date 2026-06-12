# IL Protection Lapse Explainability App — User Guide

**JUNE 2026 · INTERNAL**

Python Backend & React Frontend

---

## 1. Architecture Overview

The application is a two-tier stack: a Python FastAPI backend that fetches live data from DataRobot at startup, and a lightweight React + Vite frontend that consumes its REST API.

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Python 3.11 · FastAPI · DataRobot SDK | Data pipeline, SHAP aggregation, LLM narrative, REST API |
| Frontend | React 18 · Vite · Recharts · TypeScript | Cohort filter sidebar, group chart, policy look-up, narrative UI |
| DataRobot | DataRobot EU (app.eu.datarobot.com) | Prediction Explanations source, LLM Gateway |
| SQL export | SQLAlchemy · pyodbc · SQL Server | Power BI flat-table export (optional) |

On startup the backend uploads the scoring dataset to the project, requests predictions, initialises Prediction Explanations, and loads the results into memory. A local cache (`.prediction_dataset_cache.json`) skips the upload step on subsequent restarts.

---

## 2. Prerequisites

### 2.1 Python environment

- Python 3.11 or later
- `pip install -r requirements.txt` (from project root)
- ODBC Driver 17 for SQL Server — only required for the SQL export script

### 2.2 DataRobot access

- DataRobot EU account with access to project `6a22f2218f74af009899ddb1`
- API token with read access to Projects, Datasets, Deployments, and LLM Gateway
- The scoring dataset (`6a2275eb326d5530a77a0b30`) must be in the AI Catalog

### 2.3 Node.js (frontend only)

- Node.js 18 or later and npm

---

## 3. Configuration

Copy `.env.example` to `.env` in the project root and fill in the required values. The backend reads this file via pydantic-settings; all keys are case-insensitive.

### 3.1 Required keys

| Key | Example value | Description |
|---|---|---|
| `DATAROBOT_API_TOKEN` | `abc123…` | DataRobot personal API token |
| `DATAROBOT_ENDPOINT` | `https://app.eu.datarobot.com/api/v2` | DataRobot EU REST endpoint |

### 3.2 Optional keys

| Key | Example value | Description |
|---|---|---|
| `DR_GATEWAY_MODEL` | `azure/gpt-4o-mini` | LLM Gateway model ID (see Section 5) |
| `DR_LLM_DEPLOYMENT_ID` | `<deployment id>` | DataRobot deployed TextGen model |
| `AZURE_OPENAI_API_KEY` | `<key>` | Azure OpenAI key |
| `AZURE_OPENAI_API_BASE` | `https://….openai.azure.com/` | Azure OpenAI endpoint |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | `gpt-4o` | Azure deployment name |
| `ANTHROPIC_API_KEY` | `<key>` | Anthropic direct API key |
| `SQL_CONNECTION_STRING` | `mssql+pyodbc://…` | SQL Server connection (export only) |
| `TRAINING_EXCEL_PATH` | `data/Training.xlsx` | Adds `Lapse_ind` labels to export |

---

## 4. Starting the Application

### 4.1 Backend

From the project root:

```bash
cd backend
source ../.venv/bin/activate        # or .venv\Scripts\activate on Windows
uvicorn main:app --reload --port 8000
```

> **First startup** takes 2–5 minutes while the prediction dataset is uploaded and Prediction Explanations are computed. Progress is logged to the terminal. Subsequent starts are fast — the dataset ID is cached in `.prediction_dataset_cache.json`.

### 4.2 Frontend

```bash
cd frontend
npm install       # first time only
npm run dev
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

### 4.3 Health check

```bash
curl http://localhost:8000/api/health
```

A successful response includes `rows_loaded` (~6,668), `explanation_rows` (~26,672), and sample row IDs.

---

## 5. LLM Narrative Configuration

The **AI Narrative** tab supports four LLM providers. Configure at least one to enable narrative generation. The app detects which providers have credentials and shows only those as selectable options.

| Provider | Required `.env` keys | Notes |
|---|---|---|
| DR LLM Gateway | `DR_GATEWAY_MODEL` | Recommended. Uses your DataRobot API token — no extra credentials needed. |
| DR Deployed LLM | `DR_LLM_DEPLOYMENT_ID` | Calls a deployed TextGen model via its chat completions endpoint. |
| Azure OpenAI | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_BASE`, `AZURE_OPENAI_DEPLOYMENT_NAME` | Standard Azure OpenAI credentials. |
| Anthropic | `ANTHROPIC_API_KEY` | Direct Anthropic API. Model defaults to `claude-sonnet-4-6`. |

### 5.1 LLM Gateway model IDs

Set `DR_GATEWAY_MODEL` to the **Chat model ID** from the [DataRobot LLM Availability docs](https://docs.datarobot.com/en/docs/reference/gen-ai-ref/llm-availability.html). Examples:

- `azure/gpt-4o-mini`
- `azure/gpt-4o-2024-11-20`
- `anthropic/claude-sonnet-4-6`
- `vertex_ai/gemini-2.0-flash-001`
- `bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0`

> After changing `.env`, **restart the backend** — settings are cached at startup and a hot-reload is not sufficient.

---

## 6. API Endpoints

| Method + Path | Parameters | Returns |
|---|---|---|
| `GET /api/health` | — | Status, row counts, sample row IDs |
| `GET /api/columns` | — | All filterable columns with type, min/max, or distinct values |
| `GET /api/cohort` | `filters` (JSON string) | Cohort size, score distribution, histogram |
| `GET /api/groups` | `filters` (JSON string) | Group SHAP aggregations sorted by `|avg_shap|` |
| `GET /api/row/{row_id}` | — | SHAP explanation for one policy |
| `GET /api/llm/providers` | — | Configured LLM providers and which are available |
| `POST /api/narrative` | JSON body: `filters`, `provider`, `custom_instruction` | AI-generated narrative text |

### 6.1 Filter format

Filters are passed as a JSON string in the `filters` query parameter:

```json
// Range filter
{"Age_life1": {"min": 30, "max": 50}}

// Multi-select filter
{"Product_Desc": ["Block Life Term Cover", "Whole of Life"]}

// Combined
{"Decile": {"min": 8, "max": 10}, "SmokerStatus": ["Y"]}
```

---

## 7. Feature Group Configuration

Feature-to-group assignments are stored in [`backend/feature_group_mapping.json`](../backend/feature_group_mapping.json). Edit this file to reassign features without touching any code. The backend reloads the mapping on restart.

### 7.1 Current groups

| Group | Representative features |
|---|---|
| Policy & Product | Product type, cover, premium, term, sum assured |
| Policy Portfolio | Number and value of policies across lives |
| Agent / Adviser | Servicing agent, source of business, commission |
| Sociodemographic | Age, gender, smoker status, occupation, family status |
| Financial Profile | Income, debt, net worth, credit score, monthly expenditure |
| Engagement & Reviews | Logins, review type, months since last review |
| Persona | Persona segment labels |

### 7.2 Moving a feature

Open `backend/feature_group_mapping.json` and move the feature name string to the target group's array. Restart the backend.

---

## 8. SQL Server Export (Power BI Path)

`scripts/export_to_sql.py` pulls the same data as the backend and writes three tables to SQL Server for use in Power BI.

### 8.1 Setup

Add `SQL_CONNECTION_STRING` to `.env`:

```bash
# SQL auth
SQL_CONNECTION_STRING=mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+17+for+SQL+Server

# Windows auth
SQL_CONNECTION_STRING=mssql+pyodbc://@server/db?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes
```

### 8.2 Running the export

```bash
# First run — create tables
python scripts/export_to_sql.py --replace

# Include training labels (Lapse_ind)
python scripts/export_to_sql.py --replace --training-excel data/Training.xlsx
```

### 8.3 Output tables

| Table | Contents |
|---|---|
| `explainability_scored_population` | All source features + prediction score (~6,668 rows) |
| `explainability_explanation_long` | Unpivoted SHAP rows with group labels (~26,672 rows) |
| `explainability_feature_group_mapping` | Feature → group lookup (83 rows) |

### 8.4 Power BI setup

1. Connect to SQL Server (Import or DirectQuery)
2. Load all three tables
3. Create relationship: `scored_population[Policy_Number]` → `explanation_long[row_id]` (1 : many)
4. Add DAX measure:
   ```
   Avg Group SHAP = AVERAGEX(RELATEDTABLE(explanation_long), explanation_long[shap_strength])
   ```
5. Add slicers on: `Decile`, `Product_Desc`, `Age_life1`, `SmokerStatus`, `feature_group`

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| Startup takes > 10 min | Check that `.prediction_dataset_cache.json` exists. If missing, the full PE pipeline reruns. Delete the cache only if the scoring dataset has changed. |
| No explanation data for cohort | Run `curl /api/health` and check `explanation_sample_row_ids` matches `population_sample_row_ids` format. A type mismatch causes the join to fail. |
| LLM narrative returns 500 | Check backend logs for the LiteLLM error. Most common causes: wrong `DR_GATEWAY_MODEL` format (must be `azure/gpt-4o-mini`, not `azure-openai/gpt-4o-mini`), or backend not restarted after `.env` change. |
| Frontend shows stale data | The backend caches data at startup. Restart uvicorn to pull fresh explanations from DataRobot. |
| SQL export fails with driver error | Install ODBC Driver 17 for SQL Server. On macOS: `brew install msodbcsql17`. |

---

## 10. Key File Reference

| File / Directory | Purpose |
|---|---|
| `.env` | Runtime secrets and configuration (not committed to git) |
| `backend/main.py` | FastAPI app, lifespan startup, all REST endpoints |
| `backend/pipeline.py` | DataRobot data pipeline: upload → predict → PE → load |
| `backend/cohort.py` | Filter engine, cohort profile stats, group SHAP aggregation |
| `backend/llm_client.py` | LiteLLM abstraction for all four LLM providers |
| `backend/narrative.py` | Prompt construction and LLM call for narrative generation |
| `backend/config.py` | pydantic-settings config model — all environment variables |
| `backend/feature_group_mapping.json` | Feature → group assignments (editable without code changes) |
| `backend/.prediction_dataset_cache.json` | Auto-generated PE dataset ID cache — delete to force re-upload |
| `frontend/src/components/` | React UI components: CohortFilter, GroupExplanationChart, WaterfallChart, NarrativePanel |
| `scripts/export_to_sql.py` | SQL Server export for Power BI consumption |
| `docs/` | This guide and the original app specification |
