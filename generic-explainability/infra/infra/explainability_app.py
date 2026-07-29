# Copyright 2026 DataRobot, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Pulumi resources for the Generic Explainability Custom Application.

Drop this file into infra/infra/ after scaffolding with af-component-base
(or merge into your existing Custom Application infra module).

Pairs with:
  - .datarobot/cli/explainability-app.yaml  → dr dotenv setup prompts
  - .env.template                           → variable discovery / validation
  - start-app.sh                            → container entry point
"""

from __future__ import annotations

import os
import re
from typing import Final

import pulumi
import pulumi_datarobot
from datarobot_pulumi_utils.schema.apps import ApplicationSourceArgs
from datarobot_pulumi_utils.schema.apps import CustomAppResourceBundles
from datarobot_pulumi_utils.schema.exec_envs import RuntimeEnvironments
from datarobot_pulumi_utils.pulumi.stack import PROJECT_NAME

from . import project_dir, use_case

# Env vars collected by dr dotenv setup — injected as Custom App runtime parameters.
# Keep in sync with .datarobot/cli/explainability-app.yaml and .env.template.
STRING_RUNTIME_ENV_VARS: Final[tuple[str, ...]] = (
    "DATA_SOURCE",
    "CSV_PATH",
    "DATAROBOT_ENDPOINT",
    "DEPLOYMENT_ID",
    "PROJECT_ID",
    "MODEL_ID",
    "SCORING_DATASET_ID",
    "TRAINING_DATASET_ID",
    "DEFAULT_USE_CASE_ID",
    "ROW_ID_COL",
    "PREDICTION_COL",
    "OUTCOME_COL",
    "MAX_EXPLANATIONS",
    "APP_TITLE",
    "APP_SUBTITLE",
    "DATASET_DISPLAY_NAME",
    "DR_GATEWAY_MODEL",
    "DR_LLM_DEPLOYMENT_ID",
    "AZURE_OPENAI_API_BASE",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT_NAME",
    "ANTHROPIC_MODEL",
)

# Stored as DataRobot credentials (not plain string runtime params).
# DATAROBOT_API_TOKEN is omitted — the platform injects it automatically in Custom Apps.
SECRET_RUNTIME_ENV_VARS: Final[tuple[str, ...]] = (
    "AZURE_OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)

EXCLUDE_PATTERNS = [
    re.compile(pattern)
    for pattern in [
        r"metadata\.yaml",
        r".*node_modules/.*",
        r".*\.venv/.*",
        r".*__pycache__/.*",
        r".*\.pytest_cache/.*",
        r".*\.ruff_cache/.*",
        r".*\.mypy_cache/.*",
        r".*\.uv/.*",
        r".*\.DS_Store",
        r".*\.pyc",
        r".*htmlcov/.*",
        r".*\.coverage",
        r".*infra/.*",
        r".*\.git/.*",
        r".*\.env$",
        r".*\.prediction_dataset_cache\.json",
    ]
]

__all__ = [
    "explainability_app",
    "explainability_app_runtime_parameters",
    "explainability_app_source",
    "get_explainability_app_files",
]


def get_explainability_app_files() -> list[tuple[str, str]]:
    """Bundle the recipe root (parent of infra/) for upload to ApplicationSource."""
    application_path = project_dir.parent
    source_files: list[tuple[str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(application_path, followlinks=True):
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(file_path, application_path).replace(os.path.sep, "/")
            if any(pattern.match(rel_path) for pattern in EXCLUDE_PATTERNS):
                continue
            source_files.append((os.path.abspath(file_path), rel_path))
    return source_files


def _string_runtime_param(key: str) -> pulumi_datarobot.ApplicationSourceRuntimeParameterValueArgs | None:
    value = os.environ.get(key)
    if value is None or value == "":
        return None
    return pulumi_datarobot.ApplicationSourceRuntimeParameterValueArgs(
        type="string",
        key=key,
        value=value,
    )


def _build_runtime_parameters() -> list[pulumi_datarobot.ApplicationSourceRuntimeParameterValueArgs]:
    params: list[pulumi_datarobot.ApplicationSourceRuntimeParameterValueArgs] = []

    for key in STRING_RUNTIME_ENV_VARS:
        if param := _string_runtime_param(key):
            params.append(param)

    for key in SECRET_RUNTIME_ENV_VARS:
        secret = os.environ.get(key)
        if not secret:
            continue
        cred = pulumi_datarobot.ApiTokenCredential(
            f"Explainability App {key} [{PROJECT_NAME}]",
            args=pulumi_datarobot.ApiTokenCredentialArgs(api_token=secret),
        )
        params.append(
            pulumi_datarobot.ApplicationSourceRuntimeParameterValueArgs(
                type="credential",
                key=key,
                value=cred.id,
            )
        )

    return params


explainability_app_source_args = ApplicationSourceArgs(
    resource_name=f"Explainability App [{PROJECT_NAME}]",
    base_environment_id=RuntimeEnvironments.PYTHON_312_APPLICATION_BASE.value.id,
).model_dump(mode="json", exclude_none=True)

explainability_app_runtime_parameters = _build_runtime_parameters()

explainability_app_source = pulumi_datarobot.ApplicationSource(
    files=get_explainability_app_files(),
    runtime_parameter_values=explainability_app_runtime_parameters,
    resources=pulumi_datarobot.ApplicationSourceResourcesArgs(
        resource_label=CustomAppResourceBundles.CPU_XL.value.id,
        health_endpoint_path="/health",
    ),
    required_key_scope_level="",
    **explainability_app_source_args,
)

explainability_app = pulumi_datarobot.CustomApplication(
    resource_name=f"Explainability App [{PROJECT_NAME}]",
    source_version_id=explainability_app_source.version_id,
    use_case_ids=[use_case.id],
    allow_auto_stopping=True,
    resources=explainability_app_source.resources,
    required_key_scope_level=explainability_app_source.required_key_scope_level,
    opts=pulumi.ResourceOptions(depends_on=[explainability_app_source]),
)

pulumi.export("DATAROBOT_APPLICATION_ID", explainability_app.id)
pulumi.export("Explainability App URL", explainability_app.application_url)
