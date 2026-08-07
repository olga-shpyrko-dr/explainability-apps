"""Shared helpers for the synthetic-data time-series models (B/C/D/F).

All models train on the consistent 100-asset x 12-month subset in
0_synthetic_data/output_subset/. The same leakage discipline as the failure model
applies: only raw sensors + context are predictors; outcome/label columns are
dropped.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

import datarobot as dr
import pandas as pd
import requests
from datarobot.helpers.partitioning_methods import (
    DatetimePartitioningSpecification, FeatureSettings,
)

import config

SUBSET_DIR = config.REPO_ROOT / "0_synthetic_data" / "output_subset"
TELEMETRY = SUBSET_DIR / "asset_telemetry.csv"
WORK_ORDERS = SUBSET_DIR / "work_orders.csv"

DATETIME = "timestamp"
SERIES_ID = "asset_id"

# Legitimate predictors (raw sensors + context). NO label/outcome columns here.
BASE_PREDICTORS = [
    "asset_id", "timestamp", "asset_type", "engine_hours", "engine_rpm",
    "oil_pressure_psi", "coolant_temp_f", "hydraulic_pressure_psi",
    "fuel_burn_rate_gph", "vibration_rms_g", "load_factor_pct",
    "idle_ratio_pct", "ambient_temp_f", "days_since_last_service",
]
# Outcome / alternative-label columns — never predictors (drop all except the
# one that is the current target).
LABEL_COLS = ["rul_days", "fault_severity", "active_fault_codes",
              "failure_within_7d", "next_fault_type"]

# Hourly windows: 7 days of history -> single forecast point.
FDW_START, FDW_END = -168, 0
FW_START, FW_END = 1, 1
N_BACKTESTS = 3
VALIDATION_DURATION = "P30D"


def connect():
    dr.Client(endpoint=config.DATAROBOT_ENDPOINT, token=config.DATAROBOT_API_TOKEN)
    print(f"Connected to {config.DATAROBOT_ENDPOINT}")


def make_telemetry_upload(out_path: Path, target: str | None = None,
                          target_transform=None) -> Path:
    """Build an upload CSV: base predictors (+ target), all other labels dropped."""
    keep = list(BASE_PREDICTORS) + ([target] if target else [])
    first = True
    if out_path.exists():
        out_path.unlink()
    rows = 0
    for chunk in pd.read_csv(TELEMETRY, chunksize=500_000):
        cols = [c for c in keep if c in chunk.columns]
        ch = chunk[cols].copy()
        if target and target_transform is not None:
            ch[target] = target_transform(ch[target])
        ch.to_csv(out_path, mode="w" if first else "a", header=first, index=False)
        first, rows = False, rows + len(ch)
    print(f"Wrote {rows:,} rows -> {out_path.name}  (target={target})")
    return out_path


def ts_partitioning(target: str | None, *, unsupervised=False,
                    unsupervised_type=None, fw_start=FW_START, fw_end=FW_END):
    kwargs = dict(
        datetime_partition_column=DATETIME,
        use_time_series=True,
        multiseries_id_columns=[SERIES_ID],
        feature_derivation_window_start=FDW_START,
        feature_derivation_window_end=FDW_END,
        forecast_window_start=fw_start,
        forecast_window_end=fw_end,
        windows_basis_unit="ROW",
        number_of_backtests=N_BACKTESTS,
        validation_duration=VALIDATION_DURATION,
    )
    if unsupervised:
        kwargs.update(unsupervised_mode=True, unsupervised_type=unsupervised_type)
    elif target:
        # stop deriving lag features of the (sticky/own) target
        kwargs["feature_settings"] = [FeatureSettings(target, do_not_derive=True)]
    return DatetimePartitioningSpecification(**kwargs)


def deploy(project: dr.Project, label: str, description: str):
    try:
        model = dr.ModelRecommendation.get(project.id).get_model()
    except Exception:
        models = project.get_models()
        if not models:
            print("No models to deploy.")
            return None
        model = models[0]
    servers = dr.PredictionServer.list()
    dep = dr.Deployment.create_from_learning_model(
        model_id=model.id, label=label, description=description,
        default_prediction_server_id=servers[0].id if servers else None,
    )
    try:
        dr.Client().post(f"deployments/{dep.id}/tags/", json={"name": "tool", "value": "true"})
    except Exception as e:
        print(f"(tagging skipped: {e})")
    ui = config.DATAROBOT_ENDPOINT.replace("/api/v2", "")
    print(f"Created deployment: {dep.id}  ({label})")
    print(f"Deployment URL: {ui}/deployments/{dep.id}/overview")
    return dep


def report(project: dr.Project, n=5):
    models = project.get_models()
    metric = project.metric
    print(f"=== Top models by {metric} ===")
    for i, m in enumerate(models[:n], 1):
        print(f"{i}. {m.metrics.get(metric, {}).get('validation')!s:>10}  {m.model_type}")


# --- Cross-model dispatch decision -------------------------------------------
# Fuse the per-asset signals from model A (failure_within_7d risk), B (RUL days)
# and C (anomaly score) into one "should we dispatch" flag.
#
# Rule: A OR (B AND C). Trust the failure model; where A is unsure, escalate only
# when the RUL and anomaly models AGREE. Validated on the OOS eval (4 real
# failures / 6 healthy): recall 1.00, precision 0.80, F1 0.89 — beats any single
# model and the looser "A OR B OR C" rule (precision 0.67), because B alone is
# over-eager (whole 785 fleet) and C alone is noisy (false flag on a healthy C175).
A_RISK_THRESHOLD = 0.5       # failure_within_7d probability (model A)
B_RUL_DAYS_THRESHOLD = 7     # remaining useful life, days (model B)
C_ANOMALY_THRESHOLD = 0.9    # peak anomaly score (model C)


def ensemble_decision(a_risk=None, b_rul_days=None, c_anomaly=None, *,
                      a_thr=A_RISK_THRESHOLD, b_thr=B_RUL_DAYS_THRESHOLD,
                      c_thr=C_ANOMALY_THRESHOLD):
    """Combine the A/B/C signals into a single dispatch decision: A OR (B AND C).

    Any signal may be None (that model unavailable / not scored); a missing
    signal simply does not fire. Returns a dict the agent can put straight into a
    dispatch brief:
        failing   : bool   — final decision
        fired_by  : list   — which of A/B/C triggered
        reason    : str    — short human-readable justification
        signals   : dict   — the raw inputs echoed back
    """
    a_fire = a_risk is not None and a_risk > a_thr
    b_fire = b_rul_days is not None and b_rul_days < b_thr
    c_fire = c_anomaly is not None and c_anomaly > c_thr
    failing = a_fire or (b_fire and c_fire)

    fired_by = [n for n, f in (("A", a_fire), ("B", b_fire), ("C", c_fire)) if f]
    if a_fire:
        reason = f"failure risk {a_risk:.2f} >= {a_thr}"
    elif b_fire and c_fire:
        reason = (f"A unsure; RUL {b_rul_days:.1f}d < {b_thr} AND "
                  f"anomaly {c_anomaly:.2f} > {c_thr} (B+C agree)")
    else:
        reason = "below dispatch thresholds"
    return dict(failing=failing, fired_by=fired_by, reason=reason,
                signals=dict(a_risk=a_risk, b_rul_days=b_rul_days, c_anomaly=c_anomaly))


# --- Live multi-model assessment of one asset --------------------------------
# Deployments fronting each model. A is pinned by id (multiple versions share its
# label); B/C resolve by label, falling back gracefully.
# Pinned by id (not label): multiple deployments can share a label, so id avoids
# scoring the wrong version (as happened with A). _resolve_deployment still
# accepts a label and falls back to lookup if these are overridden with one.
DEPLOYMENT_A = "6a31b93f9b5c1b46b913d831"   # Caterpillar FTFR — failure_within_7d (synthetic, clean)
DEPLOYMENT_B = "6a31e9f96b93b06420d2c4ed"   # Caterpillar — rul_days (synthetic)
DEPLOYMENT_C = "6a31e962cfe8faec32f57e4f"   # Caterpillar — telemetry anomaly (synthetic)
DEPLOYMENT_F = "6a31bd6bcfe8faec32f57022"   # Caterpillar — fault_type (synthetic)

# Map A's top sensor driver to the BOM fault_type subsystem(s) it implicates.
SENSOR_TO_SUBSYSTEM = {
    "oil_pressure_psi": ["engine"], "coolant_temp_f": ["engine"],
    "hydraulic_pressure_psi": ["hydraulic"],
    "vibration_rms_g": ["drivetrain", "undercarriage"],
    "engine_rpm": ["electrical"], "fuel_burn_rate_gph": ["electrical"],
    "load_factor_pct": ["undercarriage"], "idle_ratio_pct": ["engine"],
}
MAX_OPTIONAL_PARTS = 5
DEFAULT_TELEMETRY = config.REPO_ROOT / "1_ts_models" / "model_a_failure" / "eval" / "eval_dataset.csv"
DEFAULT_BOM = config.REPO_ROOT / "0_synthetic_data" / "eval_dataset" / "asset_bom.csv"

_CLIENT = None


def _ensure_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = dr.Client(endpoint=config.DATAROBOT_ENDPOINT, token=config.DATAROBOT_API_TOKEN)
    return _CLIENT


def _resolve_deployment(id_or_label):
    try:
        return dr.Deployment.get(id_or_label)
    except Exception:
        for d in dr.Deployment.list():
            if d.label == id_or_label:
                return d
        raise ValueError(f"No deployment matching {id_or_label!r}")


def _score_csv(dep, df, ps, params=None):
    url = f"{ps.url}/predApi/v1.0/deployments/{dep.id}/predictions"
    headers = {"Authorization": f"Bearer {config.DATAROBOT_API_TOKEN}",
               "datarobot-key": ps.datarobot_key,
               "Content-Type": "text/csv; charset=UTF-8"}
    r = requests.post(url, params=params or {}, headers=headers,
                      data=df.to_csv(index=False).encode(), timeout=120)
    r.raise_for_status()
    return r.json().get("data", [])


def _drivers_to_subsystems(drivers):
    """Map a list of sensor-driver feature strings to deduped BOM subsystems."""
    subs = []
    for d in drivers:
        for sub in SENSOR_TO_SUBSYSTEM.get(str(d).split(" (")[0], []):
            if sub not in subs:
                subs.append(sub)
    return subs


def _score_faulttype(g, dep, ps, recent=60):
    """Model F: dominant predicted non-'none' subsystem over the recent window."""
    data = _score_csv(dep, g.tail(recent), ps)
    non_none = [r.get("prediction") for r in data
                if r.get("prediction") and r.get("prediction") != "none"]
    return Counter(non_none).most_common(1)[0][0] if non_none else None


def rank_parts(bom, asset_type, subsystems):
    """Candidate parts for the implicated subsystems, ranked critical-first then
    by typical quantity. Returns (critical_list, optional_list)."""
    p = bom[(bom.asset_type == asset_type) & (bom.fault_type.isin(subsystems))].copy()
    if p.empty:
        return [], []
    p["is_critical"] = p["is_critical"].astype(bool)
    p = p.drop_duplicates("part_number").sort_values(
        ["is_critical", "avg_qty_per_job"], ascending=[False, False])
    return (p[p.is_critical].part_number.tolist(),
            p[~p.is_critical].part_number.tolist())


def assess_asset(asset_id, telemetry=None, *, bom=None, recent=60,
                 dep_a=DEPLOYMENT_A, dep_b=DEPLOYMENT_B, dep_c=DEPLOYMENT_C,
                 dep_f=DEPLOYMENT_F):
    """Score one asset through models A (failure), B (RUL), C (anomaly), fuse them
    via ensemble_decision (A OR (B AND C)), and — when failing — recommend the
    parts to stage (critical vs if-available) from the BOM.

    telemetry / bom: DataFrame or CSV path; default to the shipped eval dataset.
    Returns a dict ready for the agent's dispatch brief.
    """
    _ensure_client()
    df = telemetry if isinstance(telemetry, pd.DataFrame) else pd.read_csv(telemetry or DEFAULT_TELEMETRY)
    g = df[df[SERIES_ID] == asset_id].sort_values(DATETIME).reset_index(drop=True)
    if g.empty:
        raise ValueError(f"asset_id {asset_id!r} not found in telemetry")
    asset_type = g["asset_type"].iloc[0] if "asset_type" in g.columns else None
    ps = dr.PredictionServer.list()[0]

    # A — failure risk + sensor drivers (forecast at the latest scorable point)
    risk, drivers, errors = None, [], []
    try:
        fp = pd.to_datetime(g.loc[len(g) - 2, DATETIME]).isoformat()
        rec = (_score_csv(_resolve_deployment(dep_a), g, ps,
                          params={"maxExplanations": 3, "forecastPoint": fp}) or [{}])[0]
        pv = {x["label"]: x["value"] for x in rec.get("predictionValues", [])}
        risk = round(float(pv.get("yes", rec.get("prediction", 0))), 3)
        drivers = [e["feature"] for e in rec.get("predictionExplanations", [])]
    except Exception as e:
        errors.append(f"A: {e}")

    # B — min predicted RUL over the recent window
    rul = None
    try:
        data = _score_csv(_resolve_deployment(dep_b), g.tail(recent), ps)
        preds = [r["prediction"] for r in data if r.get("prediction") is not None]
        rul = round(min(preds), 1) if preds else None
    except Exception as e:
        errors.append(f"B: {e}")

    # C — peak anomaly over the recent window + the sensor driving that peak row
    anom, c_drivers = None, []
    try:
        data = _score_csv(_resolve_deployment(dep_c), g.tail(recent), ps,
                          params={"maxExplanations": 3})
        scored = [r for r in data if r.get("prediction") is not None]
        if scored:
            peak = max(scored, key=lambda r: r["prediction"])
            anom = round(peak["prediction"], 3)
            c_drivers = [e["feature"] for e in peak.get("predictionExplanations", [])]
    except Exception as e:
        errors.append(f"C: {e}")

    out = ensemble_decision(risk, rul, anom)
    out["asset_id"] = asset_id
    out["asset_type"] = asset_type
    out["top_driver"] = drivers[0] if drivers else None

    # Parts: resolve the failing subsystem by source priority, then rank BOM parts.
    # The subsystem must come from whichever model actually caught the failure:
    #   A fired      -> A's prediction-explanation driver
    #   else C fired -> C's anomalous-sensor driver (A was silent, its driver is moot)
    #   else         -> F's predicted subsystem
    #   else         -> conservative kit: all subsystems for this asset_type
    subsystems, critical, optional, parts_source = [], [], [], None
    if out["failing"] and asset_type:
        bom_df = bom if isinstance(bom, pd.DataFrame) else pd.read_csv(bom or DEFAULT_BOM)
        fired = out["fired_by"]
        if "A" in fired and drivers:
            subsystems, parts_source = _drivers_to_subsystems(drivers), "A"
        elif "C" in fired and c_drivers:
            subsystems, parts_source = _drivers_to_subsystems(c_drivers), "C"
        if not subsystems:                      # fall back to F (subsystem model)
            try:
                f_sub = _score_faulttype(g, _resolve_deployment(dep_f), ps, recent)
                if f_sub:
                    subsystems, parts_source = [f_sub], "F"
            except Exception as e:
                errors.append(f"F: {e}")
        if not subsystems:                      # last resort: whole asset_type kit
            subsystems = sorted(bom_df[bom_df.asset_type == asset_type]
                                .fault_type.unique().tolist())
            parts_source = "fallback"
        critical, optional = rank_parts(bom_df, asset_type, subsystems)
    out["failing_subsystems"] = subsystems
    out["parts_source"] = parts_source        # which model named the subsystem
    out["critical_parts"] = critical          # must-stage (cuOpt hard constraint)
    out["optional_parts"] = optional[:MAX_OPTIONAL_PARTS]  # bring-if-available
    if errors:
        out["errors"] = errors
    return out
