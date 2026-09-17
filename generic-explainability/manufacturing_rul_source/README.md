# Manufacturing RUL — source data & reproducibility

This folder preserves what's needed to **retrain the model and regenerate the
subsamples** behind the manufacturing/RUL example in `../data/` and
`../backend/*.manufacturing-example.*`. See `../docs/examples.md` for the
full example writeup and `../README.md` for how to run the app with it.

## What's here

| File | What it is |
|---|---|
| `training_data.csv` | Full 370,161-row reproducible training set (hourly telemetry, already filtered to `rul_days <= 30` — the approaching-failure regime — by the upstream team's `train.py`) |
| `eval_dataset.csv` | Full 44,525-row out-of-sample eval world (different synthetic-data seed than training) |
| `build_subsamples.py` | Regenerates the training/scoring subsamples (deterministic — fixed `random_state`) |
| `train_and_score.py` | Trains a fresh DataRobot regression project on the training subsample, deploys it, and batch-scores the scoring subsample with real SHAP explanations — this is the exact script that produced the currently-committed example data |
| `upstream/` | The original `train.py` / `predict_eval.py` / `config.py` / `synth_common.py`, kept for context on where `training_data.csv`'s filtering logic and column set came from |

## Regenerating from scratch

```bash
cd generic-explainability/manufacturing_rul_source
pip install pandas datarobot
python build_subsamples.py       # -> ../data/manufacturing_rul_training_sample.csv
                                  # -> scoring_sample_raw.csv (no SHAP yet)
python train_and_score.py        # trains + deploys on DataRobot, scores with
                                  # real SHAP -> ../data/manufacturing_rul_scoring_sample.csv
```

`train_and_score.py` reads its DataRobot token from
`../backend/.env.manufacturing-example` — put a real token there first (or
export `DATAROBOT_API_TOKEN`/`DATAROBOT_ENDPOINT`). Each run creates a **new**
project/model/deployment on whichever account the token points to; it does
not reuse the original `6a7488275a589c879326e74d` project.

## Important caveat: `upstream/train.py` no longer runs as-is

The upstream `train.py` regenerates `training_data.csv` from a raw telemetry
source file that isn't included here. `training_data.csv` in this folder is
that script's **frozen output**, kept so retraining doesn't depend on the
generator. If you need to change the `rul_days <= 30` filter, resample with a
different seed, or use a different scale/asset count, you'd need the
original synthetic-data generator.

`upstream/train.py` also uses date-partitioned validation and trains on the
raw telemetry columns *including* `asset_id` (matching the original team's
full pipeline). `train_and_score.py` in this folder deliberately differs —
it excludes `asset_id` from the feature list and uses plain random-CV
partitioning — because the goal here is a demo of SHAP explainability driven
by sensor signal, not a reproduction of the original model's exact validation
methodology.
