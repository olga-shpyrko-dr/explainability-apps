"""
Trains a fresh rul_days regression model on DataRobot, deploys it, and batch-
scores the held-out sample with real SHAP prediction explanations — exactly
the pipeline that produced the manufacturing RUL example bundled with this
app (project 6a7488275a589c879326e74d, model 6a748a955bd1af802e86f383,
deployment 6a748b20ddc31eeea5d9c1a1 on the account this was originally run
against; running it again creates new resources on whichever account
DATAROBOT_API_TOKEN points to).

Prerequisites:
  pip install datarobot pandas
  Run build_subsamples.py first (needs ../data/manufacturing_rul_training_sample.csv
  and scoring_sample_raw.csv in this folder).
  backend/.env.manufacturing-example (or backend/.env) must have a real
  DATAROBOT_API_TOKEN / DATAROBOT_ENDPOINT set.

Run:
  python train_and_score.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import datarobot as dr
import pandas as pd
from datarobot.enums import AUTOPILOT_MODE, TARGET_TYPE

HERE = Path(__file__).resolve().parent
REPO = HERE.parent  # generic-explainability/
ENV_FILE = REPO / "backend" / ".env.manufacturing-example"

TRAIN_CSV = REPO / "data" / "manufacturing_rul_training_sample.csv"
SCORE_CSV = HERE / "scoring_sample_raw.csv"
OUT_SCORE_CSV = REPO / "data" / "manufacturing_rul_scoring_sample.csv"
BATCH_OUT_CSV = HERE / "batch_output.csv"  # intermediate; safe to delete after

TARGET = "rul_days"
ROW_ID_COL = "reading_id"
PROJECT_NAME = "Manufacturing RUL Explainability Demo (synthetic)"
DEPLOYMENT_LABEL = "Manufacturing RUL Explainability Demo (synthetic)"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_env() -> dict:
    env = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def main() -> None:
    env = load_env()
    token = env.get("DATAROBOT_API_TOKEN") or sys.exit(
        f"Set a real DATAROBOT_API_TOKEN in {ENV_FILE} (or export it) before running this."
    )
    endpoint = env.get("DATAROBOT_ENDPOINT", "https://app.datarobot.com/api/v2")
    dr.Client(token=token, endpoint=endpoint)
    log(f"Connected to {endpoint}")

    # ------------------------------------------------------------------
    # 1. Project + Quick Autopilot on rul_days (regression)
    # ------------------------------------------------------------------
    log(f"Creating project from {TRAIN_CSV.name}…")
    project = dr.Project.create(sourcedata=str(TRAIN_CSV), project_name=PROJECT_NAME)
    log(f"Project created: {project.id}  ({project.project_name})")

    all_features = [f.name for f in project.get_features()]
    predictors = [f for f in all_features if f not in ("asset_id", TARGET)]
    fl = project.create_featurelist("sensor_and_context_only", predictors)
    log(f"Feature list '{fl.name}' ({len(predictors)} features, asset_id excluded to avoid identity leakage)")

    project.analyze_and_model(
        target=TARGET,
        target_type=TARGET_TYPE.REGRESSION,
        mode=AUTOPILOT_MODE.QUICK,
        featurelist_id=fl.id,
        worker_count=-1,
    )
    log("Autopilot started — waiting for completion (this can take several minutes)…")
    project.wait_for_autopilot(check_interval=20.0, timeout=3600)
    log("Autopilot complete.")

    models = project.get_models()
    metric = project.metric
    log(f"=== Top models by {metric} ===")
    for i, m in enumerate(models[:5], 1):
        log(f"  {i}. {m.metrics.get(metric, {}).get('validation')!s:>10}  {m.model_type}")

    try:
        model = dr.ModelRecommendation.get(project.id).get_model()
        log(f"Recommended model: {model.model_type} ({model.id})")
    except Exception as e:
        model = models[0]
        log(f"No recommendation available ({e}); using top model: {model.model_type} ({model.id})")

    # ------------------------------------------------------------------
    # 2. Deploy
    # ------------------------------------------------------------------
    servers = dr.PredictionServer.list()
    deployment = dr.Deployment.create_from_learning_model(
        model_id=model.id,
        label=DEPLOYMENT_LABEL,
        description="Synthetic Caterpillar telemetry — rul_days regression demo for the generic-explainability app.",
        default_prediction_server_id=servers[0].id if servers else None,
    )
    log(f"Deployed: {deployment.id}  ({DEPLOYMENT_LABEL})")

    # ------------------------------------------------------------------
    # 3. Batch score the held-out sample with SHAP explanations
    # ------------------------------------------------------------------
    log(f"Scoring {SCORE_CSV.name} with SHAP prediction explanations…")
    job = dr.BatchPredictionJob.score(
        deployment=deployment.id,
        intake_settings={"type": "localFile", "file": str(SCORE_CSV)},
        output_settings={"type": "localFile", "path": str(BATCH_OUT_CSV)},
        passthrough_columns=[ROW_ID_COL],
        max_explanations=4,
        explanation_algorithm="shap",
        num_concurrent=4,
    )
    job.wait_for_completion()
    log(f"Batch prediction complete -> {BATCH_OUT_CSV}")

    batch_out = pd.read_csv(BATCH_OUT_CSV)
    log(f"Batch output: {batch_out.shape[0]} rows x {batch_out.shape[1]} cols")

    # ------------------------------------------------------------------
    # 4. Merge explanations into the full scoring sample
    # ------------------------------------------------------------------
    score_df = pd.read_csv(SCORE_CSV)
    pred_expl_cols = [
        c for c in batch_out.columns
        if c.upper().endswith("_PREDICTION") or "EXPLANATION_" in c.upper()
    ]
    merged = score_df.merge(
        batch_out[[ROW_ID_COL] + pred_expl_cols].drop_duplicates(subset=[ROW_ID_COL]),
        on=ROW_ID_COL,
        how="left",
    )
    merged.to_csv(OUT_SCORE_CSV, index=False)
    log(f"Final explained scoring sample -> {OUT_SCORE_CSV}  ({merged.shape[0]} rows x {merged.shape[1]} cols)")

    log("\n=== SUMMARY ===")
    log(f"project_id:    {project.id}")
    log(f"model_id:      {model.id}  ({model.model_type})")
    log(f"deployment_id: {deployment.id}")
    log(f"featurelist_id:{fl.id}")
    log("\nUpdate backend/.env.manufacturing-example's provenance comment block "
        "with these new IDs if you want them reflected there.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
