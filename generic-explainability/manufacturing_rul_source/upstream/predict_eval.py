"""Score the eval dataset with Model B (RUL, non-time-series) and report
predicted remaining useful life per machine. For each machine we score its most
recent rows and take the minimum predicted RUL (most urgent reading).

    python predict_eval.py            # threshold 10 days
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import datarobot as dr
import pandas as pd
import requests
from dotenv import load_dotenv

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
load_dotenv(REPO / ".env")
EVAL_CSV = HERE / "eval" / "eval_dataset.csv"
OUT_CSV = HERE / "eval" / "rul_predictions.csv"
DEPLOYMENT_LABEL = "Caterpillar — rul_days (synthetic)"
RECENT = 60


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold-days", type=float, default=10.0)
    args = ap.parse_args()
    tok = os.getenv("DATAROBOT_API_TOKEN")
    dr.Client(endpoint=os.getenv("DATAROBOT_ENDPOINT"), token=tok)
    dep = [d for d in dr.Deployment.list() if d.label == DEPLOYMENT_LABEL][0]
    ps = dr.PredictionServer.list()[0]
    url = f"{ps.url}/predApi/v1.0/deployments/{dep.id}/predictions"
    h = {"Authorization": f"Bearer {tok}", "datarobot-key": ps.datarobot_key,
         "Content-Type": "text/csv; charset=UTF-8"}

    df = pd.read_csv(EVAL_CSV).sort_values(["asset_id", "timestamp"])
    rows = []
    for aid, g in df.groupby("asset_id"):
        g = g.tail(RECENT)
        r = requests.post(url, headers=h, data=g.to_csv(index=False).encode(), timeout=120)
        if r.status_code != 200:
            print(f"  {aid}: {r.status_code} {r.text[:90]}"); continue
        preds = [rec.get("prediction") for rec in r.json().get("data", []) if rec.get("prediction") is not None]
        rul = round(min(preds), 1) if preds else None
        rows.append(dict(asset_id=aid, min_predicted_rul_days=rul,
                         status="FAILING SOON" if rul is not None and rul <= args.threshold_days else "ok"))
    rep = pd.DataFrame(rows).sort_values("min_predicted_rul_days")
    rep.to_csv(OUT_CSV, index=False)
    print(f"=== RUL predictions -> eval/{OUT_CSV.name} ===")
    for _, r in rep.iterrows():
        print(f"  {r.asset_id:<15} min RUL={r.min_predicted_rul_days:<6} days  {r.status}")


if __name__ == "__main__":
    main()
