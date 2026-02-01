"""Anthropic (Claude) LLM provider."""

import os
from typing import Optional, List, Dict, Any

from .base import LLMProvider


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider. API key from ANTHROPIC_API_KEY."""

    def __init__(self, model: Optional[str] = None):
        self._model = model or os.environ.get("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

    @property
    def name(self) -> str:
        return "anthropic"

    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("Anthropic provider requires: pip install anthropic")
        m = model or self._model
        client = anthropic.Anthropic()
        # Convert OpenAI-style messages to Anthropic (system + user/assistant)
        system = ""
        anthropic_messages = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                system = content
            else:
                anthropic_messages.append({"role": role, "content": content})
        resp = client.messages.create(
            model=m,
            max_tokens=max_tokens,
            system=system or None,
            messages=anthropic_messages,
            **kwargs,
        )
        return resp.content[0].text if resp.content else ""
