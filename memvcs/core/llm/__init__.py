"""
Multi-provider LLM integration for agmem.

Abstract interface; implementations: OpenAI, Anthropic, Ollama, custom HTTP.
"""

from .base import LLMProvider
from .factory import get_provider

__all__ = ["LLMProvider", "get_provider"]
