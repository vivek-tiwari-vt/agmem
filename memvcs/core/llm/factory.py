"""LLM provider factory: select by config or env."""

import os
from typing import Optional, Dict, Any

from .base import LLMProvider
from .openai_provider import OpenAIProvider
from .anthropic_provider import AnthropicProvider


def get_provider(
    provider_name: Optional[str] = None,
    model: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Optional[LLMProvider]:
    """
    Return LLM provider by name. Config may have llm_provider, llm_model.
    Env: AGMEM_LLM_PROVIDER, OPENAI_API_KEY, ANTHROPIC_API_KEY.
    """
    name = (
        provider_name
        or (config or {}).get("llm_provider")
        or os.environ.get("AGMEM_LLM_PROVIDER", "openai")
    )
    m = model or (config or {}).get("llm_model")
    if name == "openai":
        return OpenAIProvider(model=m)
    if name == "anthropic":
        return AnthropicProvider(model=m)
    return OpenAIProvider(model=m)
