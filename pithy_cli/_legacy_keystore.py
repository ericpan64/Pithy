"""
One-time import from the pre-keychain encrypted keystore (~/.pithy/keys).

Remove this module, `pithy keys import-legacy`, and the argon2-cffi and
cryptography dependencies in the next minor release.
"""

import getpass
import json
from pathlib import Path

import keyring
from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

from .keys import SERVICE

LEGACY_DIR = Path.home() / ".pithy"

# Old key names → provider
LEGACY_NAMES = {
    "Anthropic": "anthropic",
    "ANTHROPIC_API_KEY": "anthropic",
    "OpenAI": "openai",
    "OPENAI_API_KEY": "openai",
    "Together": "together",
    "TOGETHER_API_KEY": "together",
}


def decrypt_keystore(content: dict[str, str], password: str) -> dict[str, str]:
    """Decrypt a v2 keystore (Argon2id + ChaCha20-Poly1305)."""
    key = hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=bytes.fromhex(content["salt"]),
        time_cost=3,
        memory_cost=32768,
        parallelism=1,
        hash_len=32,
        type=Type.ID,
    )
    try:
        plaintext = ChaCha20Poly1305(key).decrypt(
            bytes.fromhex(content["nonce"]), bytes.fromhex(content["ciphertext"]), None
        )
    except Exception as e:
        raise ValueError("Invalid password or corrupted keystore") from e
    keys: dict[str, str] = json.loads(plaintext.decode("utf-8"))
    return keys


def import_legacy(legacy_dir: Path = LEGACY_DIR) -> None:
    """Copy provider keys from the old keystore into the OS keychain."""
    keystore_path = legacy_dir / "keys"
    if not keystore_path.exists():
        print(f"No legacy keystore found at {keystore_path}")
        return

    keys = decrypt_keystore(
        json.loads(keystore_path.read_text()), getpass.getpass("Master password: ")
    )

    for name, value in keys.items():
        provider = LEGACY_NAMES.get(name)
        if provider is None:
            print(f"  Skipped '{name}' (not a provider key)")
            continue
        keyring.set_password(SERVICE, provider, value)
        print(f"✓ Imported {name} → {provider}")

    response = input("Delete the old keystore and password cache? (y/N): ")
    if response.lower() == "y":
        keystore_path.unlink()
        (legacy_dir / ".cache").unlink(missing_ok=True)
        print("✓ Deleted old keystore")
