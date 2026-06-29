"""
Unified LLM client using LiteLLM as the abstraction layer.

Supported providers:
  dr_gateway     — DataRobot LLM Gateway (OpenAI-compatible, auth via DR API token)
  dr_deployment  — DataRobot deployed TextGen model (OpenAI-compatible)
  azure_openai   — Azure OpenAI
  anthropic      — Anthropic API (direct)

Provider selection and credentials come from Settings (config.py).
The caller only invokes `call_llm(messages, system, settings, provider)`.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any, Optional

import litellm

logger = logging.getLogger(__name__)

# Suppress litellm's noisy success logs
litellm.suppress_debug_info = True


class LLMProvider(str, Enum):
    DR_GATEWAY = "dr_gateway"
    DR_DEPLOYMENT = "dr_deployment"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"


class LLMProviderInfo:
    def __init__(
        self,
        provider_id: str,
        name: str,
        available: bool,
        model: str,
        notes: str = "",
    ):
        self.provider_id = provider_id
        self.name = name
        self.available = available
        self.model = model
        self.notes = notes

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.provider_id,
            "name": self.name,
            "available": self.available,
            "model": self.model,
            "notes": self.notes,
        }


def available_providers(settings: Any) -> list[LLMProviderInfo]:
    """
    Return metadata for each provider, indicating which ones have credentials set.
    """
    infos = [
        LLMProviderInfo(
            provider_id=LLMProvider.DR_GATEWAY,
            name="DataRobot LLM Gateway",
            available=bool(settings.datarobot_api_token and settings.dr_gateway_model),
            model=settings.dr_gateway_model or "",
            notes="Uses your DataRobot API token; no extra credentials needed.",
        ),
        LLMProviderInfo(
            provider_id=LLMProvider.DR_DEPLOYMENT,
            name="DataRobot Deployed LLM",
            available=bool(settings.datarobot_api_token and settings.dr_llm_deployment_id),
            model=settings.dr_llm_deployment_id or "",
            notes="Calls a deployed TextGen model via its chat completions endpoint.",
        ),
        LLMProviderInfo(
            provider_id=LLMProvider.AZURE_OPENAI,
            name="Azure OpenAI",
            available=bool(
                settings.azure_openai_api_key
                and settings.azure_openai_api_base
                and settings.azure_openai_deployment_name
            ),
            model=settings.azure_openai_deployment_name or "",
            notes="Azure-hosted OpenAI model.",
        ),
        LLMProviderInfo(
            provider_id=LLMProvider.ANTHROPIC,
            name="Anthropic",
            available=bool(settings.anthropic_api_key),
            model=settings.anthropic_model or "claude-sonnet-4-6",
            notes="Calls Anthropic API directly.",
        ),
    ]
    return infos


def default_provider(settings: Any) -> str:
    """Return the first available provider, falling back to dr_gateway."""
    for info in available_providers(settings):
        if info.available:
            return info.provider_id
    return LLMProvider.DR_GATEWAY


def call_llm(
    messages: list[dict[str, str]],
    system: str,
    settings: Any,
    provider: Optional[str] = None,
    max_tokens: int = 700,
) -> str:
    """
    Call the configured LLM provider and return the response text.

    `messages` should be the user/assistant turn list (no system message).
    `system` is injected as the system prompt in the appropriate format.
    """
    resolved_provider = LLMProvider(provider or default_provider(settings))

    # Prepend system message for non-Anthropic providers (they use system param)
    full_messages = [{"role": "system", "content": system}] + messages

    if resolved_provider == LLMProvider.DR_GATEWAY:
        return _call_dr_gateway(full_messages, settings, max_tokens)

    if resolved_provider == LLMProvider.DR_DEPLOYMENT:
        return _call_dr_deployment(full_messages, settings, max_tokens)

    if resolved_provider == LLMProvider.AZURE_OPENAI:
        return _call_azure_openai(full_messages, settings, max_tokens)

    if resolved_provider == LLMProvider.ANTHROPIC:
        # Anthropic expects system as a separate param, not in messages
        return _call_anthropic(
            messages=messages,  # no system in messages array
            system=system,
            settings=settings,
            max_tokens=max_tokens,
        )

    raise ValueError(f"Unknown LLM provider: {resolved_provider}")


# ---------------------------------------------------------------------------
# Provider-specific call helpers
# ---------------------------------------------------------------------------

def _dr_endpoint_base(settings: Any) -> str:
    """Strip trailing /api/v2 or /api/v2/ to get the raw host URL."""
    ep = settings.datarobot_endpoint.rstrip("/")
    # Normalise: ensure we always have /api/v2 on the end for DR REST calls
    return ep


def _call_dr_gateway(
    messages: list[dict[str, str]], settings: Any, max_tokens: int
) -> str:
    """
    DataRobot LLM Gateway — OpenAI-compatible route.

    Base URL: {endpoint}/genai/llmgw
    LiteLLM (openai/ provider) appends /chat/completions automatically.
    Final URL: {endpoint}/genai/llmgw/chat/completions

    Model name: Chat model ID from DataRobot docs, e.g.
      azure/gpt-4o-mini
      anthropic/claude-sonnet-4-6
      vertex_ai/gemini-2.0-flash-001
    """
    endpoint = settings.datarobot_endpoint.rstrip("/")
    gateway_base = f"{endpoint}/genai/llmgw"

    logger.info("DR Gateway call: base=%s model=%s", gateway_base, settings.dr_gateway_model)

    response = litellm.completion(
        model=f"openai/{settings.dr_gateway_model}",
        messages=messages,
        api_base=gateway_base,
        api_key=settings.datarobot_api_token,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content
    logger.info("DR Gateway raw response: %.500s", content)
    return content


def _call_dr_deployment(
    messages: list[dict[str, str]], settings: Any, max_tokens: int
) -> str:
    """
    DataRobot deployed TextGen model via LiteLLM's native 'datarobot/' provider.

    LiteLLM detects 'api/v2/deployments' in the path and uses the URL as-is,
    so pass the full deployment predictions path as api_base.
    """
    endpoint = settings.datarobot_endpoint.rstrip("/")
    deployment_base = f"{endpoint}/deployments/{settings.dr_llm_deployment_id}/"

    logger.info("DR Deployment call: deployment_id=%s", settings.dr_llm_deployment_id)

    response = litellm.completion(
        model=f"datarobot/{settings.dr_llm_deployment_id}",
        messages=messages,
        api_base=deployment_base,
        api_key=settings.datarobot_api_token,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def _call_azure_openai(
    messages: list[dict[str, str]], settings: Any, max_tokens: int
) -> str:
    """
    Azure OpenAI — standard litellm azure/ prefix.
    """
    logger.info(
        "Azure OpenAI call: deployment=%s base=%s",
        settings.azure_openai_deployment_name,
        settings.azure_openai_api_base,
    )

    response = litellm.completion(
        model=f"azure/{settings.azure_openai_deployment_name}",
        messages=messages,
        api_key=settings.azure_openai_api_key,
        api_base=settings.azure_openai_api_base,
        api_version=settings.azure_openai_api_version,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content


def _call_anthropic(
    messages: list[dict[str, str]],
    system: str,
    settings: Any,
    max_tokens: int,
) -> str:
    """
    Anthropic — system prompt separate from messages array.
    """
    logger.info("Anthropic call: model=%s", settings.anthropic_model)

    response = litellm.completion(
        model=f"anthropic/{settings.anthropic_model}",
        messages=messages,
        system=system,
        api_key=settings.anthropic_api_key,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content
