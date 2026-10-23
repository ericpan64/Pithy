"""Git operations - thin wrappers around the git CLI."""

import subprocess
from pathlib import Path

HOOK_MARKER = "# Pithy AI Commit Hook"


class GitError(RuntimeError):
    """A git command failed."""


def git(*args: str, cwd: Path | None = None) -> str:
    """Run a git command and return its stdout; raises GitError on failure."""
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {args[0]} failed")
    return result.stdout.rstrip("\n")


def repo_root() -> Path | None:
    """Return the working tree root, or None outside a git repository."""
    try:
        return Path(git("rev-parse", "--show-toplevel"))
    except GitError:
        return None


def require_root() -> Path:
    """Return the working tree root, or raise outside a git repository."""
    root = repo_root()
    if root is None:
        raise ValueError("Not in a git repository")
    return root


def git_path(name: str) -> Path:
    """
    Resolve a path inside the git dir (e.g. 'hooks/prepare-commit-msg').

    Uses `git rev-parse --git-path`, which handles subdirectories, worktrees,
    submodules, and core.hooksPath.
    """
    require_root()
    return Path(git("rev-parse", "--git-path", name)).resolve()


def has_staged_changes() -> bool:
    """Check if there are staged changes (works before the first commit too)."""
    result = subprocess.run(["git", "diff", "--cached", "--quiet"], capture_output=True)
    return result.returncode == 1


def get_staged_diff(max_chars: int = 400_000) -> str:
    """Get staged diff; if over max_chars, truncate it and append the --stat."""
    diff = git("diff", "--cached", "--no-color", "-U3")
    if len(diff) <= max_chars:
        return diff

    stat = git("diff", "--cached", "--stat")
    return f"{diff[:max_chars]}\n\n[Diff truncated at {max_chars} characters. Full stat:]\n{stat}"


def get_recent_subjects(n: int = 10) -> list[str]:
    """Get the subjects of the last n commits (empty in a new repo)."""
    try:
        return git("log", f"-{n}", "--format=%s").splitlines()
    except GitError:
        return []


def get_repo_name() -> str:
    """Get repository name from git root directory."""
    root = repo_root()
    return root.name if root else "unknown"


def get_branch_name() -> str:
    """Get current branch name ('HEAD' when detached)."""
    return git("branch", "--show-current") or "HEAD"


def format_summary(summary: list[str]) -> str:
    """Format summary items as bullets, keeping existing (sub-)bullets."""
    return "\n".join(
        point if point.lstrip().startswith(("- ", "* ", "• ")) else f"- {point}"
        for point in summary
    )


def format_commit_message(title: str, summary: list[str]) -> str:
    """Format complete commit message with title and summary."""
    if not summary:
        return title
    return f"{title}\n\n{format_summary(summary)}"


def _read(path: Path) -> str | None:
    try:
        return path.read_text()
    except FileNotFoundError:
        return None


def install_git_hook(force: bool = False) -> Path:
    """
    Install git prepare-commit-msg hook.

    Refuses to overwrite a hook not written by Pithy unless force is set.

    Returns:
        Path to installed hook
    """
    hook_path = git_path("hooks/prepare-commit-msg")

    existing = _read(hook_path)
    if existing is not None and HOOK_MARKER not in existing and not force:
        raise ValueError(
            f"A prepare-commit-msg hook already exists at {hook_path}. "
            "Use --force to replace it."
        )

    hook_path.parent.mkdir(parents=True, exist_ok=True)
    hook_path.write_text(
        f'#!/bin/sh\n{HOOK_MARKER}\npithy ai-commit hook "$1" ${{2:+--source "$2"}}\n'
    )
    hook_path.chmod(0o755)

    return hook_path


def uninstall_git_hook() -> Path | None:
    """
    Uninstall the Pithy prepare-commit-msg hook.

    Returns:
        Path to uninstalled hook, or None if no Pithy hook was found
    """
    hook_path = git_path("hooks/prepare-commit-msg")

    existing = _read(hook_path)
    if existing is not None and HOOK_MARKER in existing:
        hook_path.unlink()
        return hook_path

    return None
