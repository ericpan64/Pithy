"""
Unit tests for pithy_cli.summarize module.

Run with: pytest tests/test_summarize.py -v
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from pithy_cli.cli import app
from pithy_cli.summarize import _is_text_file, build_context, list_files

runner = CliRunner()


@pytest.fixture
def project(git_repo: Path) -> Path:
    (git_repo / "src").mkdir()
    (git_repo / "src" / "app.py").write_text("print('hi')\n")
    (git_repo / "src" / "util.py").write_text("def f():\n    return 1\n")
    (git_repo / "logo.bin").write_bytes(b"\x89PNG\x00\x00binary")
    (git_repo / "uv.lock").write_text("lock")
    (git_repo / "secret.env").write_text("TOKEN=x")
    (git_repo / "build").mkdir()
    (git_repo / "build" / "out.py").write_text("generated\n")
    (git_repo / ".gitignore").write_text("secret.env\nbuild/\n")
    subprocess.run(["git", "add", "src", ".gitignore"], cwd=git_repo, check=True)
    return git_repo


def _rel(root: Path, files: list[Path]) -> set[str]:
    return {f.relative_to(root).as_posix() for f in files}


# list_files


def test_list_files_respects_gitignore_and_excludes(project):
    root, files = list_files(project, [])

    rel = _rel(root, files)
    assert {"README.md", "src/app.py", "src/util.py", "logo.bin"} <= rel
    assert "secret.env" not in rel  # gitignored
    assert not any(p.startswith("build") for p in rel)  # ignored directory
    assert "uv.lock" not in rel  # default exclude


def test_list_files_subdirectory_and_custom_exclude(project):
    root, files = list_files(project / "src", ["util.py"])

    assert _rel(root, files) == {"src/app.py"}


def test_list_files_directory_exclude(project):
    root, files = list_files(project, ["src/"])

    assert not any(p.startswith("src/") for p in _rel(root, files))


def test_list_files_filename_with_newline(project):
    (project / "odd\nname.py").write_text("x = 1\n")

    root, files = list_files(project, [])

    assert "odd\nname.py" in _rel(root, files)


def test_list_files_outside_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="Not in a git repository"):
        list_files(tmp_path, [])


# build_context


def test_build_context_skips_binary(project):
    root, files = list_files(project, [])

    context = build_context(root, files, max_chars=100_000)

    assert "- logo.bin" in context  # listed
    assert "--- logo.bin ---" not in context  # contents skipped
    assert "--- src/app.py ---\nprint('hi')" in context


def test_build_context_budget_notes_omitted(project):
    root, files = list_files(project, [])

    context = build_context(root, files, max_chars=150)

    assert "Contents omitted (over size budget)" in context


def test_build_context_reads_only_budget(project):
    (project / "big.txt").write_text("y" * 10_000)
    root, files = list_files(project, [])
    real_open = Path.open
    reads = []

    def tracking_open(self, *args, **kwargs):
        f = real_open(self, *args, **kwargs)
        if self.name == "big.txt" and "b" not in (args[0] if args else "r"):
            original = f.read
            f.read = lambda n=-1: reads.append(n) or original(n)
        return f

    with patch.object(Path, "open", tracking_open):
        context = build_context(root, files, max_chars=500)

    assert "--- big.txt ---" not in context
    assert reads and all(0 <= n <= 500 for n in reads)


def test_is_text_file_tolerates_cut_multibyte_char(tmp_path):
    path = tmp_path / "notes.dat"
    path.write_bytes(b"a" * 4095 + "é".encode())  # é split at the 4096 boundary

    assert _is_text_file(path)


# CLI


def test_cli_summarize_writes_output(project):
    client = Mock()
    client.complete.return_value = "## Purpose\nA test repo.\n"

    with patch("pithy_cli.summarize.resolve_client", return_value=client):
        result = runner.invoke(app, ["summarize", "src", "-o", "AGENTS.md"])

    assert result.exit_code == 0, result.output
    assert (project / "AGENTS.md").read_text() == "## Purpose\nA test repo.\n"
    system, user = client.complete.call_args.args
    assert "codebase overview" in system
    assert user.startswith("Path: src")


def test_cli_summarize_stdout(project):
    client = Mock()
    client.complete.return_value = "overview text"

    with patch("pithy_cli.summarize.resolve_client", return_value=client):
        result = runner.invoke(app, ["summarize"])

    assert result.exit_code == 0
    assert "overview text" in result.stdout


def test_cli_summarize_missing_path(project):
    result = runner.invoke(app, ["summarize", "nope"])

    assert result.exit_code == 1
    assert "Path not found" in result.output
