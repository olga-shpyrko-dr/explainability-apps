"""Model B — Remaining Useful Life (rul_days), as a NON-time-series regression
on the approaching-failure regime only. Reproducible end-to-end.

Fix vs. the first version: the TS model capped rul at 30, so ~87% of rows were
30 and it regressed to the mean (predicted ~25 even when the truth was ~3 days).
Here we train ONLY on rows with rul_days <= 30 (genuinely approaching failure),
so the target spans 1..30 and the model learns the ramp-down. Non-TS lets us
filter rows (which would break TS cadence); out-of-time validation keeps it
time-honest.

Run (reproducible): regenerates training_data.csv from the source telemetry,
creates the project, runs Autopilot, deploys.
    python train.py
"""
from __future__ import annotations

from pathlib import Path

import datarobot as dr
import pandas as pd
from datarobot import AUTOPILOT_MODE
from datarobot.enums import TARGET_TYPE
from datarobot.helpers.partitioning_methods import DatetimePartitioningSpecification

import config
import synth_common as sc

MODEL_DIR = Path(__file__).resolve().parent
SOURCE = sc.TELEMETRY                          # 0_synthetic_data/output_subset/asset_telemetry.csv
TRAIN_CSV = MODEL_DIR / "training_data.csv"     # reproducible training dataset
PROJECT_NAME = "Caterpillar — rul_days (synthetic, approaching-failure)"
DEPLOYMENT_LABEL = "Caterpillar — rul_days (synthetic)"
TARGET = "rul_days"
RUL_MAX = 30                                    # keep only rows within 30 days of a failure


def build_training_data() -> Path:
    """Regenerate the training dataset from source: approaching-failure rows only."""
    keep = sc.BASE_PREDICTORS + [TARGET]
    first, rows = True, 0
    if TRAIN_CSV.exists():
        TRAIN_CSV.unlink()
    for chunk in pd.read_csv(SOURCE, chunksize=500_000):
        ch = chunk[chunk[TARGET] <= RUL_MAX][[c for c in keep if c in chunk.columns]]
        if ch.empty:
            continue
        ch.to_csv(TRAIN_CSV, mode="w" if first else "a", header=first, index=False)
        first, rows = False, rows + len(ch)
    print(f"training_data.csv: {rows:,} rows (rul_days <= {RUL_MAX})")
    return TRAIN_CSV


def main():
    sc.connect()
    build_training_data()
    p = dr.Project.create(sourcedata=str(TRAIN_CSV), project_name=PROJECT_NAME)
    print(f"Project: {p.id}")
    part = DatetimePartitioningSpecification(
        datetime_partition_column=sc.DATETIME, use_time_series=False,
        number_of_backtests=2, validation_duration="P30D",
    )
    p.analyze_and_model(target=TARGET, mode=AUTOPILOT_MODE.QUICK,
                        target_type=TARGET_TYPE.REGRESSION,
                        partitioning_method=part, worker_count=config.WORKER_COUNT)
    print("Waiting for Autopilot...")
    p.wait_for_autopilot()
    sc.report(p)
    sc.deploy(p, DEPLOYMENT_LABEL, "Remaining useful life (days) in the approaching-failure regime.")


if __name__ == "__main__":
    main()
