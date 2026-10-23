"""
Unit tests for pithy_cli.keys and pithy_cli._legacy_keystore.

Run with: pytest tests/test_keys.py -v
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from typer.testing import CliRunner

from pithy_cli._legacy_keystore import decrypt_keystore, import_legacy
from pithy_cli.cli import app
from pithy_cli.keys import get_key, key_status, remove_key, set_key

runner = CliRunner()


# get_key


def test_get_key_missing():
    assert get_key("anthropic") is None


def test_get_key_from_keychain(memory_keyring):
    memory_keyring.set_password("pithy", "openai", "sk-1")

    assert get_key("openai") == "sk-1"


def test_get_key_env_takes_precedence(memory_keyring, monkeypatch):
    memory_keyring.set_password("pithy", "openai", "sk-keychain")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    assert get_key("openai") == "sk-env"


def test_get_key_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        get_key("nope")


# set_key / remove_key


def test_set_key_with_value(memory_keyring):
    set_key("together", "  tg-key  ")

    assert memory_keyring.get_password("pithy", "together") == "tg-key"


@patch("getpass.getpass", return_value="prompted-key")
def test_set_key_prompts_when_no_value(_getpass, memory_keyring):
    set_key("anthropic")

    assert memory_keyring.get_password("pithy", "anthropic") == "prompted-key"


@patch("builtins.input", return_value="n")
def test_set_key_existing_cancelled(_input, memory_keyring):
    memory_keyring.set_password("pithy", "anthropic", "old")

    set_key("anthropic", "new")

    assert memory_keyring.get_password("pithy", "anthropic") == "old"


def test_set_key_empty_rejected():
    with pytest.raises(ValueError, match="cannot be empty"):
        set_key("anthropic", "   ")


@patch("builtins.input", return_value="y")
def test_remove_key(_input, memory_keyring):
    memory_keyring.set_password("pithy", "openai", "sk")

    remove_key("openai")

    assert memory_keyring.get_password("pithy", "openai") is None


def test_remove_key_missing():
    with pytest.raises(ValueError, match="No stored key"):
        remove_key("openai")


# key_status


def test_key_status(memory_keyring, monkeypatch):
    memory_keyring.set_password("pithy", "anthropic", "sk")
    monkeypatch.setenv("TOGETHER_API_KEY", "tg")

    assert key_status() == {"anthropic": "keychain", "openai": "", "together": "env"}


def test_cli_keys_list(memory_keyring):
    memory_keyring.set_password("pithy", "openai", "sk")

    result = runner.invoke(app, ["keys", "list"])

    assert result.exit_code == 0
    assert "openai" in result.stdout
    assert "keychain" in result.stdout


def test_cli_keys_set_unknown_provider():
    result = runner.invoke(app, ["keys", "set", "nope", "--value", "x"])

    assert result.exit_code == 1
    assert "Unknown provider" in result.output


# Legacy import


def _write_legacy_keystore(
    directory: Path, keys: dict[str, str], password: str
) -> None:
    salt, nonce = os.urandom(16), os.urandom(12)
    key = hash_secret_raw(
        secret=password.encode(),
        salt=salt,
        time_cost=3,
        memory_cost=32768,
        parallelism=1,
        hash_len=32,
        type=Type.ID,
    )
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, json.dumps(keys).encode(), None)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "keys").write_text(
        json.dumps(
            {
                "version": 2,
                "salt": salt.hex(),
                "nonce": nonce.hex(),
                "ciphertext": ciphertext.hex(),
            }
        )
    )
    (directory / ".cache").write_text("{}")


def test_decrypt_keystore_wrong_password(tmp_path):
    _write_legacy_keystore(tmp_path, {"Anthropic": "sk"}, "right")
    content = json.loads((tmp_path / "keys").read_text())

    with pytest.raises(ValueError, match="Invalid password"):
        decrypt_keystore(content, "wrong")


@patch("builtins.input", return_value="y")
@patch("getpass.getpass", return_value="master")
def test_import_legacy(_getpass, _input, tmp_path, memory_keyring, capsys):
    _write_legacy_keystore(
        tmp_path,
        {"Anthropic": "sk-ant", "OPENAI_API_KEY": "sk-oa", "github": "ghp"},
        "master",
    )

    import_legacy(tmp_path)

    assert memory_keyring.get_password("pithy", "anthropic") == "sk-ant"
    assert memory_keyring.get_password("pithy", "openai") == "sk-oa"
    assert "Skipped 'github'" in capsys.readouterr().out
    assert not (tmp_path / "keys").exists()
    assert not (tmp_path / ".cache").exists()


def test_import_legacy_no_keystore(tmp_path, capsys):
    import_legacy(tmp_path)

    assert "No legacy keystore" in capsys.readouterr().out
