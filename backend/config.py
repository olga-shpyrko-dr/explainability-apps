from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ------------------------------------------------------------------
    # DataRobot core
    # ------------------------------------------------------------------
    datarobot_api_token: str
    datarobot_endpoint: str = "https://app.eu.datarobot.com/api/v2"

    # ------------------------------------------------------------------
    # Explainability pipeline
    # ------------------------------------------------------------------
    project_id: str = "6a22f2218f74af009899ddb1"
    model_id: str = "6a22f2ab13b0a82934ef1155"
    # Scoring dataset — used for PE generation and as the runtime population
    scoring_dataset_id: str = "6a2275eb326d5530a77a0b30"
    # Training dataset — used for Lapse_ind outcome labels (optional)
    training_dataset_id: str = "6a2275eb1a27ddce9c076a03"
    row_id_col: str = "Policy_Number"
    max_explanations: int = 4

    # ------------------------------------------------------------------
    # LLM — DataRobot LLM Gateway
    # Set DR_GATEWAY_MODEL to the gateway model name, e.g.:
    #   azure-openai/gpt-4o-mini
    #   google-cloud/google-gemini-2.0-flash-001
    # ------------------------------------------------------------------
    dr_gateway_model: Optional[str] = None

    # ------------------------------------------------------------------
    # LLM — DataRobot deployed TextGen model
    # Set DR_LLM_DEPLOYMENT_ID to the deployment ID of a TextGen deployment.
    # ------------------------------------------------------------------
    dr_llm_deployment_id: Optional[str] = None

    # ------------------------------------------------------------------
    # LLM — Azure OpenAI
    # ------------------------------------------------------------------
    azure_openai_api_key: Optional[str] = None
    azure_openai_api_base: Optional[str] = None          # e.g. https://my-instance.openai.azure.com/
    azure_openai_api_version: str = "2024-02-01"
    azure_openai_deployment_name: Optional[str] = None   # e.g. gpt-4o

    # ------------------------------------------------------------------
    # LLM — Anthropic (direct API)
    # ------------------------------------------------------------------
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-6"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # Allow both UPPER_CASE and lower_case env var names
        case_sensitive = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
