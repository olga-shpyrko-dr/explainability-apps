"""
Export DataRobot explanation data to SQL Server for Power BI consumption.

Data sources:
  - DataRobot API  : SHAP prediction explanations + scored population
  - Local Excel    : optional training file for Lapse_ind outcome labels

Output tables in SQL Server:
  {prefix}scored_population     — all source features + prediction score
  {prefix}explanation_long      — unpivoted SHAP rows with group labels
  {prefix}feature_group_mapping — feature → group config (from JSON)

Usage:
  python scripts/export_to_sql.py [--replace]
  python scripts/export_to_sql.py --training-excel data/training.xlsx

Config (read from .env in project root or environment variables):
  DATAROBOT_API_TOKEN         required
  DATAROBOT_ENDPOINT          default: https://app.eu.datarobot.com/api/v2
  SQL_CONNECTION_STRING       required  e.g. mssql+pyodbc://server/db?driver=...
  SQL_SCHEMA                  default: dbo
  SQL_TABLE_PREFIX            default: explainability_
  TRAINING_EXCEL_PATH         optional  adds Lapse_ind column to scored_population
  PROJECT_ID                  default from backend config
  MODEL_ID                    default from backend config
  SCORING_DATASET_ID          default from backend config
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ── Paths ─────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
_BACKEND = _ROOT / "backend"

# Load .env from project root
load_dotenv(_ROOT / ".env")

# Put backend on path so we can import pipeline helpers
sys.path.insert(0, str(_BACKEND))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────

def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"ERROR: {name} is not set. Add it to .env or the environment.")
    return val


def _get_config() -> dict:
    return {
        "sql_connection": _require_env("SQL_CONNECTION_STRING"),
        "sql_schema": os.environ.get("SQL_SCHEMA", "dbo"),
        "table_prefix": os.environ.get("SQL_TABLE_PREFIX", "explainability_"),
        "project_id": os.environ.get("PROJECT_ID", "6a22f2218f74af009899ddb1"),
        "model_id": os.environ.get("MODEL_ID", "6a22f2ab13b0a82934ef1155"),
        "scoring_dataset_id": os.environ.get("SCORING_DATASET_ID", "6a2275eb326d5530a77a0b30"),
        "row_id_col": os.environ.get("ROW_ID_COL", "Policy_Number"),
        "max_explanations": int(os.environ.get("MAX_EXPLANATIONS", "4")),
        "training_excel": os.environ.get("TRAINING_EXCEL_PATH"),
    }


# ── Data loading ──────────────────────────────────────────────────────────────

def load_from_datarobot(cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Pull scored_population and explanation_long from DataRobot API."""
    logger.info("Pulling data from DataRobot API…")
    os.environ["DATAROBOT_API_TOKEN"] = _require_env("DATAROBOT_API_TOKEN")
    os.environ["DATAROBOT_ENDPOINT"] = os.environ.get(
        "DATAROBOT_ENDPOINT", "https://app.eu.datarobot.com/api/v2"
    )
    from pipeline import build_tables
    scored_pop, explanation_long = build_tables(
        project_id=cfg["project_id"],
        model_id=cfg["model_id"],
        scoring_dataset_id=cfg["scoring_dataset_id"],
        max_explanations=cfg["max_explanations"],
        row_id_col=cfg["row_id_col"],
    )
    logger.info(
        "DataRobot data ready — scored_population=%s  explanation_long=%s",
        scored_pop.shape, explanation_long.shape,
    )
    return scored_pop, explanation_long


def enrich_with_training_labels(
    scored_pop: pd.DataFrame, training_excel: str, row_id_col: str
) -> pd.DataFrame:
    """Merge Lapse_ind from training Excel into scored_population."""
    logger.info("Reading training Excel for Lapse_ind labels: %s", training_excel)
    train_df = pd.read_excel(training_excel, dtype={row_id_col: str})

    if "Lapse_ind" not in train_df.columns:
        logger.warning("Lapse_ind column not found in training Excel — skipping merge")
        return scored_pop

    labels = train_df[[row_id_col, "Lapse_ind"]].drop_duplicates(row_id_col)
    n_before = len(scored_pop)
    merged = scored_pop.merge(labels, on=row_id_col, how="left", suffixes=("", "_train"))

    # Keep the training label; drop duplicate if scoring file already had one
    if "Lapse_ind_train" in merged.columns:
        merged["Lapse_ind"] = merged["Lapse_ind_train"].combine_first(merged.get("Lapse_ind"))
        merged.drop(columns=["Lapse_ind_train"], inplace=True)

    match_count = merged["Lapse_ind"].notna().sum()
    logger.info(
        "Lapse_ind merged — %d / %d rows matched (%.1f%%)",
        match_count, n_before, 100 * match_count / n_before if n_before else 0,
    )
    return merged


def load_group_mapping() -> pd.DataFrame:
    """Return feature_group_mapping as a DataFrame from the JSON config."""
    import json
    mapping_path = _BACKEND / "feature_group_mapping.json"
    with open(mapping_path) as f:
        raw = json.load(f)
    rows = [
        {"feature_name": feat, "feature_group": group}
        for group, features in raw["groups"].items()
        for feat in features
    ]
    return pd.DataFrame(rows)


# ── SQL export ────────────────────────────────────────────────────────────────

def write_table(
    df: pd.DataFrame,
    table_name: str,
    engine,
    schema: str,
    if_exists: str,
) -> None:
    full_name = f"{schema}.{table_name}"
    logger.info("Writing %s rows → %s…", len(df), full_name)
    df.to_sql(
        table_name,
        con=engine,
        schema=schema,
        if_exists=if_exists,
        index=False,
        chunksize=5000,
    )
    logger.info("  ✓ %s", full_name)


def ensure_schema(engine, schema: str) -> None:
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT schema_id FROM sys.schemas WHERE name = :s"),
            {"s": schema},
        )
        if not result.fetchone():
            conn.execute(text(f"CREATE SCHEMA [{schema}]"))
            conn.commit()
            logger.info("Created schema [%s]", schema)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Export explainability tables to SQL Server")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="DROP and recreate tables (default: fail if tables exist)",
    )
    parser.add_argument(
        "--training-excel",
        metavar="PATH",
        help="Path to training Excel file (overrides TRAINING_EXCEL_PATH env var)",
    )
    args = parser.parse_args()

    cfg = _get_config()
    if args.training_excel:
        cfg["training_excel"] = args.training_excel

    if_exists = "replace" if args.replace else "fail"
    prefix = cfg["table_prefix"]
    schema = cfg["sql_schema"]

    # ── 1. Load data ──────────────────────────────────────────────────────────
    scored_pop, explanation_long = load_from_datarobot(cfg)

    if cfg["training_excel"]:
        scored_pop = enrich_with_training_labels(
            scored_pop, cfg["training_excel"], cfg["row_id_col"]
        )

    group_mapping = load_group_mapping()

    # ── 2. Normalise types ────────────────────────────────────────────────────
    # Ensure row_id is string in both tables so Power BI joins work
    row_id_col = cfg["row_id_col"]
    scored_pop[row_id_col] = scored_pop[row_id_col].astype(str)
    explanation_long["row_id"] = explanation_long["row_id"].astype(str)

    # Convert any object columns that are really numeric
    for col in scored_pop.columns:
        if scored_pop[col].dtype == object:
            try:
                scored_pop[col] = pd.to_numeric(scored_pop[col])
            except (ValueError, TypeError):
                pass

    # ── 3. Connect and write ──────────────────────────────────────────────────
    logger.info("Connecting to SQL Server…")
    engine = create_engine(cfg["sql_connection"], fast_executemany=True)

    ensure_schema(engine, schema)

    write_table(scored_pop,      f"{prefix}scored_population",     engine, schema, if_exists)
    write_table(explanation_long, f"{prefix}explanation_long",      engine, schema, if_exists)
    write_table(group_mapping,   f"{prefix}feature_group_mapping",  engine, schema, if_exists)

    # ── 4. Print Power BI setup notes ─────────────────────────────────────────
    pop_table  = f"[{schema}].[{prefix}scored_population]"
    expl_table = f"[{schema}].[{prefix}explanation_long]"
    map_table  = f"[{schema}].[{prefix}feature_group_mapping]"

    print(f"""
╔══════════════════════════════════════════════════════════════════╗
  Export complete — 3 tables written to SQL Server
╚══════════════════════════════════════════════════════════════════╝

  {pop_table}
    {len(scored_pop):,} rows × {len(scored_pop.columns)} cols
    Key columns: {row_id_col}, Lapse_ind_1_PREDICTION, Decile, …

  {expl_table}
    {len(explanation_long):,} rows  (top-{cfg["max_explanations"]} explanations per policy)
    Key columns: row_id, explanation_rank, feature_name, shap_strength, feature_group

  {map_table}
    {len(group_mapping):,} feature → group mappings

──────────────────────────────────────────────────────────────────
  Power BI setup:
  1. Connect to SQL Server → Import or DirectQuery
  2. Load all three tables
  3. Create relationship:
       {pop_table}[{row_id_col}]  →  {expl_table}[row_id]  (1:many)
  4. Add DAX measure for group SHAP:
       Avg Group SHAP =
         AVERAGEX(RELATEDTABLE({expl_table}), {expl_table}[shap_strength])

  Suggested slicers: Decile, Product_Desc, Age_life1, SmokerStatus,
                     MonthsSinceReview, feature_group
──────────────────────────────────────────────────────────────────
""")


if __name__ == "__main__":
    main()
