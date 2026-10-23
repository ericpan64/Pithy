"""API key storage: environment variables first, then the OS keychain."""

import getpass
import os

import keyring

from .llm import PROVIDERS

SERVICE = "pithy"


def _check_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise ValueError(
            f"Unknown provider '{provider}'. Choose from: {', '.join(PROVIDERS)}"
        )


def get_key(provider: str) -> str | None:
    """Get a provider's API key from its env var, falling back to the keychain."""
    _check_provider(provider)
    return os.environ.get(PROVIDERS[provider].env_var) or keyring.get_password(
        SERVICE, provider
    )


def set_key(provider: str, value: str | None = None) -> None:
    """Store a provider's API key in the keychain."""
    _check_provider(provider)

    if keyring.get_password(SERVICE, provider) is not None:
        response = input(f"Key for '{provider}' exists. Replace? (y/N): ")
        if response.lower() != "y":
            print("Cancelled")
            return

    if value is None:
        value = getpass.getpass(f"API key for {provider}: ")
    if not value.strip():
        raise ValueError("Key cannot be empty")

    keyring.set_password(SERVICE, provider, value.strip())
    print(f"✓ Saved {provider} key to the OS keychain")


def remove_key(provider: str) -> None:
    """Remove a provider's API key from the keychain."""
    _check_provider(provider)

    if keyring.get_password(SERVICE, provider) is None:
        raise ValueError(f"No stored key for '{provider}'")

    response = input(f"Remove {provider} key? (y/N): ")
    if response.lower() != "y":
        print("Cancelled")
        return

    keyring.delete_password(SERVICE, provider)
    print(f"✓ Removed {provider} key")


def key_status() -> dict[str, str]:
    """Map each provider to where its key comes from: 'env', 'keychain', or ''."""
    status = {}
    for provider, spec in PROVIDERS.items():
        if os.environ.get(spec.env_var):
            status[provider] = "env"
        elif keyring.get_password(SERVICE, provider) is not None:
            status[provider] = "keychain"
        else:
            status[provider] = ""
    return status
