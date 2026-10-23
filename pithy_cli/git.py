"""Git operations - pure tactical functions."""

from pathlib import Path

from git import GitCommandError, InvalidGitRepositoryError, Repo

HOOK_MARKER = "# Pithy AI Commit Hook"


def get_repo() -> Repo | None:
    """Get git repository from current directory."""
    try:
        return Repo(".", search_parent_directories=True)
    except InvalidGitRepositoryError:
        return None


def _require_repo() -> Repo:
    repo = get_repo()
    if repo is None:
        raise ValueError("Not in a git repository")
    return repo


def git_path(name: str) -> Path:
    """
    Resolve a path inside the git dir (e.g. 'hooks/prepare-commit-msg').

    Uses `git rev-parse --git-path`, which handles subdirectories, worktrees,
    submodules, and core.hooksPath.
    """
    repo = _require_repo()
    # GitPython runs git in the working tree, so relative output is relative to it
    return Path(repo.working_dir) / str(repo.git.rev_parse("--git-path", name))


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


def get_staged_diff(max_chars: int = 400_000) -> str:
    """Get staged diff; if over max_chars, truncate it and append the --stat."""
    repo = get_repo()
    if not repo:
        return ""

    try:
        diff = str(repo.git.diff("--cached", "--no-color", "-U3"))
        if len(diff) <= max_chars:
            return diff

        stat = repo.git.diff("--cached", "--stat")
        return f"{diff[:max_chars]}\n\n[Diff truncated at {max_chars} characters. Full stat:]\n{stat}"
    except GitCommandError:
        return ""


def get_recent_subjects(n: int = 10) -> list[str]:
    """Get the subjects of the last n commits (empty in a new repo)."""
    repo = get_repo()
    if not repo:
        return []

    try:
        return str(repo.git.log(f"-{n}", "--format=%s")).splitlines()
    except GitCommandError:
        return []


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


def read_commit_msg(path: str | Path) -> str | None:
    """Read commit message file."""
    try:
        return Path(path).read_text()
    except FileNotFoundError:
        return None


def write_commit_msg(path: str | Path, content: str) -> None:
    """Write commit message file."""
    Path(path).write_text(content)


def format_commit_message(title: str, summary: list[str]) -> str:
    """Format complete commit message with title and summary."""
    if not summary:
        return title

    lines = [title, ""]
    for point in summary:
        # Keep items that are already bullets (including indented sub-bullets)
        if point.lstrip().startswith(("- ", "* ", "• ")):
            lines.append(point)
        else:
            lines.append(f"- {point}")

    return "\n".join(lines)


def install_git_hook(titles: int = 3, force: bool = False) -> Path:
    """
    Install git prepare-commit-msg hook.

    Refuses to overwrite a hook not written by Pithy unless force is set.

    Returns:
        Path to installed hook
    """
    hook_path = git_path("hooks/prepare-commit-msg")

    existing = read_commit_msg(hook_path)
    if existing is not None and HOOK_MARKER not in existing and not force:
        raise ValueError(
            f"A prepare-commit-msg hook already exists at {hook_path}. "
            "Use --force to replace it."
        )

    hook_path.parent.mkdir(parents=True, exist_ok=True)

    hook_content = f"""#!/bin/sh
{HOOK_MARKER}

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


def uninstall_git_hook() -> Path | None:
    """
    Uninstall the Pithy prepare-commit-msg hook.

    Returns:
        Path to uninstalled hook, or None if no Pithy hook was found
    """
    hook_path = git_path("hooks/prepare-commit-msg")

    existing = read_commit_msg(hook_path)
    if existing is not None and HOOK_MARKER in existing:
        hook_path.unlink()
        return hook_path

    return None
