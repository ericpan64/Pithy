import typer
from pathlib import Path
from typing import List, Tuple, Optional


def find_git_root(start_path: Path = None) -> Optional[Path]:
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


def ensure_pithy_directory(git_root: Path) -> Path:
    """
    Create .pithy directory at git repository root if it doesn't exist.

    Args:
        git_root: Path to git repository root

    Returns:
        Path to .pithy directory
    """
    pithy_dir = git_root / ".pithy"
    pithy_dir.mkdir(exist_ok=True)
    return pithy_dir


def read_gitignore(git_root: Path) -> List[str]:
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
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            return f.read().splitlines()
    except (OSError, UnicodeDecodeError):
        return []


def update_gitignore(git_root: Path, entries_to_add: List[str]) -> Tuple[List[str], bool]:
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
        with open(gitignore_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content_lines) + '\n')
        return new_entries, True
    except OSError:
        return [], False


def run_init() -> None:
    """
    Initialize Pithy CLI configuration for a git repository.

    This function:
    1. Finds the git repository root
    2. Creates .pithy directory
    3. Copies default prompts to .pithy/prompts/
    4. Updates .gitignore with required entries
    5. Reports actions taken to user
    """
    # Import here to avoid circular dependency
    from .prompt import copy_default_prompts, get_prompts_dir

    # Find git repository root
    git_root = find_git_root()

    if git_root is None:
        typer.echo("❌ Error: Not in a git repository.", err=True)
        typer.echo("💡 Hint: Run 'git init' to initialize a git repository first.", err=True)
        raise typer.Exit(1)

    typer.echo(f"📍 Found git repository at: {git_root}")

    # Create .pithy directory
    pithy_dir = ensure_pithy_directory(git_root)
    if pithy_dir.exists():
        typer.echo(f"📁 Ensured .pithy directory exists at: {pithy_dir}")

    # Copy default prompts
    prompts_dir = get_prompts_dir(git_root)
    copied = copy_default_prompts(prompts_dir)
    if copied:
        typer.echo(f"📝 Copied default prompts: {', '.join(copied)}")
    else:
        typer.echo("✅ Prompts directory ready (defaults already present)")

    # Update .gitignore
    required_entries = [
        ".pithy/",
        ".DS_Store",
        ".specstory/",
        ".cursor*",
        ".claude*"
    ]

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
