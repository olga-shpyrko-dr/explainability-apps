#!/usr/bin/env python3
"""
create_scoring_sample.py

Generate a scoring dataset sample from a DataRobot model's holdout predictions.

What it does:
  1. Loads the training dataset from AI Catalog by TRAINING_DATASET_ID (all input features).
  2. Requests holdout-partition training predictions for the model (reuses existing job if found).
  3. Joins predictions with the corresponding holdout rows.
  4. Saves the result as a CSV (and optionally uploads to AI Catalog).

The output CSV contains all input feature columns + the prediction score.
Upload it to the AI Catalog and set its ID as SCORING_DATASET_ID in .env.
The app will then run the batch scoring pipeline on it to generate explanations.

Usage:
  # reads PROJECT_ID, MODEL_ID, TRAINING_DATASET_ID, etc. from .env
  python create_scoring_sample.py

  # override any setting via CLI
  python create_scoring_sample.py \\
      --project-id 6a42312643e91bbd48762db8 \\
      --model-id   6a42323c6d777a364c9d320e \\
      --training-dataset-id 6a423013ed3aba6d87aeceeb \\
      --output     data/fraud_scoring_sample.csv \\
      --upload \\
      --dataset-name "Motor Fraud — Holdout Scoring Sample"
"""

import argparse
import os
import sys
from pathlib import Path

# Load .env from the same directory as this script
_HERE = Path(__file__).parent
_dotenv = _HERE / ".env"

try:
    from dotenv import load_dotenv  # type: ignore
    if _dotenv.exists():
        load_dotenv(_dotenv)
        print(f"Loaded .env from {_dotenv}")
    else:
        print("No .env found — relying on environment variables.")
except ImportError:
    print("python-dotenv not installed; relying on environment variables.")


def _require(value, name: str):
    if not value:
        sys.exit(f"Error: {name} is not set. Pass --{name.lower().replace('_', '-')} or set {name} in .env")
    return value


def main():
    parser = argparse.ArgumentParser(
        description="Create a scoring dataset sample from a DataRobot model's holdout predictions."
    )
    parser.add_argument("--project-id", default=os.getenv("PROJECT_ID"),
                        help="DataRobot project ID (or set PROJECT_ID in .env)")
    parser.add_argument("--model-id", default=os.getenv("MODEL_ID"),
                        help="DataRobot model ID (or set MODEL_ID in .env)")
    parser.add_argument(
        "--training-dataset-id",
        default=os.getenv("TRAINING_DATASET_ID", "6a423013ed3aba6d87aeceeb"),
        help="AI Catalog dataset ID for the training data (default: TRAINING_DATASET_ID env var "
             "or 6a423013ed3aba6d87aeceeb)",
    )
    parser.add_argument("--output", default=str(_HERE.parent / "data" / "scoring_sample.csv"),
                        help="Output CSV path (default: ../data/scoring_sample.csv)")
    parser.add_argument("--upload", action="store_true",
                        help="Upload the CSV to DataRobot AI Catalog after saving")
    parser.add_argument("--dataset-name", default=None,
                        help="Display name for the AI Catalog dataset (used with --upload)")
    parser.add_argument("--use-case-id", default=os.getenv("DEFAULT_USE_CASE_ID"),
                        help="Associate the uploaded dataset with this use case ID")
    args = parser.parse_args()

    token    = _require(os.getenv("DATAROBOT_API_TOKEN"), "DATAROBOT_API_TOKEN")
    endpoint = os.getenv("DATAROBOT_ENDPOINT", "https://app.datarobot.com/api/v2")
    project_id = _require(args.project_id, "PROJECT_ID")
    model_id   = _require(args.model_id,   "MODEL_ID")
    training_dataset_id = _require(args.training_dataset_id, "TRAINING_DATASET_ID")

    import datarobot as dr  # type: ignore
    import pandas as pd

    print(f"\nConnecting to {endpoint} …")
    dr.Client(token=token, endpoint=endpoint)

    # ------------------------------------------------------------------
    # 1. Fetch project + model metadata
    # ------------------------------------------------------------------
    project = dr.Project.get(project_id)
    model   = dr.Model.get(project_id, model_id)

    print(f"\nProject : {project.project_name}  ({project_id})")
    print(f"Model   : {model.model_type}  ({model_id})")
    print(f"Target  : {project.target}")

    # ------------------------------------------------------------------
    # 2. Load the training dataset (all input features)
    # ------------------------------------------------------------------
    print(f"\nLoading training dataset from AI Catalog ({training_dataset_id}) …")
    from datarobot.models.dataset import Dataset  # type: ignore
    training_df = Dataset.get(training_dataset_id).get_as_dataframe()
    print(f"  Training rows: {len(training_df):,}   columns: {len(training_df.columns)}")

    # ------------------------------------------------------------------
    # 3. Holdout training predictions — reuse existing job if available
    # ------------------------------------------------------------------
    print("\nLooking for existing holdout training predictions …")
    tp = None
    try:
        for existing in dr.TrainingPredictions.list(project_id):
            if (getattr(existing, "model_id", None) == model_id and
                    getattr(existing, "data_subset", "").lower() == "holdout"):
                tp = existing
                print(f"  Reusing existing training predictions: {existing.prediction_id}")
                break
    except Exception as exc:
        print(f"  Warning: could not list existing training predictions: {exc}")

    if tp is None:
        print("  None found — requesting new holdout training predictions …")
        try:
            job = model.request_training_predictions(
                data_subset=dr.enums.DATA_SUBSET.HOLDOUT
            )
            tp = job.get_result_when_complete()
            print("  Done.")
        except Exception as exc:
            sys.exit(f"Error requesting training predictions: {exc}")

    pred_df = tp.get_all_as_dataframe()

    print(f"  Holdout predictions: {len(pred_df):,} rows")
    print(f"  Prediction columns : {list(pred_df.columns)}")

    if pred_df.empty:
        sys.exit(
            "Error: no holdout predictions returned. "
            "Ensure the project has a holdout partition configured."
        )

    # ------------------------------------------------------------------
    # 4. Align by integer row_id (training predictions use 0-based index)
    # ------------------------------------------------------------------
    # pred_df["row_id"] are 0-based integer indices into the training dataset.
    pred_df = pred_df.rename(columns={"row_id": "_row_idx"})
    holdout_indices = pred_df["_row_idx"].values

    if holdout_indices.max() >= len(training_df):
        sys.exit(
            f"Error: holdout row_id {holdout_indices.max()} exceeds training dataset "
            f"length {len(training_df)}. Dataset may not match the project's training data."
        )

    holdout_features = training_df.iloc[holdout_indices].reset_index(drop=True)

    # Drop target column from features (app only needs input features + prediction)
    target = project.target
    if target in holdout_features.columns:
        holdout_features = holdout_features.drop(columns=[target])
        print(f"\nDropped target column '{target}' from feature set.")

    # Merge prediction scores alongside features
    pred_cols = [c for c in pred_df.columns if c != "_row_idx"]
    pred_values = pred_df[pred_cols].reset_index(drop=True)
    result_df = pd.concat([holdout_features, pred_values], axis=1)

    print(f"\nFinal dataset: {len(result_df):,} rows × {len(result_df.columns)} columns")
    print(f"Prediction column(s): {pred_cols}")

    # ------------------------------------------------------------------
    # 5. Save to CSV
    # ------------------------------------------------------------------
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(output_path, index=False)
    print(f"\nSaved → {output_path.resolve()}")

    # ------------------------------------------------------------------
    # 6. Optionally upload to AI Catalog
    # ------------------------------------------------------------------
    if args.upload:
        dataset_name = args.dataset_name or output_path.stem
        print(f"\nUploading '{dataset_name}' to AI Catalog …")
        catalog_dataset = Dataset.create_from_file(file_path=str(output_path))
        catalog_dataset.modify(name=dataset_name)
        print(f"  Uploaded dataset ID: {catalog_dataset.id}")

        if args.use_case_id:
            print(f"  Associating with use case {args.use_case_id} …")
            client = dr.client.get_client()
            try:
                client.post(
                    f"useCases/{args.use_case_id}/entities/",
                    json={"entityId": catalog_dataset.id, "entityType": "DATASET"},
                )
                print("  Associated.")
            except Exception as exc:
                print(f"  Warning: could not associate with use case: {exc}")

        print(f"\nAdd to .env:\n  SCORING_DATASET_ID={catalog_dataset.id}")
    else:
        print("\nTo upload manually, run with --upload flag.")
        print(f"Or set:\n  SCORING_DATASET_ID=<id after uploading {output_path.name} to AI Catalog>")


if __name__ == "__main__":
    main()
