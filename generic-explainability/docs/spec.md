# Generic Binary Classification Explainability App — Specification

**Version:** 0.1 (Generic MVP)
**Derived from:** IL Protection Lapse Explainability App v0.1
**Date:** 2026-06-26

---

## Table of contents

1. [Problem statement](#1-problem-statement)
2. [Solution overview](#2-solution-overview)
3. [Configuration schema](#3-configuration-schema)
4. [Data contract](#4-data-contract)
5. [Application modules](#5-application-modules)
6. [SHAP aggregation algorithm](#6-shap-aggregation-algorithm)
7. [LLM narrative layer](#7-llm-narrative-layer)
8. [Technical architecture](#8-technical-architecture)
9. [Example configurations](#9-example-configurations)
10. [Migration from the IL app](#10-migration-from-the-il-app)
11. [Open questions and caveats](#11-open-questions-and-caveats)

---

## 1. Problem statement

DataRobot provides row-level prediction explanations (SHAP values) for every model it builds. In practice these are difficult to act on because:

- Features are often correlated; individual explanation strengths shift depending on which correlated features appear in the top-N for a given row.
- Models with many features make it hard to identify the dominant business drivers — even when individual row explanations are accurate, the signal is spread across numerous features.
- There is no cohort-level view: analysts must inspect individual rows or build custom aggregations outside the platform.
- End users need plain-language insight into *why* a segment is high-risk, not a raw list of feature names and SHAP values.

This app addresses all four problems for **any binary classification model** deployed in DataRobot, without requiring code changes when switching models or domains.

---

## 2. Solution overview

Three layers on top of DataRobot prediction outputs:

| Layer | What it does |
|---|---|
| **Cohort filter & profile** | Slice the scored population by configurable attributes; inspect score distribution and key field breakdowns for the selected segment |
| **Grouped explanations** | Aggregate SHAP values by business-domain feature group; surface combined group impact alongside drill-down to individual features |
| **LLM narrative** | Generate a plain-English summary of the selected cohort's profile and the drivers of their predicted score |

SHAP (not XEMP) is used throughout so that explanation values are additive and group-level sums are mathematically valid.

**Data sources supported:**

| Mode | Description |
|---|---|
| **DataRobot** | Scored dataset lives in the AI Catalog; predictions and SHAP explanations are fetched via the DataRobot SDK at startup. Primary mode for production deployments. |
| **CSV** | A pre-scored CSV file (with `EXPLANATION_N_STRENGTH` columns already computed by DataRobot) is loaded directly. No DataRobot API calls required. Useful for offline analysis or when the SDK pipeline is not accessible. |

---

## 3. Configuration schema

All domain-specific behaviour is controlled through four configuration artifacts. Nothing domain-specific is hardcoded.

### 3.1 Environment variables (`.env`)

#### 3.1.1 Required for DataRobot mode

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATAROBOT_API_TOKEN` | string | — | DataRobot API token |
| `DATAROBOT_ENDPOINT` | string | `https://app.datarobot.com/api/v2` | DataRobot instance base URL |
| `PROJECT_ID` | string | — | DataRobot project UUID |
| `MODEL_ID` | string | — | DataRobot model UUID within the project |
| `SCORING_DATASET_ID` | string | — | AI Catalog dataset ID containing the scored population |

#### 3.1.2 Required for CSV mode

| Variable | Type | Default | Description |
|---|---|---|---|
| `DATA_SOURCE` | `datarobot` \| `csv` | `datarobot` | Select data loading mode |
| `CSV_PATH` | string | — | Absolute or relative path to the pre-scored CSV file (CSV mode only) |

#### 3.1.3 Optional — data pipeline

| Variable | Type | Default | Description |
|---|---|---|---|
| `TRAINING_DATASET_ID` | string | — | AI Catalog dataset ID for the training population (enables outcome rate in narrative). Unused in CSV mode. |
| `TRAINING_CSV_PATH` | string | — | Path to training CSV with outcome labels (CSV mode equivalent of `TRAINING_DATASET_ID`) |
| `ROW_ID_COL` | string | `id` | Column name used as the unique row identifier |
| `PREDICTION_COL` | string | auto-detect | Name of the prediction score column (0–1 float). If omitted, the first column ending in `_PREDICTION` is used; startup fails if zero or multiple matches. |
| `OUTCOME_COL` | string | — | Column name for the binary outcome label in the training dataset (0/1). If provided, the narrative includes an observed outcome rate. |
| `MAX_EXPLANATIONS` | int | `4` | Number of top SHAP explanation slots available in the dataset (`EXPLANATION_1_*` through `EXPLANATION_{N}_*`) |

#### 3.1.4 Optional — application metadata

| Variable | Type | Default | Description |
|---|---|---|---|
| `APP_TITLE` | string | `Prediction Explainability` | Main heading shown in the browser and app header |
| `APP_SUBTITLE` | string | `` | Secondary line beneath the title (e.g., model name, cohort description) |

#### 3.1.5 Optional — tuning parameters

| Variable | Type | Default | Description |
|---|---|---|---|
| `COHORT_WARNING_MIN_ROWS` | int | `30` | Cohort sizes below this threshold trigger a stability warning in the narrative |
| `TOP_FEATURES_PER_GROUP` | int | `5` | Number of top features shown per group in the drill-down view |
| `SCORE_HISTOGRAM_BINS` | int | `20` | Number of bins in the score distribution histogram |
| `NARRATIVE_MAX_TOKENS` | int | `700` | Maximum token budget for LLM narrative response |
| `NARRATIVE_GROUPS_IN_PROMPT` | int | `6` | Number of top explanation groups included in the LLM prompt |
| `NARRATIVE_FEATURES_PER_GROUP` | int | `2` | Number of top features per group included in the LLM prompt |

#### 3.1.6 Optional — LLM providers (at least one required for narrative)

| Variable | Description |
|---|---|
| `DR_GATEWAY_MODEL` | DataRobot LLM Gateway model name (e.g., `azure-openai/gpt-4o-mini`, `anthropic/claude-sonnet-4-6`) |
| `DR_LLM_DEPLOYMENT_ID` | ID of a DataRobot-deployed TextGen model |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_API_BASE` | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_VERSION` | Azure API version (default: `2024-02-01`) |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Azure deployment name (e.g., `gpt-4o`) |
| `ANTHROPIC_API_KEY` | Anthropic direct API key |
| `ANTHROPIC_MODEL` | Anthropic model ID (default: `claude-sonnet-4-6`) |

---

### 3.2 Feature group mapping (`feature_group_mapping.json`)

Maps individual feature names to business-domain groups. The backend uses this to aggregate SHAP values by group.

**Schema:**

```json
{
  "groups": {
    "<Group Label>": ["feature_a", "feature_b", "feature_c"],
    "<Group Label 2>": ["feature_d", "feature_e"]
  }
}
```

**Rules:**
- Group labels are arbitrary strings; they appear verbatim in the UI and LLM prompt.
- A feature may appear in at most one group. If a feature appears in multiple groups, the first match (by JSON key order) wins.
- Features present in the dataset but absent from the mapping are assigned to an implicit **"Other"** group. "Other" is always displayed last regardless of its SHAP magnitude.
- Empty groups (no features appearing in the top-N explanations for any row) are silently excluded from the group chart.
- Group display order in the UI is sorted by `avg_abs_shap` descending, not by JSON key order.
- The file is loaded at startup; changes require a backend restart.

**Validation at startup:**
- Warn (do not fail) if a feature listed in the mapping does not appear in the dataset column list — it may be a future feature or an alias.
- Fail if the file is missing or malformed JSON.

---

### 3.3 Profile attributes config (`profile_config.json`)

Controls which columns appear in the filter sidebar and the cohort profile section. This replaces the hardcoded filter columns in the frontend.

**Schema:**

```json
{
  "profile_attributes": [
    {
      "column": "<column_name>",
      "display_name": "<human-readable label>",
      "filter_type": "range | multiselect | toggle",
      "show_in_profile": true
    }
  ],
  "score_filter": {
    "show": true,
    "display_name": "Prediction Score"
  },
  "top_explanation_filter": {
    "show": true,
    "display_name": "Top Explanation Feature",
    "explanation_slot": 1
  }
}
```

#### `profile_attributes` fields

| Field | Type | Required | Description |
|---|---|---|---|
| `column` | string | yes | Exact column name in the scored dataset |
| `display_name` | string | yes | Label shown in the sidebar and profile view |
| `filter_type` | enum | yes | Controls UI widget type (see below) |
| `show_in_profile` | bool | no (default `true`) | If `true`, this attribute also appears as a breakdown chart in the cohort profile section |

#### `filter_type` values

| Value | Widget | Column requirement |
|---|---|---|
| `range` | Numeric slider with min/max inputs | Numeric column |
| `multiselect` | Scrollable checkbox list | Categorical or low-cardinality string column |
| `toggle` | Binary yes/no switch | Column with exactly 2 distinct non-null values |

**Cardinality guard:** if a `multiselect` column has more than 200 distinct values, the backend returns only the top 200 by frequency. A note is shown in the sidebar.

#### `score_filter`

Always driven by the auto-detected `PREDICTION_COL`. Set `show: false` to hide it from the sidebar (not recommended).

#### `top_explanation_filter`

Exposes the feature name from `EXPLANATION_{explanation_slot}_FEATURE_NAME` as a multiselect filter. Lets users filter to cohorts where a specific feature was the top driver. Default slot: `1`.

**Validation at startup:**
- Fail if a `profile_attributes` column does not exist in the dataset.
- Warn if a `toggle` column has more than 2 distinct values; downgrade to `multiselect` automatically.

---

### 3.4 Narrative config (`narrative_config.json`)

Controls the LLM system prompt and the language used in the user prompt template. Allows the narrative to be contextualised for any domain and audience without changing code.

**Schema:**

```json
{
  "domain_description": "<short description of the model's use case>",
  "entity_label": "<what each row represents, singular>",
  "entity_label_plural": "<plural form>",
  "target_audience": "<who reads the narrative>",
  "high_score_label": "<what a high score means in plain language>",
  "low_score_label": "<what a low score means in plain language>",
  "factor_positive_label": "<label for SHAP > 0>",
  "factor_negative_label": "<label for SHAP < 0>",
  "outcome_label": "<what the observed outcome column means, if present>",
  "recommended_action_hint": "<optional sentence fragment to steer the action recommendation>",
  "custom_system_prompt": null
}
```

| Field | Example (insurance lapse) | Example (telecom churn) |
|---|---|---|
| `domain_description` | `life insurance protection lapse propensity` | `mobile subscriber churn prediction` |
| `entity_label` | `policyholder` | `subscriber` |
| `entity_label_plural` | `policyholders` | `subscribers` |
| `target_audience` | `financial adviser` | `customer success manager` |
| `high_score_label` | `high lapse risk` | `high churn risk` |
| `low_score_label` | `low lapse risk` | `likely to be retained` |
| `factor_positive_label` | `factor increasing surrender risk` | `factor increasing churn likelihood` |
| `factor_negative_label` | `factor reducing surrender risk` | `factor reducing churn likelihood` |
| `outcome_label` | `observed lapse rate` | `observed churn rate` |
| `recommended_action_hint` | `Prioritise outreach to ...` | `Consider a targeted retention offer for ...` |
| `custom_system_prompt` | `null` | `null` |

If `custom_system_prompt` is a non-null string, it is used verbatim as the LLM system prompt and all other fields are ignored. Use this for full control over the persona without modifying code.

---

## 4. Data contract

### 4.1 Required columns

The following columns must be present in the scored dataset (DataRobot mode: in the AI Catalog CSV; CSV mode: in the loaded file):

| Column | Type | Description |
|---|---|---|
| `{ROW_ID_COL}` | string or int | Unique row identifier (value of `ROW_ID_COL` env var) |
| `{PREDICTION_COL}` | float, 0–1 | Prediction score (value of `PREDICTION_COL` env var, or auto-detected) |
| `EXPLANATION_1_FEATURE_NAME` | string | Name of the top-ranked SHAP feature for this row |
| `EXPLANATION_1_STRENGTH` | float | Signed SHAP value for rank-1 feature |
| `EXPLANATION_1_ACTUAL_VALUE` | string | Value of the rank-1 feature at scoring time |
| `EXPLANATION_1_QUALITATIVE_STRENGTH` | string | Discretised strength: `+++`, `++`, `+`, `-`, `--`, `---` |
| … (repeat for ranks 2 through `MAX_EXPLANATIONS`) | | |

### 4.2 Optional columns

| Column | Description |
|---|---|
| `Percentile`, `Decile`, `20-quantile` | Pre-computed rank bands. If present, automatically added as `range` filter options in the sidebar. |
| Any column referenced in `profile_config.json` | Source feature columns used for filtering and profiling. All other columns in the dataset are ignored at runtime but retained for individual row lookup. |

### 4.3 Training dataset (optional)

If `TRAINING_DATASET_ID` or `TRAINING_CSV_PATH` is provided, the training dataset must contain:
- `{ROW_ID_COL}` — for joining to the scored population (rows not found in the scored population are ignored)
- `{OUTCOME_COL}` — binary 0/1 outcome label

The training dataset is used only to compute the observed outcome rate for the selected cohort, which is included in the LLM prompt and displayed in the cohort profile view.

### 4.4 SHAP vs XEMP note

`EXPLANATION_N_STRENGTH` must contain true SHAP values (additive, centred at the model base rate) for group-level sums to be mathematically valid. DataRobot prediction explanations use SHAP by default; XEMP is a legacy format. The app checks for this at startup:

- If the explanation strengths for a sample of rows sum to approximately `prediction - base_rate`, SHAP is confirmed.
- If the check fails, a banner warning is shown in the UI: *"Explanation values may not be additive — group totals are indicative only."* The app continues to function.

---

## 5. Application modules

### 5.1 Module 1 — Cohort filter & profile

**Purpose:** Define the population subset to be analysed in Modules 2 and 3.

#### 5.1.1 Cohort profile

- Row count and percentage of total scored population shown prominently.
- Score distribution: histogram of `{PREDICTION_COL}` for the full population and filtered segment (overlay). Bin count: `SCORE_HISTOGRAM_BINS`.
- Score statistics table: mean, median, 90th percentile — cohort vs full population.
- Breakdown charts for each attribute where `show_in_profile: true`: bar chart of the most common categories (categorical) or box plot / histogram (numeric). Cohort vs full population shown side-by-side.
- Observed outcome rate (if training data is available): cohort actual outcome rate vs full scored population.

#### 5.1.2 Filters

The sidebar is fully driven by `profile_config.json`. Filters apply to any source feature listed in `profile_attributes`. All filters are additive (AND logic). Filtered row count updates with a 400 ms debounce.

Two implicit filters are always present (unless disabled in profile config):
- **Score filter**: range slider over `{PREDICTION_COL}`.
- **Top explanation filter**: multiselect over `EXPLANATION_{slot}_FEATURE_NAME`.

#### 5.1.3 Individual row lookup

- **Search by row ID**: type or paste a `{ROW_ID_COL}` value; displays that row's position in the score distribution and all explanation slot values.
- **CSV upload**: upload a file containing a column of `{ROW_ID_COL}` values; the union of matching rows becomes the cohort for Modules 2 and 3. The row ID column name in the uploaded file is configurable (default: same as `ROW_ID_COL`).

---

### 5.2 Module 2 — Grouped explanations

**Purpose:** Quantify the contribution of each configured feature group to the predicted score in the selected cohort.

#### 5.2.1 Group summary view

- Horizontal bar chart: one bar per group, sorted by `avg_abs_shap` descending.
- Bar height (length): `avg_abs_shap` — mean of absolute SHAP values across cohort rows where the group appears.
- Bar colour: derived from `sum_shap` (net signed direction). Red = net positive (increases predicted probability); green = net negative (reduces predicted probability). Neutral grey when magnitude is near zero.
- Filter buttons: show all groups / only groups increasing score / only groups reducing score.
- Tooltip: group name, `avg_abs_shap`, `sum_shap`, number of cohort rows where the group has coverage, coverage %.
- Coverage note below chart: "Group SHAP totals are based on top-`{MAX_EXPLANATIONS}` explanations only. Groups with many moderate features may be underrepresented."

#### 5.2.2 Feature drill-down

Clicking a group bar expands it to show:
- Individual feature bars within the group (same `avg_abs_shap` / `sum_shap` treatment), top `TOP_FEATURES_PER_GROUP` features.
- Coverage: "X of Y features in this group appeared in top-`{MAX_EXPLANATIONS}` explanations for at least one row."

#### 5.2.3 Individual row waterfall

When a single row ID is selected (Section 5.1.3):
- Waterfall chart: baseline → SHAP contribution of explanation 1 → … → explanation N → final score.
- Bars colour-coded by group (group colour palette auto-assigned from a fixed set, consistent within the session).
- Actual feature value displayed on each bar.
- Disclaimer: "SHAP values shown are for the top-`{MAX_EXPLANATIONS}` explanations and do not sum exactly to the prediction score."

---

### 5.3 Module 3 — LLM narrative summary

**Purpose:** Translate the cohort profile and grouped explanation data into plain-language insight for non-technical users.

#### 5.3.1 Input to LLM

The prompt includes (assembled by the backend, never passed to client):
- Cohort size and filter criteria.
- Score distribution summary (cohort vs full population).
- Top `NARRATIVE_GROUPS_IN_PROMPT` groups by `avg_abs_shap`, with direction and coverage %.
- Top `NARRATIVE_FEATURES_PER_GROUP` features per group.
- Observed outcome rate (if available).
- Domain labels from `narrative_config.json`.
- Optional custom instruction from the user.

`{ROW_ID_COL}` values and individual entity identifiers are **never** included in the prompt.

#### 5.3.2 Output format

Three sections:
1. **Profile**: who is in this cohort — characteristics that distinguish them from the overall scored population, using `entity_label_plural` and the domain vocabulary from `narrative_config.json`.
2. **Drivers**: what is driving their high (or low) predicted score — leading groups, specific features, direction of effect, using `factor_positive_label` / `factor_negative_label`.
3. **Recommended action**: a single sentence starting with "Recommended action:".

#### 5.3.3 Guardrails

- If cohort size < `COHORT_WARNING_MIN_ROWS`, prepend: *"[Note: cohort has only N rows — group-level averages may not be stable.]"*
- Always append a disclaimer: *"AI-generated summary — for indicative use only. Verify against source data before acting."*
- If the LLM call fails, display an error message with the raw exception (not a silent failure).

#### 5.3.4 Regeneration and export

- User can select the LLM provider from a list of configured providers.
- User can append a custom instruction (e.g., "Focus on financial stress indicators", "Write for a non-technical audience").
- Output is copyable as plain text.

---

## 6. SHAP aggregation algorithm

For a given set of rows (selected cohort):

1. **Unpivot** the `MAX_EXPLANATIONS` explanation slots into a long table: `(row_id, explanation_rank, feature_name, shap_strength, actual_value, qualitative_strength)`.
2. **Left-join** to `feature_group_mapping.json` to assign each feature a group label. Features without a mapping are assigned `"Other"`.
3. Features not appearing in any explanation slot for a given row have `shap_strength = NULL`. Do **not** impute zero — treat as absent.
4. **Aggregate per group per cohort:**
   - `avg_abs_shap = mean(|shap_strength|)` over all rows where the group has ≥1 feature in top-N. This is the sort key and bar height.
   - `sum_shap = sum(shap_strength)` over the same rows. This is the net direction and colour driver.
   - `avg_shap = mean(shap_strength)` — signed average, used in the LLM prompt table.
   - `n_rows_with_coverage = count(distinct row_id)` where ≥1 feature from this group appears.
   - `coverage_pct = n_rows_with_coverage / cohort_size × 100`.
5. **Sort** groups by `avg_abs_shap` descending. "Other" always placed last.
6. **Top features per group:** for each group, take the top `TOP_FEATURES_PER_GROUP` features by `mean(|shap_strength|)` across cohort rows where that feature appears.

**Why `avg_abs_shap` for sort/height, `sum_shap` for colour:**
When a group contains both risk-increasing and risk-reducing features, their signed SHAP values partially cancel in `sum_shap`. Using `avg_abs_shap` for the bar height preserves the group's total signal magnitude regardless of internal cancellation. `sum_shap` then reveals whether the group's net effect is positive or negative.

**Output schema (`group_shap_summary`):**

| Field | Type | Description |
|---|---|---|
| `feature_group` | string | Group label |
| `avg_abs_shap` | float | Mean of \|SHAP\| — bar height, sort key |
| `sum_shap` | float | Net signed SHAP sum — bar colour |
| `avg_shap` | float | Mean signed SHAP — used in narrative prompt |
| `n_rows_with_coverage` | int | Rows where ≥1 group feature appears in top-N |
| `coverage_pct` | float | `n_rows_with_coverage / cohort_size × 100` |
| `top_features` | list | Top-N features: `{feature_name, avg_shap, avg_abs_shap, n_rows}` |

---

## 7. LLM narrative layer

### 7.1 System prompt construction

If `custom_system_prompt` in `narrative_config.json` is non-null, it is used verbatim.

Otherwise the system prompt is assembled from the narrative config fields:

```
You are a data analyst summarising {domain_description} model outputs for a {target_audience}.
Your summaries are concise, factual, and use plain language a {target_audience} would understand.
Never use the terms 'SHAP' or 'feature importance'.
Instead say '{factor_positive_label}' or '{factor_negative_label}'.
End your response with a one-sentence recommended action.
```

### 7.2 User prompt template

```
COHORT: {n_rows} {entity_label_plural} ({pct_of_total:.1f}% of total scored population).
Filter criteria: {filter_description}

SCORE DISTRIBUTION (probability of {high_score_label}):
  Cohort    — mean={mean_score:.3f}, median={median_score:.3f}
  Full pop. — mean={mean_score_full:.3f}, median={median_score_full:.3f}

TOP EXPLANATION GROUPS (average contribution, cohort):
{group_table}

KEY FEATURE VALUES (cohort vs full population):
{feature_table}

{outcome_note}

Write two short paragraphs:
1. Profile: describe who these {entity_label_plural} are based on the feature values above.
2. Drivers: explain what is driving their {high_score_label} scores.

Then add one recommended action sentence starting with "Recommended action:".

{custom_instruction}
```

### 7.3 LLM providers

Four providers are supported via LiteLLM, selected by the user in the UI:

| Provider | Required env vars |
|---|---|
| DataRobot LLM Gateway | `DR_GATEWAY_MODEL`, `DATAROBOT_API_TOKEN`, `DATAROBOT_ENDPOINT` |
| DataRobot deployed TextGen | `DR_LLM_DEPLOYMENT_ID`, `DATAROBOT_API_TOKEN`, `DATAROBOT_ENDPOINT` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_API_BASE`, `AZURE_OPENAI_DEPLOYMENT_NAME` |
| Anthropic (direct) | `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` |

The UI only shows providers for which credentials are configured. If exactly one provider is available, it is selected automatically with no UI shown.

---

## 8. Technical architecture

### 8.1 Component map

```
.env + JSON config files
        │
        ▼
  Python backend (FastAPI)
  ┌─────────────────────────────────────────────────────────────┐
  │ config.py       — Pydantic settings from .env               │
  │ config_loader.py — Load + validate JSON config files        │
  │ pipeline.py     — Data loading (DataRobot mode or CSV mode) │
  │ cohort.py       — Filter engine + SHAP aggregation          │
  │ narrative.py    — Prompt builder (parameterised)            │
  │ llm_client.py   — Multi-provider LLM abstraction (LiteLLM)  │
  │ main.py         — FastAPI app, endpoints                     │
  └─────────────────────────────────────────────────────────────┘
        │
        ▼
  REST API (localhost:8000)
  ├── GET  /api/config        ← app metadata + resolved config for frontend
  ├── GET  /api/health        ← status, row counts, sample row IDs
  ├── GET  /api/columns       ← column metadata (type, range, distinct values)
  ├── GET  /api/cohort        ← cohort profile stats (filters param)
  ├── GET  /api/groups        ← group SHAP summary (filters param)
  ├── GET  /api/row/{row_id}  ← waterfall data for one row
  ├── GET  /api/llm/providers ← available LLM providers
  └── POST /api/narrative     ← LLM narrative generation
        │
        ▼
  React frontend (Vite, localhost:5173)
  ├── Startup: GET /api/config → drives title, labels, sidebar layout
  ├── CohortFilter    — sidebar, config-driven from profile_attributes
  ├── ScoreHistogram  — cohort vs full distribution
  ├── CohortProfile   — breakdown charts for show_in_profile attributes
  ├── GroupExplanationChart — bar chart + drill-down
  ├── WaterfallChart  — single-row SHAP waterfall
  └── NarrativePanel  — LLM narrative with provider selector
```

### 8.2 New endpoint: `GET /api/config`

Returns the resolved application configuration so the frontend has zero domain-specific hardcoding. Called once at startup.

**Response schema:**

```json
{
  "app_title": "string",
  "app_subtitle": "string",
  "row_id_col": "string",
  "prediction_col": "string",
  "max_explanations": 4,
  "entity_label": "string",
  "entity_label_plural": "string",
  "high_score_label": "string",
  "factor_positive_label": "string",
  "factor_negative_label": "string",
  "profile_attributes": [
    {
      "column": "string",
      "display_name": "string",
      "filter_type": "range | multiselect | toggle",
      "show_in_profile": true
    }
  ],
  "score_filter": { "show": true, "display_name": "string" },
  "top_explanation_filter": { "show": true, "display_name": "string", "explanation_slot": 1 },
  "feature_groups": ["Group A", "Group B", "Other"]
}
```

### 8.3 Startup validation

At startup the backend validates:

1. All required env vars are present (fail fast with clear error).
2. `PREDICTION_COL` resolves to exactly one column in the dataset. If auto-detecting, fail if zero or multiple `_PREDICTION` columns found.
3. `ROW_ID_COL` exists in the dataset.
4. All columns in `profile_config.json` → `profile_attributes` exist in the dataset.
5. `EXPLANATION_1_FEATURE_NAME` through `EXPLANATION_{MAX_EXPLANATIONS}_FEATURE_NAME` columns exist.
6. `narrative_config.json` is valid JSON with all required fields non-empty.
7. At least one LLM provider has credentials configured (warn, not fail — app works without narrative).

### 8.4 Data pipeline modes

#### DataRobot mode (startup, ~2–5 min on first run)

1. Initialise DataRobot client from `DATAROBOT_API_TOKEN` + `DATAROBOT_ENDPOINT`.
2. Upload `SCORING_DATASET_ID` from AI Catalog to the project as a prediction dataset (cached after first run in `.prediction_dataset_cache.json`).
3. Request predictions on the dataset.
4. Initialise Prediction Explanations engine for the model.
5. Fetch SHAP explanations (up to `MAX_EXPLANATIONS` per row).
6. Load the scored dataset from the AI Catalog as the source of truth for all source feature columns.
7. Map PE positional indices to `ROW_ID_COL` values.
8. Attach group labels to the explanation long table.
9. Cache both DataFrames in memory for the lifetime of the process.

#### CSV mode (startup, seconds)

1. Load CSV from `CSV_PATH` into a DataFrame.
2. Validate required columns (see Section 4.1).
3. Attach group labels to the explanation long table (unpivoted from the CSV's explanation columns).
4. Cache both DataFrames in memory.

No DataRobot API calls are made in CSV mode.

---

## 9. Example configurations

### 9.1 Insurance protection lapse (the IL app, generalized)

**.env:**
```bash
APP_TITLE=Protection Lapse Propensity — Explainability
APP_SUBTITLE=Under-55 cohort, excl. UL
DATA_SOURCE=datarobot
DATAROBOT_API_TOKEN=...
DATAROBOT_ENDPOINT=https://app.eu.datarobot.com/api/v2
PROJECT_ID=6a22f2218f74af009899ddb1
MODEL_ID=6a22f2ab13b0a82934ef1155
SCORING_DATASET_ID=6a2275eb326d5530a77a0b30
TRAINING_DATASET_ID=6a2275eb1a27ddce9c076a03
ROW_ID_COL=Policy_Number
PREDICTION_COL=Lapse_ind_1_PREDICTION
OUTCOME_COL=Lapse_ind
MAX_EXPLANATIONS=4
DR_GATEWAY_MODEL=azure-openai/gpt-4o-mini
```

**narrative_config.json:**
```json
{
  "domain_description": "life insurance protection lapse propensity",
  "entity_label": "policyholder",
  "entity_label_plural": "policyholders",
  "target_audience": "financial adviser",
  "high_score_label": "high lapse risk",
  "low_score_label": "low lapse risk",
  "factor_positive_label": "factor increasing surrender risk",
  "factor_negative_label": "factor reducing surrender risk",
  "outcome_label": "observed lapse rate",
  "recommended_action_hint": "Prioritise outreach to policyholders with ...",
  "custom_system_prompt": null
}
```

**profile_config.json:**
```json
{
  "profile_attributes": [
    { "column": "Age_life1", "display_name": "Age", "filter_type": "range", "show_in_profile": true },
    { "column": "SmokerStatus", "display_name": "Smoker", "filter_type": "toggle", "show_in_profile": true },
    { "column": "Product_Desc", "display_name": "Product", "filter_type": "multiselect", "show_in_profile": true },
    { "column": "MonthsSinceReview", "display_name": "Months since review", "filter_type": "range", "show_in_profile": true },
    { "column": "Decile", "display_name": "Score decile", "filter_type": "range", "show_in_profile": false }
  ],
  "score_filter": { "show": true, "display_name": "Lapse Propensity Score" },
  "top_explanation_filter": { "show": true, "display_name": "Top Explanation Feature", "explanation_slot": 1 }
}
```

---

### 9.2 Telecom subscriber churn

**.env:**
```bash
APP_TITLE=Subscriber Churn Explainability
APP_SUBTITLE=Prepaid segment · Q2 2026 scoring
DATA_SOURCE=csv
CSV_PATH=data/churn_scored_q2_2026.csv
ROW_ID_COL=subscriber_id
PREDICTION_COL=churn_PREDICTION
OUTCOME_COL=churned
MAX_EXPLANATIONS=5
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-sonnet-4-6
```

**narrative_config.json:**
```json
{
  "domain_description": "mobile subscriber churn prediction",
  "entity_label": "subscriber",
  "entity_label_plural": "subscribers",
  "target_audience": "customer success manager",
  "high_score_label": "high churn risk",
  "low_score_label": "likely to be retained",
  "factor_positive_label": "factor increasing churn likelihood",
  "factor_negative_label": "factor reducing churn likelihood",
  "outcome_label": "observed churn rate",
  "recommended_action_hint": "Consider a targeted retention offer for subscribers with ...",
  "custom_system_prompt": null
}
```

**profile_config.json:**
```json
{
  "profile_attributes": [
    { "column": "tenure_months", "display_name": "Tenure (months)", "filter_type": "range", "show_in_profile": true },
    { "column": "plan_type", "display_name": "Plan type", "filter_type": "multiselect", "show_in_profile": true },
    { "column": "avg_monthly_spend", "display_name": "Avg monthly spend (€)", "filter_type": "range", "show_in_profile": true },
    { "column": "support_calls_last_90d", "display_name": "Support calls (90 days)", "filter_type": "range", "show_in_profile": true },
    { "column": "has_bundle", "display_name": "Has bundle", "filter_type": "toggle", "show_in_profile": false }
  ],
  "score_filter": { "show": true, "display_name": "Churn Probability" },
  "top_explanation_filter": { "show": true, "display_name": "Top Explanation Feature", "explanation_slot": 1 }
}
```

**feature_group_mapping.json (excerpt):**
```json
{
  "groups": {
    "Contract & Plan": ["plan_type", "contract_type", "tenure_months", "auto_renew"],
    "Usage": ["avg_data_gb_30d", "avg_calls_min_30d", "avg_sms_30d", "roaming_active"],
    "Spend & Billing": ["avg_monthly_spend", "last_bill_amount", "payment_on_time_pct"],
    "Service Issues": ["support_calls_last_90d", "network_complaints_6m", "outage_hours_6m"],
    "Engagement": ["app_logins_30d", "self_serve_pct", "promo_clicks_90d"]
  }
}
```

---

## 10. Migration from the IL app

Every domain-specific value currently hardcoded in the IL app maps to a generic config parameter:

| Hardcoded location | Current value | Generic config |
|---|---|---|
| `frontend/src/App.tsx` — title | `"Protection Lapse Propensity — Explainability"` | `APP_TITLE` (.env) |
| `frontend/src/App.tsx` — subtitle | `"Model 6a22f2ab · Under-55 cohort, excl. UL"` | `APP_SUBTITLE` (.env) |
| `frontend/src/components/CohortFilter.tsx` — filter columns | `Age_life1`, `SmokerStatus`, `Product_Desc`, `MonthsSinceReview`, `Decile` | `profile_config.json` → `profile_attributes` |
| `frontend/src/components/CohortFilter.tsx` — explanation filter | `EXPLANATION_1_FEATURE_NAME` | `profile_config.json` → `top_explanation_filter` |
| `backend/narrative.py` — `SYSTEM_PROMPT` | `"You are an insurance data analyst..."` | `narrative_config.json` → assembled system prompt |
| `backend/narrative.py` — `USER_TEMPLATE` | `"lapse propensity"`, `"policyholders"`, `"surrender risk"` | `narrative_config.json` fields |
| `backend/config.py` — prediction column | `Lapse_ind_1_PREDICTION` | `PREDICTION_COL` (.env) |
| `backend/config.py` — project/model/dataset IDs | hardcoded defaults | `.env` — no defaults |
| `backend/cohort.py` — warning threshold | `30` | `COHORT_WARNING_MIN_ROWS` (.env) |
| `backend/cohort.py` — top features | `5` | `TOP_FEATURES_PER_GROUP` (.env) |
| `backend/narrative.py` — `max_tokens` | `700` | `NARRATIVE_MAX_TOKENS` (.env) |
| `backend/narrative.py` — groups in prompt | `6` | `NARRATIVE_GROUPS_IN_PROMPT` (.env) |
| `backend/narrative.py` — features per group | `2` | `NARRATIVE_FEATURES_PER_GROUP` (.env) |
| `backend/narrative.py` — outcome note wording | `"OBSERVED LAPSE RATE"` | `narrative_config.json` → `outcome_label` |

**Steps to migrate the IL app to the generic framework:**

1. Create `narrative_config.json` using the insurance lapse values from Section 9.1.
2. Create `profile_config.json` using the IL filter columns from `CohortFilter.tsx`.
3. Move `project_id`, `model_id`, `scoring_dataset_id` from hardcoded defaults in `config.py` to required env vars.
4. Add `APP_TITLE` and `APP_SUBTITLE` to `.env`.
5. Replace the hardcoded `SYSTEM_PROMPT` and `USER_TEMPLATE` in `narrative.py` with the parameterised template (reading labels from `narrative_config.json`).
6. Add `GET /api/config` endpoint; update the React frontend to read title, labels, and sidebar layout from this endpoint rather than hardcoded constants.
7. Update `CohortFilter.tsx` to render filter controls from `/api/config` → `profile_attributes` rather than hardcoded column names.

---

## 11. Open questions and caveats

| # | Question | Impact |
|---|---|---|
| 1 | **SHAP additivity check**: is a runtime check on explanation additivity feasible, or should this be documented as a deployment prerequisite only? | Minor — affects whether to show the XEMP warning banner |
| 2 | **Auto-detection of `PREDICTION_COL`**: DataRobot's naming convention is `{target}_PREDICTION`. Should the auto-detection also handle `{target}_1_PREDICTION` (binary positive class) vs `{target}_0_PREDICTION`? | Affects correctness for models where target has multiple values |
| 3 | **Group colour palette**: how many groups can the auto-assigned colour palette support before collisions? Should users be able to specify group colours in `feature_group_mapping.json`? | UX — up to ~8 groups are comfortable with a qualitative palette |
| 4 | **Cardinality guard for multiselect (200 values)**: is top-200-by-frequency the right cut? Should there be a search box instead? | UX for high-cardinality columns like postal codes |
| 5 | **CSV mode and PE columns**: some deployments export DataRobot explanations with column name variants (`Explanation_N_feature_name` vs `EXPLANATION_N_FEATURE_NAME`). Should the config accept a case-insensitive match or require exact column names? | Affects CSV mode compatibility |
| 6 | **Training dataset join**: if the scored population (top-5%) and the training population are different row sets, the outcome rate is only computable for the intersection. How should zero-match be handled? | Minor — show N/A in the profile view |
| 7 | **Privacy — narrative prompt**: aggregate statistics (mean spend, % smoker) could be identifying if the cohort is small. The `COHORT_WARNING_MIN_ROWS` guard addresses this partially. Is a minimum cohort size hard block needed for the narrative? | Privacy / governance decision |
| 8 | **Feature group mapping validation**: should unrecognised features (in dataset but not in mapping) silently go to "Other", or should a startup warning list them explicitly? | Operational — helps config authors spot typos |
