"""
LLM provider interface for agmem.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class LLMProvider(ABC):
    """Abstract LLM provider (complete(messages) -> text)."""

    @abstractmethod
    def complete(
        self,
        messages: List[Dict[str, str]],
        *,
        model: Optional[str] = None,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> str:
        """Return completion text for messages. Raises on failure."""
        pass

    @property
    def name(self) -> str:
        """Provider name (e.g. openai, anthropic)."""
        return "base"
