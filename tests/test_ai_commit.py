"""
Unit tests for pithy_cli.ai_commit module.

Run with: pytest tests/test_ai_commit.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from typer.testing import CliRunner

from pithy_cli.git import (
    format_commit_message,
    get_repo_name,
    has_staged_changes,
)
from pithy_cli.llm import (
    LLMProvider,
    create_llm_client,
    AnthropicClient,
    OpenAIClient,
    TogetherClient,
)
from pithy_cli.cli import app

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
    title = "fix: resolve bug"
    summary = []

    result = format_commit_message(title, summary)

    assert result == title


def test_format_commit_message_preserves_existing_bullets():
    """Test that existing bullet points are preserved."""
    title = "refactor: clean up code"
    summary = ["- Already has bullet", "No bullet here"]

    result = format_commit_message(title, summary)

    assert "- Already has bullet" in result
    assert "- No bullet here" in result


def test_get_repo_name():
    """Test getting repository name."""
    name = get_repo_name()
    # Should not crash, returns string
    assert isinstance(name, str)
    assert len(name) > 0


# Tests for llm.py

def test_create_llm_client_anthropic():
    """Test creating Anthropic LLM client."""
    client = create_llm_client(LLMProvider.ANTHROPIC, "test-key")

    assert isinstance(client, AnthropicClient)
    assert client.api_key == "test-key"


def test_create_llm_client_openai():
    """Test creating OpenAI LLM client."""
    client = create_llm_client(LLMProvider.OPENAI, "test-key")

    assert isinstance(client, OpenAIClient)
    assert client.api_key == "test-key"


def test_create_llm_client_together():
    """Test creating Together AI LLM client."""
    client = create_llm_client(LLMProvider.TOGETHER, "test-key")

    assert isinstance(client, TogetherClient)
    assert client.api_key == "test-key"


@patch("openai.OpenAI")
def test_together_client_complete(mock_openai):
    """Test Together client targets Together's endpoint with reasoning disabled."""
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="hello"))]
    mock_openai.return_value.chat.completions.create.return_value = mock_response

    result = TogetherClient(api_key="test-key").complete("prompt", max_tokens=100)

    assert result == "hello"
    mock_openai.assert_called_once_with(
        api_key="test-key", base_url="https://api.together.ai/v1"
    )
    kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "moonshotai/Kimi-K3"
    assert kwargs["max_tokens"] == 100
    assert kwargs["extra_body"] == {"reasoning": {"enabled": False}}


def test_create_llm_client_invalid_provider():
    """Test that invalid provider raises error."""
    with pytest.raises(ValueError, match="Unsupported provider"):
        create_llm_client("invalid", "test-key")


# Mock LLM client for testing

class MockLLMClient:
    """Mock LLM client for testing."""

    def complete(self, prompt: str, max_tokens: int = 4096) -> str:
        """Return mock JSON response."""
        if "summary" in prompt.lower():
            return '''{"summary": ["Add new feature", "Update tests", "Fix bug"]}'''
        else:
            return '''{
                "titles": [
                    "feat: add new feature",
                    "test: update test suite",
                    "fix: resolve critical bug"
                ]
            }'''


# Integration tests

@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repository."""
    repo_root = tmp_path / "test_repo"
    repo_root.mkdir()
    (repo_root / ".git").mkdir()
    (repo_root / ".git/hooks").mkdir(parents=True)
    return repo_root


def test_install_hook_creates_file(temp_git_repo: Path, monkeypatch):
    """Test that install command creates hook file."""
    monkeypatch.chdir(temp_git_repo)

    result = runner.invoke(app, ["ai-commit", "install"])

    assert result.exit_code == 0
    hook_path = temp_git_repo / ".git/hooks/prepare-commit-msg"
    assert hook_path.exists()
    assert hook_path.stat().st_mode & 0o111  # Check executable


def test_install_hook_with_custom_titles(temp_git_repo: Path, monkeypatch):
    """Test installing hook with custom title count."""
    monkeypatch.chdir(temp_git_repo)

    result = runner.invoke(app, ["ai-commit", "install", "--titles", "5"])

    assert result.exit_code == 0
    hook_path = temp_git_repo / ".git/hooks/prepare-commit-msg"
    content = hook_path.read_text()
    assert "--titles 5" in content


def test_uninstall_hook_removes_file(temp_git_repo: Path, monkeypatch):
    """Test that uninstall removes hook file."""
    monkeypatch.chdir(temp_git_repo)

    # Install first
    runner.invoke(app, ["ai-commit", "install"])

    # Then uninstall
    result = runner.invoke(app, ["ai-commit", "uninstall"])

    assert result.exit_code == 0
    hook_path = temp_git_repo / ".git/hooks/prepare-commit-msg"
    assert not hook_path.exists()


def test_uninstall_hook_when_not_installed(temp_git_repo: Path, monkeypatch):
    """Test uninstalling when hook doesn't exist."""
    monkeypatch.chdir(temp_git_repo)

    result = runner.invoke(app, ["ai-commit", "uninstall"])

    assert result.exit_code == 0
    assert "not found" in result.stdout.lower()


@patch('pithy_cli.ai_commit.get_provider_config')
@patch('pithy_cli.ai_commit.has_staged_changes', return_value=True)
@patch('pithy_cli.ai_commit.get_staged_diff', return_value="diff content")
@patch('pithy_cli.ai_commit.get_repo_name', return_value="test-repo")
@patch('pithy_cli.ai_commit.get_branch_name', return_value="main")
def test_generate_json_output(
    mock_branch,
    mock_repo,
    mock_diff,
    mock_staged,
    mock_config,
    temp_git_repo,
    monkeypatch
):
    """Test generate command with JSON output."""
    monkeypatch.chdir(temp_git_repo)

    # Mock provider config
    mock_config.return_value = (LLMProvider.ANTHROPIC, "test-key")

    # Mock LLM client
    with patch('pithy_cli.ai_commit.create_llm_client', return_value=MockLLMClient()):
        result = runner.invoke(app, ["ai-commit", "generate", "--json"])

        assert result.exit_code == 0
        # Should output JSON
        assert "{" in result.stdout
        assert "summary" in result.stdout or "titles" in result.stdout


# Edge cases

def test_format_commit_message_with_unicode():
    """Test formatting with unicode characters."""
    title = "feat: add emoji support 🎉"
    summary = ["Support emoji in messages 🚀"]

    result = format_commit_message(title, summary)

    assert "🎉" in result
    assert "🚀" in result


def test_format_commit_message_with_long_summary():
    """Test formatting with many summary points."""
    title = "refactor: major cleanup"
    summary = [f"Change {i}" for i in range(10)]

    result = format_commit_message(title, summary)

    lines = result.split("\n")
    # Title + blank line + 10 summary points
    assert len(lines) >= 12


def test_install_creates_executable_hook(temp_git_repo: Path, monkeypatch):
    """Test that installed hook is executable."""
    monkeypatch.chdir(temp_git_repo)

    result = runner.invoke(app, ["ai-commit", "install"])

    assert result.exit_code == 0
    hook_path = temp_git_repo / ".git/hooks/prepare-commit-msg"
    assert hook_path.stat().st_mode & 0o100  # Owner execute bit
