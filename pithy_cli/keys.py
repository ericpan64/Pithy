#!/usr/bin/env python3
"""
pithy_cli.keys - Minimal secure key management

Key management functionality for storing and retrieving API keys
with Argon2id + ChaCha20-Poly1305 encryption.
"""

import os
import sys
import json
import time
import getpass
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Optional
from enum import Enum

from argon2.low_level import hash_secret_raw, Type
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

PITHY_DIR = Path.home() / ".pithy"
KEYSTORE_PATH = PITHY_DIR / "keys"
CACHE_PATH = PITHY_DIR / ".cache"
DEFAULT_TTL = 8 * 60 * 60  # 8 hours

ARGON2_MEMORY = 32768
ARGON2_ITERATIONS = 3
ARGON2_PARALLELISM = 1
ARGON2_KEY_LENGTH = 32


# Provider Configuration

class Provider(str, Enum):
    """Supported API providers."""
    ANTHROPIC = "Anthropic"
    OPENAI = "OpenAI"


# Provider key mapping - single source of truth
PROVIDER_KEYS = {
    Provider.ANTHROPIC: "Anthropic",
    Provider.OPENAI: "OpenAI",
}

# Backward compatibility mapping
LEGACY_KEY_NAMES = {
    "ANTHROPIC_API_KEY": Provider.ANTHROPIC,
    "OPENAI_API_KEY": Provider.OPENAI,
}


@dataclass
class KeyStore:
    keys: Dict[str, str] = field(default_factory=dict)


@dataclass
class EncryptedKeyStore:
    version: int = 2
    salt: str = ""
    nonce: str = ""
    ciphertext: str = ""


@dataclass
class CachedPassword:
    password: str = ""
    expires_at: int = 0


def ensure_pithy_dir():
    """Create .pithy directory with secure permissions."""
    PITHY_DIR.mkdir(exist_ok=True)
    if os.name != 'nt':
        os.chmod(PITHY_DIR, 0o700)


def encrypt_keystore(keystore: KeyStore, password: str) -> EncryptedKeyStore:
    """Encrypt keystore with Argon2id + ChaCha20-Poly1305."""
    salt = os.urandom(16)

    key = hash_secret_raw(
        secret=password.encode('utf-8'),
        salt=salt,
        time_cost=ARGON2_ITERATIONS,
        memory_cost=ARGON2_MEMORY,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_KEY_LENGTH,
        type=Type.ID
    )

    plaintext = json.dumps(keystore.keys).encode('utf-8')

    cipher = ChaCha20Poly1305(key)
    nonce = os.urandom(12)
    ciphertext = cipher.encrypt(nonce, plaintext, None)

    return EncryptedKeyStore(
        version=2,
        salt=salt.hex(),
        nonce=nonce.hex(),
        ciphertext=ciphertext.hex()
    )


def decrypt_keystore(encrypted: EncryptedKeyStore, password: str) -> KeyStore:
    """Decrypt keystore."""
    salt = bytes.fromhex(encrypted.salt)

    key = hash_secret_raw(
        secret=password.encode('utf-8'),
        salt=salt,
        time_cost=ARGON2_ITERATIONS,
        memory_cost=ARGON2_MEMORY,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_KEY_LENGTH,
        type=Type.ID
    )

    cipher = ChaCha20Poly1305(key)
    nonce = bytes.fromhex(encrypted.nonce)
    ciphertext = bytes.fromhex(encrypted.ciphertext)

    try:
        plaintext = cipher.decrypt(nonce, ciphertext, None)
    except Exception:
        raise ValueError("Invalid password or corrupted keystore")

    keys_dict = json.loads(plaintext.decode('utf-8'))
    return KeyStore(keys=keys_dict)


def read_cached_password() -> Optional[str]:
    """Read cached password if valid."""
    if not CACHE_PATH.exists():
        return None

    try:
        data = json.loads(CACHE_PATH.read_text())
        now = int(time.time())

        if now < data['expires_at']:
            return data['password']
        else:
            CACHE_PATH.unlink(missing_ok=True)
            return None
    except:
        CACHE_PATH.unlink(missing_ok=True)
        return None


def write_cached_password(password: str, ttl_seconds: int = DEFAULT_TTL):
    """Cache password with TTL."""
    ensure_pithy_dir()

    data = {
        'password': password,
        'expires_at': int(time.time()) + ttl_seconds
    }

    CACHE_PATH.write_text(json.dumps(data))

    if os.name != 'nt':
        os.chmod(CACHE_PATH, 0o600)


def clear_cached_password():
    """Clear password cache."""
    CACHE_PATH.unlink(missing_ok=True)


def load_keystore() -> KeyStore:
    """Load and decrypt keystore."""
    if not KEYSTORE_PATH.exists():
        return KeyStore()

    password = read_cached_password()

    if password:
        try:
            content = json.loads(KEYSTORE_PATH.read_text())
            encrypted = EncryptedKeyStore(**content)
            return decrypt_keystore(encrypted, password)
        except:
            clear_cached_password()

    password = getpass.getpass("Master password: ")
    if not password.strip():
        raise ValueError("Password cannot be empty")

    content = json.loads(KEYSTORE_PATH.read_text())
    encrypted = EncryptedKeyStore(**content)
    keystore = decrypt_keystore(encrypted, password)

    write_cached_password(password)
    print("= Unlocked (cached for 8h)", file=sys.stderr)

    return keystore


def save_keystore(keystore: KeyStore):
    """Encrypt and save keystore."""
    ensure_pithy_dir()

    password = read_cached_password()

    if not password:
        password = getpass.getpass("Master password: ")
        if not password.strip():
            raise ValueError("Password cannot be empty")
        write_cached_password(password)

    encrypted = encrypt_keystore(keystore, password)

    content = {
        'version': encrypted.version,
        'salt': encrypted.salt,
        'nonce': encrypted.nonce,
        'ciphertext': encrypted.ciphertext
    }

    KEYSTORE_PATH.write_text(json.dumps(content, indent=2))

    if os.name != 'nt':
        os.chmod(KEYSTORE_PATH, 0o600)


def set_key(name: str, value: Optional[str] = None):
    """Set a key."""
    keystore = load_keystore()

    if name in keystore.keys:
        response = input(f"Key '{name}' exists. Replace? (y/N): ")
        if response.lower() != 'y':
            print("Cancelled")
            return

    if value is None:
        value = getpass.getpass(f"Enter value for '{name}': ")

    if not value.strip():
        raise ValueError("Value cannot be empty")

    keystore.keys[name] = value
    save_keystore(keystore)

    print(f" Key '{name}' saved")


def get_key(name: str) -> Optional[str]:
    """Get a key."""
    try:
        keystore = load_keystore()
        return keystore.keys.get(name)
    except FileNotFoundError:
        return None


def list_keys():
    """List all keys."""
    try:
        keystore = load_keystore()
    except FileNotFoundError:
        print("No keys stored")
        return

    if not keystore.keys:
        print("No keys stored")
        return

    print("= Stored Keys:")
    for name in sorted(keystore.keys.keys()):
        print(f"  • {name}")


def remove_key(name: str):
    """Remove a key."""
    keystore = load_keystore()

    if name not in keystore.keys:
        raise ValueError(f"Key '{name}' not found")

    response = input(f"Remove '{name}'? (y/N): ")
    if response.lower() != 'y':
        print("Cancelled")
        return

    del keystore.keys[name]
    save_keystore(keystore)

    print(f" Key '{name}' removed")


def unlock(ttl_hours: float = 8.0):
    """Unlock keystore."""
    password = getpass.getpass("Master password: ")
    if not password.strip():
        raise ValueError("Password cannot be empty")

    if KEYSTORE_PATH.exists():
        content = json.loads(KEYSTORE_PATH.read_text())
        encrypted = EncryptedKeyStore(**content)
        decrypt_keystore(encrypted, password)

    ttl_seconds = int(ttl_hours * 3600)
    write_cached_password(password, ttl_seconds)

    print(f"= Unlocked for {ttl_hours}h")


def lock():
    """Lock keystore."""
    clear_cached_password()
    print("= Locked")


# Provider-specific key management

def get_provider_key(provider: Provider) -> Optional[str]:
    """
    Get API key for a specific provider.

    Checks both new standardized names and legacy names for backward compatibility.

    Args:
        provider: The provider to get the key for

    Returns:
        The API key if found, None otherwise
    """
    try:
        keystore = load_keystore()
    except FileNotFoundError:
        return None

    # Try new naming convention first
    key_name = PROVIDER_KEYS.get(provider)
    if key_name and key_name in keystore.keys:
        return keystore.keys[key_name]

    # Fallback to legacy names for backward compatibility
    legacy_name = f"{provider.name}_API_KEY"
    return keystore.keys.get(legacy_name)


def set_provider_key(provider: Provider, value: Optional[str] = None):
    """
    Set API key for a specific provider using standard naming.

    Args:
        provider: The provider to set the key for
        value: The API key value (will prompt if None)
    """
    key_name = PROVIDER_KEYS[provider]
    set_key(key_name, value)


def list_providers() -> Dict[Provider, bool]:
    """
    List all providers and their key availability.

    Returns:
        Dict mapping Provider to whether a key exists (new or legacy)
    """
    try:
        keystore = load_keystore()
    except FileNotFoundError:
        return {provider: False for provider in Provider}

    return {
        provider: (
            PROVIDER_KEYS[provider] in keystore.keys or
            f"{provider.name}_API_KEY" in keystore.keys
        )
        for provider in Provider
    }


def migrate_legacy_keys():
    """
    Migrate legacy key names to new standard format.

    Renames keys like:
    - ANTHROPIC_API_KEY → Anthropic
    - OPENAI_API_KEY → OpenAI

    This is a one-time migration helper.
    """
    try:
        keystore = load_keystore()
    except FileNotFoundError:
        print("No keystore found - nothing to migrate")
        return

    changed = False

    for legacy_name, provider in LEGACY_KEY_NAMES.items():
        if legacy_name in keystore.keys:
            new_name = PROVIDER_KEYS[provider]
            if new_name not in keystore.keys:
                # Migrate the key
                keystore.keys[new_name] = keystore.keys[legacy_name]
                del keystore.keys[legacy_name]
                changed = True
                print(f"✓ Migrated {legacy_name} → {new_name}")
            else:
                # New key already exists - ask user which to keep
                print(f"⚠ Both {legacy_name} and {new_name} exist")
                print(f"  Keeping {new_name}, removing {legacy_name}")
                del keystore.keys[legacy_name]
                changed = True

    if changed:
        save_keystore(keystore)
        print("Migration complete!")
    else:
        print("No legacy keys found to migrate")
