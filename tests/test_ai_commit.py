"""
Unit tests for pithy_cli.ai_commit module.

Run with: pytest tests/test_ai_commit.py -v
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from pithy_cli.ai_commit import (
    COMMIT_SCHEMA,
    CommitMessage,
    generate_commit_message,
    run_hook,
)
from pithy_cli.cli import app
from pithy_cli.git import (
    format_commit_message,
    get_recent_subjects,
    get_repo_name,
    get_staged_diff,
    git_path,
    has_staged_changes,
)

runner = CliRunner()


# Tests for git.py functions


def test_format_commit_message_with_summary():
    """Test formatting commit message with summary."""
    title = "feat(auth): add OAuth2 support"
    summary = ["Add OAuth2 login", "  - JWT tokens", "Update docs"]

    result = format_commit_message(title, summary)

    assert result.startswith(title)
    assert "- Add OAuth2 login" in result
    assert "  - JWT tokens" in result
    assert "- Update docs" in result


def test_format_commit_message_without_summary():
    """Test formatting commit message without summary."""
    assert format_commit_message("fix: resolve bug", []) == "fix: resolve bug"


def test_format_commit_message_preserves_existing_bullets():
    """Test that existing bullet points are preserved."""
    result = format_commit_message(
        "refactor: clean up code", ["- Already has bullet", "No bullet here"]
    )

    assert "- Already has bullet" in result
    assert "- - Already" not in result
    assert "- No bullet here" in result


def test_format_commit_message_with_unicode():
    """Test formatting with unicode characters."""
    result = format_commit_message(
        "feat: add emoji support 🎉", ["Support emoji in messages 🚀"]
    )

    assert "🎉" in result
    assert "🚀" in result


def test_get_repo_name(git_repo):
    assert get_repo_name() == "repo"


def test_has_staged_changes(git_repo):
    assert not has_staged_changes()

    (git_repo / "new.txt").write_text("x")
    subprocess.run(["git", "add", "new.txt"], check=True)

    assert has_staged_changes()


def test_get_staged_diff_truncates_and_appends_stat(git_repo):
    (git_repo / "big.txt").write_text("line\n" * 1000)
    subprocess.run(["git", "add", "big.txt"], check=True)

    diff = get_staged_diff(max_chars=200)

    assert "[Diff truncated at 200 characters. Full stat:]" in diff
    assert "big.txt" in diff.split("Full stat:]")[1]


def test_has_staged_changes_before_first_commit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True)
    (tmp_path / "a.txt").write_text("a")
    subprocess.run(["git", "add", "a.txt"], check=True)

    assert has_staged_changes()
    assert get_recent_subjects() == []


def test_get_recent_subjects(git_repo):
    assert get_recent_subjects() == ["chore: initial commit"]


def test_git_path_from_subdirectory(git_repo, monkeypatch):
    (git_repo / "sub").mkdir()
    monkeypatch.chdir(git_repo / "sub")

    assert git_path("COMMIT_EDITMSG") == git_repo / ".git" / "COMMIT_EDITMSG"


# generate_commit_message


@patch("pithy_cli.ai_commit.resolve_client")
def test_generate_commit_message_single_structured_call(mock_resolve, git_repo):
    (git_repo / "feature.py").write_text("def feature(): pass\n")
    subprocess.run(["git", "add", "feature.py"], check=True)
    client = Mock()
    client.complete.return_value = json.dumps(
        {"summary": ["Add feature"], "titles": ["feat: a", "feat: b", "feat: c", "x"]}
    )
    mock_resolve.return_value = client

    message = generate_commit_message(titles_count=3)

    assert message.summary == ["Add feature"]
    assert message.titles == ["feat: a", "feat: b", "feat: c"]
    client.complete.assert_called_once()
    system, user = client.complete.call_args.args
    assert "commit" in system.lower()
    assert "Number of titles: 3" in user
    assert "- chore: initial commit" in user  # recent subjects for style
    assert "feature.py" in user
    assert client.complete.call_args.kwargs["schema"] == COMMIT_SCHEMA


def test_generate_commit_message_requires_staged_changes(git_repo):
    with pytest.raises(ValueError, match="No staged changes"):
        generate_commit_message()


@patch("pithy_cli.ai_commit.generate_commit_message")
def test_generate_json_output(mock_generate, git_repo):
    mock_generate.return_value = CommitMessage(["Add X"], ["feat: add x"])

    result = runner.invoke(app, ["ai-commit", "generate", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "summary": ["Add X"],
        "titles": ["feat: add x"],
    }


@patch("pithy_cli.ai_commit.generate_commit_message")
def test_generate_text_output(mock_generate, git_repo):
    mock_generate.return_value = CommitMessage(["Add X"], ["feat: add x", "feat: x"])

    result = runner.invoke(app, ["ai-commit", "generate", "-n", "2"])

    assert result.exit_code == 0
    assert result.stdout == "1. feat: add x\n2. feat: x\n\n- Add X\n"
    mock_generate.assert_called_once_with(titles_count=2)


def test_generate_without_staged_changes_errors(git_repo):
    result = runner.invoke(app, ["ai-commit", "generate"])

    assert result.exit_code == 1
    assert "No staged changes" in result.output


# Hook handler


def _stage(repo: Path) -> None:
    (repo / "feature.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "feature.py"], check=True)


@patch("pithy_cli.ai_commit.generate_commit_message")
def test_run_hook_prepends_message_and_keeps_comments(mock_generate, git_repo):
    _stage(git_repo)
    mock_generate.return_value = CommitMessage(["Add X"], ["feat: add x"])
    msg_file = git_repo / ".git/COMMIT_EDITMSG"
    msg_file.write_text("\n# Please enter the commit message\n")

    run_hook(str(msg_file))

    assert msg_file.read_text() == (
        "feat: add x\n\n- Add X\n\n# Please enter the commit message\n"
    )


@pytest.mark.parametrize("source", ["message", "merge", "squash", "commit"])
@patch("pithy_cli.ai_commit.generate_commit_message")
def test_run_hook_skips_sources_with_messages(mock_generate, source, git_repo):
    _stage(git_repo)
    msg_file = git_repo / ".git/COMMIT_EDITMSG"
    msg_file.write_text("my message\n")

    run_hook(str(msg_file), source)

    mock_generate.assert_not_called()
    assert msg_file.read_text() == "my message\n"


@patch("pithy_cli.ai_commit.generate_commit_message")
def test_run_hook_drafts_for_template_source(mock_generate, git_repo):
    _stage(git_repo)
    mock_generate.return_value = CommitMessage([], ["feat: add x"])
    msg_file = git_repo / ".git/COMMIT_EDITMSG"
    msg_file.write_text("Ticket: \n")

    run_hook(str(msg_file), "template")

    assert msg_file.read_text() == "feat: add x\nTicket: \n"


@patch("pithy_cli.ai_commit.generate_commit_message", side_effect=ValueError("boom"))
def test_run_hook_errors_never_block_commit(_mock_generate, git_repo, capsys):
    _stage(git_repo)
    msg_file = git_repo / ".git/COMMIT_EDITMSG"
    msg_file.write_text("# comments\n")

    run_hook(str(msg_file))  # must not raise

    assert msg_file.read_text() == "# comments\n"
    assert "boom" in capsys.readouterr().err


# Hook install/uninstall


def _hook(repo: Path) -> Path:
    return repo / ".git/hooks/prepare-commit-msg"


def test_install_hook_creates_executable_file(git_repo):
    result = runner.invoke(app, ["ai-commit", "install"])

    assert result.exit_code == 0
    assert _hook(git_repo).stat().st_mode & 0o100
    assert 'pithy ai-commit hook "$1"' in _hook(git_repo).read_text()


def test_install_hook_from_subdirectory(git_repo, monkeypatch):
    (git_repo / "sub").mkdir()
    monkeypatch.chdir(git_repo / "sub")

    result = runner.invoke(app, ["ai-commit", "install"])

    assert result.exit_code == 0
    assert _hook(git_repo).exists()
    assert not (git_repo / "sub/.git").exists()


def test_install_hook_in_worktree(git_repo, tmp_path, monkeypatch):
    worktree = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", str(worktree)], check=True, capture_output=True
    )
    monkeypatch.chdir(worktree)

    result = runner.invoke(app, ["ai-commit", "install"])

    assert result.exit_code == 0, result.output
    assert _hook(git_repo).exists()  # worktrees share the main repo's hooks


def test_install_refuses_foreign_hook(git_repo):
    _hook(git_repo).parent.mkdir(parents=True, exist_ok=True)
    _hook(git_repo).write_text("#!/bin/sh\necho mine\n")

    result = runner.invoke(app, ["ai-commit", "install"])

    assert result.exit_code == 1
    assert "--force" in result.output
    assert "echo mine" in _hook(git_repo).read_text()

    result = runner.invoke(app, ["ai-commit", "install", "--force"])

    assert result.exit_code == 0
    assert "Pithy AI Commit Hook" in _hook(git_repo).read_text()


def test_uninstall_hook_removes_file(git_repo):
    runner.invoke(app, ["ai-commit", "install"])

    result = runner.invoke(app, ["ai-commit", "uninstall"])

    assert result.exit_code == 0
    assert not _hook(git_repo).exists()


def test_uninstall_leaves_foreign_hook(git_repo):
    _hook(git_repo).parent.mkdir(parents=True, exist_ok=True)
    _hook(git_repo).write_text("#!/bin/sh\necho mine\n")

    result = runner.invoke(app, ["ai-commit", "uninstall"])

    assert result.exit_code == 0
    assert "not found" in result.stdout.lower()
    assert _hook(git_repo).exists()
