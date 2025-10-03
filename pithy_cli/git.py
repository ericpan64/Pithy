"""Git operations - pure tactical functions."""

import subprocess
from pathlib import Path
from typing import Optional


def run_git_command(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        check=check,
    )


def has_staged_changes() -> bool:
    """Check if there are staged changes."""
    result = run_git_command(["diff", "--cached", "--quiet"], check=False)
    return result.returncode != 0


def get_staged_diff(max_bytes: int = 120_000) -> str:
    """
    Get staged diff with size limit.

    If diff exceeds max_bytes, returns a summary instead.
    """
    result = run_git_command(["diff", "--cached", "--no-color", "-U3"])
    diff = result.stdout

    if len(diff) <= max_bytes:
        return diff

    # Fallback: get summary for large diffs
    return get_staged_summary()


def get_staged_summary() -> str:
    """Get summary when diff is too large."""
    stats = run_git_command(["diff", "--cached", "--stat"]).stdout
    status = run_git_command(["diff", "--cached", "--name-status"]).stdout

    return f"File changes:\n{status}\n\nStats:\n{stats}"


def get_repo_name() -> str:
    """Get repository name from git root directory."""
    result = run_git_command(["rev-parse", "--show-toplevel"], check=False)

    if result.returncode == 0:
        return Path(result.stdout.strip()).name

    return "unknown"


def get_branch_name() -> str:
    """Get current branch name."""
    result = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], check=False)

    if result.returncode == 0:
        return result.stdout.strip()

    return "unknown"


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
pithy ai-commit hook --file "$1" ${{2:+--source "$2"}} --titles {titles}
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
