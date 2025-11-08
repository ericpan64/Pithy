"""Configuration and shared utilities for Pithy CLI."""

import os
from typing import Tuple

from .llm import LLMProvider
from .keys import get_provider_key, Provider


def get_provider_config() -> Tuple[LLMProvider, str]:
    """
    Get LLM provider and API key from keystore or environment.

    Returns:
        Tuple of (provider, api_key)

    Raises:
        ValueError: If no API key is found in keystore or environment
    """
    # Map Provider enum to LLMProvider enum
    provider_map = {
        Provider.ANTHROPIC: LLMProvider.ANTHROPIC,
        Provider.OPENAI: LLMProvider.OPENAI,
    }

    # Try each provider in order
    for provider, llm_provider in provider_map.items():
        if key := get_provider_key(provider):
            return llm_provider, key

    # Check environment as fallback
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return LLMProvider.ANTHROPIC, key
    if key := os.environ.get("OPENAI_API_KEY"):
        return LLMProvider.OPENAI, key

    from .keys import PROVIDER_KEYS
    raise ValueError(
        "No API key found. Set one with:\n"
        f"  pithy keys set {PROVIDER_KEYS[Provider.ANTHROPIC]}\n"
        "  or\n"
        f"  pithy keys set {PROVIDER_KEYS[Provider.OPENAI]}"
    )
