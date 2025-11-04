"""
Unit tests for pithy_cli.summarize module.

Run with: pytest tests/test_summarize.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from pithy_cli.summarize import (
    run_summarize,
    _relative_to,
    _matches_excludes,
    _is_text_file,
    _dest_for_file,
    _dest_meta_for_dir,
    _should_skip_file,
    _extract_first_bullet,
    _render_dir_meta,
    DEFAULT_EXCLUDES,
)
from pithy_cli.llm import LLMClient


class StubLLMClient:
    """Stub LLM client for deterministic testing."""

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        """Return deterministic summary with required structure."""
        # Extract path from prompt for more realistic output
        lines = prompt.split("\n")
        path = "test.py"
        for line in lines:
            if line.startswith("Path:"):
                path = line.split("Path:")[1].strip()
                break

        return f"""## {path}

### Key Points
- Main purpose and functionality
- Key classes or functions defined
- Important dependencies
- Notable side effects or risks
- Testing considerations

### Notes
- This is a stub summary for testing"""


# Tests for helper functions


def test_relative_to_within_root(tmp_path):
    """Test computing relative path when path is within root."""
    root = tmp_path / "repo"
    root.mkdir()
    file = root / "src" / "app.py"
    file.parent.mkdir()
    file.touch()

    rel = _relative_to(file, root)
    assert rel == Path("src/app.py")


def test_relative_to_outside_root(tmp_path):
    """Test computing relative path when path is outside root."""
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "other" / "file.py"
    outside.parent.mkdir()
    outside.touch()

    rel = _relative_to(outside, root)
    assert rel == Path("file.py")


def test_matches_excludes_directory():
    """Test exclusion matching for directories."""
    patterns = [".git/", "node_modules/", "*.pyc"]

    assert _matches_excludes(Path(".git"), True, patterns)
    assert _matches_excludes(Path("node_modules"), True, patterns)
    assert _matches_excludes(Path("src/node_modules"), True, patterns)
    assert not _matches_excludes(Path("src"), True, patterns)


def test_matches_excludes_file():
    """Test exclusion matching for files."""
    patterns = ["*.pyc", "*lock*", "*.min.*"]

    assert _matches_excludes(Path("test.pyc"), False, patterns)
    assert _matches_excludes(Path("package-lock.json"), False, patterns)
    assert _matches_excludes(Path("app.min.js"), False, patterns)
    assert not _matches_excludes(Path("app.py"), False, patterns)


def test_is_text_file_python(tmp_path):
    """Test text file detection for Python file."""
    py_file = tmp_path / "test.py"
    py_file.write_text("print('hello')")

    assert _is_text_file(py_file)


def test_is_text_file_json(tmp_path):
    """Test text file detection for JSON file."""
    json_file = tmp_path / "data.json"
    json_file.write_text('{"key": "value"}')

    assert _is_text_file(json_file)


def test_is_text_file_binary(tmp_path):
    """Test text file detection for binary file."""
    bin_file = tmp_path / "image.png"
    bin_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    assert not _is_text_file(bin_file)


def test_dest_for_file():
    """Test destination path computation for file summary."""
    pithy_root = Path("/repo/.pithy")
    rel_file = Path("src/app.py")

    dest = _dest_for_file(pithy_root, rel_file)
    assert dest == Path("/repo/.pithy/src/app.py.md")


def test_dest_meta_for_dir():
    """Test destination path computation for directory meta."""
    pithy_root = Path("/repo/.pithy")
    rel_dir = Path("src")

    dest = _dest_meta_for_dir(pithy_root, rel_dir)
    assert dest == Path("/repo/.pithy/src/_meta.md")


def test_should_skip_file_force(tmp_path):
    """Test skip logic with force=True."""
    src = tmp_path / "src.py"
    dest = tmp_path / "dest.md"
    src.write_text("code")
    dest.write_text("summary")

    assert not _should_skip_file(src, dest, force=True)


def test_should_skip_file_dest_missing(tmp_path):
    """Test skip logic when destination doesn't exist."""
    src = tmp_path / "src.py"
    dest = tmp_path / "dest.md"
    src.write_text("code")

    assert not _should_skip_file(src, dest, force=False)


def test_should_skip_file_dest_older(tmp_path):
    """Test skip logic when destination is older."""
    src = tmp_path / "src.py"
    dest = tmp_path / "dest.md"

    dest.write_text("old summary")
    # Wait and modify source to ensure newer mtime
    import time
    time.sleep(0.01)
    src.write_text("new code")

    assert not _should_skip_file(src, dest, force=False)


def test_extract_first_bullet_success():
    """Test extracting first bullet from summary."""
    summary = """## test.py

### Key Points
- Main purpose and functionality
- Secondary point
- Third point

### Notes
- Some note"""

    result = _extract_first_bullet(summary)
    assert result == "Main purpose and functionality"


def test_extract_first_bullet_no_key_points():
    """Test extracting first bullet when Key Points section missing."""
    summary = """## test.py

### Overview
- Some overview"""

    result = _extract_first_bullet(summary)
    assert result is None


def test_render_dir_meta_with_files():
    """Test rendering directory meta with files."""
    rel_dir = Path("src")
    file_lines = ["- **app.py**: Main application entry point", "- **utils.py**: Utility functions"]
    subdir_lines = []

    result = _render_dir_meta(rel_dir, file_lines, subdir_lines)

    assert "# src" in result
    assert "## Files" in result
    assert "- **app.py**: Main application entry point" in result
    assert "- **utils.py**: Utility functions" in result
    assert "## Subdirectories" in result
    assert "- *(none)*" in result


def test_render_dir_meta_with_subdirs():
    """Test rendering directory meta with subdirectories."""
    rel_dir = Path("src")
    file_lines = []
    subdir_lines = ["- [utils/](.pithy/src/utils/_meta.md)", "- [tests/](.pithy/src/tests/_meta.md)"]

    result = _render_dir_meta(rel_dir, file_lines, subdir_lines)

    assert "# src" in result
    assert "## Files" in result
    assert "- *(none)*" in result
    assert "## Subdirectories" in result
    assert "- [utils/](.pithy/src/utils/_meta.md)" in result


def test_render_dir_meta_root():
    """Test rendering directory meta for root."""
    rel_dir = Path(".")
    file_lines = ["- README.md"]
    subdir_lines = ["- [src/](.pithy/src/_meta.md)"]

    result = _render_dir_meta(rel_dir, file_lines, subdir_lines)

    assert "# ." in result


# Integration tests


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_summarize_single_file(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test summarizing a single file."""
    # Setup
    repo = tmp_path / "repo"
    repo.mkdir()
    src_file = repo / "test.py"
    src_file.write_text("print('hello')")
    pithy_dir = repo / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run
    run_summarize(str(src_file), quiet=True)

    # Verify
    summary_path = pithy_dir / "test.py.md"
    assert summary_path.exists()
    content = summary_path.read_text()
    assert "## test.py" in content
    assert "### Key Points" in content


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_summarize_directory_structure(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test summarizing a directory structure."""
    # Setup
    repo = tmp_path / "repo"
    repo.mkdir()

    # Create test structure
    src = repo / "src"
    src.mkdir()
    (src / "app.py").write_text("def main(): pass")
    (src / "utils.py").write_text("def helper(): pass")

    tests = src / "tests"
    tests.mkdir()
    (tests / "test_app.py").write_text("def test_main(): assert True")

    pithy_dir = repo / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run
    run_summarize(str(src), quiet=True)

    # Verify file summaries
    assert (pithy_dir / "src" / "app.py.md").exists()
    assert (pithy_dir / "src" / "utils.py.md").exists()
    assert (pithy_dir / "src" / "tests" / "test_app.py.md").exists()

    # Verify directory metas
    src_meta = pithy_dir / "src" / "_meta.md"
    assert src_meta.exists()
    src_meta_content = src_meta.read_text()
    assert "# src" in src_meta_content
    assert "app.py" in src_meta_content
    assert "utils.py" in src_meta_content
    assert "[tests/]" in src_meta_content

    tests_meta = pithy_dir / "src" / "tests" / "_meta.md"
    assert tests_meta.exists()
    tests_meta_content = tests_meta.read_text()
    assert "# src/tests" in tests_meta_content
    assert "test_app.py" in tests_meta_content


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_summarize_respects_excludes(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test that exclusion patterns are respected."""
    # Setup
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "app.py").write_text("code")
    node_modules = repo / "node_modules"
    node_modules.mkdir()
    (node_modules / "lib.js").write_text("library")

    pithy_dir = repo / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run
    run_summarize(str(repo), quiet=True)

    # Verify app.py was summarized
    assert (pithy_dir / "app.py.md").exists()

    # Verify node_modules was excluded
    assert not (pithy_dir / "node_modules").exists()


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_summarize_custom_exclude(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test custom exclusion patterns."""
    # Setup
    repo = tmp_path / "repo"
    repo.mkdir()

    (repo / "important.py").write_text("code")
    (repo / "secret.txt").write_text("secret")

    pithy_dir = repo / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run with custom exclude
    run_summarize(str(repo), excludes=["secret.txt"], quiet=True)

    # Verify important.py was summarized
    assert (pithy_dir / "important.py.md").exists()

    # Verify secret.txt was excluded
    assert not (pithy_dir / "secret.txt.md").exists()


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_summarize_depth_limit(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test depth limit for recursion."""
    # Setup
    repo = tmp_path / "repo"
    repo.mkdir()

    level1 = repo / "level1"
    level1.mkdir()
    (level1 / "file1.py").write_text("code")

    level2 = level1 / "level2"
    level2.mkdir()
    (level2 / "file2.py").write_text("code")

    pithy_dir = repo / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run with depth=1 (process repo root and one level down)
    run_summarize(str(repo), depth=1, quiet=True)

    # Verify level1 meta exists (depth 1)
    assert (pithy_dir / "level1" / "_meta.md").exists()

    # Verify level2 was not processed (depth 2 - exceeded)
    assert not (pithy_dir / "level1" / "level2" / "_meta.md").exists()


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_summarize_force_regenerate(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test force regeneration of summaries."""
    # Setup
    repo = tmp_path / "repo"
    repo.mkdir()
    src_file = repo / "test.py"
    src_file.write_text("original")

    pithy_dir = repo / ".pithy"
    pithy_dir.mkdir()
    summary_path = pithy_dir / "test.py.md"
    summary_path.write_text("old summary")

    # Ensure summary is newer than source
    import time
    time.sleep(0.01)
    summary_path.touch()
    mtime_before = summary_path.stat().st_mtime

    mock_find_git.return_value = repo
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run without force (should skip - summary is newer)
    run_summarize(str(src_file), force=False, quiet=True)
    content_after_skip = summary_path.read_text()
    assert content_after_skip == "old summary"  # Should not have changed

    # Run with force (should regenerate even though summary is newer)
    time.sleep(0.01)
    run_summarize(str(src_file), force=True, quiet=True)
    content_after_force = summary_path.read_text()
    mtime_after = summary_path.stat().st_mtime

    # Verify regeneration occurred
    assert content_after_force != "old summary"
    assert "### Key Points" in content_after_force
    assert mtime_after > mtime_before


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_summarize_dry_run(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test dry run mode."""
    # Setup
    repo = tmp_path / "repo"
    repo.mkdir()
    src_file = repo / "test.py"
    src_file.write_text("code")

    pithy_dir = repo / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run in dry-run mode
    run_summarize(str(src_file), dry_run=True, quiet=True)

    # Verify no files were created
    summary_path = pithy_dir / "test.py.md"
    assert not summary_path.exists()


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_summarize_binary_file(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test handling of binary files."""
    # Setup
    repo = tmp_path / "repo"
    repo.mkdir()
    bin_file = repo / "image.png"
    bin_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    pithy_dir = repo / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run
    run_summarize(str(bin_file), quiet=True)

    # Verify stub was created
    summary_path = pithy_dir / "image.png.md"
    assert summary_path.exists()
    content = summary_path.read_text()
    assert "Binary or non-text file" in content
