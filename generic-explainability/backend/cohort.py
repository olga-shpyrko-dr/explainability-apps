"""
Cohort filtering engine and SHAP aggregation.
"""

from __future__ import annotations

import math
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
    score_histogram_bins: int = 20,
    row_id_col: str = "id",
    sample_size: int = 5,
) -> dict[str, Any]:
    """Return summary statistics for the cohort vs. full population."""
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
        bins=score_histogram_bins,
    )

    # Sample rows sorted by prediction score descending (highest-risk first)
    if row_id_col in cohort_df.columns and n > 0:
        if prediction_col in cohort_df.columns:
            sample_df = cohort_df.nlargest(sample_size, prediction_col, keep="first")
        else:
            sample_df = cohort_df.head(sample_size)
        sample_row_ids = sample_df[row_id_col].dropna().astype(str).tolist()
    else:
        sample_row_ids = []

    return {
        "n_rows": n,
        "n_total": n_total,
        "pct_of_total": round(n / n_total * 100, 2) if n_total else 0,
        "score_stats": score_stats(cohort_df),
        "score_stats_full": score_stats(full_df),
        "score_histogram": score_hist,
        "sample_row_ids": sample_row_ids,
    }


def _histogram(series: pd.Series, bins: int = 20) -> list[dict]:
    s = series.dropna()
    if len(s) == 0:
        return []
    counts, edges = np.histogram(s, bins=bins, range=(0.0, 1.0))
    return [
        {
            "bin_start": round(float(edges[i]), 3),
            "bin_end": round(float(edges[i + 1]), 3),
            "count": int(counts[i]),
        }
        for i in range(len(counts))
    ]


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-float(x)))


# ---------------------------------------------------------------------------
# Group SHAP aggregation
# ---------------------------------------------------------------------------

def group_shap_summary(
    cohort_row_ids: list[str],
    explanation_long: pd.DataFrame,
    row_id_col: str = "row_id",
    top_features_per_group: int = 5,
    cohort_predictions: Optional[pd.Series] = None,
) -> list[dict[str, Any]]:
    """
    Aggregate SHAP values by feature group for the cohort.

    Returns list of dicts sorted by avg_pp_contribution descending (falls back
    to avg_abs_shap when predictions are not supplied):
        feature_group, avg_abs_shap, avg_shap, sum_shap, avg_pp_contribution,
        n_rows_with_coverage, coverage_pct,
        top_features: [{feature_name, avg_shap, avg_abs_shap, n_rows}]

    Metrics:
      avg_abs_shap — mean(|strength|) — bar height; immune to cancellation.
      avg_shap     — mean(strength)   — signed average; used in narrative table.
      sum_shap     — sum(strength)    — net direction driver; used for bar colour.

    avg_pp_contribution — average probability-space contribution per row (pp).
      For each row: groups are sorted by abs(group SHAP sum) and cumulated
      through sigmoid, so contributions are meaningful in probability space
      and sum to (prediction − baseline_probability) for that row.
    """
    cohort_set = set(cohort_row_ids)
    cohort_exp = explanation_long[explanation_long[row_id_col].isin(cohort_set)].copy()
    n_cohort = len(cohort_set)

    if cohort_exp.empty:
        return []

    cohort_exp["shap_strength"] = pd.to_numeric(cohort_exp["shap_strength"], errors="coerce")
    cohort_exp["abs_shap"] = cohort_exp["shap_strength"].abs()

    group_agg = (
        cohort_exp.groupby("feature_group")
        .agg(
            avg_abs_shap=("abs_shap", "mean"),
            avg_shap=("shap_strength", "mean"),
            sum_shap=("shap_strength", "sum"),
            n_rows_with_coverage=(row_id_col, "nunique"),
        )
        .reset_index()
    )
    group_agg["coverage_pct"] = (group_agg["n_rows_with_coverage"] / n_cohort * 100).round(1)
    group_agg["avg_abs_shap"] = group_agg["avg_abs_shap"].round(5)
    group_agg["avg_shap"] = group_agg["avg_shap"].round(5)
    group_agg["sum_shap"] = group_agg["sum_shap"].round(5)

    # Feature-level breakdown per group
    feat_agg = (
        cohort_exp.groupby(["feature_group", "feature_name"])
        .agg(
            avg_shap=("shap_strength", "mean"),
            avg_abs_shap=("abs_shap", "mean"),
            n_rows=(row_id_col, "nunique"),
        )
        .reset_index()
    )

    top_features: dict[str, list] = {}
    for group in group_agg["feature_group"]:
        top = (
            feat_agg[feat_agg["feature_group"] == group]
            .nlargest(top_features_per_group, "avg_abs_shap")
        )
        top_features[group] = top[
            ["feature_name", "avg_shap", "avg_abs_shap", "n_rows"]
        ].round(5).to_dict("records")

    result = group_agg.to_dict("records")
    for row in result:
        row["top_features"] = top_features.get(row["feature_group"], [])

    # ---------------------------------------------------------------------------
    # Per-row probability contributions via sigmoid transform
    # ---------------------------------------------------------------------------
    if cohort_predictions is not None and not cohort_predictions.empty:
        # Per-row, per-group SHAP sums — shape (n_rows, n_groups)
        row_group = (
            cohort_exp.groupby([row_id_col, "feature_group"])["shap_strength"]
            .sum()
            .unstack(fill_value=0.0)
        )
        # Align predictions index
        preds = cohort_predictions.reindex(row_group.index).dropna()
        row_group = row_group.loc[preds.index]

        row_total_shap = row_group.sum(axis=1)
        # logit per row, clamped to avoid ±inf
        logodds = preds.clip(1e-7, 1 - 1e-7).apply(lambda p: math.log(p / (1 - p)))
        baseline_logodds = logodds - row_total_shap

        # Consistent group ordering for cumulation: descending mean abs contribution
        group_order = row_group.abs().mean().sort_values(ascending=False).index.tolist()
        row_group = row_group[group_order]

        # Vectorised cumulative sigmoid pass
        cum_lo = baseline_logodds.copy()
        pp_cols: dict[str, pd.Series] = {}
        for g in group_order:
            prob_before = cum_lo.apply(_sigmoid)
            cum_lo = cum_lo + row_group[g]
            prob_after = cum_lo.apply(_sigmoid)
            pp_cols[g] = (prob_after - prob_before).abs()

        pp_df = pd.DataFrame(pp_cols)
        avg_pp: dict[str, float] = pp_df.mean().to_dict()
        for row in result:
            row["avg_pp_contribution"] = round(avg_pp.get(row["feature_group"], 0.0), 6)
    else:
        for row in result:
            row["avg_pp_contribution"] = None

    # Sort: "Other" always last; remaining by avg_pp_contribution (or avg_abs_shap) descending
    def _sort_key(r: dict) -> tuple:
        pp = r.get("avg_pp_contribution")
        key = -pp if pp is not None else -r["avg_abs_shap"]
        return (r["feature_group"] == "Other", key)

    result.sort(key=_sort_key)
    return result


# ---------------------------------------------------------------------------
# Individual row explanation
# ---------------------------------------------------------------------------

def row_explanation(
    row_id: str,
    scored_population: pd.DataFrame,
    explanation_long: pd.DataFrame,
    row_id_col: str = "id",
    prediction_col: str = "prediction",
) -> Optional[dict[str, Any]]:
    """Return the waterfall data for a single row."""
    row_mask = scored_population[row_id_col].astype(str) == str(row_id)
    if not row_mask.any():
        return None

    row_data = scored_population[row_mask].iloc[0]
    exp_mask = explanation_long["row_id"].astype(str) == str(row_id)
    expl_rows = explanation_long[exp_mask].sort_values("explanation_rank")

    if prediction_col in scored_population.columns:
        _pred = float(row_data[prediction_col])
        prediction = None if (math.isnan(_pred) or math.isinf(_pred)) else _pred
    else:
        prediction = None

    def _clean(v: Any) -> Any:
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

    waterfall = [
        {k: _clean(val) for k, val in rec.items()}
        for rec in expl_rows[[
            "explanation_rank", "feature_name", "shap_strength",
            "actual_value", "qualitative_strength", "feature_group",
        ]].to_dict("records")
    ]

    return {
        "row_id": str(row_id),
        "prediction": prediction,
        "waterfall": waterfall,
    }
