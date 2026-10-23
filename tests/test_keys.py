"""
Unit tests for pithy_cli.keys module.

Run with: pytest tests/test_keys.py -v
"""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

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
