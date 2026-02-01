"""Tests for LLM provider abstraction."""

import os
from unittest.mock import patch, MagicMock

from memvcs.core.llm.factory import get_provider
from memvcs.core.llm.base import LLMProvider


class TestGetProvider:
    """Test provider factory."""

    def test_get_provider_default_openai(self):
        provider = get_provider()
        assert provider is not None
        assert provider.name == "openai"

    def test_get_provider_by_name_anthropic(self):
        provider = get_provider(provider_name="anthropic")
        assert provider is not None
        assert provider.name == "anthropic"

    def test_get_provider_with_config(self):
        provider = get_provider(config={"llm_provider": "openai", "llm_model": "gpt-4"})
        assert provider is not None


def _mock_create_return(content: str):
    return MagicMock(choices=[MagicMock(message=MagicMock(content=content))])


class TestOpenAIProviderMocked:
    """Test OpenAI provider with mocked API (no network, no real API key)."""

    def test_complete_returns_text(self):
        from memvcs.core.llm.openai_provider import OpenAIProvider

        provider = OpenAIProvider(model="gpt-3.5-turbo")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch("openai.chat.completions.create") as m:
                m.return_value = _mock_create_return("Hi")
                out = provider.complete([{"role": "user", "content": "Hello"}])
        assert out == "Hi"

    def test_complete_mocked_no_network(self):
        from memvcs.core.llm.openai_provider import OpenAIProvider

        provider = OpenAIProvider(model="gpt-3.5-turbo")
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with patch("openai.chat.completions.create") as m:
                m.return_value = _mock_create_return("mocked")
                out = provider.complete([{"role": "user", "content": "test"}], max_tokens=10)
        assert out == "mocked"
