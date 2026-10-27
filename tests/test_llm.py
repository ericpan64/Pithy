"""
Unit tests for pithy_cli.llm module.

Run with: pytest tests/test_llm.py -v
"""

from unittest.mock import Mock, patch

import pytest

from pithy_cli.llm import (
    PROVIDERS,
    AnthropicClient,
    ModelType,
    OpenAICompatClient,
    create_client,
    resolve_client,
)

SCHEMA = {"type": "object", "properties": {"a": {"type": "string"}}}


def _openai_response(content: str) -> Mock:
    response = Mock()
    response.choices = [Mock(message=Mock(content=content))]
    return response


# create_client


def test_create_client_anthropic():
    client = create_client("anthropic", "test-key")

    assert isinstance(client, AnthropicClient)
    assert client.model == PROVIDERS["anthropic"].regular


def test_create_client_fast_model():
    client = create_client("together", "test-key", ModelType.FAST)

    assert isinstance(client, OpenAICompatClient)
    assert client.model == "Qwen/Qwen3.5-9B"


def test_create_client_model_override():
    client = create_client("openai", "test-key", model="custom-model")

    assert client.model == "custom-model"


def test_create_client_model_override_drops_default_params():
    default = create_client("openai", "test-key")
    custom = create_client("openai", "test-key", model="custom-model")

    assert default.spec.params == {"reasoning_effort": "low"}
    assert custom.spec.params == {}


def test_create_client_invalid_provider():
    with pytest.raises(ValueError, match="Unsupported provider"):
        create_client("invalid", "test-key")


# Request shapes


@patch("anthropic.Anthropic")
def test_anthropic_complete_with_schema(mock_anthropic):
    mock_anthropic.return_value.messages.create.return_value = Mock(
        content=[Mock(type="text", text='{"a": "b"}')]
    )

    result = AnthropicClient("test-key", "claude-x").complete(
        "sys", "user", max_tokens=100, schema=SCHEMA
    )

    assert result == '{"a": "b"}'
    kwargs = mock_anthropic.return_value.messages.create.call_args.kwargs
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "user"}]
    assert kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": SCHEMA}
    }


@patch("anthropic.Anthropic")
def test_anthropic_complete_without_schema(mock_anthropic):
    mock_anthropic.return_value.messages.create.return_value = Mock(
        content=[Mock(type="text", text="hello")]
    )

    AnthropicClient("test-key", "claude-x").complete("sys", "user")

    kwargs = mock_anthropic.return_value.messages.create.call_args.kwargs
    assert "output_config" not in kwargs


@patch("openai.OpenAI")
def test_together_complete(mock_openai):
    mock_openai.return_value.chat.completions.create.return_value = _openai_response(
        "hello"
    )

    client = create_client("together", "test-key")
    result = client.complete("sys", "user", max_tokens=100)

    assert result == "hello"
    mock_openai.assert_called_once_with(
        api_key="test-key", base_url="https://api.together.ai/v1"
    )
    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "moonshotai/Kimi-K3"
    assert kwargs["max_tokens"] == 100
    assert kwargs["extra_body"] == {"reasoning": {"enabled": False}}
    assert kwargs["messages"][0] == {"role": "system", "content": "sys"}


@patch("openai.OpenAI")
def test_openai_complete_uses_reasoning_params_and_schema(mock_openai):
    mock_openai.return_value.chat.completions.create.return_value = _openai_response(
        "{}"
    )

    create_client("openai", "test-key").complete(
        "sys", "user", max_tokens=100, schema=SCHEMA
    )

    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["max_completion_tokens"] == 100
    assert "max_tokens" not in kwargs
    assert kwargs["reasoning_effort"] == "low"
    assert kwargs["response_format"]["json_schema"]["schema"] == SCHEMA


# resolve_client


def test_resolve_client_no_keys():
    with pytest.raises(ValueError, match="pithy keys set anthropic"):
        resolve_client()


def test_resolve_client_first_provider_with_key(monkeypatch):
    monkeypatch.setenv("TOGETHER_API_KEY", "tg-key")
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")

    client = resolve_client()

    assert isinstance(client, OpenAICompatClient)
    assert client.spec is PROVIDERS["openai"]  # openai precedes together


def test_resolve_client_forced_provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")
    monkeypatch.setenv("TOGETHER_API_KEY", "tg-key")
    monkeypatch.setenv("PITHY_PROVIDER", "together")
    monkeypatch.setenv("PITHY_MODEL", "some/model")

    client = resolve_client()

    assert client.spec.base_url == PROVIDERS["together"].base_url
    assert client.spec.params == {}  # default-model params dropped for an override
    assert client.model == "some/model"


def test_resolve_client_unknown_forced_provider(monkeypatch):
    monkeypatch.setenv("PITHY_PROVIDER", "nope")

    with pytest.raises(ValueError, match="Unknown PITHY_PROVIDER"):
        resolve_client()


def test_resolve_client_reads_keychain(memory_keyring):
    memory_keyring.set_password("pithy", "anthropic", "sk-ant")

    client = resolve_client(ModelType.FAST)

    assert isinstance(client, AnthropicClient)
    assert client.api_key == "sk-ant"
    assert client.model == PROVIDERS["anthropic"].fast
