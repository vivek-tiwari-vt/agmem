"""OpenAI LLM provider."""

import os
from typing import Optional, List, Dict, Any

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    """OpenAI (GPT) provider. API key from OPENAI_API_KEY."""

    def __init__(self, model: Optional[str] = None):
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")

    @property
    def name(self) -> str:
        return "openai"

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        import openai

        m = model or self._model
        response = openai.chat.completions.create(
            model=m,
            messages=messages,
            max_tokens=max_tokens,
            **kwargs,
        )
        return response.choices[0].message.content or ""
