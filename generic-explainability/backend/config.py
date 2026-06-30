from functools import lru_cache
from typing import Optional
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # Data source — "datarobot" (default) or "csv"
    # ------------------------------------------------------------------
    data_source: str = "datarobot"
    csv_path: Optional[str] = None           # required when data_source=csv
    training_csv_path: Optional[str] = None  # optional; enables outcome rate in CSV mode

    # ------------------------------------------------------------------
    # DataRobot core — required when data_source=datarobot
    # ------------------------------------------------------------------
    datarobot_api_token: Optional[str] = None
    datarobot_endpoint: str = "https://app.datarobot.com/api/v2"

    # ------------------------------------------------------------------
    # DataRobot pipeline — required when data_source=datarobot.
    # Priority: deployment_id (BatchPredictionJob) → project_id + model_id (PE API).
    # ------------------------------------------------------------------
    deployment_id: Optional[str] = None         # preferred: batch predictions via deployment
    project_id: Optional[str] = None            # fallback when deployment_id not set
    model_id: Optional[str] = None              # fallback when deployment_id not set
    scoring_dataset_id: Optional[str] = None
    training_dataset_id: Optional[str] = None   # optional; enables outcome rate

    # ------------------------------------------------------------------
    # Column config
    # ------------------------------------------------------------------
    row_id_col: str = "id"
    # prediction_col: auto-detected from first column ending in _PREDICTION if not set
    prediction_col: Optional[str] = None
    outcome_col: Optional[str] = None          # binary 0/1 outcome in training data
    max_explanations: int = 4

    # ------------------------------------------------------------------
    # Application metadata
    # ------------------------------------------------------------------
    app_title: str = "Prediction Explainability"
    app_subtitle: str = ""
    dataset_display_name: Optional[str] = None  # overrides dr.Dataset.name in the UI

    # ------------------------------------------------------------------
    # DataRobot Use Case — scopes the dataset selector in the UI.
    # Accepts DEFAULT_USE_CASE_ID (explicit) or the DATAROBOT_USE_CASE_ID
    # that DR injects into Custom Application containers automatically.
    # ------------------------------------------------------------------
    default_use_case_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("DEFAULT_USE_CASE_ID", "DATAROBOT_USE_CASE_ID"),
    )

    # ------------------------------------------------------------------
    # Tuning parameters
    # ------------------------------------------------------------------
    cohort_warning_min_rows: int = 30
    top_features_per_group: int = 5
    score_histogram_bins: int = 20
    narrative_max_tokens: int = 700
    narrative_groups_in_prompt: int = 6
    narrative_features_per_group: int = 2

    # ------------------------------------------------------------------
    # LLM — DataRobot LLM Gateway
    # ------------------------------------------------------------------
    dr_gateway_model: Optional[str] = None

    # ------------------------------------------------------------------
    # LLM — DataRobot deployed TextGen model
    # ------------------------------------------------------------------
    dr_llm_deployment_id: Optional[str] = None

    # ------------------------------------------------------------------
    # LLM — Azure OpenAI
    # ------------------------------------------------------------------
    azure_openai_api_key: Optional[str] = None
    azure_openai_api_base: Optional[str] = None
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_deployment_name: Optional[str] = None

    # ------------------------------------------------------------------
    # LLM — Anthropic (direct API)
    # ------------------------------------------------------------------
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-6"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
