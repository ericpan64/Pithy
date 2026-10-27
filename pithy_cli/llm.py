"""LLM provider table and clients."""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class ModelType(str, Enum):
    """Model speed/capability trade-off."""

    REGULAR = "regular"  # Higher capability, slower/more expensive
    FAST = "fast"  # Lower capability, faster/cheaper


@dataclass(frozen=True)
class ProviderSpec:
    """How to reach a provider and which models to use."""

    env_var: str
    regular: str
    fast: str
    base_url: str | None = None  # None → Anthropic SDK, else OpenAI-compatible
    token_param: str = "max_tokens"
    params: dict[str, Any] = field(default_factory=dict)  # sent with every model
    default_params: dict[str, Any] = field(default_factory=dict)  # built-in models only


# Order matters: the first provider with a key is used unless PITHY_PROVIDER is set
PROVIDERS: dict[str, ProviderSpec] = {
    "anthropic": ProviderSpec(
        env_var="ANTHROPIC_API_KEY",
        regular="claude-sonnet-5-5",
        fast="claude-haiku-5-5",
    ),
    "openai": ProviderSpec(
        env_var="OPENAI_API_KEY",
        regular="gpt-6.1-sol",
        fast="gpt-6-luna",
        base_url="https://api.openai.com/v1",
        # Reasoning models: reject max_tokens, and reasoning tokens count toward the cap
        token_param="max_completion_tokens",
        default_params={"reasoning_effort": "low"},
    ),
    "together": ProviderSpec(
        env_var="TOGETHER_API_KEY",
        regular="moonshotai/Kimi-K3",
        fast="Qwen/Qwen3.5-9B",
        base_url="https://api.together.ai/v1",
        # Many Together models are hybrid reasoners with thinking on by default
        params={"extra_body": {"reasoning": {"enabled": False}}},
    ),
}


class LLMClient(Protocol):
    """Protocol for LLM clients."""

    def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 4096,
        schema: dict[str, Any] | None = None,
    ) -> str:
        """Generate a completion; returns JSON text when a schema is given."""
        ...


@dataclass
class AnthropicClient:
    """Anthropic Claude client."""

    api_key: str
    model: str

    def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 4096,
        schema: dict[str, Any] | None = None,
    ) -> str:
        from anthropic import Anthropic

        kwargs: dict[str, Any] = {}
        if schema is not None:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": schema}
            }

        response = Anthropic(api_key=self.api_key).messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            **kwargs,
        )
        text = next(
            (str(block.text) for block in response.content if block.type == "text"),
            None,
        )
        if text is None:
            raise ValueError(
                f"Response contained no text (stop reason: {response.stop_reason})"
            )
        return text


@dataclass
class OpenAICompatClient:
    """Client for OpenAI and OpenAI-compatible APIs (e.g. Together)."""

    api_key: str
    model: str
    spec: ProviderSpec
    params: dict[str, Any] = field(default_factory=dict)

    def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 4096,
        schema: dict[str, Any] | None = None,
    ) -> str:
        from openai import OpenAI

        kwargs: dict[str, Any] = {self.spec.token_param: max_tokens, **self.params}
        if schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": schema, "strict": True},
            }

        client = OpenAI(api_key=self.api_key, base_url=self.spec.base_url)
        response = client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            **kwargs,
        )
        return response.choices[0].message.content or ""


def create_client(
    provider: str,
    api_key: str,
    model_type: ModelType = ModelType.REGULAR,
    model: str | None = None,
) -> LLMClient:
    """Create a client for a provider in PROVIDERS."""
    spec = PROVIDERS.get(provider)
    if spec is None:
        raise ValueError(f"Unsupported provider: {provider}")

    model = model or (spec.fast if model_type == ModelType.FAST else spec.regular)
    if spec.base_url is None:
        return AnthropicClient(api_key=api_key, model=model)

    # Options like reasoning_effort may not apply to a custom model
    params = dict(spec.params)
    if model in (spec.regular, spec.fast):
        params.update(spec.default_params)
    return OpenAICompatClient(api_key=api_key, model=model, spec=spec, params=params)


def resolve_client(model_type: ModelType = ModelType.REGULAR) -> LLMClient:
    """
    Pick a provider and build its client.

    Env vars beat the config file (`pithy config`), which beats the defaults:
    provider is PITHY_PROVIDER, then config `provider`, then the first provider
    in PROVIDERS with a key; model is PITHY_MODEL, then config
    `<provider>.model` (or `.fast-model` for FAST), then the provider default.
    """
    from .config import config_path, load
    from .keys import get_key

    settings = load()
    source = ""
    if forced := os.environ.get("PITHY_PROVIDER"):
        source = "PITHY_PROVIDER"
    elif forced := settings.get("provider"):
        source = f"provider in {config_path()}"
    names = [forced] if forced else list(PROVIDERS)

    for name in names:
        if name not in PROVIDERS:
            raise ValueError(
                f"Unknown {source} '{name}'. Choose from: {', '.join(PROVIDERS)}"
            )
        if key := get_key(name):
            model_key = "fast-model" if model_type == ModelType.FAST else "model"
            model = os.environ.get("PITHY_MODEL") or settings.get(name, {}).get(
                model_key
            )
            return create_client(name, key, model_type, model)

    raise ValueError(
        "No API key found"
        + (f" for {forced} (set by {source})" if forced else "")
        + ". Set one with:\n"
        + "\n".join(f"  pithy keys set {name}" for name in names)
    )
