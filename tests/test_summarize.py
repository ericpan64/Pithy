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
    _is_gitignored,
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


def _get_latest_summary_dir(pithy_dir: Path) -> Path:
    """Get the latest timestamped summary directory."""
    summarize_dir = pithy_dir / "summarize"
    if not summarize_dir.exists():
        raise FileNotFoundError(f"No summarize directory found in {pithy_dir}")

    # Find all timestamped directories
    timestamp_dirs = sorted([d for d in summarize_dir.iterdir() if d.is_dir()])
    if not timestamp_dirs:
        raise FileNotFoundError(f"No timestamp directories found in {summarize_dir}")

    # Return the latest (last in sorted order)
    return timestamp_dirs[-1]


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
    output_dir = _get_latest_summary_dir(pithy_dir)
    summary_path = output_dir / "test.py.md"
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
    output_dir = _get_latest_summary_dir(pithy_dir)
    assert (output_dir / "src" / "app.py.md").exists()
    assert (output_dir / "src" / "utils.py.md").exists()
    assert (output_dir / "src" / "tests" / "test_app.py.md").exists()

    # Verify directory metas
    src_meta = output_dir / "src" / "_meta.md"
    assert src_meta.exists()
    src_meta_content = src_meta.read_text()
    assert "# src" in src_meta_content
    assert "app.py" in src_meta_content
    assert "utils.py" in src_meta_content
    assert "[tests/]" in src_meta_content

    tests_meta = output_dir / "src" / "tests" / "_meta.md"
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

    # Get output directory
    output_dir = _get_latest_summary_dir(pithy_dir)
    assert (output_dir / "app.py.md").exists()

    # Verify node_modules was excluded
    assert not (output_dir / "node_modules").exists()


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

    # Get output directory
    output_dir = _get_latest_summary_dir(pithy_dir)
    assert (output_dir / "important.py.md").exists()

    # Verify secret.txt was excluded
    assert not (output_dir / "secret.txt.md").exists()


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

    # Get output directory
    output_dir = _get_latest_summary_dir(pithy_dir)
    assert (output_dir / "level1" / "_meta.md").exists()

    # Verify level2 was not processed (depth 2 - exceeded)
    assert not (output_dir / "level1" / "level2" / "_meta.md").exists()


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_summarize_force_regenerate(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test that force flag works (creates summary regardless)."""
    # Note: With timestamped directories, each run creates a new output directory,
    # so force primarily matters for ensuring summaries are generated even if
    # they would otherwise be skipped

    # Setup
    repo = tmp_path / "repo"
    repo.mkdir()
    src_file = repo / "test.py"
    src_file.write_text("test code")

    pithy_dir = repo / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run with force=True
    run_summarize(str(src_file), force=True, quiet=True)

    # Get output directory
    output_dir = _get_latest_summary_dir(pithy_dir)

    # Verify summary was created
    summary_path = output_dir / "test.py.md"
    assert summary_path.exists()
    content = summary_path.read_text()
    assert "### Key Points" in content


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

    # Verify no files were created in dry-run mode
    # The timestamp directory might be created, but no summary files should exist
    try:
        output_dir = _get_latest_summary_dir(pithy_dir)
        summary_path = output_dir / "test.py.md"
        assert not summary_path.exists()
    except FileNotFoundError:
        # If no summarize directory was created at all, that's also fine for dry-run
        pass


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

    # Get output directory
    output_dir = _get_latest_summary_dir(pithy_dir)
    summary_path = output_dir / "image.png.md"
    assert summary_path.exists()
    content = summary_path.read_text()
    assert "Binary or non-text file" in content


# Gitignore tests


def test_is_gitignored_with_gitignore(tmp_path):
    """Test that _is_gitignored detects ignored files."""
    # Setup git repo with .gitignore
    from git import Repo
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Create .gitignore
    gitignore = repo_path / ".gitignore"
    gitignore.write_text("*.pyc\nbuild/\n.venv/\n")

    # Create files
    ignored_file = repo_path / "test.pyc"
    ignored_file.write_text("ignored")

    normal_file = repo_path / "app.py"
    normal_file.write_text("code")

    # Test
    assert _is_gitignored(ignored_file, repo_path)
    assert not _is_gitignored(normal_file, repo_path)


def test_is_gitignored_directory(tmp_path):
    """Test that _is_gitignored detects ignored directories."""
    from git import Repo
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Create .gitignore
    gitignore = repo_path / ".gitignore"
    gitignore.write_text("build/\nnode_modules/\n")

    # Create directories
    build_dir = repo_path / "build"
    build_dir.mkdir()

    src_dir = repo_path / "src"
    src_dir.mkdir()

    # Test
    assert _is_gitignored(build_dir, repo_path)
    assert not _is_gitignored(src_dir, repo_path)


def test_is_gitignored_no_gitignore(tmp_path):
    """Test that _is_gitignored handles missing .gitignore gracefully."""
    from git import Repo
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Create file without .gitignore
    normal_file = repo_path / "app.py"
    normal_file.write_text("code")

    # Should not be considered ignored
    assert not _is_gitignored(normal_file, repo_path)


def test_is_gitignored_not_in_repo(tmp_path):
    """Test that _is_gitignored handles non-repo paths gracefully."""
    non_repo = tmp_path / "not_repo"
    non_repo.mkdir()

    file = non_repo / "test.py"
    file.write_text("code")

    # Should return False (not excluded)
    assert not _is_gitignored(file, non_repo)


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_respects_gitignore_files(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test that gitignored files are skipped by default."""
    from git import Repo

    # Setup git repo
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Create .gitignore
    gitignore = repo_path / ".gitignore"
    gitignore.write_text("*.pyc\nsecret.txt\n")

    # Create files
    (repo_path / "app.py").write_text("print('hello')")
    (repo_path / "test.pyc").write_text("compiled")
    (repo_path / "secret.txt").write_text("secret")

    pithy_dir = repo_path / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo_path
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run without include_ignored (default)
    run_summarize(str(repo_path), quiet=True)

    # Verify app.py was summarized

    # Get output directory
    output_dir = _get_latest_summary_dir(pithy_dir)
    assert (output_dir / "app.py.md").exists()

    # Verify gitignored files were NOT summarized
    assert not (output_dir / "test.pyc.md").exists()
    assert not (output_dir / "secret.txt.md").exists()


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_respects_gitignore_directories(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test that gitignored directories are skipped by default."""
    from git import Repo

    # Setup git repo
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Create .gitignore
    gitignore = repo_path / ".gitignore"
    gitignore.write_text("build/\n.venv/\n")

    # Create directories
    src = repo_path / "src"
    src.mkdir()
    (src / "app.py").write_text("code")

    build = repo_path / "build"
    build.mkdir()
    (build / "output.js").write_text("compiled")

    pithy_dir = repo_path / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo_path
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run
    run_summarize(str(repo_path), quiet=True)

    # Verify src/ was processed

    # Get output directory
    output_dir = _get_latest_summary_dir(pithy_dir)
    assert (output_dir / "src" / "_meta.md").exists()
    assert (output_dir / "src" / "app.py.md").exists()

    # Verify build/ was NOT processed
    assert not (output_dir / "build").exists()


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_include_ignored_flag(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test that --include-ignored processes gitignored files."""
    from git import Repo

    # Setup git repo
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Create .gitignore
    gitignore = repo_path / ".gitignore"
    gitignore.write_text("*.pyc\n")

    # Create files
    (repo_path / "app.py").write_text("code")
    (repo_path / "test.pyc").write_text("compiled")

    pithy_dir = repo_path / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo_path
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run WITH include_ignored=True
    run_summarize(str(repo_path), include_ignored=True, quiet=True)

    # Verify both files were summarized

    # Get output directory
    output_dir = _get_latest_summary_dir(pithy_dir)
    assert (output_dir / "app.py.md").exists()
    assert (output_dir / "test.pyc.md").exists()


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_gitignore_with_custom_excludes(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test that gitignore and custom --exclude work together."""
    from git import Repo

    # Setup git repo
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Create .gitignore
    gitignore = repo_path / ".gitignore"
    gitignore.write_text("*.pyc\n")

    # Create files
    (repo_path / "app.py").write_text("code")
    (repo_path / "test.pyc").write_text("compiled")
    (repo_path / "docs.md").write_text("documentation")

    pithy_dir = repo_path / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo_path
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run with custom exclude
    run_summarize(str(repo_path), excludes=["*.md"], quiet=True)

    # Verify app.py was summarized

    # Get output directory
    output_dir = _get_latest_summary_dir(pithy_dir)
    assert (output_dir / "app.py.md").exists()

    # Verify gitignored file was NOT summarized
    assert not (output_dir / "test.pyc.md").exists()

    # Verify custom excluded file was NOT summarized
    assert not (output_dir / "docs.md.md").exists()


@patch("pithy_cli.summarize.get_provider_config")
@patch("pithy_cli.summarize.create_llm_client")
@patch("pithy_cli.summarize.find_git_root")
def test_no_gitignore_fallback(mock_find_git, mock_create_client, mock_get_config, tmp_path):
    """Test graceful handling when no .gitignore exists."""
    from git import Repo

    # Setup git repo WITHOUT .gitignore
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    repo = Repo.init(repo_path)

    # Create files
    (repo_path / "app.py").write_text("code")
    (repo_path / "test.txt").write_text("text")

    pithy_dir = repo_path / ".pithy"
    pithy_dir.mkdir()

    mock_find_git.return_value = repo_path
    mock_get_config.return_value = ("anthropic", "test-key")
    mock_create_client.return_value = StubLLMClient()

    # Run (should work fine without .gitignore)
    run_summarize(str(repo_path), quiet=True)

    # Verify both files were summarized

    # Get output directory
    output_dir = _get_latest_summary_dir(pithy_dir)
    assert (output_dir / "app.py.md").exists()
    assert (output_dir / "test.txt.md").exists()
