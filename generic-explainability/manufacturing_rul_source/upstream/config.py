"""Configuration for the failure_within_7d time-series model.

Loads DataRobot credentials from a .env file and centralizes all modeling
hyperparameters. See TIME_SERIES_SPEC.md (Model A) for the rationale behind
these values.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# --- Paths --------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent

# Load credentials. Prefer this folder's .env, then fall back to the repo-root
# .env (where the project keeps DATAROBOT_ENDPOINT / DATAROBOT_API_TOKEN).
load_dotenv(REPO_ROOT / ".env")
load_dotenv(HERE / ".env", override=True)

# --- DataRobot credentials ----------------------------------------------------
DATAROBOT_ENDPOINT = os.getenv("DATAROBOT_ENDPOINT")
DATAROBOT_API_TOKEN = os.getenv("DATAROBOT_API_TOKEN")

# --- Data ---------------------------------------------------------------------
# Raw telemetry file (note the .csv.csv naming in the provided dataset).
RAW_TELEMETRY = REPO_ROOT / "input_data" / "asset_telemetry - asset_telemetry.csv.csv"
CLEAN_TELEMETRY = HERE / "asset_telemetry_clean.csv"

# --- Modeling spec (Model A: failure_within_7d) -------------------------------
PROJECT_NAME = "Caterpillar FTFR — failure_within_7d (TS)"
DEPLOYMENT_LABEL = "Caterpillar FTFR — failure_within_7d"
TARGET = "failure_within_7d"
# The raw boolean target is mapped to these text labels in prepare_data.py.
POSITIVE_CLASS = "yes"           # failure within 7 days
NEGATIVE_CLASS = "no"
DATETIME_COLUMN = "timestamp"
SERIES_ID_COLUMN = "asset_id"    # multiseries key (50 assets)

# Windows are expressed in ROW units (= time steps). Without this, DataRobot
# interprets the integers in the detected time unit (hours), and values like 1
# are rejected as "not a multiple of the time step" (the step is 6 hours).
WINDOWS_BASIS_UNIT = "ROW"

# Window units are TIME STEPS; the detected step is 6 hours (4 steps/day).
#   FDW  -28 -> 0  = 7 days of history used to derive lags / rolling features.
#   FW     1 -> 1  = single forecast point. failure_within_7d is a PRE-ENGINEERED
#                    label that already encodes the 7-day horizon, so we predict
#                    the label at the forecast point and do NOT forecast 1..28.
FEATURE_DERIVATION_WINDOW_START = -28
FEATURE_DERIVATION_WINDOW_END = 0
FORECAST_WINDOW_START = 1
FORECAST_WINDOW_END = 1

# Backtests / validation. Data is only ~90 days, so keep these modest.
# If partitioning fails ("not enough history"), lower NUMBER_OF_BACKTESTS to 1
# or shorten VALIDATION_DURATION.
NUMBER_OF_BACKTESTS = 2
VALIDATION_DURATION = "P14D"     # ISO-8601 duration: 14 days per backtest

# Autopilot mode: "quick" | "auto" (full) | "comprehensive" | "manual"
AUTOPILOT_MODE = os.getenv("AUTOPILOT_MODE", "quick")
WORKER_COUNT = int(os.getenv("WORKER_COUNT", "-1"))  # -1 = use all available


def validate() -> None:
    """Fail fast with a clear message if credentials or data are missing."""
    missing = [k for k in ("DATAROBOT_ENDPOINT", "DATAROBOT_API_TOKEN")
               if not os.getenv(k)]
    if missing:
        raise SystemExit(
            f"Missing {', '.join(missing)}. Copy .env.example to .env and fill "
            f"in your DataRobot credentials."
        )
    if not RAW_TELEMETRY.exists():
        raise SystemExit(f"Telemetry file not found: {RAW_TELEMETRY}")
