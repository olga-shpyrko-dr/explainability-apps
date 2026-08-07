# Model B — `rul_days` (Remaining Useful Life)

Predicts days-to-failure for an asset. **Non-time-series regression** trained on
the approaching-failure regime only.

## Train
```bash
cd 1_ts_models/model_b_rul
python train.py                       # regenerate training_data.csv → project → Autopilot → deploy
```
`train.py` regenerates `training_data.csv` from
`0_synthetic_data/output_subset/asset_telemetry.csv`, keeping **only rows with
`rul_days ≤ 30`** (genuinely approaching failure) so the target spans 1..30
instead of being dominated by the "no upcoming failure" sentinel. Base
sensor/context predictors only; out-of-time validation on `timestamp`.

## Predict / eval
```bash
python predict_eval.py                # min predicted RUL per machine → eval/rul_predictions.csv
```
Scores recent rows per machine and reports the minimum predicted RUL (most urgent).

## Deployment
`6a31e9f96b93b06420d2c4ed` (label `Caterpillar — rul_days (synthetic)`, tag `tool`).

## Notes
- **Why non-TS + filtered:** the first version was TS with `rul` capped at 30, so
  ~87% of rows were 30 and the model regressed to the mean (predicted ~25 when
  the truth was ~3 days). Training only on `rul ≤ 30` fixed the discrimination
  (failing machines now predict 2.5–6.6 days, healthy 14+).
- Filtering rows requires non-TS (it would break TS cadence).
