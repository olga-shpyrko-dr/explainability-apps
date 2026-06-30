"""
FastAPI backend for the Generic Explainability App.

On startup:
  - Loads all JSON config files (feature groups, profile attributes, narrative labels)
  - Builds scored_population and explanation_long DataFrames (DataRobot or CSV mode)
  - Resolves the prediction column name
  - Caches everything in _state for the process lifetime

Endpoints:
  GET  /api/config           — resolved app config for the frontend
  GET  /api/health           — status + row counts
  GET  /api/columns          — filterable column metadata
  GET  /api/cohort           — cohort profile stats
  GET  /api/groups           — group SHAP aggregations
  GET  /api/row/{row_id}     — waterfall for one row
  GET  /api/llm/providers    — available LLM providers
  POST /api/narrative        — LLM narrative generation
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import get_settings
from config_loader import (
    load_narrative_config,
    load_profile_config,
    validate_columns_against_profile,
)
from cohort import apply_filters, cohort_profile, group_shap_summary, row_explanation
from llm_client import available_providers, default_provider
from narrative import generate_narrative, generate_row_narrative
from pipeline import build_tables, build_tables_from_deployment, get_dataset_name, list_use_case_datasets, load_precalculated_dataset

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()

    # Load JSON configs synchronously (fast, fail-fast on bad config)
    profile_cfg = load_profile_config()
    narrative_cfg = load_narrative_config()

    # Populate config-derived state immediately so the app is ready to accept
    # health-check requests before the (potentially slow) data load completes.
    _state.update({
        "ready": False,
        "profile_cfg": profile_cfg,
        "narrative_cfg": narrative_cfg,
        "cfg": cfg,
        "row_id_col": cfg.row_id_col,
        "outcome_col": cfg.outcome_col,
        "app_title": cfg.app_title,
        "app_subtitle": cfg.app_subtitle,
        "max_explanations": cfg.max_explanations,
        "score_histogram_bins": cfg.score_histogram_bins,
        "top_features_per_group": cfg.top_features_per_group,
        "cohort_warning_min_rows": cfg.cohort_warning_min_rows,
        "narrative_max_tokens": cfg.narrative_max_tokens,
        "narrative_groups_in_prompt": cfg.narrative_groups_in_prompt,
        "narrative_features_per_group": cfg.narrative_features_per_group,
        "data_source": cfg.data_source,
        "default_use_case_id": cfg.default_use_case_id,
    })

    async def _load_data() -> None:
        try:
            logger.info("Building data tables (mode=%s)…", cfg.data_source)
            loop = asyncio.get_running_loop()
            scored_pop, expl_long, prediction_col = await loop.run_in_executor(
                None, lambda: build_tables(cfg)
            )
            validate_columns_against_profile(list(scored_pop.columns), profile_cfg)

            default_dataset_name: Optional[str] = cfg.dataset_display_name
            if not default_dataset_name and cfg.data_source == "datarobot" and cfg.scoring_dataset_id:
                try:
                    default_dataset_name = get_dataset_name(cfg.scoring_dataset_id)
                except Exception:
                    default_dataset_name = cfg.scoring_dataset_id

            _state.update({
                "scored_population": scored_pop,
                "explanation_long": expl_long,
                "prediction_col": prediction_col,
                "current_dataset_id": cfg.scoring_dataset_id,
                "current_dataset_name": default_dataset_name,
                "ready": True,
            })
            logger.info(
                "Ready. scored_population=%s  explanation_long=%s  prediction_col=%s",
                scored_pop.shape, expl_long.shape, prediction_col,
            )
        except Exception as exc:
            logger.error("Data loading failed: %s", exc, exc_info=True)
            _state["init_error"] = str(exc)

    asyncio.create_task(_load_data())
    yield
    _state.clear()


app = FastAPI(title="Explainability API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _require_ready() -> None:
    if not _state.get("ready"):
        err = _state.get("init_error")
        if err:
            raise HTTPException(status_code=503, detail=f"Data loading failed: {err}")
        raise HTTPException(status_code=503, detail="Data is loading, please try again in a moment.")


def _pop() -> pd.DataFrame:
    _require_ready()
    return _state["scored_population"]


def _expl() -> pd.DataFrame:
    _require_ready()
    return _state["explanation_long"]


def _row_id_col() -> str:
    return _state["row_id_col"]


def _prediction_col() -> str:
    _require_ready()
    return _state["prediction_col"]


def _parse_filters(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# /api/config — frontend reads this once at startup
# ---------------------------------------------------------------------------

@app.get("/api/config")
def get_config():
    """Return resolved app configuration for the frontend."""
    nc = _state["narrative_cfg"]
    pc = _state["profile_cfg"]
    expl = _expl()

    # Derive available group names from the explanation data
    feature_groups = sorted(expl["feature_group"].dropna().unique().tolist())
    if "Other" in feature_groups:
        feature_groups = [g for g in feature_groups if g != "Other"] + ["Other"]

    return {
        "app_title": _state["app_title"],
        "app_subtitle": _state["app_subtitle"],
        "row_id_col": _row_id_col(),
        "prediction_col": _prediction_col(),
        "max_explanations": _state["max_explanations"],
        # Narrative labels
        "entity_label": nc["entity_label"],
        "entity_label_plural": nc["entity_label_plural"],
        "high_score_label": nc["high_score_label"],
        "low_score_label": nc["low_score_label"],
        "factor_positive_label": nc["factor_positive_label"],
        "factor_negative_label": nc["factor_negative_label"],
        # Filter / profile config
        "profile_attributes": pc.get("profile_attributes", []),
        "score_filter": pc.get("score_filter", {"show": True, "display_name": "Prediction Score"}),
        "top_explanation_filter": pc.get(
            "top_explanation_filter",
            {"show": True, "display_name": "Top Explanation Feature", "explanation_slot": 1},
        ),
        "feature_groups": feature_groups,
        # Dataset selector
        "current_dataset_id": _state.get("current_dataset_id"),
        "current_dataset_name": _state.get("current_dataset_name"),
        "dataset_selector_enabled": _state.get("data_source") == "datarobot",
    }


# ---------------------------------------------------------------------------
# /api/datasets  — list datasets available for selection
# ---------------------------------------------------------------------------

@app.get("/api/datasets")
def list_datasets():
    """Return datasets available for selection (scoped to use case if configured)."""
    if _state.get("data_source") != "datarobot":
        return {"datasets": [], "use_case_mode": False}
    datasets = list_use_case_datasets(_state.get("default_use_case_id"))
    return {
        "datasets": datasets,
        "use_case_mode": bool(_state.get("default_use_case_id")),
    }


# ---------------------------------------------------------------------------
# /api/dataset/switch  — hot-swap the active dataset
# ---------------------------------------------------------------------------

class DatasetSwitchRequest(BaseModel):
    dataset_id: str
    display_name: Optional[str] = None


@app.post("/api/dataset/switch")
async def switch_dataset(req: DatasetSwitchRequest):
    """
    Switch the active dataset.

    Fast path: the selected dataset already has EXPLANATION_N_* columns —
    loads directly from the AI Catalog and returns {"status": "ready"}.

    Slow path: raw dataset without explanation columns — runs batch prediction
    using the configured deployment in the background and returns
    {"status": "loading"}. The frontend should poll GET /api/health until
    status == "ok", then refresh.
    """
    _require_ready()
    if _state.get("data_source") != "datarobot":
        raise HTTPException(status_code=400, detail="Dataset switching is only available in DataRobot mode.")

    cfg = _state["cfg"]

    # --- Fast path: pre-scored dataset ---
    try:
        scored_pop, expl_long, prediction_col = load_precalculated_dataset(
            dataset_id=req.dataset_id,
            max_explanations=cfg.max_explanations,
            row_id_col=cfg.row_id_col,
            prediction_col_cfg=cfg.prediction_col,
        )
        dataset_name = req.display_name or get_dataset_name(req.dataset_id)
        validate_columns_against_profile(list(scored_pop.columns), _state["profile_cfg"])
        _state.update({
            "scored_population": scored_pop,
            "explanation_long": expl_long,
            "prediction_col": prediction_col,
            "current_dataset_id": req.dataset_id,
            "current_dataset_name": dataset_name,
        })
        logger.info("Dataset switched (pre-scored) → %s (%d rows)", dataset_name, len(scored_pop))
        return {"status": "ready", "dataset_id": req.dataset_id, "dataset_name": dataset_name, "rows_loaded": len(scored_pop)}
    except RuntimeError as exc:
        if "EXPLANATION" not in str(exc):
            raise HTTPException(status_code=400, detail=str(exc))
        # Dataset has no explanation columns → fall through to batch prediction

    # --- Slow path: raw dataset, run batch prediction ---
    if not cfg.deployment_id:
        raise HTTPException(
            status_code=400,
            detail="Dataset has no explanation columns and no DEPLOYMENT_ID is configured for on-demand scoring.",
        )

    # Snapshot current working state so we can restore it if scoring fails
    _prev = {k: _state[k] for k in [
        "scored_population", "explanation_long", "prediction_col",
        "current_dataset_id", "current_dataset_name",
    ] if k in _state}

    _state["ready"] = False
    _state.pop("init_error", None)
    _state.pop("switch_error", None)

    async def _score_and_switch() -> None:
        try:
            loop = asyncio.get_running_loop()
            scored_pop, expl_long, prediction_col = await loop.run_in_executor(
                None,
                lambda: build_tables_from_deployment(
                    deployment_id=cfg.deployment_id,
                    scoring_dataset_id=req.dataset_id,
                    max_explanations=cfg.max_explanations,
                    row_id_col=cfg.row_id_col,
                    prediction_col_cfg=cfg.prediction_col,
                ),
            )
            validate_columns_against_profile(list(scored_pop.columns), _state["profile_cfg"])
            dataset_name = req.display_name or get_dataset_name(req.dataset_id)
            _state.update({
                "scored_population": scored_pop,
                "explanation_long": expl_long,
                "prediction_col": prediction_col,
                "current_dataset_id": req.dataset_id,
                "current_dataset_name": dataset_name,
                "ready": True,
            })
            logger.info("Dataset switch complete (scored) → %s (%d rows)", dataset_name, len(scored_pop))
        except Exception as exc:
            logger.error("Dataset switch failed: %s", exc, exc_info=True)
            # Restore previous working state so the app stays usable
            _state.update(_prev)
            _state["ready"] = True
            _state["switch_error"] = str(exc)

    asyncio.create_task(_score_and_switch())
    logger.info("Dataset switch started (batch prediction) for %s", req.dataset_id)
    return {"status": "loading", "dataset_id": req.dataset_id}


# ---------------------------------------------------------------------------
# /api/health
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    if not _state.get("ready"):
        return {
            "status": "error" if _state.get("init_error") else "loading",
            "detail": _state.get("init_error"),
            "rows_loaded": 0,
            "explanation_rows": 0,
        }
    pop = _state["scored_population"]
    expl = _state["explanation_long"]
    return {
        "status": "ok",
        "rows_loaded": len(pop),
        "explanation_rows": len(expl),
        "prediction_col": _state.get("prediction_col"),
        "sample_row_ids": pop[_row_id_col()].dropna().astype(str).unique()[:5].tolist(),
        "switch_error": _state.get("switch_error"),
    }


# ---------------------------------------------------------------------------
# /api/columns
# ---------------------------------------------------------------------------

@app.get("/api/columns")
def list_columns():
    """Return metadata for each column suitable for building filter controls."""
    df = _pop()
    result = []
    for col in df.columns:
        series = df[col]
        n_unique = series.nunique()

        if pd.api.types.is_numeric_dtype(series):
            result.append({
                "name": col,
                "type": "numeric",
                "min": float(series.min()) if not series.isna().all() else None,
                "max": float(series.max()) if not series.isna().all() else None,
            })
        elif n_unique <= 200:
            result.append({
                "name": col,
                "type": "categorical",
                "values": sorted(series.dropna().astype(str).unique().tolist())[:200],
            })
        else:
            result.append({"name": col, "type": "text", "n_unique": n_unique})

    return {"columns": result}


# ---------------------------------------------------------------------------
# /api/cohort
# ---------------------------------------------------------------------------

@app.get("/api/cohort")
def get_cohort(filters: Optional[str] = Query(None)):
    df = _pop()
    parsed = _parse_filters(filters)
    cohort_df = apply_filters(df, parsed) if parsed else df
    profile = cohort_profile(
        cohort_df, df,
        prediction_col=_prediction_col(),
        score_histogram_bins=_state["score_histogram_bins"],
        row_id_col=_row_id_col(),
    )
    return profile


# ---------------------------------------------------------------------------
# /api/groups
# ---------------------------------------------------------------------------

@app.get("/api/groups")
def get_groups(filters: Optional[str] = Query(None)):
    df = _pop()
    expl = _expl()
    parsed = _parse_filters(filters)
    cohort_df = apply_filters(df, parsed) if parsed else df
    row_ids = cohort_df[_row_id_col()].astype(str).tolist()
    groups = group_shap_summary(
        row_ids, expl,
        row_id_col="row_id",
        top_features_per_group=_state["top_features_per_group"],
    )
    return {"n_rows": len(row_ids), "groups": groups}


# ---------------------------------------------------------------------------
# /api/row/{row_id}
# ---------------------------------------------------------------------------

@app.get("/api/row/{row_id}")
def get_row(row_id: str):
    result = row_explanation(
        row_id, _pop(), _expl(),
        row_id_col=_row_id_col(),
        prediction_col=_prediction_col(),
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Row '{row_id}' not found")
    return result


# ---------------------------------------------------------------------------
# /api/llm/providers
# ---------------------------------------------------------------------------

@app.get("/api/llm/providers")
def get_llm_providers():
    cfg = get_settings()
    providers = [p.to_dict() for p in available_providers(cfg)]
    return {"providers": providers, "default": default_provider(cfg)}


# ---------------------------------------------------------------------------
# /api/narrative
# ---------------------------------------------------------------------------

class NarrativeRequest(BaseModel):
    filters: dict[str, Any] = {}
    custom_instruction: str = ""
    include_outcome_rate: bool = False
    provider: Optional[str] = None


@app.post("/api/narrative")
def post_narrative(req: NarrativeRequest):
    cfg = get_settings()
    nc = _state["narrative_cfg"]
    outcome_col = _state.get("outcome_col")

    df = _pop()
    cohort_df = apply_filters(df, req.filters) if req.filters else df
    profile = cohort_profile(
        cohort_df, df,
        prediction_col=_prediction_col(),
        score_histogram_bins=_state["score_histogram_bins"],
        row_id_col=_row_id_col(),
    )

    row_ids = cohort_df[_row_id_col()].astype(str).tolist()
    groups = group_shap_summary(
        row_ids, _expl(),
        row_id_col="row_id",
        top_features_per_group=_state["top_features_per_group"],
    )

    outcome_rate: Optional[float] = None
    if req.include_outcome_rate and outcome_col and outcome_col in cohort_df.columns:
        outcome_rate = float(
            pd.to_numeric(cohort_df[outcome_col], errors="coerce").mean()
        )

    try:
        text = generate_narrative(
            profile=profile,
            groups=groups,
            filters=req.filters,
            nc=nc,
            settings=cfg,
            outcome_rate=outcome_rate,
            custom_instruction=req.custom_instruction,
            provider=req.provider,
            cohort_warning_min_rows=_state["cohort_warning_min_rows"],
            narrative_max_tokens=_state["narrative_max_tokens"],
            narrative_groups_in_prompt=_state["narrative_groups_in_prompt"],
            narrative_features_per_group=_state["narrative_features_per_group"],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    used_provider = req.provider or default_provider(cfg)
    return {
        "narrative": text,
        "provider_used": used_provider,
        "disclaimer": "AI-generated summary — for indicative use only. Verify against source data before acting.",
    }


# ---------------------------------------------------------------------------
# /api/narrative/row
# ---------------------------------------------------------------------------

class RowNarrativeRequest(BaseModel):
    row_id: str
    custom_instruction: str = ""
    provider: Optional[str] = None


@app.post("/api/narrative/row")
def post_row_narrative(req: RowNarrativeRequest):
    cfg = get_settings()
    nc = _state["narrative_cfg"]

    row_data = row_explanation(
        req.row_id, _pop(), _expl(),
        row_id_col=_row_id_col(),
        prediction_col=_prediction_col(),
    )
    if row_data is None:
        raise HTTPException(status_code=404, detail=f"Row '{req.row_id}' not found")

    try:
        text = generate_row_narrative(
            row_data=row_data,
            nc=nc,
            settings=cfg,
            provider=req.provider,
            custom_instruction=req.custom_instruction,
            narrative_max_tokens=_state["narrative_max_tokens"],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    used_provider = req.provider or default_provider(cfg)
    return {
        "narrative": text,
        "provider_used": used_provider,
        "disclaimer": "AI-generated summary — for indicative use only. Verify against source data before acting.",
    }


# ---------------------------------------------------------------------------
# Static frontend (production / Codespace)
# ---------------------------------------------------------------------------

_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str):
        return FileResponse(os.path.join(_DIST, "index.html"))
