"""
Cohort filtering engine.

Applies filter criteria to scored_population and returns the matching row IDs,
profile stats, and group SHAP aggregations.
"""

from __future__ import annotations

from typing import Any, Optional
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Filter application
# ---------------------------------------------------------------------------

def apply_filters(df: pd.DataFrame, filters: dict[str, Any]) -> pd.DataFrame:
    """
    Apply a dict of filter specs to a DataFrame.

    Supported filter types:
      range:        {"min": ..., "max": ...}
      multiselect:  list of values
      scalar:       single value (equality)
    """
    mask = pd.Series(True, index=df.index)

    for col, spec in filters.items():
        if col not in df.columns:
            continue

        if isinstance(spec, dict) and ("min" in spec or "max" in spec):
            lo = spec.get("min")
            hi = spec.get("max")
            col_series = pd.to_numeric(df[col], errors="coerce")
            if lo is not None:
                mask &= col_series >= lo
            if hi is not None:
                mask &= col_series <= hi

        elif isinstance(spec, list):
            mask &= df[col].isin(spec)

        else:
            mask &= df[col] == spec

    return df[mask]


# ---------------------------------------------------------------------------
# Profile statistics
# ---------------------------------------------------------------------------

def cohort_profile(
    cohort_df: pd.DataFrame,
    full_df: pd.DataFrame,
    prediction_col: str = "prediction",
) -> dict[str, Any]:
    """
    Return summary statistics for the cohort vs. full population.
    """
    n = len(cohort_df)
    n_total = len(full_df)

    def score_stats(df: pd.DataFrame) -> dict:
        if prediction_col not in df.columns or df[prediction_col].isna().all():
            return {"mean": None, "median": None, "p90": None}
        s = pd.to_numeric(df[prediction_col], errors="coerce").dropna()
        return {
            "mean": round(float(s.mean()), 4),
            "median": round(float(s.median()), 4),
            "p90": round(float(s.quantile(0.9)), 4),
        }

    score_hist = _histogram(
        pd.to_numeric(cohort_df.get(prediction_col, pd.Series(dtype=float)), errors="coerce"),
        bins=20,
    )

    return {
        "n_rows": n,
        "n_total": n_total,
        "pct_of_total": round(n / n_total * 100, 2) if n_total else 0,
        "score_stats": score_stats(cohort_df),
        "score_stats_full": score_stats(full_df),
        "score_histogram": score_hist,
    }


def _histogram(series: pd.Series, bins: int = 20) -> list[dict]:
    s = series.dropna()
    if len(s) == 0:
        return []
    counts, edges = np.histogram(s, bins=bins, range=(0.0, 1.0))
    return [
        {"bin_start": round(float(edges[i]), 3), "bin_end": round(float(edges[i + 1]), 3),
         "count": int(counts[i])}
        for i in range(len(counts))
    ]


# ---------------------------------------------------------------------------
# Group SHAP aggregation
# ---------------------------------------------------------------------------

def group_shap_summary(
    cohort_row_ids: list[str],
    explanation_long: pd.DataFrame,
    row_id_col: str = "row_id",
) -> list[dict[str, Any]]:
    """
    Aggregate SHAP values by feature group for the cohort.

    Returns list of dicts sorted by |avg_shap| descending:
        feature_group, avg_shap, n_rows_with_coverage, coverage_pct,
        top_features (list of {feature_name, avg_shap, n_rows})
    """
    cohort_set = set(cohort_row_ids)
    cohort_exp = explanation_long[explanation_long[row_id_col].isin(cohort_set)].copy()
    n_cohort = len(cohort_set)

    if cohort_exp.empty:
        return []

    cohort_exp["shap_strength"] = pd.to_numeric(cohort_exp["shap_strength"], errors="coerce")

    # Group-level aggregation
    # avg_abs_shap — mean(|strength|) — drives bar height and sort order;
    #   preserves signal when strong features of opposite sign are present in the group.
    # sum_shap — sum of signed strengths — drives colour (net direction);
    #   a single strong feature outweighs many weak ones of the opposite sign.
    cohort_exp["abs_shap"] = cohort_exp["shap_strength"].abs()
    group_agg = (
        cohort_exp.groupby("feature_group")
        .agg(
            avg_abs_shap=("abs_shap", "mean"),
            sum_shap=("shap_strength", "sum"),
            n_rows_with_coverage=(row_id_col, "nunique"),
        )
        .reset_index()
    )
    group_agg["coverage_pct"] = (group_agg["n_rows_with_coverage"] / n_cohort * 100).round(1)
    group_agg["avg_abs_shap"] = group_agg["avg_abs_shap"].round(5)
    group_agg["sum_shap"] = group_agg["sum_shap"].round(5)

    # Feature-level breakdown per group (top 5 features by |avg_shap|)
    feat_agg = (
        cohort_exp.groupby(["feature_group", "feature_name"])
        .agg(avg_shap=("shap_strength", "mean"), n_rows=(row_id_col, "nunique"))
        .reset_index()
    )

    top_features: dict[str, list] = {}
    for group in group_agg["feature_group"]:
        top = (
            feat_agg[feat_agg["feature_group"] == group]
            .assign(abs_shap=lambda d: d["avg_shap"].abs())
            .nlargest(5, "abs_shap")
            .drop(columns="abs_shap")
        )
        top_features[group] = top[["feature_name", "avg_shap", "n_rows"]].to_dict("records")

    result = group_agg.to_dict("records")
    for row in result:
        row["top_features"] = top_features.get(row["feature_group"], [])

    result.sort(key=lambda r: r["avg_abs_shap"], reverse=True)
    return result


# ---------------------------------------------------------------------------
# Individual row explanation
# ---------------------------------------------------------------------------

def row_explanation(
    row_id: str,
    scored_population: pd.DataFrame,
    explanation_long: pd.DataFrame,
    row_id_col: str = "Policy_Number",
) -> Optional[dict[str, Any]]:
    """
    Return the waterfall data for a single policy.
    """
    # Find the row in scored_population
    row_mask = scored_population[row_id_col].astype(str) == str(row_id)
    if not row_mask.any():
        return None

    row_data = scored_population[row_mask].iloc[0]

    # Find explanations
    exp_mask = explanation_long["row_id"].astype(str) == str(row_id)
    expl_rows = explanation_long[exp_mask].sort_values("explanation_rank")

    prediction_col = next(
        (c for c in scored_population.columns if "PREDICTION" in c.upper() or c == "prediction"),
        None,
    )
    prediction = float(row_data[prediction_col]) if prediction_col else None

    waterfall = expl_rows[[
        "explanation_rank", "feature_name", "shap_strength",
        "actual_value", "qualitative_strength", "feature_group",
    ]].to_dict("records")

    return {
        "row_id": str(row_id),
        "prediction": prediction,
        "waterfall": waterfall,
    }
