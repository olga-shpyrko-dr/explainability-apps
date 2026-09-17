"""
Set up accuracy and monitoring for the manufacturing RUL deployment.

Enables, IN THIS ORDER (order matters — association ID + drift tracking
must be enabled on the deployment BEFORE a batch prediction job runs, so
DataRobot's monitoring subsystem records each prediction keyed by the
association ID; predictions made before these settings existed are not
retroactively tracked):
  1. Feature + target drift tracking
  2. Predictions data collection
  3. Association ID settings (reading_id — already present as a column in
     every scoring request, so no scoring-dataset changes needed)
  4. Accuracy metric selection appropriate for a regression target (RMSE,
     MAE, R_SQUARED, MAPE)
  5. A FRESH batch prediction job (does not reuse any pre-existing cache,
     since prior predictions were made before association ID tracking was
     enabled and would not be linkable to submitted actuals)
  6. Submits ground-truth actuals (actual_rul_days_holdout, already present
     in the scoring dataset) so the Accuracy tab has real data to compare
     predictions against

Run: python3 setup_monitoring.py
"""
from __future__ import annotations

import os

import datarobot as dr
import pandas as pd
from datarobot.enums import ACCURACY_METRIC

DEPLOYMENT_ID = "6aaa853bf7fbb3d75c3144e8"
SCORING_DATASET_ID = "6aaa8502ab527827e5dcac0d"
ROW_ID_COL = "reading_id"
ACTUAL_COL = "actual_rul_days_holdout"

MONITORING_BATCH_OUTPUT = "/home/notebooks/storage/generic-explainability/scripts/monitoring/monitoring_batch_output.csv"
SCORING_CSV = "/home/notebooks/storage/generic-explainability/data/manufacturing_rul_scoring_input.csv"


def log(msg: str) -> None:
    print(f"[monitoring-setup] {msg}", flush=True)


def main() -> None:
    dr.Client(
        token=os.environ["DATAROBOT_API_TOKEN"],
        endpoint=os.environ["DATAROBOT_ENDPOINT"],
    )
    deployment = dr.Deployment.get(DEPLOYMENT_ID)
    log(f"Deployment: {deployment.label} ({deployment.id})")

    # ------------------------------------------------------------------
    # 1. Drift tracking
    # ------------------------------------------------------------------
    log("Enabling target + feature drift tracking…")
    deployment.update_drift_tracking_settings(
        target_drift_enabled=True,
        feature_drift_enabled=True,
    )
    log("Drift tracking enabled.")

    # ------------------------------------------------------------------
    # 2. Predictions data collection
    # ------------------------------------------------------------------
    log("Enabling predictions data collection…")
    deployment.update_predictions_data_collection_settings(enabled=True)
    log("Predictions data collection enabled.")

    # ------------------------------------------------------------------
    # 3. Association ID settings (needed for accuracy tracking — links a
    #    prediction to a later-submitted actual via a shared row key)
    # ------------------------------------------------------------------
    log(f"Setting association ID column to '{ROW_ID_COL}'…")
    deployment.update_association_id_settings(
        column_names=[ROW_ID_COL],
        required_in_prediction_requests=False,
    )
    log("Association ID settings updated.")

    # ------------------------------------------------------------------
    # 4. Accuracy metrics selection (regression-appropriate)
    # ------------------------------------------------------------------
    log("Selecting accuracy metrics for regression target…")
    metrics = [
        ACCURACY_METRIC.RMSE,
        ACCURACY_METRIC.MAE,
        ACCURACY_METRIC.R_SQUARED,
        ACCURACY_METRIC.MAPE,
    ]
    result = deployment.update_accuracy_metrics_settings(metrics)
    log(f"Accuracy metrics set: {result}")

    # ------------------------------------------------------------------
    # 4b. Accuracy HEALTH settings — separate from the metric selection
    #    above. This is what drives the deployment's accuracy_health status
    #    rollup (passing/warning/failing) rather than just what's plotted
    #    on the Accuracy tab. Thresholds chosen relative to the deployed
    #    model's own validation RMSE (~7.0 on featurelist BP69_v2):
    #    warn if live RMSE exceeds it by ~15%, fail if it roughly doubles.
    # ------------------------------------------------------------------
    log("Setting accuracy health thresholds (RMSE warning=8.0, failing=14.0)…")
    deployment.update_health_settings(
        accuracy={
            "batchCount": 10000,
            "metric": "RMSE",
            "measurement": "value",
            "warningThreshold": 8.0,
            "failingThreshold": 14.0,
        }
    )
    log("Accuracy health thresholds set.")

    # ------------------------------------------------------------------
    # 5. Run a FRESH batch prediction job now that association ID + drift
    #    tracking are enabled, so this job's predictions are recorded by
    #    DataRobot's monitoring subsystem and linkable to actuals submitted
    #    in step 6. The deployment's association_id_settings (step 3, above)
    #    already declares reading_id as the association ID column — passing
    #    it through here is what makes each scored row's association ID
    #    equal to its reading_id value.
    # ------------------------------------------------------------------
    log("Running a fresh batch prediction job for monitoring linkage…")
    job = dr.BatchPredictionJob.score(
        deployment=DEPLOYMENT_ID,
        intake_settings={"type": "dataset", "dataset": dr.Dataset.get(SCORING_DATASET_ID)},
        output_settings={"type": "localFile"},
        num_concurrent=4,
        passthrough_columns=[ROW_ID_COL],
    )
    job.wait_for_completion()
    with open(MONITORING_BATCH_OUTPUT, "wb") as f:
        job.download(f)
    batch_df = pd.read_csv(MONITORING_BATCH_OUTPUT)
    log(f"Monitoring batch job complete — {len(batch_df)} rows scored and recorded.")

    scoring_df = pd.read_csv(SCORING_CSV)

    pred_col = [c for c in batch_df.columns if c.upper().endswith("_PREDICTION")][0]
    log(f"Prediction column: {pred_col}")

    merged = batch_df[[ROW_ID_COL, pred_col]].merge(
        scoring_df[[ROW_ID_COL, ACTUAL_COL]], on=ROW_ID_COL, how="inner"
    )
    merged = merged.dropna(subset=[ACTUAL_COL])
    log(f"Rows with ground truth to submit as actuals: {len(merged)}")

    actuals_df = pd.DataFrame({
        "association_id": merged[ROW_ID_COL].astype(str),
        "actual_value": merged[ACTUAL_COL].astype(float),
    })

    log("Submitting actuals to the deployment…")
    deployment.submit_actuals(actuals_df)
    log(f"Submitted {len(actuals_df)} actuals.")

    log("\n=== Monitoring setup complete ===")
    log("Drift tracking: target=True, feature=True")
    log("Predictions data collection: enabled")
    log(f"Association ID column: {ROW_ID_COL}")
    log(f"Accuracy metrics: {[m for m in metrics]}")
    log(f"Actuals submitted: {len(actuals_df)}")


if __name__ == "__main__":
    main()
