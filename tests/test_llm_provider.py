"""Tests for LLM provider abstraction."""

import os
import sys
from unittest.mock import MagicMock, patch

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


def _mock_openai_module(create_return_content: str):
    """Build a fake 'openai' module so tests run without the real package (e.g. in CI)."""
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content=create_return_content))]
    )
    return mock_openai


class TestOpenAIProviderMocked:
    """Test OpenAI provider with mocked API (no network, no real API key)."""

    def test_complete_returns_text(self):
        from memvcs.core.llm.openai_provider import OpenAIProvider

        provider = OpenAIProvider(model="gpt-3.5-turbo")
        mock_openai = _mock_openai_module("Hi")
        with patch.dict(sys.modules, {"openai": mock_openai}):
            out = provider.complete([{"role": "user", "content": "Hello"}])
        assert out == "Hi"

    def test_complete_mocked_no_network(self):
        from memvcs.core.llm.openai_provider import OpenAIProvider

        provider = OpenAIProvider(model="gpt-3.5-turbo")
        mock_openai = _mock_openai_module("mocked")
        with patch.dict(sys.modules, {"openai": mock_openai}):
            out = provider.complete(
                [{"role": "user", "content": "test"}], max_tokens=10
            )
        assert out == "mocked"
