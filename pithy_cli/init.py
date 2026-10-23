from pathlib import Path

import typer

PRE_COMMIT_CONFIG = """\
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: detect-private-key
"""


def find_git_root(start_path: Path | None = None) -> Path | None:
    """
    Find the git repository root by looking for .git directory.

    Args:
        start_path: Path to start searching from. Defaults to current directory.

    Returns:
        Path to git repository root, or None if not in a git repository.
    """
    if start_path is None:
        start_path = Path.cwd()

    current = start_path.resolve()

    # Traverse up the directory tree
    while current != current.parent:
        git_dir = current / ".git"
        if git_dir.exists():
            return current
        current = current.parent

    return None


def read_gitignore(git_root: Path) -> list[str]:
    """
    Read existing .gitignore file and return lines as list.

    Args:
        git_root: Path to git repository root

    Returns:
        List of lines from .gitignore file, empty list if file doesn't exist
    """
    gitignore_path = git_root / ".gitignore"

    if not gitignore_path.exists():
        return []

    try:
        with open(gitignore_path, encoding="utf-8") as f:
            return f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return []


def update_gitignore(
    git_root: Path, entries_to_add: list[str]
) -> tuple[list[str], bool]:
    """
    Update .gitignore file with new entries, avoiding duplicates.

    Args:
        git_root: Path to git repository root
        entries_to_add: List of gitignore patterns to add

    Returns:
        Tuple of (newly_added_entries, was_modified)
    """
    gitignore_path = git_root / ".gitignore"
    existing_lines = read_gitignore(git_root)

    # Normalize existing entries (strip whitespace for comparison)
    existing_normalized = {line.strip() for line in existing_lines if line.strip()}

    # Find entries that don't already exist
    new_entries = []
    for entry in entries_to_add:
        if entry.strip() not in existing_normalized:
            new_entries.append(entry)

    if not new_entries:
        return [], False

    # Prepare content to write
    content_lines = existing_lines.copy()

    # Add newline before new entries if file doesn't end with newline
    if content_lines and not content_lines[-1] == "":
        content_lines.append("")

    # Add new entries
    content_lines.extend(new_entries)

    # Write updated content
    try:
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write("\n".join(content_lines) + "\n")
        return new_entries, True
    except OSError:
        return [], False


def create_pre_commit_config(git_root: Path) -> bool:
    """
    Create .pre-commit-config.yaml at git repository root if it doesn't exist.

    Args:
        git_root: Path to git repository root

    Returns:
        True if file was created, False if it already exists
    """
    config_path = git_root / ".pre-commit-config.yaml"

    if config_path.exists():
        return False

    try:
        config_path.write_text(PRE_COMMIT_CONFIG, encoding="utf-8")
        return True
    except OSError:
        return False


def run_init() -> None:
    """
    Initialize Pithy CLI configuration for a git repository.

    This function:
    1. Finds the git repository root
    2. Creates .pre-commit-config.yaml
    3. Updates .gitignore with required entries
    4. Reports actions taken to user
    """
    # Find git repository root
    git_root = find_git_root()

    if git_root is None:
        typer.echo("❌ Error: Not in a git repository.", err=True)
        typer.echo(
            "💡 Hint: Run 'git init' to initialize a git repository first.", err=True
        )
        raise typer.Exit(1)

    typer.echo(f"📍 Found git repository at: {git_root}")

    # Create pre-commit config
    if create_pre_commit_config(git_root):
        typer.echo("📝 Created .pre-commit-config.yaml with default hooks")
        typer.echo("   💡 Run 'pre-commit install' to activate hooks")
    else:
        typer.echo("✅ .pre-commit-config.yaml already exists")

    # Update .gitignore
    required_entries = [".pithy/", ".DS_Store"]

    added_entries, was_modified = update_gitignore(git_root, required_entries)

    if was_modified:
        if added_entries:
            typer.echo("📝 Updated .gitignore with new entries:")
            for entry in added_entries:
                typer.echo(f"  + {entry}")
        else:
            typer.echo("📝 Updated .gitignore")
    else:
        typer.echo("✅ .gitignore already contains all required entries")

    typer.echo("✨ Pithy initialization complete!")
