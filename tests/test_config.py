"""
Unit tests for pithy_cli.config module.

Run with: pytest tests/test_config.py -v
"""

import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pithy_cli import config
from pithy_cli.cli import app

runner = CliRunner()


# config_path


def test_config_path_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PITHY_CONFIG", str(tmp_path / "custom.toml"))

    assert config.config_path() == tmp_path / "custom.toml"


def test_config_path_xdg(tmp_path, monkeypatch):
    monkeypatch.delenv("PITHY_CONFIG")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert config.config_path() == tmp_path / "pithy" / "config.toml"


def test_config_path_default(tmp_path, monkeypatch):
    monkeypatch.delenv("PITHY_CONFIG")
    monkeypatch.setenv("HOME", str(tmp_path))

    assert config.config_path() == tmp_path / ".config" / "pithy" / "config.toml"


# load / set / unset


def test_load_missing_file_is_empty():
    assert config.load() == {}


def test_set_get_round_trip_writes_valid_toml():
    config.set_value("provider", "together")
    config.set_value("together.model", '  odd/"model"  ')
    config.set_value("together.fast-model", "small/model")

    assert config.get("provider") == "together"
    assert config.get("together.model") == 'odd/"model"'
    assert tomllib.loads(config.config_path().read_text()) == {
        "provider": "together",
        "together": {"model": 'odd/"model"', "fast-model": "small/model"},
    }


def test_set_creates_parent_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("PITHY_CONFIG", str(tmp_path / "a" / "b" / "config.toml"))

    config.set_value("provider", "openai")

    assert config.get("provider") == "openai"


@pytest.mark.parametrize("key", ["model", "together.temperature", "nope.model"])
def test_set_rejects_unknown_keys(key):
    with pytest.raises(ValueError, match="Unknown key"):
        config.set_value(key, "x")


def test_set_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unknown provider"):
        config.set_value("provider", "nope")


def test_set_rejects_blank_value():
    with pytest.raises(ValueError, match="empty"):
        config.set_value("together.model", "   ")


def test_unset_removes_empty_tables():
    config.set_value("provider", "together")
    config.set_value("together.model", "big/model")

    config.unset("together.model")

    assert config.load() == {"provider": "together"}


def test_unset_missing_key_is_noop():
    config.unset("openai.model")

    assert config.load() == {}


def test_load_invalid_toml():
    path = config.config_path()
    path.write_text("provider = [unclosed")

    with pytest.raises(ValueError, match="invalid TOML"):
        config.load()


# CLI


def test_cli_config_set_list_unset():
    result = runner.invoke(app, ["config", "set", "together.model", "big/model"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["config", "list"])
    assert result.exit_code == 0
    assert "big/model" in result.stdout
    assert "(config)" in result.stdout
    assert "(default)" in result.stdout

    result = runner.invoke(app, ["config", "unset", "together.model"])
    assert result.exit_code == 0
    assert "big/model" not in runner.invoke(app, ["config", "list"]).stdout


def test_cli_config_list_shows_env_overrides(monkeypatch):
    config.set_value("provider", "openai")
    monkeypatch.setenv("PITHY_PROVIDER", "together")
    monkeypatch.setenv("PITHY_MODEL", "env/model")

    result = runner.invoke(app, ["config", "list"])

    assert "together" in result.stdout
    assert "(env)" in result.stdout
    assert "env/model" in result.stdout


def test_cli_config_set_bad_key():
    result = runner.invoke(app, ["config", "set", "bogus", "x"])

    assert result.exit_code == 1
    assert "Unknown key" in result.output


def test_config_file_isolated_from_home():
    # The autouse fixture points PITHY_CONFIG at a temp file
    assert Path.home() not in config.config_path().parents
