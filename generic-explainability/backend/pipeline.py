"""
Builds the two runtime DataFrames the API consumes:

  scored_population  — one row per entity; all source cols + prediction score
  explanation_long   — unpivoted SHAP slots with group labels attached

Two modes:
  DataRobot mode (data_source=datarobot) — fetches predictions and SHAP values
    via the DataRobot SDK. Full pipeline runs on first startup (~2-5 min);
    subsequent restarts use a local cache of the prediction dataset ID.

  CSV mode (data_source=csv) — loads a pre-scored CSV that already contains
    EXPLANATION_N_FEATURE_NAME / EXPLANATION_N_STRENGTH columns. No DataRobot
    API calls are made.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd

from config_loader import load_group_map

logger = logging.getLogger(__name__)

_HERE = Path(__file__).parent
_CACHE_FILE = _HERE / ".prediction_dataset_cache.json"


# ---------------------------------------------------------------------------
# Shared — prediction column auto-detection
# ---------------------------------------------------------------------------

def resolve_prediction_col(df: pd.DataFrame, configured: Optional[str]) -> str:
    """
    Return the prediction column name.

    Uses configured value if set. Otherwise finds the first column ending in
    _PREDICTION (DataRobot convention). Raises RuntimeError if none found or
    if the configured column is absent.
    """
    if configured:
        if configured not in df.columns:
            raise RuntimeError(
                f"PREDICTION_COL='{configured}' not found in dataset. "
                f"Available columns: {list(df.columns)[:20]}…"
            )
        return configured

    candidates = [c for c in df.columns if c.upper().endswith("_PREDICTION")]
    if not candidates:
        raise RuntimeError(
            "No prediction column found. Set PREDICTION_COL in .env, or ensure "
            "the dataset has a column ending in '_PREDICTION'."
        )
    if len(candidates) > 1:
        logger.warning(
            "Multiple _PREDICTION columns found: %s — using '%s'. "
            "Set PREDICTION_COL in .env to pick a specific one.",
            candidates, candidates[0],
        )
    return candidates[0]


# ---------------------------------------------------------------------------
# Shared — explanation unpivot (used by both modes)
# ---------------------------------------------------------------------------

def unpivot_explanations(
    df: pd.DataFrame,
    max_explanations: int,
    row_id_col: str,
    prediction_col: str,
) -> pd.DataFrame:
    """
    Unpivot EXPLANATION_N_* columns from a wide DataFrame into long format.

    Returns a DataFrame with columns:
      row_id, prediction, explanation_rank, feature_name,
      shap_strength, actual_value, qualitative_strength
    """
    dfs = []
    for rank in range(1, max_explanations + 1):
        feat_col = f"EXPLANATION_{rank}_FEATURE_NAME"
        strength_col = f"EXPLANATION_{rank}_STRENGTH"
        value_col = f"EXPLANATION_{rank}_ACTUAL_VALUE"
        qual_col = f"EXPLANATION_{rank}_QUALITATIVE_STRENGTH"

        if feat_col not in df.columns:
            break

        cols = {
            row_id_col: "row_id",
            prediction_col: "prediction",
            feat_col: "feature_name",
        }
        present_extra = {
            c: n for c, n in [
                (strength_col, "shap_strength"),
                (value_col, "actual_value"),
                (qual_col, "qualitative_strength"),
            ] if c in df.columns
        }
        cols.update(present_extra)

        sub = df[list(cols.keys())].rename(columns=cols).copy()
        sub["explanation_rank"] = rank

        # Fill missing optional columns with defaults
        for col_name, default in [("shap_strength", None), ("actual_value", ""), ("qualitative_strength", "")]:
            if col_name not in sub.columns:
                sub[col_name] = default

        sub = sub[sub["feature_name"].notna() & (sub["feature_name"].astype(str) != "")]
        dfs.append(sub)

    if not dfs:
        return pd.DataFrame(columns=[
            "row_id", "prediction", "explanation_rank",
            "feature_name", "shap_strength", "actual_value", "qualitative_strength",
        ])

    return pd.concat(dfs, ignore_index=True)


# ---------------------------------------------------------------------------
# CSV mode
# ---------------------------------------------------------------------------

def build_tables_from_csv(
    csv_path: str,
    max_explanations: int,
    row_id_col: str,
    prediction_col_cfg: Optional[str],
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """
    Load a pre-scored CSV and return (scored_population, explanation_long, prediction_col).
    """
    logger.info("Loading scored population from CSV: %s", csv_path)
    scored_population = pd.read_csv(csv_path, low_memory=False)

    if row_id_col not in scored_population.columns:
        logger.warning("row_id_col '%s' not in CSV; using DataFrame index", row_id_col)
        scored_population[row_id_col] = scored_population.index.astype(str)

    prediction_col = resolve_prediction_col(scored_population, prediction_col_cfg)
    logger.info("Using prediction column: '%s'", prediction_col)

    group_map = load_group_map()
    explanation_long = unpivot_explanations(
        scored_population, max_explanations, row_id_col, prediction_col
    )
    explanation_long["row_id"] = explanation_long["row_id"].astype(str)
    explanation_long["feature_group"] = (
        explanation_long["feature_name"].map(group_map).fillna("Other")
    )

    logger.info(
        "CSV mode ready — scored_population=%s  explanation_long=%s",
        scored_population.shape, explanation_long.shape,
    )
    return scored_population, explanation_long, prediction_col


# ---------------------------------------------------------------------------
# DataRobot mode
# ---------------------------------------------------------------------------

def _init_dr_client() -> None:
    import datarobot as dr  # type: ignore
    dr.Client(
        token=os.environ["DATAROBOT_API_TOKEN"],
        endpoint=os.environ.get("DATAROBOT_ENDPOINT", "https://app.datarobot.com/api/v2"),
    )


def _read_cache() -> dict:
    return json.loads(_CACHE_FILE.read_text()) if _CACHE_FILE.exists() else {}


def _write_cache(data: dict) -> None:
    _CACHE_FILE.write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# Deployment-based batch prediction (preferred path)
# ---------------------------------------------------------------------------

def _get_or_create_batch_prediction_deployment(
    deployment_id: str,
    catalog_dataset_id: str,
    max_explanations: int,
    row_id_col: str,
) -> pd.DataFrame:
    """
    Run a batch prediction job using a DataRobot deployment and return the
    scored output as a DataFrame.  Result is cached to a local CSV so restarts
    are fast without re-running scoring.

    The deployment must have SHAP prediction explanations enabled.
    """
    import datarobot as dr  # type: ignore

    # Cache key: local CSV file alongside the cache JSON
    cache = _read_cache()
    local_csv = _CACHE_FILE.parent / ".batch_output_cache.csv"
    if (
        cache.get("mode") == "deployment"
        and cache.get("deployment_id") == deployment_id
        and cache.get("catalog_dataset_id") == catalog_dataset_id
        and cache.get("row_id_col") == row_id_col
        and local_csv.exists()
    ):
        logger.info("Using cached batch prediction output from %s", local_csv)
        return pd.read_csv(local_csv)

    logger.info(
        "Running deployment batch prediction job (deployment=%s, dataset=%s)…",
        deployment_id, catalog_dataset_id,
    )

    job = dr.BatchPredictionJob.score(
        deployment=deployment_id,
        intake_settings={
            "type": "dataset",
            "dataset": dr.Dataset.get(catalog_dataset_id),
        },
        output_settings={"type": "localFile", "path": str(local_csv)},
        num_concurrent=4,
        max_explanations=max_explanations,
        explanation_algorithm="shap",
        passthrough_columns=[row_id_col],
    )
    job.wait_for_completion()

    if not local_csv.exists():
        raise RuntimeError(
            f"Batch prediction job {job.id} completed but output file not found at {local_csv}"
        )

    _write_cache({
        "mode": "deployment",
        "deployment_id": deployment_id,
        "catalog_dataset_id": catalog_dataset_id,
        "row_id_col": row_id_col,
    })
    logger.info("Batch prediction job complete — output written to %s", local_csv)
    return pd.read_csv(local_csv)


def build_tables_from_deployment(
    deployment_id: str,
    scoring_dataset_id: str,
    max_explanations: int,
    row_id_col: str,
    prediction_col_cfg: Optional[str],
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """
    Score via a DataRobot deployment BatchPredictionJob.

    Flow:
      1. Run (or reuse cached) batch prediction job → output catalog dataset with
         PREDICTION and EXPLANATION_N_* columns.
      2. Load original scoring dataset for profile/feature columns.
      3. Merge output into scoring dataset on row_id_col.
      4. Unpivot explanations and attach group labels.

    Client must already be initialised by the caller (build_tables does this).
    """
    import datarobot as dr  # type: ignore
    from datarobot.models.dataset import Dataset  # type: ignore

    group_map = load_group_map()

    output_df = _get_or_create_batch_prediction_deployment(
        deployment_id=deployment_id,
        catalog_dataset_id=scoring_dataset_id,
        max_explanations=max_explanations,
        row_id_col=row_id_col,
    )
    logger.info("Batch output loaded: %s rows × %s cols", *output_df.shape)

    logger.info("Loading original scoring dataset %s for profile attributes…", scoring_dataset_id)
    scoring_df = Dataset.get(scoring_dataset_id).get_as_dataframe()

    # Columns to pull from the batch output
    pred_expl_cols = [
        c for c in output_df.columns
        if c.upper().endswith("_PREDICTION") or "EXPLANATION_" in c.upper()
    ]

    if row_id_col in output_df.columns:
        # Merge by ID when the row identifier is present in the output
        merge_cols = [row_id_col] + pred_expl_cols
        scored_population = scoring_df.merge(
            output_df[merge_cols].drop_duplicates(subset=[row_id_col]),
            on=row_id_col,
            how="left",
        )
    else:
        # localFile output omits input columns — join positionally (batch preserves row order)
        logger.info(
            "row_id_col '%s' absent from batch output; joining by row position", row_id_col
        )
        scored_population = scoring_df.reset_index(drop=True).copy()
        if len(output_df) != len(scored_population):
            raise RuntimeError(
                f"Batch output row count ({len(output_df)}) != "
                f"scoring dataset row count ({len(scored_population)}); cannot join."
            )
        for col in pred_expl_cols:
            scored_population[col] = output_df[col].values

    prediction_col = resolve_prediction_col(scored_population, prediction_col_cfg)
    logger.info("Using prediction column: '%s'", prediction_col)

    explanation_long = unpivot_explanations(
        scored_population, max_explanations, row_id_col, prediction_col
    )
    explanation_long["row_id"] = explanation_long["row_id"].astype(str)
    explanation_long["feature_group"] = (
        explanation_long["feature_name"].map(group_map).fillna("Other")
    )

    logger.info(
        "Deployment mode ready — scored_population=%s  explanation_long=%s",
        scored_population.shape, explanation_long.shape,
    )
    return scored_population, explanation_long, prediction_col


# ---------------------------------------------------------------------------
# Project/model PE path (fallback)
# ---------------------------------------------------------------------------

def _get_or_create_prediction_dataset(
    project_id: str,
    model_id: str,
    catalog_dataset_id: str,
) -> str:
    import datarobot as dr  # type: ignore

    cache = _read_cache()
    if (
        cache.get("mode") in ("project_model", None)  # None = legacy cache without mode key
        and cache.get("catalog_dataset_id") == catalog_dataset_id
        and cache.get("project_id") == project_id
    ):
        pred_dataset_id = cache["pred_dataset_id"]
        logger.info("Using cached prediction dataset %s", pred_dataset_id)
        return pred_dataset_id

    logger.info("Uploading catalog dataset %s to project %s…", catalog_dataset_id, project_id)
    project = dr.Project.get(project_id)
    pred_dataset = project.upload_dataset_from_catalog(catalog_dataset_id)
    pred_dataset_id = pred_dataset.id

    logger.info("Requesting predictions for dataset %s…", pred_dataset_id)
    model = dr.Model.get(project_id, model_id)
    predict_job = model.request_predictions(dataset_id=pred_dataset_id)
    predict_job.wait_for_completion()

    _write_cache({
        "mode": "project_model",
        "project_id": project_id,
        "catalog_dataset_id": catalog_dataset_id,
        "pred_dataset_id": pred_dataset_id,
    })
    return pred_dataset_id


def _ensure_pe_init(project_id: str, model_id: str) -> None:
    from datarobot.models.prediction_explanations import PredictionExplanationsInitialization  # type: ignore
    try:
        PredictionExplanationsInitialization.get(project_id, model_id)
        logger.info("PE initialisation already exists for model %s", model_id)
    except Exception:
        logger.info("Creating PE initialisation for model %s…", model_id)
        PredictionExplanationsInitialization.create(project_id, model_id)


def _fetch_prediction_explanations(
    project_id: str,
    model_id: str,
    pred_dataset_id: str,
    max_explanations: int,
) -> pd.DataFrame:
    from datarobot.models.prediction_explanations import PredictionExplanations  # type: ignore

    logger.info("Creating PredictionExplanations for pred_dataset=%s…", pred_dataset_id)
    pe_job = PredictionExplanations.create(
        project_id=project_id,
        model_id=model_id,
        dataset_id=pred_dataset_id,
        max_explanations=max_explanations,
    )
    pe = pe_job.get_result_when_complete()

    rows = []
    for row in pe.get_rows():
        row_id = row.row_id
        prediction = getattr(row, "prediction", None)
        for rank, expl in enumerate(getattr(row, "prediction_explanations", None) or [], start=1):
            rows.append({
                "row_id": row_id,
                "prediction": prediction,
                "explanation_rank": rank,
                "feature_name": expl.get("feature", expl.get("featureName", "")),
                "shap_strength": expl.get("strength"),
                "actual_value": str(expl.get("actual_value", expl.get("actualValue", ""))),
                "qualitative_strength": expl.get(
                    "qualitative_strength", expl.get("qualitativeStrength", "")
                ),
            })

    df = pd.DataFrame(rows)
    logger.info(
        "Fetched %d explanation rows for %d entities",
        len(df), df["row_id"].nunique() if not df.empty else 0,
    )
    return df


def build_tables_from_datarobot(
    project_id: str,
    model_id: str,
    scoring_dataset_id: str,
    max_explanations: int,
    row_id_col: str,
    prediction_col_cfg: Optional[str],
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """
    Returns (scored_population, explanation_long, prediction_col).
    Client must already be initialised by the caller (build_tables does this).
    """
    import datarobot as dr  # type: ignore
    from datarobot.models.dataset import Dataset

    group_map = load_group_map()

    pred_dataset_id = _get_or_create_prediction_dataset(
        project_id, model_id, scoring_dataset_id
    )
    _ensure_pe_init(project_id, model_id)

    explanation_long = _fetch_prediction_explanations(
        project_id, model_id, pred_dataset_id, max_explanations
    )

    logger.info("Loading scoring dataset %s from AI Catalog…", scoring_dataset_id)
    scored_population = Dataset.get(scoring_dataset_id).get_as_dataframe()

    if row_id_col not in scored_population.columns:
        logger.warning("row_id_col '%s' not in dataset; using index", row_id_col)
        scored_population[row_id_col] = scored_population.index.astype(str)

    # Map PE integer indices → actual row_id_col values
    if not explanation_long.empty and pd.api.types.is_integer_dtype(explanation_long["row_id"]):
        logger.info("Mapping PE integer indices to '%s' values…", row_id_col)
        idx_to_id = scored_population[row_id_col].astype(str).to_dict()
        explanation_long["row_id"] = explanation_long["row_id"].map(idx_to_id)

    prediction_col = resolve_prediction_col(scored_population, prediction_col_cfg)
    logger.info("Using prediction column: '%s'", prediction_col)

    # Attach group labels
    explanation_long["feature_group"] = (
        explanation_long["feature_name"].map(group_map).fillna("Other")
    )

    # Merge prediction into scored_population if not already present
    has_prediction = any(c.upper().endswith("_PREDICTION") for c in scored_population.columns)
    if not has_prediction and "prediction" in explanation_long.columns:
        score_map = (
            explanation_long[["row_id", "prediction"]]
            .drop_duplicates("row_id")
            .rename(columns={"row_id": row_id_col})
        )
        scored_population = scored_population.merge(score_map, on=row_id_col, how="left")

    logger.info(
        "DR mode ready — scored_population=%s  explanation_long=%s",
        scored_population.shape, explanation_long.shape,
    )
    return scored_population, explanation_long, prediction_col


# ---------------------------------------------------------------------------
# Dataset selector helpers (DataRobot mode only)
# ---------------------------------------------------------------------------

def get_dataset_name(dataset_id: str) -> str:
    """Fetch the display name of a catalog dataset. Returns dataset_id on failure."""
    try:
        from datarobot.models.dataset import Dataset  # type: ignore
        return Dataset.get(dataset_id).name
    except Exception:
        return dataset_id


def list_use_case_datasets(use_case_id: Optional[str], limit: int = 100) -> list[dict]:
    """
    Return [{id, name}] for datasets in the given use case (or all datasets if
    use_case_id is None). Tries the useCases/{id}/entities/ endpoint first;
    falls back to the datasets/ list endpoint.
    """
    import datarobot as dr  # type: ignore

    client = dr.client.get_client()
    items: list[dict] = []

    try:
        if use_case_id:
            resp = client.get(
                f"useCases/{use_case_id}/entities/",
                params={"entityType": "dataset", "limit": limit},
            ).json()
            raw = resp.get("data", []) if isinstance(resp, dict) else resp
            items = [
                {
                    "id": r.get("id") or r.get("entityId", ""),
                    "name": r.get("name", "Unknown"),
                }
                for r in raw
                if r.get("entityType", "").upper() in ("", "DATASET")
            ]
        else:
            resp = client.get("datasets/", params={"limit": limit}).json()
            raw = resp.get("data", []) if isinstance(resp, dict) else resp
            items = [
                {
                    "id": r.get("datasetId") or r.get("id", ""),
                    "name": r.get("datasetName") or r.get("name", "Unknown"),
                }
                for r in raw
            ]
    except Exception as exc:
        logger.warning("Failed to list datasets (use_case_id=%s): %s", use_case_id, exc)

    return [i for i in items if i["id"]]


def load_precalculated_dataset(
    dataset_id: str,
    max_explanations: int,
    row_id_col: str,
    prediction_col_cfg: Optional[str],
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """
    Load a pre-scored catalog dataset (must already have EXPLANATION_N_* columns).
    Returns (scored_population, explanation_long, prediction_col).
    Raises RuntimeError if no EXPLANATION columns are found.
    """
    from datarobot.models.dataset import Dataset  # type: ignore

    logger.info("Loading pre-scored dataset %s from AI Catalog…", dataset_id)
    df = Dataset.get(dataset_id).get_as_dataframe()

    if row_id_col not in df.columns:
        logger.warning("row_id_col '%s' not in dataset; using index", row_id_col)
        df[row_id_col] = df.index.astype(str)

    if not any("EXPLANATION_" in c for c in df.columns):
        raise RuntimeError(
            f"Dataset {dataset_id!r} has no EXPLANATION_N_* columns. "
            "Select a pre-scored dataset that already contains prediction explanations."
        )

    prediction_col = resolve_prediction_col(df, prediction_col_cfg)
    group_map = load_group_map()

    explanation_long = unpivot_explanations(df, max_explanations, row_id_col, prediction_col)
    explanation_long["row_id"] = explanation_long["row_id"].astype(str)
    explanation_long["feature_group"] = (
        explanation_long["feature_name"].map(group_map).fillna("Other")
    )

    logger.info(
        "Pre-scored dataset ready — scored_population=%s  explanation_long=%s",
        df.shape, explanation_long.shape,
    )
    return df, explanation_long, prediction_col


# ---------------------------------------------------------------------------
# Dispatcher — called once at startup
# ---------------------------------------------------------------------------

def build_tables(settings) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """
    Entry point called at startup. Dispatches to:
      CSV mode          — data_source=csv, uses CSV_PATH
      Deployment mode   — data_source=datarobot + DEPLOYMENT_ID  (preferred)
      Project/model PE  — data_source=datarobot + PROJECT_ID + MODEL_ID  (fallback)
    Returns (scored_population, explanation_long, prediction_col).
    """
    if settings.data_source == "csv":
        if not settings.csv_path:
            raise RuntimeError("data_source=csv requires CSV_PATH to be set in .env")
        return build_tables_from_csv(
            csv_path=settings.csv_path,
            max_explanations=settings.max_explanations,
            row_id_col=settings.row_id_col,
            prediction_col_cfg=settings.prediction_col,
        )

    # DataRobot mode — shared requirements
    if not settings.datarobot_api_token:
        raise RuntimeError("data_source=datarobot requires DATAROBOT_API_TOKEN to be set in .env")
    if not settings.scoring_dataset_id:
        raise RuntimeError("data_source=datarobot requires SCORING_DATASET_ID to be set in .env")

    os.environ["DATAROBOT_API_TOKEN"] = settings.datarobot_api_token
    os.environ["DATAROBOT_ENDPOINT"] = settings.datarobot_endpoint

    _init_dr_client()

    # Deployment path (preferred)
    if settings.deployment_id:
        logger.info("Using deployment-based batch prediction (DEPLOYMENT_ID=%s)", settings.deployment_id)
        return build_tables_from_deployment(
            deployment_id=settings.deployment_id,
            scoring_dataset_id=settings.scoring_dataset_id,
            max_explanations=settings.max_explanations,
            row_id_col=settings.row_id_col,
            prediction_col_cfg=settings.prediction_col,
        )

    # Project/model PE fallback
    if not settings.project_id or not settings.model_id:
        raise RuntimeError(
            "data_source=datarobot requires either DEPLOYMENT_ID "
            "or both PROJECT_ID and MODEL_ID to be set in .env"
        )
    logger.info("Using project/model PE path (PROJECT_ID=%s, MODEL_ID=%s)", settings.project_id, settings.model_id)
    return build_tables_from_datarobot(
        project_id=settings.project_id,
        model_id=settings.model_id,
        scoring_dataset_id=settings.scoring_dataset_id,
        max_explanations=settings.max_explanations,
        row_id_col=settings.row_id_col,
        prediction_col_cfg=settings.prediction_col,
    )
