"""Git operations - pure tactical functions."""

from pathlib import Path
from typing import Optional

from git import Repo, InvalidGitRepositoryError, GitCommandError


def get_repo() -> Optional[Repo]:
    """Get git repository from current directory."""
    try:
        return Repo(".", search_parent_directories=True)
    except InvalidGitRepositoryError:
        return None


def has_staged_changes() -> bool:
    """Check if there are staged changes."""
    repo = get_repo()
    if not repo:
        return False

    try:
        # Check if there are differences between index and HEAD
        return len(repo.index.diff("HEAD")) > 0
    except (GitCommandError, ValueError):
        # No HEAD yet (new repo) - check if index has any entries
        return len(repo.index.entries) > 0


def get_staged_diff(max_bytes: int = 120_000) -> str:
    """
    Get staged diff with size limit.

    If diff exceeds max_bytes, returns a summary instead.
    """
    repo = get_repo()
    if not repo:
        return ""

    try:
        diff = repo.git.diff("--cached", "--no-color", "-U3")

        if len(diff) <= max_bytes:
            return diff

        # Fallback: get summary for large diffs
        return get_staged_summary()
    except GitCommandError:
        return ""


def get_staged_summary() -> str:
    """Get summary when diff is too large."""
    repo = get_repo()
    if not repo:
        return ""

    try:
        stats = repo.git.diff("--cached", "--stat")
        status = repo.git.diff("--cached", "--name-status")

        return f"File changes:\n{status}\n\nStats:\n{stats}"
    except GitCommandError:
        return ""


def get_repo_name() -> str:
    """Get repository name from git root directory."""
    repo = get_repo()
    if not repo:
        return "unknown"

    return Path(repo.working_dir).name


def get_branch_name() -> str:
    """Get current branch name."""
    repo = get_repo()
    if not repo:
        return "unknown"

    try:
        return repo.active_branch.name
    except TypeError:
        # Detached HEAD state
        return "HEAD"


def read_commit_msg(path: str) -> Optional[str]:
    """Read commit message file."""
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        return None


def write_commit_msg(path: str, content: str) -> None:
    """Write commit message file."""
    Path(path).write_text(content)


def format_commit_message(title: str, summary: list[str]) -> str:
    """Format complete commit message with title and summary."""
    if not summary:
        return title

    lines = [title, ""]
    for point in summary:
        # Handle nested bullet points
        if point.strip().startswith(("- ", "• ", "*")):
            lines.append(point)
        elif point.strip().startswith(("  -", "  •", "  *")):
            lines.append(point)
        else:
            lines.append(f"- {point}")

    return "\n".join(lines)


def install_git_hook(titles: int = 3) -> Path:
    """
    Install git prepare-commit-msg hook.

    Returns:
        Path to installed hook
    """
    hook_path = Path(".git/hooks/prepare-commit-msg")

    # Create hook script
    hook_path.parent.mkdir(parents=True, exist_ok=True)

    hook_content = f"""#!/bin/sh
# Pithy AI Commit Hook

# Skip merges/squashes
case "$2" in
  merge|squash) exit 0 ;;
esac

# Reattach to TTY for interactive input
if [ -c /dev/tty ] 2>/dev/null; then
  if [ -r /dev/tty ] && [ -w /dev/tty ]; then
    exec < /dev/tty > /dev/tty 2>&1
  fi
fi

# Call pithy ai-commit hook
pithy ai-commit hook "$1" ${{2:+--source "$2"}} --titles {titles}
"""

    hook_path.write_text(hook_content)
    hook_path.chmod(0o755)

    return hook_path


def uninstall_git_hook() -> Optional[Path]:
    """
    Uninstall git prepare-commit-msg hook.

    Returns:
        Path to uninstalled hook, or None if not found
    """
    hook_path = Path(".git/hooks/prepare-commit-msg")

    if hook_path.exists():
        hook_path.unlink()
        return hook_path

    return None
