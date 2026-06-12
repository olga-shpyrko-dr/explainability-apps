# Enhanced Explainability App — Project Specification

**Version:** 0.1 (MVP)
**Model:** Protection Lapse Propensity (under-55 cohort, excl. UL)
**Date:** 2026-05-26

---

## Table of contents

1. [Problem statement](#1-problem-statement)
2. [Solution overview](#2-solution-overview)
3. [Data inputs](#3-data-inputs)
4. [Feature grouping strategy](#4-feature-grouping-strategy)
5. [Application modules](#5-application-modules)
6. [LLM narrative layer](#6-llm-narrative-layer)
7. [Technical architecture](#7-technical-architecture)
8. [MVP scope and phasing](#8-mvp-scope-and-phasing)
9. [Open questions and caveats](#9-open-questions-and-caveats)
10. [References](#10-references)

---

## 1. Problem statement

DataRobot provides row-level prediction explanations for every model it builds. In practice, these are difficult to act on because:

- Features are often correlated; individual explanation strengths shift depending on which correlated features appear in the top-N for a given row.
- Models with many features and complex interaction patterns make it hard to identify the dominant business drivers — even when individual row explanations are accurate, the signal is spread across numerous features in ways that obscure the underlying pattern.
- There is no cohort-level view: analysts must inspect individual rows or build custom aggregations outside the platform.
- End users (advisers, actuaries, retention teams) need plain-language insight into *why* a segment is high-risk, not a raw list of feature names and SHAP values.

---

## 2. Solution overview

The app adds three layers on top of standard DataRobot prediction outputs:

| Layer | What it does |
|---|---|
| **Cohort filter & profile** | Slice the scored population by any feature; inspect the distribution of key fields in the selected segment |
| **Grouped explanations** | Aggregate SHAP values by business-domain feature group; surface combined group impact alongside drill-down to individual features |
| **LLM narrative** | Generate a plain-English summary of the selected cohort's profile and the drivers of their lapse propensity |

SHAP (not XEMP) is used throughout so that explanation values are additive and group-level sums are mathematically valid.

---

## 3. Data inputs

### 3.1 MVP files

All three files represent the **top-5% highest-scoring policies** from their respective populations (~6,800 rows ≈ 5% of ~136,000 total policies). The full training and scoring populations are not included in the MVP files.

| File | Rows | Columns | Role |
|---|---|---|---|
| `…Training…(full dataset).xlsx` | 6,822 | 173 | Top-5% of the training population; all source features + outcome label (`Lapse_ind`). Primary input for feature analysis, feature clustering, and simulating SHAP explanations across a labelled cohort. |
| `…Training…M40BP69.xlsx` | 6,822 | 25 | Same training cohort scored by the deployed model; cross-validation + deployment predictions, top-4 explanations. |
| `…Scoring…M40BP69.xlsx` | 6,668 | 196 | Top-5% of the current live scoring population; deployment predictions, top-4 SHAP explanations, plus all source features. Primary runtime data source for the app. |

The scoring file is the primary runtime data source for the app. The training files add outcome labels and cross-validation predictions useful for calibration views and explanation simulation.

> **Caveat — population coverage:** Feature distributions and group SHAP aggregations derived from these files reflect only the highest-risk cohort. They are not representative of the full policy portfolio and should not be used to draw conclusions about the average policyholder.

### 3.2 Schema alignment

The full training dataset (173 cols) and the scoring file's source feature columns (171 cols) are aligned: the only columns in training but absent from scoring are `Status_Cd` and `Status_Desc` (policy status at training time, not needed at score time). All 171 model input features are present in both files — no normalisation required to join training features with scored output.

### 3.3 Key column inventory

**Identity & outcome**

| Column | File(s) | Role |
|---|---|---|
| `Policy_Number` | All | Row ID (configurable app parameter) |
| `Lapse_ind` | Training | Actual lapse outcome (binary target) |
| `Lapse_ind_1_PREDICTION` | Scoring | Lapse propensity score (0–1) |
| `Precentile`, `Decile`, `20-quantile` | Scoring | Pre-computed rank bands |

**Explanation slots** (×4, scoring file)

```
EXPLANATION_{N}_FEATURE_NAME
EXPLANATION_{N}_STRENGTH             ← signed SHAP value (additive)
EXPLANATION_{N}_ACTUAL_VALUE
EXPLANATION_{N}_QUALITATIVE_STRENGTH ← +++/++/+/-/--/---
```

**Source features (171)** — available in both training and scoring files; all usable for filtering, profile display, and feature clustering. See Section 4 for domain mapping.

### 3.4 Schema notes and caveats

- `EXPLANATION_N_STRENGTH` is a signed numeric SHAP value. Confirm with DataRobot deployment settings that SHAP (not XEMP) is configured — the qualitative strength field (`+++` etc.) is a separate discretised representation.
- Features not appearing in any explanation slot have no SHAP value in the unpivoted frame. Do not impute zero — treat as absent for group aggregation and track coverage % per group separately.

---

## 4. Feature grouping strategy

### 4.1 Business-domain groups (MVP)

Eight groups proposed based on the scoring file feature inventory. These are the primary grouping mechanism for the MVP.

| Group | Representative features | Feature count |
|---|---|---|
| **Policy & Product** | `Product_Desc`, `Cover_Shrt_Nm`, `Benefit Combos Detailed`, `AP_Amt`, `Term`, `Commencement_Date`, `Maturity_Date`, `TTG_v2`, `IndexationDesc` | ~16 |
| **Policy Portfolio** | `ProtPolsIF_Life1/2`, `MortgPolsIF_Life1/2`, `WOLPolsIF_Life1/2`, `ProtPolsOOF_Last2yrs_*`, Sum-assured fields | ~17 |
| **Agent / Adviser** | `Sl_Level3/6_Shortname`, `Servicing_Agent_Cd`, `AuthorisedAdvisor`, `Source_Of_Business`, `Pols_IF_PerAgent`, `CommissionScaleCode` | ~8 |
| **Sociodemographic** | `Age_life1/2`, `Gender`, `SmokerStatus`, `JobTitle_L1`, `FamilyStatusName_L1`, `EmploymentStatus_L1`, `NumberofDependents_L1` | ~11 |
| **Financial Profile** | `NetIncomeAmount_L1`, `SalaryAmount_L1`, `TotalIncome_L1`, `HouseholdDisposableIncomeMonthly_L1`, `FamilyHomeOutstandingBalance_L1`, `TotalLoansOutstandingBalance_L1` | ~12 |
| **Expenditure** | `FoodMonthlyAmount_L1`, `MotorMonthlyAmount_L1`, `OtherExpensesMonthlyAmount_L1`, `ChildCareMonthlyAmount_L1`, `HolidyMonthlyAmount_L1`, `MedicalMonthlyAmount_L1` | ~8 |
| **Engagement & Reviews** | `OnlineServiesLogins_Last12Months_Life1/2`, `MonthsSinceReview`, `ReviewType_L1/L2`, `DiscussedDeathProtection_L1`, `DiscussedMortgages_L1` | ~10 |
| **Persona** | `PersonaDesc_1`, `PersonaDesc_2` | 2 |

The group-to-feature mapping is stored in a configuration file (JSON or SQL lookup table) so business users can adjust without code changes.

### 4.2 Alternative / complementary grouping methods

These are not required for MVP but are the recommended path to grouping automation in v2.

| Method | Description | Reference |
|---|---|---|
| **Pairwise correlation clustering** | DBSCAN or affinity propagation on a correlation distance matrix of source features; produces data-driven clusters independent of domain labels | Feature Clustering notebook (attached) |
| **ACE correlation to target** | Rank features by alternating conditional expectation score against target; group by ACE band (high / medium / low predictive signal) | — |
| **Feature impact from DataRobot model** | Use permutation feature impact scores from the deployed model to rank within and across groups; useful for ordering groups by importance | DataRobot Feature Impact API |
| **Explanation-space clustering** | Flatten top-N SHAP values per row into a feature × row matrix; apply UMAP + HDBSCAN to find explanation archetypes | UMAP/HDBSCAN notebook (attached) |

### 4.3 Group SHAP aggregation

For a given set of rows (selected cohort):

1. Unpivot the four explanation slots into a long table: `(Policy_Number, Feature, SHAP_strength)`.
2. Left-join to the group mapping table to assign each feature a group.
3. For features not appearing in any explanation slot, `SHAP_strength = NULL` (excluded from group totals — not assumed zero).
4. Aggregate: `group_shap = SUM(SHAP_strength)` per group per row, then average across cohort.
5. Sort groups by `|avg_group_shap|` descending.

> **Caveat:** With only top-4 explanations, group SHAP totals are partial — they reflect only the most impactful features per row. A group with many moderate features may be underrepresented vs. a group with one dominant feature. Flag this in the UI ("based on top-4 explanations only").

---

## 5. Application modules

### 5.1 Module 1 — Cohort filter & profile

**Purpose:** Define the population subset to be analysed in Modules 2 and 3.

#### 5.1.1 Group profile

- Score distribution: histogram of `Lapse_ind_1_PREDICTION` for full population and filtered segment (overlay).
- Key demographic breakdowns: decile/quantile distribution, age bands, product type, premium band, smoker status.
- Comparison table: filtered segment vs. full scored population (mean / median / top-decile rate for key fields).
- Row count and % of total population shown prominently.

#### 5.1.2 Filters

Filters apply to any source feature in the scoring file. Suggested pre-built filters:

| Filter | Type |
|---|---|
| Score decile / percentile | Range slider |
| Product description | Multi-select |
| Age band (life1) | Range |
| Smoker status | Toggle |
| Adviser / SL Level 6 | Multi-select |
| Policy commencement year | Range |
| Annual premium band | Multi-select |
| Months since last review | Range |

All filters are additive (AND logic). Filtered row count updates live.

#### 5.1.3 Individual row / CSV selection

- **Single row**: search by `Policy_Number`; displays that row's full feature values and its position in the score distribution.
- **CSV upload**: upload a file containing a list of `Policy_Number` values; the union of those rows becomes the cohort for Modules 2 and 3. The row ID column name is a configurable app parameter (default: `Policy_Number`).

---

### 5.2 Module 2 — Grouped explanations

**Purpose:** Quantify the contribution of each business-domain group to lapse propensity in the selected cohort.

#### 5.2.1 Group summary view (default)

- Horizontal bar chart: one bar per group, showing `avg_group_shap` (signed).
- Bars coloured by direction: red = increases propensity, blue = decreases.
- Groups sorted by absolute value.
- Tooltip: group name, mean SHAP contribution, number of rows in cohort where this group appears in top-4, % coverage.

#### 5.2.2 Feature drill-down (on demand)

User clicks a group bar to expand:
- Individual feature bars within the group (same avg SHAP treatment).
- Feature value distribution: for the top 2–3 features in the group, show the distribution of actual values for the cohort vs. full population.
- Coverage note: "X of N features in this group appeared in top-4 explanations for at least one row."

#### 5.2.3 Individual row view

When a single `Policy_Number` is selected (Section 5.1.3):
- Waterfall chart of the four explanation slots (SHAP waterfall: baseline → feature 1 → feature 2 → feature 3 → feature 4 → final score).
- Group colour coding applied to each bar.
- Actual feature value displayed on each bar.

---

### 5.3 Module 3 — LLM narrative summary

**Purpose:** Translate the cohort profile and explanation data into a plain-language summary for non-technical users.

#### 5.3.1 Input to LLM

The prompt includes:
- Cohort size and filter criteria applied.
- Score distribution summary (mean, median, % in top decile).
- Top 3–4 groups by absolute SHAP contribution with their direction and magnitude.
- Top 2–3 individual features from each leading group, with cohort-average actual values and comparison to full population.
- Outcome rate (if training labels are available for the cohort).

#### 5.3.2 Output format

Two paragraph types:
1. **Profile summary**: who is in this cohort — demographics, product, financial characteristics that distinguish them from the overall population.
2. **Driver summary**: what is driving their high (or low) lapse propensity — leading groups, specific features, direction of effect.

Optionally: a recommended action sentence (e.g., "Prioritise outreach to policyholders with `FoodMonthlyAmount_L1` above €800 and no review in the last 12 months.").

#### 5.3.3 Regeneration and editing

- User can regenerate with a custom instruction appended to the prompt (e.g., "Focus on financial stress indicators" or "Write for a financial adviser audience").
- Output is copyable as plain text or formatted for export.

---

## 6. LLM narrative layer

### 6.1 Model and API

Use DataRobot's LLM integration (as in the Predictive Content Generator template). For the standalone MVP on sample data, call the Anthropic API directly (`claude-sonnet-4-20250514`) via a Python backend or a React artifact using the `/v1/messages` endpoint.

### 6.2 Prompt template (draft)

```
You are an insurance data analyst summarising model outputs for a retention team.

COHORT: {n_rows} policies filtered by {filter_description}.
SCORE DISTRIBUTION: mean={mean_score:.2f}, median={median_score:.2f}, {pct_top_decile:.0f}% in top decile.

TOP EXPLANATION GROUPS (average SHAP contribution, cohort):
{group_table}

KEY FEATURE VALUES VS POPULATION:
{feature_comparison_table}

Write two short paragraphs:
1. Profile: describe who these policyholders are based on the feature values above.
2. Drivers: explain what is driving their lapse propensity scores, using plain language a financial adviser would understand. Avoid technical terms like "SHAP" — refer to "factors increasing / reducing surrender risk."
```

### 6.3 Caveats on LLM output

- LLM output must not be presented as actuarial fact; include a disclaimer ("AI-generated summary — for indicative use only").
- Do not pass `Policy_Number` or individual policyholder names into the LLM prompt; aggregate statistics only.
- If the cohort is fewer than ~30 rows, warn that group-level averages may not be stable.

---

## 7. Technical architecture

### 7.1 MVP (Power BI / SQL path)

The MVP delivers Modules 1 and 2 (cohort profile + grouped explanations) via Power BI. **The LLM narrative (Module 3) is out of scope for this path** — deferred to the v2 DataRobot-hosted app.

```
Excel files (Scoring + Training)
        |
        v
  extract_to_sql.py  (batch script; re-run each scoring cycle)
  +----------------------------------------------+
  | 1. Load scoring file; normalise column names |
  | 2. Unpivot 4 explanation slots -> long table |
  | 3. LEFT JOIN to feature_group_mapping        |
  | 4. Write 3 tables to SQL / CSV               |
  +----------------------------------------------+
        |
        v
  SQL (3 tables, imported into Power BI)
  +------------------------------------------+
  | scored_population                         |  <- one row per policy; all source features + score
  | explanation_long                          |  <- (row_id, feature, shap, group, rank)
  | feature_group_mapping                     |  <- config: feature_name -> feature_group
  +------------------------------------------+
        |
        v
  Power BI (Import mode)
  +-- Page 1: Cohort filter & profile
  |     slicers on scored_population columns
  |     DAX measures: mean/median score, row count, % of total
  |     score distribution histogram
  +-- Page 2: Group explanations + feature drill-down
        DAX measures on explanation_long via scored_population relationship
        group bar chart sorted by |avg_shap|, coloured by direction
        feature drill-down on group select
        coverage % annotation per group
```

**Group SHAP aggregation on slicer change** is handled entirely in DAX — no pre-computation or Python required at query time. Power BI Import mode holds all ~27k explanation rows (4 slots x 6,800 policies) in memory; DAX `CALCULATE` filters `explanation_long` through the active slicer context on `scored_population` via the `Policy_Number` relationship, recalculating live on every slicer change.

The `group_shap_by_cohort` pre-aggregated table (previously listed) is dropped — unnecessary with DAX measures and would require rebuild on every filter change anyway.

### 7.2 Generic DataRobot-hosted app (v2 path)

For a deployable, parameterisable app hosted in DataRobot:

```
DataRobot Deployment (any model)
        │  Prediction + Explanation API
        ▼
  Python backend (FastAPI or DataRobot App)
  ├── Feature group config loader
  ├── SHAP aggregation engine
  ├── Cohort filter engine
  ├── LLM prompt builder + API caller
  └── REST endpoints for frontend
        │
        ▼
  React frontend (af-components or lightweight)
  ├── CohortFilter component
  ├── GroupExplanationChart (recharts / D3)
  ├── FeatureDrillDown component
  ├── WaterfallChart (single row)
  └── NarrativePanel (LLM output)
```

The app accepts three configuration parameters at startup:
- `deployment_id`: DataRobot deployment to pull scores from
- `row_id_column`: name of the row identifier field (default: `Policy_Number`)
- `group_config_path`: path to JSON file defining feature → group mapping

### 7.3 Output table schemas

**`scored_population`** (~6,800 rows × 171 columns)

| Column | Type | Description |
|---|---|---|
| `Policy_Number` | string | Primary key / row ID |
| `Lapse_ind_1_PREDICTION` | float | Lapse propensity score (0–1) |
| `Decile`, `Percentile` | int / float | Pre-computed rank bands |
| `Lapse_ind` | int | Actual outcome (training set only; NULL for scoring-only rows) |
| *(171 source feature columns)* | mixed | All model input features; used for slicers and profile display |

**`explanation_long`** (~27,000 rows — 4 slots × 6,800 policies)

| Column | Type | Description |
|---|---|---|
| `row_id` | string | Foreign key → `scored_population.Policy_Number` |
| `explanation_rank` | int | 1–4 (1 = strongest) |
| `feature_name` | string | Feature name as returned by DataRobot |
| `shap_strength` | float | Signed SHAP value (additive) |
| `actual_value` | string | Feature value for this row |
| `qualitative_strength` | string | `+++`/`++`/`+`/`-`/`--`/`---` |
| `feature_group` | string | Assigned group label (from `feature_group_mapping`) |

**`feature_group_mapping`** (config table; ~84 rows)

| Column | Type | Description |
|---|---|---|
| `feature_name` | string | Primary key |
| `feature_group` | string | Business domain group label |

Group SHAP aggregations are not materialised — they are computed as DAX measures at query time using the relationship between `explanation_long` and `scored_population`.

---

## 8. MVP scope and phasing

### Phase 1 — Extraction pipeline + SQL tables (week 1)

- [ ] Write `extract_to_sql.py`: load scoring Excel file, unpivot 4 explanation slots into long format, LEFT JOIN `feature_group_mapping`, write 3 output tables to SQL database (or CSV for initial Power BI import).
- [ ] Confirm `feature_group_mapping.json` covers all feature names that appear in `EXPLANATION_N_FEATURE_NAME` columns; add any missing entries as "Other" or assign to correct group.
- [ ] Validate: spot-check `shap_strength` values in `explanation_long` against raw `EXPLANATION_N_STRENGTH` in the source file for five sample policies.

### Phase 2 — Power BI report (week 1–2)

- [ ] Connect Power BI to the 3 SQL tables; define the `Policy_Number` relationship between `scored_population` and `explanation_long`.
- [ ] Page 1 (Cohort profile): slicers for decile, product, age band, smoker status, adviser; score distribution histogram; cohort vs. full population comparison card.
- [ ] Page 2 (Group explanations): DAX measures for `avg_shap` and `coverage_pct` per group; horizontal bar chart sorted by `|avg_shap|`; feature drill-down on group select showing top features and their actual value distributions.
- [ ] Validate: confirm DAX group SHAP totals match manual calculation for a fixed filter combination.

### Phase 3 — Individual row view (week 2–3)

- [ ] Policy Number slicer / search to isolate a single row.
- [ ] Waterfall chart for the 4 explanation slots (Deneb custom visual or horizontal bar chart fallback).
- [ ] Row detail card: key feature values, score percentile, actual outcome (if available).

### Phase 4 — Generalisation (v2 DataRobot-hosted app, post-MVP)

- [ ] FastAPI + React app (existing backend codebase) with configurable `deployment_id` and `row_id_column`.
- [ ] LLM narrative module (Module 3) — on-demand cohort summary via DataRobot LLM Gateway or Azure OpenAI.
- [ ] Automated group generation via correlation clustering (Feature Clustering notebook).
- [ ] UMAP + HDBSCAN explanation-space clustering to identify explanation archetypes across the scored population.
- [ ] User-editable group configuration in the UI.

---

## 9. Open questions and caveats

| # | Question | Impact |
|---|---|---|
| 1 | Are `EXPLANATION_N_STRENGTH` values in the scoring file true SHAP values (additive, centred at base rate) or a DataRobot-proprietary scale? | Determines whether group sums are interpretable as probability-scale contributions |
| 2 | Is the training file explanation format (XEMP) intentional, or can SHAP be re-requested? | If XEMP, cross-file comparison of explanation magnitudes is not valid |
| 3 | What is the model base rate (average prediction)? Needed for waterfall chart anchor | Minor; derivable from the data |
| 4 | Should group membership be static (business-defined) or dynamic (data-driven per model)? | Architecture decision for v2 |
| 5 | LLM narrative (Module 3) is deferred to the v2 DataRobot-hosted app. The Power BI path has no LLM dependency. | Resolved for MVP; revisit in Phase 4 |
| 6 | Privacy: does the LLM prompt inadvertently expose policyholder data if aggregate values are distinctive enough? | Prompt must use aggregated statistics only; avoid passing `Policy_Number` or adviser names |
| 7 | With only top-4 explanations, groups with diffuse signal (many features, each moderate) will be systematically underweighted. How should this be communicated? | Add coverage % per group to the UI |
| 8 | SHAP generation and explanation-space clustering (Phase 4) ideally require the full training population (~136,000 policies), not just the top-5% cohort in the MVP files. Confirm whether the full dataset can be extracted from source systems and passed through DataRobot for SHAP scoring. | Required for UMAP/HDBSCAN explanation archetype work; top-5% clustering will be biased toward high-risk patterns only |

---

## 10. References

### DataRobot platform

- [DataRobot Prediction Explanations (SHAP)](https://docs.datarobot.com/en/docs/modeling/analyze-models/understand/pred-explain/pe-tabular.html) — row-level SHAP explanation generation and retrieval
- [DataRobot Python Client — PredictionExplanations](https://datarobot-public-api-client.readthedocs-hosted.com/en/stable/autodoc/api_reference.html#prediction-explanations) — API for requesting and downloading explanations
- [DataRobot Feature Impact](https://docs.datarobot.com/en/docs/modeling/analyze-models/understand/fi.html) — permutation feature importance; use for ranking groups
- [DataRobot Hosted Apps (af-components)](https://af.datarobot.com/) — component library for DataRobot-hosted React apps
- [Predictive Content Generator (community template)](https://github.com/datarobot-community/predictive-content-generator) — reference architecture for LLM-over-predictions apps (uses XEMP; this project uses SHAP)

### Explainability methods

- [SHAP (SHapley Additive exPlanations)](https://shap.readthedocs.io/en/latest/) — Lundberg & Lee (2017); additivity property justifies group summation
- [SHAP Waterfall Plots](https://shap.readthedocs.io/en/latest/example_notebooks/api_examples/plots/waterfall.html) — reference for waterfall visualisation
- [UMAP](https://umap-learn.readthedocs.io/en/latest/) — dimensionality reduction for explanation-space clustering (notebook attached)
- [HDBSCAN](https://hdbscan.readthedocs.io/en/latest/) — density-based clustering; handles noise class (-1) automatically (notebook attached)

### Feature clustering

- Feature Clustering Demo notebook — `Feature clustering - DEMO.ipynb` (attached); uses DBSCAN + affinity propagation on pairwise feature correlations via DataRobot API
- [scikit-learn DBSCAN](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.DBSCAN.html)
- [scikit-learn AffinityPropagation](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.AffinityPropagation.html)

### Power BI integration

- [Power BI Python script visuals](https://learn.microsoft.com/en-us/power-bi/connect-data/desktop-python-visuals) — required for LLM API calls and dynamic Python aggregations
- [Power BI DirectQuery with parameters](https://learn.microsoft.com/en-us/power-bi/connect-data/desktop-dynamic-m-query-parameters) — option for parameterised SQL aggregation on filter change

### LLM

- [Anthropic Messages API](https://docs.anthropic.com/en/api/messages) — `/v1/messages` endpoint used for narrative generation
- [DataRobot LLM Blueprint documentation](https://docs.datarobot.com/en/docs/gen-ai/index.html) — for v2 DataRobot-hosted LLM integration
