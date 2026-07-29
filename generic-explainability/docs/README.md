# Generic Explainability App

A DataRobot-hosted application that transforms raw SHAP prediction explanations into actionable, business-readable insights. It works with any DataRobot binary classification deployment that has SHAP prediction explanations enabled.

---

## The problem it solves

DataRobot generates row-level SHAP prediction explanations for every model it builds. In practice, these are hard to act on:

- Models with many features spread signal across dozens of correlated features, obscuring the dominant business drivers.
- While DataRobot's modeling experiments support sliced insights, there is no equivalent mechanism in production deployments — scored rows cannot be grouped or filtered into cohorts out of the box.
- Business users (advisers, underwriters, retention teams) need plain-language insight into *why* a segment is high-risk, not a raw list of feature names and SHAP scores.

---

## What the app does

The app adds three layers on top of standard DataRobot prediction outputs:

| Module | Description |
|---|---|
| **Cohort filter & profile** | Filter the scored population by any feature combination; inspect score distribution and key field breakdowns for the selected segment vs. the full population |
| **Grouped explanations** | Aggregate SHAP values by named business-domain feature groups (e.g. "Agent Behaviour", "Claim Details"); surface combined group impact with drill-down to individual features |
| **AI narrative** | Generate a natural language summary of the cohort's profile and the drivers of their predictions via a configurable LLM provider |

SHAP additivity is exploited throughout: because `prediction = base_value + Σ SHAP_i + remaining`, group-level SHAP sums are mathematically valid probability-scale contributions, not approximations.

---

## Repository structure

```
generic-explainability/
├── backend/
│   ├── main.py                    # FastAPI app — API endpoints + startup pipeline
│   ├── pipeline.py                # Data acquisition: batch prediction via DR deployment
│   ├── cohort.py                  # Filter engine, profile stats, group SHAP aggregation
│   ├── narrative.py               # LLM prompt builder + narrative generation
│   ├── llm_client.py              # Unified LLM client (LiteLLM abstraction)
│   ├── config.py                  # Settings (pydantic-settings, .env / dr dotenv)
│   ├── config_loader.py           # Domain config loader
│   ├── feature_group_mapping.json # Feature → business group mapping (edit per use case)
│   ├── profile_config.json        # Filter panel columns and score display config
│   ├── narrative_config.json      # Entity labels, score labels, LLM prompt overrides
│   ├── create_scoring_sample.py   # Helper: generate + upload a scoring dataset
│   └── .env.template              # Environment variable template
├── frontend/
│   ├── src/
│   │   ├── App.tsx                # Root component — layout, tab routing, state
│   │   ├── api.ts                 # API client + TypeScript interfaces
│   │   └── components/
│   │       ├── CohortFilter.tsx       # Sidebar filter panel
│   │       ├── GroupExplanationChart.tsx  # Group SHAP bar chart + feature drill-down
│   │       ├── WaterfallChart.tsx     # Individual row SHAP waterfall
│   │       ├── ScoreHistogram.tsx     # Score distribution histogram
│   │       └── NarrativePanel.tsx     # AI narrative display + LLM provider selector
│   ├── vite.config.ts
│   └── package.json
├── docs/
│   ├── README.md                  # This file
│   ├── codespaces-guide.md        # Deployment guide (Markdown)
│   └── codespaces-guide.pdf       # Deployment guide (PDF)
├── start-codespace.sh             # Local Codespace test launcher
├── start-app.sh                   # Custom Application container entry point
├── build-app.sh                   # Pre-build frontend (required before dr run deploy)
└── requirements.txt
```

---

## How it works

### Data pipeline

On startup, `pipeline.py` runs a **batch prediction job** against the configured DataRobot deployment (`DEPLOYMENT_ID`) and scoring dataset (`SCORING_DATASET_ID`). The deployment must have SHAP prediction explanations enabled. Results are downloaded from the DR Data Registry and cached locally — subsequent restarts load from cache without re-running the job.

The pipeline produces two in-memory DataFrames:

- **`scored_population`** — one row per entity, containing all source features and the prediction score. Used for cohort filtering and profile display.
- **`explanation_long`** — one row per explanation slot, unpivoted from the wide `EXPLANATION_N_*` columns. Contains `feature_name`, `shap_strength`, `actual_value`, `qualitative_strength`, and `feature_group`.

### Feature grouping

Features are mapped to named business-domain groups via `feature_group_mapping.json`. This file is the primary configuration artefact for each deployment — it must cover all feature names that appear in `EXPLANATION_N_FEATURE_NAME` columns. Unmatched features fall into "Other".

Group SHAP aggregation for any cohort:

```
group_avg_shap = MEAN(shap_strength) across all explanation rows
                 where row_id ∈ selected cohort
                 and feature_group = <group>
```

Coverage % per group (rows in the cohort where ≥1 feature from the group appeared in top-N explanations) is reported alongside the SHAP value to flag groups with diffuse signal.

### API

The FastAPI backend exposes these endpoints:

| Endpoint | Description |
|---|---|
| `GET /api/cohort` | Profile stats for a filtered cohort (score distribution, row count, % of total) |
| `GET /api/groups` | Group SHAP aggregations + top-feature drill-down for a filtered cohort |
| `GET /api/row/{row_id}` | Waterfall data for a single entity |
| `GET /api/columns` | Column metadata for building filter controls |
| `GET /api/config` | App title, subtitle, and display configuration |
| `GET /api/llm/providers` | Available LLM providers and which have credentials |
| `POST /api/narrative` | Generate LLM narrative for the current cohort |
| `GET /health` | Health check — returns 200 when data is loaded, 503 while pipeline is running |

Filters are passed as a JSON query parameter: `{"Age_life1": {"min": 30, "max": 45}, "SmokerStatus": ["Smoker"]}`.

### LLM narrative

`llm_client.py` abstracts across four LLM providers via LiteLLM:

| Provider | Config variable |
|---|---|
| DataRobot LLM Gateway (recommended) | `DR_GATEWAY_MODEL` |
| DataRobot deployed TextGen model | `DR_LLM_DEPLOYMENT_ID` |
| Azure OpenAI | `AZURE_OPENAI_*` |
| Anthropic | `ANTHROPIC_API_KEY` |

The narrative prompt includes cohort size, score distribution, top group SHAP contributions, and key feature values vs. the full population. Individual entity identifiers are never passed to the LLM.

---

## Configuration files

All three files live in `backend/` and should be committed per use case:

### `feature_group_mapping.json`

Maps model feature names to named business-domain groups. The group structure is entirely user-defined — adapt it to your organization's business vocabulary.

```json
{
  "groups": {
    "Agent Behaviour": ["AGENT_DENIAL_RATE", "AGENT_DENIED_CLAIMS", ...],
    "Claim Details":   ["CLAIM_DESCRIPTION", "CLAIM_AMOUNT", ...],
    "Vendor Behaviour": ["VENDOR_DENIAL_RATE", ...]
  }
}
```

To find the actual feature names used by the model, download any completed batch prediction result from **DR Console → Batch Jobs** and inspect the `EXPLANATION_N_FEATURE_NAME` columns. Note that DataRobot may auto-generate date-part features (e.g. `Claim_Date (Month)`) that also need to be mapped.

### `profile_config.json`

Controls which columns appear in the cohort filter panel and what the score/prediction column is called in the UI.

### `narrative_config.json`

Entity labels (e.g. "policy", "claim"), score labels (e.g. "lapse propensity", "fraud score"), recommended action hint, and optional prompt overrides for the LLM narrative.

---

## Environment variables

| Variable | Description | Required |
|---|---|---|
| `DATAROBOT_API_TOKEN` | DR API token — auto-injected in Codespaces | auto |
| `DATAROBOT_ENDPOINT` | DR API endpoint, e.g. `https://app.eu.datarobot.com/api/v2` | required |
| `DEPLOYMENT_ID` | DR deployment with SHAP enabled — preferred scoring path | recommended |
| `PROJECT_ID` + `MODEL_ID` | Fallback if no deployment is available | fallback |
| `SCORING_DATASET_ID` | DR Data Registry dataset to score on startup | required |
| `ROW_ID_COL` | Unique row identifier column name | required |
| `MAX_EXPLANATIONS` | Number of SHAP explanation slots to request (default: 4, max: 100) | optional |
| `OUTCOME_COL` | Binary 0/1 outcome column — enables actual outcome rate in narrative | optional |
| `DEFAULT_USE_CASE_ID` | Scopes the in-app dataset selector to one use case folder | optional |
| `DR_GATEWAY_MODEL` | LLM Gateway model for narrative, e.g. `azure/gpt-4o-mini` | optional |
| `DR_LLM_DEPLOYMENT_ID` | Deployed TextGen model for narrative | optional |
| `AZURE_OPENAI_*` | Azure OpenAI credentials | optional |
| `ANTHROPIC_API_KEY` | Anthropic API key | optional |
| `APP_TITLE` / `APP_SUBTITLE` | Displayed in the app header | optional |

---

## Compatibility

### Supported project types

| Project type | Deployment path (`DEPLOYMENT_ID`) | Project+Model fallback (`PROJECT_ID + MODEL_ID`) |
|---|---|---|
| Binary classification — standard / cross-validation | ✅ | ✅ |
| Regression — standard / cross-validation | ✅ | ✅ |
| Group-partitioned | ✅ | ✅ |
| **OTV / datetime-partitioned** | ✅ | ❌ |
| **Time series** | ⚠️ See below | ❌ |
| Multiclass classification | ❌ | ❌ |

### Deployment path — recommended for all use cases

`BatchPredictionJob.score()` against a deployment is partitioning-agnostic. It works for standard, cross-validation, group-partitioned, OTV, and time series projects, provided the deployment has SHAP prediction explanations enabled.

**Exception — time series SHAP:** SHAP-based prediction explanations for time series deployments are currently affected by a known temporary bug and will fail at the batch prediction step. Time series projects should not be used with this app until the issue is resolved. Use a non-time-series deployment in the meantime.

### Project+Model fallback — standard projects only

The `PROJECT_ID + MODEL_ID` path uses `model.request_predictions()` and `PredictionExplanations.create()` directly against the project. This path has hard restrictions:

- **OTV / datetime-partitioned projects:** `DATA_SUBSET.ALL` is not valid; the call fails with a 422 error. The recommended model in these projects is typically retrained on validation+holdout data, which also blocks `PredictionExplanations.create()` with the error `Prediction explanations are not supported for models that use validation data for training`.
- **Time series projects:** Scoring requires a forecast-point-aware prediction dataset with the correct historical context rows — an arbitrary scoring dataset cannot be uploaded and scored.

Always use `DEPLOYMENT_ID` for any project type other than standard binary classification or regression with random/stratified partitioning.

### Other known limitations

- **Multiclass classification:** SHAP-based prediction explanations are not supported by DataRobot for multiclass projects. XEMP is the only available method, which is incompatible with the group summation approach used by this app.
- **Image features:** Prediction explanations are not available for image features.
- **Text features:** SHAP explanations are supported — the text feature column receives a single SHAP value like any other feature and maps to a group normally. Token-level explanations within the text feature are not available via SHAP (only via XEMP Text Explanations).

---

See [`docs/codespaces-guide.md`](docs/codespaces-guide.md) for the full step-by-step guide covering:

- Local testing in a DataRobot Codespace (`./start-codespace.sh`)
- Custom Application deployment (`./build-app.sh` + `dr run deploy`)

Quick reference:

```bash
# Local test
cp backend/.env.template backend/.env  # fill in values
./start-codespace.sh

# Custom Application
uvx copier copy https://github.com/datarobot-community/af-component-base .
dr dotenv setup && dr dotenv validate
./build-app.sh
dr run deploy
```

---

## Technical notes

**SHAP additivity.** DataRobot outputs SHAP values in the prediction output scale — probability space for binary classifiers, target units for regression — so the following identity holds exactly without further transformation:

```
prediction = SHAP_BASE_VALUE + Σ EXPLANATION_N_STRENGTH + SHAP_REMAINING_TOTAL
```

Group sums are directly interpretable as contributions to the prediction score in the same units as the output. Note that raw SHAP implementations (e.g. the `shap` Python library) operate in log-odds space for classifiers — values from those tools are not directly comparable in magnitude.

**Explanation coverage.** With a small `MAX_EXPLANATIONS` value, groups with many moderate features may be underrepresented — their signal is spread across slots that don't make the top-N for any given row. Coverage % is reported per group to make this visible. Increase `MAX_EXPLANATIONS` and apply a minimum `|shap_strength|` cut-off to balance completeness against noise.

**Batch prediction cache.** The pipeline caches batch job results to `backend/.batch_output_cache.csv`. This cache is local to the running environment — it is not bundled into the Custom Application container, which always cold-starts the batch job on first load (~1–2 minutes).

---

## References

- [DataRobot Prediction Explanations (SHAP)](https://docs.datarobot.com/en/docs/modeling/analyze-models/understand/pred-explain/pe-tabular.html)
- [DataRobot App Framework components](https://af.datarobot.com/)
- [SHAP — SHapley Additive exPlanations](https://shap.readthedocs.io/en/latest/)
- [LiteLLM](https://docs.litellm.ai/) — LLM provider abstraction used in `llm_client.py`
- [Predictive Content Generator](https://github.com/datarobot-community/predictive-content-generator) — related DataRobot community template
