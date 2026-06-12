"""
Fetches prediction explanations from DataRobot and builds the two runtime
DataFrames the API consumes:

  scored_population   — one row per policy; all source cols + prediction score
  explanation_long    — unpivoted SHAP slots with group labels attached

Startup flow (full pipeline, ~2–5 min on first run):
  1. Upload scoring dataset from AI Catalog → project prediction dataset
  2. Request predictions on that dataset
  3. Ensure PE initialisation exists for the model
  4. Create PredictionExplanations
  5. Load AI Catalog dataset as scored_population

A local cache (.prediction_dataset_cache.json) stores the prediction dataset ID
so steps 1–2 are skipped on subsequent restarts.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import datarobot as dr
from datarobot.models.dataset import Dataset
from datarobot.models.prediction_explanations import (
    PredictionExplanations,
    PredictionExplanationsInitialization,
)
import pandas as pd

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
_GROUP_MAP_PATH = _HERE / "feature_group_mapping.json"
_CACHE_FILE = _HERE / ".prediction_dataset_cache.json"


# ---------------------------------------------------------------------------
# Group mapping helpers
# ---------------------------------------------------------------------------

def load_group_map() -> dict[str, str]:
    """Return {feature_name: group_label} from the JSON config."""
    with open(_GROUP_MAP_PATH) as f:
        raw = json.load(f)
    mapping: dict[str, str] = {}
    for group, features in raw["groups"].items():
        for feat in features:
            mapping[feat] = group
    return mapping


# ---------------------------------------------------------------------------
# DR client
# ---------------------------------------------------------------------------

def _init_dr_client() -> None:
    dr.Client(  # type: ignore[call-non-callable]
        token=os.environ["DATAROBOT_API_TOKEN"],
        endpoint=os.environ.get("DATAROBOT_ENDPOINT", "https://app.eu.datarobot.com/api/v2"),
    )


# ---------------------------------------------------------------------------
# Prediction dataset — upload from catalog + cache
# ---------------------------------------------------------------------------

def _get_or_create_prediction_dataset(
    project_id: str,
    model_id: str,
    catalog_dataset_id: str,
) -> str:
    """
    Return a prediction dataset ID suitable for PredictionExplanations.create().

    On first call, uploads the AI Catalog dataset to the project and requests
    predictions, then caches the result. Subsequent calls return from cache.
    """
    # Check local cache
    if _CACHE_FILE.exists():
        cache = json.loads(_CACHE_FILE.read_text())
        if (
            cache.get("catalog_dataset_id") == catalog_dataset_id
            and cache.get("project_id") == project_id
        ):
            pred_dataset_id = cache["pred_dataset_id"]
            logger.info(
                "Using cached prediction dataset %s (skip upload + predict)", pred_dataset_id
            )
            return pred_dataset_id

    # Step 1 — upload AI Catalog dataset to the project
    logger.info(
        "Uploading catalog dataset %s to project %s as a prediction dataset…",
        catalog_dataset_id, project_id,
    )
    project = dr.Project.get(project_id)
    pred_dataset = project.upload_dataset_from_catalog(catalog_dataset_id)
    pred_dataset_id = pred_dataset.id
    logger.info("Prediction dataset created: %s", pred_dataset_id)

    # Step 2 — request predictions (required before PE can be created)
    logger.info("Requesting predictions for dataset %s…", pred_dataset_id)
    model = dr.Model.get(project_id, model_id)
    predict_job = model.request_predictions(dataset_id=pred_dataset_id)
    predict_job.wait_for_completion()
    logger.info("Predictions complete.")

    # Cache so we skip this on next startup
    _CACHE_FILE.write_text(json.dumps({
        "project_id": project_id,
        "catalog_dataset_id": catalog_dataset_id,
        "pred_dataset_id": pred_dataset_id,
    }))

    return pred_dataset_id


# ---------------------------------------------------------------------------
# PE initialisation
# ---------------------------------------------------------------------------

def _ensure_pe_init(project_id: str, model_id: str) -> None:
    try:
        PredictionExplanationsInitialization.get(project_id, model_id)
        logger.info("PE initialisation already exists for model %s", model_id)
    except Exception:
        logger.info("Creating PE initialisation for model %s…", model_id)
        PredictionExplanationsInitialization.create(project_id, model_id)


# ---------------------------------------------------------------------------
# Explanation fetch
# ---------------------------------------------------------------------------

def fetch_prediction_explanations(
    project_id: str,
    model_id: str,
    pred_dataset_id: str,
    max_explanations: int = 4,
) -> pd.DataFrame:
    logger.info("Creating PredictionExplanations for pred_dataset=%s…", pred_dataset_id)

    pe_job = PredictionExplanations.create(
        project_id=project_id,
        model_id=model_id,
        dataset_id=pred_dataset_id,
        max_explanations=max_explanations,
    )
    pe = pe_job.get_result_when_complete()  # returns PredictionExplanations once done

    rows = []
    for row in pe.get_rows():
        policy = row.row_id
        prediction = getattr(row, "prediction", None)
        explanations = getattr(row, "prediction_explanations", None) or []
        for rank, expl in enumerate(explanations, start=1):
            rows.append({
                "row_id": policy,
                "prediction": prediction,
                "explanation_rank": rank,
                "feature_name": expl.get("feature", expl.get("featureName", "")),
                "shap_strength": expl.get("strength", None),
                "actual_value": str(expl.get("actual_value", expl.get("actualValue", ""))),
                "qualitative_strength": expl.get(
                    "qualitative_strength", expl.get("qualitativeStrength", "")
                ),
            })

    df = pd.DataFrame(rows)
    logger.info(
        "Fetched %d explanation rows for %d policies",
        len(df), df["row_id"].nunique() if not df.empty else 0,
    )
    return df


# ---------------------------------------------------------------------------
# Main entry point — called once at startup
# ---------------------------------------------------------------------------

def build_tables(
    project_id: str,
    model_id: str,
    scoring_dataset_id: str,
    max_explanations: int = 4,
    row_id_col: str = "Policy_Number",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns (scored_population, explanation_long).
    """
    _init_dr_client()
    group_map = load_group_map()

    # 1. Get or create the prediction dataset (upload + predict if needed)
    pred_dataset_id = _get_or_create_prediction_dataset(
        project_id, model_id, scoring_dataset_id
    )

    # 2. Ensure PE initialisation exists
    _ensure_pe_init(project_id, model_id)

    # 3. Fetch SHAP explanations
    explanation_long = fetch_prediction_explanations(
        project_id, model_id, pred_dataset_id, max_explanations
    )

    # 4. Load scoring dataset from AI Catalog for source feature / filter columns
    logger.info("Loading scoring dataset %s from AI Catalog…", scoring_dataset_id)
    scored_population = Dataset.get(scoring_dataset_id).get_as_dataframe()

    if row_id_col not in scored_population.columns:
        logger.warning("row_id_col '%s' not in dataset; using index", row_id_col)
        scored_population[row_id_col] = scored_population.index.astype(str)

    # 5. Map integer PE row indices → actual row_id_col values.
    # PredictionExplanations returns 0-based positional indices (numpy.int64),
    # not the identifier column value.
    if not explanation_long.empty and pd.api.types.is_integer_dtype(explanation_long["row_id"]):
        logger.info("Mapping PE integer row indices to '%s' values…", row_id_col)
        idx_to_id = scored_population[row_id_col].astype(str).to_dict()
        explanation_long["row_id"] = explanation_long["row_id"].map(idx_to_id)

    # 6. Attach group labels
    explanation_long["feature_group"] = (
        explanation_long["feature_name"].map(group_map).fillna("Other")
    )

    # Join prediction score if not already present
    has_prediction = any("PREDICTION" in c.upper() for c in scored_population.columns)
    if not has_prediction and "prediction" in explanation_long.columns:
        score_map = (
            explanation_long[["row_id", "prediction"]]
            .drop_duplicates("row_id")
            .rename(columns={"row_id": row_id_col})
        )
        scored_population = scored_population.merge(score_map, on=row_id_col, how="left")

    logger.info(
        "Tables ready — scored_population=%s  explanation_long=%s",
        scored_population.shape, explanation_long.shape,
    )
    return scored_population, explanation_long
