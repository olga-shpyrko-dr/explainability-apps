"""
FastAPI backend for the IL Explainability App.

On startup, fetches prediction explanations from DataRobot and caches two
DataFrames in memory:  scored_population  and  explanation_long.

Endpoints:
  GET  /api/health
  GET  /api/cohort            — profile stats for a filtered cohort
  GET  /api/groups            — group SHAP aggregations for a filtered cohort
  GET  /api/row/{row_id}      — waterfall explanation for one policy
  GET  /api/columns           — list of filterable columns + unique values/range
  GET  /api/llm/providers     — available LLM providers + which have credentials
  POST /api/narrative         — generate LLM summary (provider selectable)
"""

from __future__ import annotations

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
from cohort import apply_filters, cohort_profile, group_shap_summary, row_explanation
from llm_client import available_providers, default_provider
from narrative import generate_narrative
from pipeline import build_tables

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = get_settings()
    os.environ["DATAROBOT_API_TOKEN"] = cfg.datarobot_api_token
    os.environ["DATAROBOT_ENDPOINT"] = cfg.datarobot_endpoint

    logger.info("Fetching data from DataRobot…")
    scored_pop, expl_long = build_tables(
        project_id=cfg.project_id,
        model_id=cfg.model_id,
        scoring_dataset_id=cfg.scoring_dataset_id,
        max_explanations=cfg.max_explanations,
        row_id_col=cfg.row_id_col,
    )
    _state["scored_population"] = scored_pop
    _state["explanation_long"] = expl_long
    _state["row_id_col"] = cfg.row_id_col
    logger.info(
        "Ready. scored_population=%s  explanation_long=%s",
        scored_pop.shape, expl_long.shape,
    )
    yield
    _state.clear()


app = FastAPI(title="IL Explainability API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _pop() -> pd.DataFrame:
    return _state["scored_population"]


def _expl() -> pd.DataFrame:
    return _state["explanation_long"]


def _row_id_col() -> str:
    return _state.get("row_id_col", "Policy_Number")


def _parse_filters(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    import json
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _prediction_col(df: pd.DataFrame) -> Optional[str]:
    return next(
        (c for c in df.columns if "PREDICTION" in c.upper() or c == "prediction"), None
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health():
    pop = _state.get("scored_population")
    expl = _state.get("explanation_long")
    return {
        "status": "ok",
        "rows_loaded": len(pop) if pop is not None else 0,
        "explanation_rows": len(expl) if expl is not None else 0,
        "explanation_sample_row_ids": (
            expl["row_id"].dropna().unique()[:5].tolist() if expl is not None and not expl.empty else []
        ),
        "population_sample_row_ids": (
            pop[_state.get("row_id_col", "Policy_Number")].dropna().astype(str).unique()[:5].tolist()
            if pop is not None else []
        ),
    }


@app.get("/api/columns")
def list_columns():
    """Return metadata for each column suitable for building filter controls."""
    df = _pop()
    result = []
    for col in df.columns:
        series = df[col]
        dtype = str(series.dtype)
        n_unique = series.nunique()

        if pd.api.types.is_numeric_dtype(series):
            result.append({
                "name": col,
                "type": "numeric",
                "min": float(series.min()) if not series.isna().all() else None,
                "max": float(series.max()) if not series.isna().all() else None,
            })
        elif n_unique <= 50:
            result.append({
                "name": col,
                "type": "categorical",
                "values": sorted(series.dropna().astype(str).unique().tolist()),
            })
        else:
            result.append({"name": col, "type": "text", "n_unique": n_unique})

    return {"columns": result}


@app.get("/api/cohort")
def get_cohort(filters: Optional[str] = Query(None, description="JSON filter object")):
    """
    Returns cohort profile statistics.
    filters: JSON string, e.g. {"Age_life1": {"min": 30, "max": 45}, "SmokerStatus": ["Y"]}
    """
    df = _pop()
    parsed = _parse_filters(filters)
    cohort_df = apply_filters(df, parsed) if parsed else df
    pred_col = _prediction_col(df) or "prediction"
    profile = cohort_profile(cohort_df, df, prediction_col=pred_col)
    return profile


@app.get("/api/groups")
def get_groups(filters: Optional[str] = Query(None)):
    """Return group SHAP aggregations for the filtered cohort."""
    df = _pop()
    expl = _expl()
    parsed = _parse_filters(filters)
    cohort_df = apply_filters(df, parsed) if parsed else df
    row_ids = cohort_df[_row_id_col()].astype(str).tolist()
    groups = group_shap_summary(row_ids, expl, row_id_col="row_id")
    n_cohort = len(row_ids)
    return {"n_rows": n_cohort, "groups": groups}


@app.get("/api/row/{row_id}")
def get_row(row_id: str):
    """Return waterfall explanation for a single policy."""
    result = row_explanation(
        row_id, _pop(), _expl(), row_id_col=_row_id_col()
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Policy {row_id!r} not found")
    return result


@app.get("/api/llm/providers")
def get_llm_providers():
    """Return which LLM providers have credentials configured."""
    cfg = get_settings()
    providers = [p.to_dict() for p in available_providers(cfg)]
    return {
        "providers": providers,
        "default": default_provider(cfg),
    }


class NarrativeRequest(BaseModel):
    filters: dict[str, Any] = {}
    custom_instruction: str = ""
    include_outcome_rate: bool = False
    provider: Optional[str] = None  # dr_gateway | dr_deployment | azure_openai | anthropic


@app.post("/api/narrative")
def post_narrative(req: NarrativeRequest):
    """Generate an LLM narrative for the current cohort."""
    cfg = get_settings()

    df = _pop()
    cohort_df = apply_filters(df, req.filters) if req.filters else df
    pred_col = _prediction_col(df) or "prediction"
    profile = cohort_profile(cohort_df, df, prediction_col=pred_col)

    row_ids = cohort_df[_row_id_col()].astype(str).tolist()
    groups = group_shap_summary(row_ids, _expl(), row_id_col="row_id")

    outcome_rate: Optional[float] = None
    if req.include_outcome_rate and "Lapse_ind" in cohort_df.columns:
        outcome_rate = float(
            pd.to_numeric(cohort_df["Lapse_ind"], errors="coerce").mean()
        )

    try:
        text = generate_narrative(
            profile=profile,
            groups=groups,
            filters=req.filters,
            settings=cfg,
            outcome_rate=outcome_rate,
            custom_instruction=req.custom_instruction,
            provider=req.provider,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    used_provider = req.provider or default_provider(cfg)
    return {
        "narrative": text,
        "provider_used": used_provider,
        "disclaimer": "AI-generated summary — for indicative use only.",
    }


# ---------------------------------------------------------------------------
# Static frontend — must be registered AFTER all /api routes so they take
# precedence. Only active when frontend/dist/ exists (production / Codespace).
# In local dev the Vite dev server handles the frontend instead.
# ---------------------------------------------------------------------------
_DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str):
        return FileResponse(os.path.join(_DIST, "index.html"))
