# Example configurations

The app ships with one **active** config (`backend/feature_group_mapping.json`,
`backend/profile_config.json`, `backend/narrative_config.json`, and whichever
`.env` is in place). Each example below is a set of `-example` reference files
you copy over the active ones to switch domains — no code changes required.

| Example | Target type | Files |
|---|---|---|
| **Motor claim fraud detection** | Binary classification | `backend/.env.fraud-example` |
| **Manufacturing — remaining useful life (RUL)** | Regression (numeric target) | `backend/.env.manufacturing-example`, `backend/feature_group_mapping.manufacturing-example.json`, `backend/profile_config.manufacturing-example.json`, `backend/narrative_config.manufacturing-example.json` |

## Manufacturing — Remaining Useful Life (RUL)

Predicts `rul_days` — days until failure — for heavy equipment (synthetic
Caterpillar-style fleet) from sensor telemetry: oil pressure, coolant temp,
vibration, hydraulic pressure, etc. See
[`manufacturing_rul_source/`](../manufacturing_rul_source/README.md) to
retrain the model or regenerate the subsamples below.

- **Model**: a fresh Quick-Autopilot regression project trained on a 30k-row
  sample of `manufacturing_rul_source/training_data.csv` (filtered to the
  approaching-failure regime, `rul_days` 0–30). `asset_id` is excluded from
  the feature list so the model learns from sensor/context signal, not
  machine identity.
- **Scoring sample**: `data/manufacturing_rul_scoring_sample.csv` — 1,657
  telemetry readings from a held-out eval set, stratified so both healthy
  (RUL near the 30-day cap) and near-failure assets are represented. Scored
  with a real DataRobot batch prediction job (`explanation_algorithm=shap`),
  so the `EXPLANATION_N_*` columns are genuine SHAP values — additivity
  checked directly (`SHAP_BASE_VALUE` + strengths + `SHAP_REMAINING_TOTAL` ==
  prediction to ~1e-10).
- **DataRobot resources**: project `6a7488275a589c879326e74d`, model
  `6a748a955bd1af802e86f383` (LightGBM Regressor w/ Early Stopping, validation
  RMSE 4.09), deployment `6a748b20ddc31eeea5d9c1a1`. Left running — delete
  them from the DataRobot UI if you don't want to keep them.
- **Reference training sample**: `data/manufacturing_rul_training_sample.csv`
  — the 30k-row sample used to train the demo model; not required at app
  runtime in CSV mode.
- **Mode**: `DATA_SOURCE=csv` — fully self-contained, no live DataRobot calls
  needed to run the demo. `PREDICTION_COL` auto-detects to `rul_days_PREDICTION`.

### Activate it

```bash
cp backend/.env.manufacturing-example backend/.env
cp backend/feature_group_mapping.manufacturing-example.json backend/feature_group_mapping.json
cp backend/profile_config.manufacturing-example.json backend/profile_config.json
cp backend/narrative_config.manufacturing-example.json backend/narrative_config.json
```

Then add an LLM provider (see the main `.env.template`) if you want the AI
narrative, and start the app as usual.

### Known limitation exercised by this example

`OUTCOME_COL` (optional; enables an "observed outcome rate" line in the
narrative) is formatted in `narrative.py` as a **percentage**
(`f"{outcome_rate:.1%}"`), which only makes sense for a binary 0/1 column. For
a continuous target like `rul_days`, `pd.Series.mean()` still computes fine
(e.g. a mean of 12.3 days), but it would render as a nonsensical percentage
("1230.0%"). This example leaves `OUTCOME_COL` unset and instead carries the
true holdout value as a plain reference column
(`actual_rul_days_holdout`, shown in the cohort profile) so predicted-vs-actual
is still visible without exercising the bug.
