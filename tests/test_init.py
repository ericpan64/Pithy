"""
Unit tests for pithy_cli.init module.

Run with: pytest tests/test_init.py -v
"""

import pytest
from pathlib import Path
from typer.testing import CliRunner
from pithy_cli.init import (
    find_git_root,
    ensure_pithy_directory,
    read_gitignore,
    update_gitignore,
    run_init
)
from pithy_cli.cli import app

runner = CliRunner()


# Fixtures

@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository."""
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    return repo_root


@pytest.fixture
def nested_git_repo(temp_git_repo: Path) -> Path:
    """Create a nested directory structure within a git repo."""
    nested = temp_git_repo / "src" / "components" / "deep"
    nested.mkdir(parents=True)
    return nested


@pytest.fixture
def git_repo_with_gitignore(temp_git_repo: Path) -> Path:
    """Create a git repo with an existing .gitignore."""
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text("node_modules/\n*.log\n")
    return temp_git_repo


# Tests for find_git_root

def test_find_git_root_in_root_directory(temp_git_repo: Path):
    """Should find .git when called from repository root."""
    result = find_git_root(temp_git_repo)
    assert result == temp_git_repo


def test_find_git_root_from_nested_directory(nested_git_repo: Path, temp_git_repo: Path):
    """Should traverse up to find .git from nested directories."""
    result = find_git_root(nested_git_repo)
    assert result == temp_git_repo


def test_find_git_root_returns_none_when_not_in_repo(tmp_path: Path):
    """Should return None when not in a git repository."""
    non_git_dir = tmp_path / "not_a_repo"
    non_git_dir.mkdir()
    result = find_git_root(non_git_dir)
    assert result is None


def test_find_git_root_stops_at_filesystem_root(tmp_path: Path):
    """Should not traverse beyond filesystem root."""
    result = find_git_root(Path("/tmp/unlikely_to_have_git_here_12345"))
    # Should either find a git root or return None, not crash
    assert result is None or isinstance(result, Path)


# Tests for ensure_pithy_directory

def test_ensure_pithy_directory_creates_new_directory(temp_git_repo: Path):
    """Should create .pithy directory if it doesn't exist."""
    pithy_dir = ensure_pithy_directory(temp_git_repo)

    assert pithy_dir.exists()
    assert pithy_dir.is_dir()
    assert pithy_dir.name == ".pithy"
    assert pithy_dir.parent == temp_git_repo


def test_ensure_pithy_directory_is_idempotent(temp_git_repo: Path):
    """Should not fail when .pithy directory already exists."""
    # Create it twice
    first_call = ensure_pithy_directory(temp_git_repo)
    second_call = ensure_pithy_directory(temp_git_repo)

    assert first_call == second_call
    assert first_call.exists()


# Tests for read_gitignore

def test_read_gitignore_returns_empty_list_when_file_missing(temp_git_repo: Path):
    """Should return empty list when .gitignore doesn't exist."""
    result = read_gitignore(temp_git_repo)
    assert result == []


def test_read_gitignore_returns_existing_entries(git_repo_with_gitignore: Path):
    """Should read and return existing .gitignore entries."""
    result = read_gitignore(git_repo_with_gitignore)

    assert len(result) == 2
    assert "node_modules/" in result
    assert "*.log" in result


def test_read_gitignore_preserves_empty_lines(temp_git_repo: Path):
    """Should preserve empty lines and whitespace structure."""
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text("# Comment\n\nnode_modules/\n\n*.log\n")

    result = read_gitignore(temp_git_repo)

    assert "" in result  # Empty lines preserved


# Tests for update_gitignore

def test_update_gitignore_creates_file_if_missing(temp_git_repo: Path):
    """Should create .gitignore if it doesn't exist."""
    entries = [".pithy/", ".cursor*"]
    added, modified = update_gitignore(temp_git_repo, entries)

    assert modified is True
    assert set(added) == set(entries)

    gitignore_path = temp_git_repo / ".gitignore"
    assert gitignore_path.exists()

    content = gitignore_path.read_text()
    assert ".pithy/" in content
    assert ".cursor*" in content


def test_update_gitignore_adds_new_entries(git_repo_with_gitignore: Path):
    """Should append new entries to existing .gitignore."""
    entries = [".pithy/", ".specstory/", ".cursor*"]
    added, modified = update_gitignore(git_repo_with_gitignore, entries)

    assert modified is True
    assert set(added) == set(entries)

    gitignore = git_repo_with_gitignore / ".gitignore"
    content = gitignore.read_text()

    # Original entries preserved
    assert "node_modules/" in content
    assert "*.log" in content

    # New entries added
    assert ".pithy/" in content
    assert ".specstory/" in content
    assert ".cursor*" in content


def test_update_gitignore_avoids_duplicates(temp_git_repo: Path):
    """Should not add entries that already exist."""
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text(".pithy/\n.cursor*\n")

    entries = [".pithy/", ".specstory/", ".cursor*"]
    added, modified = update_gitignore(temp_git_repo, entries)

    assert modified is True
    assert added == [".specstory/"]  # Only new entry

    content = gitignore.read_text()
    # Check that .pithy/ and .cursor* appear only once
    assert content.count(".pithy/") == 1
    assert content.count(".cursor*") == 1


def test_update_gitignore_is_idempotent(temp_git_repo: Path):
    """Should return no modifications when all entries exist."""
    entries = [".pithy/", ".specstory/", ".cursor*"]

    # First call adds entries
    _, first_modified = update_gitignore(temp_git_repo, entries)
    assert first_modified is True

    # Second call should detect duplicates
    added, second_modified = update_gitignore(temp_git_repo, entries)
    assert second_modified is False
    assert added == []


def test_update_gitignore_handles_whitespace_variations(temp_git_repo: Path):
    """Should normalize entries and detect existing ones despite whitespace."""
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text("  .pithy/  \n.cursor*\n")

    entries = [".pithy/", ".cursor*"]
    added, modified = update_gitignore(temp_git_repo, entries)

    # Should detect existing entries despite whitespace
    assert modified is False
    assert added == []


def test_update_gitignore_preserves_file_structure(git_repo_with_gitignore: Path):
    """Should append to end without modifying existing content."""
    original_content = (git_repo_with_gitignore / ".gitignore").read_text()

    entries = [".pithy/"]
    update_gitignore(git_repo_with_gitignore, entries)

    new_content = (git_repo_with_gitignore / ".gitignore").read_text()

    # Original content should be preserved at the start
    assert new_content.startswith(original_content.rstrip())


# Integration Tests for run_init

def test_run_init_full_workflow_new_repo(temp_git_repo: Path, monkeypatch):
    """Should complete full initialization workflow in a fresh repo."""
    monkeypatch.chdir(temp_git_repo)

    run_init()

    # Verify .pithy directory created
    pithy_dir = temp_git_repo / ".pithy"
    assert pithy_dir.exists()
    assert pithy_dir.is_dir()

    # Verify .gitignore updated
    gitignore = temp_git_repo / ".gitignore"
    assert gitignore.exists()

    content = gitignore.read_text()
    assert ".pithy/" in content
    assert ".specstory/" in content
    assert ".cursor*" in content


def test_run_init_from_nested_directory(nested_git_repo: Path, temp_git_repo: Path, monkeypatch):
    """Should work correctly when run from a nested subdirectory."""
    monkeypatch.chdir(nested_git_repo)

    run_init()

    # Should create .pithy at root, not in nested directory
    pithy_dir = temp_git_repo / ".pithy"
    assert pithy_dir.exists()

    nested_pithy = nested_git_repo / ".pithy"
    assert not nested_pithy.exists()


def test_run_init_is_idempotent(temp_git_repo: Path, monkeypatch):
    """Should safely run multiple times without errors."""
    monkeypatch.chdir(temp_git_repo)

    # Run three times
    run_init()
    run_init()
    run_init()

    # Verify structure is correct
    assert (temp_git_repo / ".pithy").exists()

    gitignore_content = (temp_git_repo / ".gitignore").read_text()
    # Each entry should appear exactly once
    assert gitignore_content.count(".pithy/") == 1
    assert gitignore_content.count(".specstory/") == 1
    assert gitignore_content.count(".cursor*") == 1


def test_run_init_exits_when_not_in_git_repo(tmp_path: Path, monkeypatch):
    """Should exit with error when not in a git repository."""
    import typer
    non_git_dir = tmp_path / "not_a_repo"
    non_git_dir.mkdir()
    monkeypatch.chdir(non_git_dir)

    with pytest.raises(typer.Exit) as exc_info:
        run_init()

    assert exc_info.value.exit_code == 1


def test_run_init_preserves_existing_gitignore(git_repo_with_gitignore: Path, monkeypatch):
    """Should preserve existing .gitignore entries."""
    monkeypatch.chdir(git_repo_with_gitignore)

    original_content = (git_repo_with_gitignore / ".gitignore").read_text()

    run_init()

    new_content = (git_repo_with_gitignore / ".gitignore").read_text()

    # Original entries should still be present
    assert "node_modules/" in new_content
    assert "*.log" in new_content

    # New entries should be added
    assert ".pithy/" in new_content


# CLI Integration Tests

def test_cli_init_command_success(temp_git_repo: Path, monkeypatch):
    """Should successfully run init command via CLI."""
    monkeypatch.chdir(temp_git_repo)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 0
    assert "Found git repository" in result.stdout or "📍" in result.stdout
    assert ".pithy" in result.stdout
    assert "complete" in result.stdout.lower() or "✨" in result.stdout


def test_cli_init_command_fails_outside_git(tmp_path: Path, monkeypatch):
    """Should fail gracefully when run outside a git repository."""
    non_git = tmp_path / "no_git"
    non_git.mkdir()
    monkeypatch.chdir(non_git)

    result = runner.invoke(app, ["init"])

    assert result.exit_code == 1
    # Check both stdout and stderr for error messages
    combined_output = (result.stdout + result.stderr).lower()
    assert "not in a git repository" in combined_output or "error" in combined_output


def test_cli_init_shows_progress_messages(temp_git_repo: Path, monkeypatch):
    """Should output informative progress messages."""
    monkeypatch.chdir(temp_git_repo)

    result = runner.invoke(app, ["init"])

    # Should show what actions were taken
    output = result.stdout.lower()
    assert any(keyword in output for keyword in ["created", "found", "updated", "complete"])


# Edge Cases

def test_gitignore_with_no_trailing_newline(temp_git_repo: Path):
    """Should handle .gitignore without trailing newline."""
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text("node_modules/")  # No trailing newline

    entries = [".pithy/"]
    update_gitignore(temp_git_repo, entries)

    content = gitignore.read_text()
    lines = content.split("\n")

    # Should add newline before appending
    assert "node_modules/" in lines
    assert ".pithy/" in lines


def test_empty_gitignore_file(temp_git_repo: Path):
    """Should handle empty .gitignore file."""
    gitignore = temp_git_repo / ".gitignore"
    gitignore.write_text("")

    entries = [".pithy/", ".cursor*"]
    added, modified = update_gitignore(temp_git_repo, entries)

    assert modified is True
    assert set(added) == set(entries)


def test_gitignore_with_comments_and_sections(temp_git_repo: Path):
    """Should preserve comments and structure in .gitignore."""
    gitignore = temp_git_repo / ".gitignore"
    original = """# Python
*.pyc
__pycache__/

# Node
node_modules/
"""
    gitignore.write_text(original)

    entries = [".pithy/"]
    update_gitignore(temp_git_repo, entries)

    content = gitignore.read_text()

    # Comments preserved
    assert "# Python" in content
    assert "# Node" in content

    # New entry added
    assert ".pithy/" in content