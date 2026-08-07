"""Rebuild the manufacturing RUL example's training + scoring subsamples from
the full source CSVs in this folder (training_data.csv, eval_dataset.csv).

Regenerates the same two files committed in ../data/ (deterministic — fixed
random_state, so re-running reproduces them byte-for-byte):
  manufacturing_rul_training_sample.csv  (30,000-row training subsample)
  manufacturing_rul_scoring_sample.csv   (scoring subsample, stratified per
                                          asset so short/near-failure series
                                          aren't drowned out by long healthy
                                          ones)

Writes the scoring sample here as scoring_sample_raw.csv (features only, no
SHAP yet) rather than directly to ../data/ — run train_and_score.py next,
which scores it with real SHAP prediction explanations and writes the final
../data/manufacturing_rul_scoring_sample.csv (the file the app actually reads).

Run: python build_subsamples.py
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data"

# --- Training sample ---------------------------------------------------------
train = pd.read_csv(HERE / "training_data.csv")
train_sample = (
    train.sample(n=30000, random_state=42)
    .sort_values(["asset_id", "timestamp"])
    .reset_index(drop=True)
)
train_sample.to_csv(OUT / "manufacturing_rul_training_sample.csv", index=False)
print(f"training sample -> {OUT / 'manufacturing_rul_training_sample.csv'}  {train_sample.shape}")

# --- Scoring sample ------------------------------------------------------------
# Some assets' series end early in the eval world because the asset fails
# partway through (survival-style truncation) — those short series are exactly
# the near-failure cases worth keeping in full. Long series (~8,700 rows) are
# mostly healthy (rul_days pinned at the 30-day cap) and get thinned out so
# they don't dominate the sample.
eval_df = pd.read_csv(HERE / "eval_dataset.csv")
counts = eval_df.groupby("asset_id").size()
small_assets = counts[counts <= 1000].index

parts = []
for aid, g in eval_df.groupby("asset_id"):
    parts.append(g if aid in small_assets else g.sample(n=150, random_state=7))

score_sample = (
    pd.concat(parts).sort_values(["asset_id", "timestamp"]).reset_index(drop=True)
)
score_sample["reading_id"] = (
    score_sample["asset_id"] + "_" + score_sample["timestamp"].astype(str).str.replace(" ", "T")
)
score_sample = score_sample.rename(columns={"rul_days": "actual_rul_days_holdout"})
cols = ["reading_id"] + [c for c in score_sample.columns if c != "reading_id"]
score_sample = score_sample[cols]
score_sample.to_csv(HERE / "scoring_sample_raw.csv", index=False)
print(f"scoring sample (no SHAP yet) -> {HERE / 'scoring_sample_raw.csv'}  {score_sample.shape}")
print("Run train_and_score.py next to add real SHAP explanations and write "
      "the final ../data/manufacturing_rul_scoring_sample.csv")
