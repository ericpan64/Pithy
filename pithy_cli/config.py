"""Saved settings: provider and per-provider models in a small TOML file."""

import json
import os
import tomllib
from pathlib import Path
from typing import Any

from .llm import PROVIDERS

MODEL_KEYS = ("model", "fast-model")


def config_path() -> Path:
    """$PITHY_CONFIG, else $XDG_CONFIG_HOME/pithy/config.toml, else ~/.config."""
    if path := os.environ.get("PITHY_CONFIG"):
        return Path(path)
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "pithy" / "config.toml"


def valid_keys() -> list[str]:
    return ["provider"] + [f"{p}.{k}" for p in PROVIDERS for k in MODEL_KEYS]


def _split(key: str) -> tuple[str, str | None]:
    """Split 'together.model' into ('together', 'model'); validate the key."""
    if key not in valid_keys():
        raise ValueError(f"Unknown key '{key}'. Valid keys: {', '.join(valid_keys())}")
    table, _, name = key.partition(".")
    return table, name or None


def load() -> dict[str, Any]:
    """Read the config file; a missing file is an empty config."""
    path = config_path()
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        raise ValueError(f"{path}: invalid TOML: {e}") from e


def get(key: str) -> str | None:
    table, name = _split(key)
    data = load()
    value = data.get(table) if name is None else data.get(table, {}).get(name)
    return None if value is None else str(value)


def set_value(key: str, value: str) -> None:
    table, name = _split(key)
    value = value.strip()
    if not value:
        raise ValueError("Value cannot be empty")
    if name is None and value not in PROVIDERS:
        raise ValueError(
            f"Unknown provider '{value}'. Choose from: {', '.join(PROVIDERS)}"
        )

    data = load()
    if name is None:
        data[table] = value
    else:
        data.setdefault(table, {})[name] = value
    _write(data)


def unset(key: str) -> None:
    table, name = _split(key)
    data = load()
    if name is None:
        data.pop(table, None)
    else:
        section = data.get(table, {})
        section.pop(name, None)
        if not section:
            data.pop(table, None)
    _write(data)


def _dump(data: dict[str, Any]) -> str:
    """Write top-level strings, then one table per provider (JSON strings are TOML)."""
    lines = [f"{k} = {json.dumps(v)}" for k, v in data.items() if isinstance(v, str)]
    for table, values in data.items():
        if isinstance(values, dict) and values:
            lines += ["", f"[{table}]"]
            lines += [f"{k} = {json.dumps(v)}" for k, v in values.items()]
    return "\n".join(lines).lstrip("\n") + "\n"


def _write(data: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump(data), encoding="utf-8")
