"""Shared fixtures: isolate every test from the real keychain and API key env vars."""

import subprocess
from pathlib import Path

import keyring
import pytest
from keyring.backend import KeyringBackend

from pithy_cli.llm import PROVIDERS


class MemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self.store[(service, username)]


@pytest.fixture(autouse=True)
def memory_keyring(monkeypatch, tmp_path) -> MemoryKeyring:
    # Never read or write the user's real config file
    monkeypatch.setenv("PITHY_CONFIG", str(tmp_path / "pithy-config.toml"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    for spec in PROVIDERS.values():
        monkeypatch.delenv(spec.env_var, raising=False)
    monkeypatch.delenv("PITHY_PROVIDER", raising=False)
    monkeypatch.delenv("PITHY_MODEL", raising=False)

    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def git_repo(tmp_path: Path, monkeypatch) -> Path:
    """A real git repository with one commit, as the working directory."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Ignore the user's global/system git config (e.g. core.hooksPath)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)

    git("init", "-q", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (repo / "README.md").write_text("# test\n")
    git("add", ".")
    git("commit", "-q", "-m", "chore: initial commit")

    monkeypatch.chdir(repo)
    return repo
