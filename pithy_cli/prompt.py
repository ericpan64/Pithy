"""Prompt management for Pithy CLI."""

import os
import re
import subprocess
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.syntax import Syntax

from .init import find_git_root

# Constants
DEFAULT_PROMPTS_DIR = Path(__file__).parent / "default_prompts"
PITHY_PROMPTS_SUBDIR = "prompts"

PROMPT_NAMES = [
    "commit-summary",
    "commit-titles",
    "file-summary",
]

# Meta-prompt for AI-assisted iteration
ITERATE_PROMPT = """You are a prompt engineering expert. Improve the following prompt based on the user's instruction.

CURRENT PROMPT:
```
{current_prompt}
```

IMPROVEMENT INSTRUCTION:
{instruction}

REQUIREMENTS:
- Preserve all variable placeholders exactly as written (e.g., {{diff}}, {{repo_name}})
- Make targeted improvements based on the instruction
- Keep the prompt clear and unambiguous for LLMs
- Maintain the same output format requirements if present

Return ONLY the improved prompt text, no explanations or markdown fences."""

console = Console()


# ============================================================================
# Pure Functions
# ============================================================================


def get_prompts_dir(git_root: Path) -> Path:
    """Return path to .pithy/prompts/ for a given git root."""
    return git_root / ".pithy" / PITHY_PROMPTS_SUBDIR


def list_prompt_files(prompts_dir: Path) -> list[Path]:
    """List all .md files in a prompts directory."""
    if not prompts_dir.exists():
        return []
    return sorted(prompts_dir.glob("*.md"))


def list_prompt_names(prompts_dir: Path) -> list[str]:
    """List available prompt names (without .md extension) in a directory."""
    return [f.stem for f in list_prompt_files(prompts_dir)]


def load_prompt_from_file(file_path: Path) -> str:
    """Load prompt content from a file."""
    return file_path.read_text(encoding="utf-8")


def load_prompt(name: str, git_root: Optional[Path] = None) -> str:
    """
    Load prompt content by name.

    Resolution order:
    1. .pithy/prompts/<name>.md (if git_root provided and file exists)
    2. pithy_cli/default_prompts/<name>.md (bundled fallback)

    Raises FileNotFoundError if prompt doesn't exist in either location.
    """
    # Try local first
    if git_root is not None:
        local_path = get_prompts_dir(git_root) / f"{name}.md"
        if local_path.exists():
            return load_prompt_from_file(local_path)

    # Fall back to bundled defaults
    default_path = DEFAULT_PROMPTS_DIR / f"{name}.md"
    if default_path.exists():
        return load_prompt_from_file(default_path)

    raise FileNotFoundError(f"Prompt '{name}' not found")


def save_prompt(name: str, content: str, prompts_dir: Path) -> Path:
    """
    Save prompt content to .pithy/prompts/<name>.md

    Creates prompts_dir if it doesn't exist.
    Returns the path to the saved file.
    """
    prompts_dir.mkdir(parents=True, exist_ok=True)
    file_path = prompts_dir / f"{name}.md"
    file_path.write_text(content, encoding="utf-8")
    return file_path


def copy_default_prompts(target_dir: Path) -> list[str]:
    """
    Copy all default prompts to target directory.

    Returns list of prompt names that were copied.
    Skips prompts that already exist in target_dir.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = []

    for default_file in DEFAULT_PROMPTS_DIR.glob("*.md"):
        target_file = target_dir / default_file.name
        if not target_file.exists():
            content = default_file.read_text(encoding="utf-8")
            target_file.write_text(content, encoding="utf-8")
            copied.append(default_file.stem)

    return copied


def validate_prompt_name(name: str) -> bool:
    """Validate prompt name: lowercase, alphanumeric, hyphens only."""
    return bool(re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$", name))


def get_editor() -> str:
    """Return user's preferred editor from $EDITOR, $VISUAL, or fallback to 'vim'."""
    return os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vim"


def open_in_editor(file_path: Path) -> int:
    """Open file in user's editor. Returns editor exit code."""
    editor = get_editor()
    result = subprocess.run([editor, str(file_path)])
    return result.returncode


def generate_improved_prompt(current_prompt: str, instruction: str) -> str:
    """
    Use LLM to generate an improved version of the prompt.

    Returns the improved prompt text.
    """
    # Import here to avoid circular dependency
    from .keys import get_api_key, LLMProvider
    from .llm import create_llm_client, ModelType

    # Get API key (try Anthropic first, then OpenAI)
    api_key = get_api_key(LLMProvider.ANTHROPIC)
    provider = LLMProvider.ANTHROPIC

    if not api_key:
        api_key = get_api_key(LLMProvider.OPENAI)
        provider = LLMProvider.OPENAI

    if not api_key:
        raise RuntimeError("No API key configured. Run 'pithy keys set' first.")

    client = create_llm_client(provider, api_key, ModelType.REGULAR)

    prompt = ITERATE_PROMPT.format(
        current_prompt=current_prompt,
        instruction=instruction,
    )

    return client.complete(prompt, max_tokens=2000)


def show_diff(old: str, new: str) -> None:
    """Display a colorized diff between old and new content."""
    import difflib

    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)

    diff = difflib.unified_diff(old_lines, new_lines, fromfile="current", tofile="improved")

    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            console.print(line.rstrip(), style="green")
        elif line.startswith("-") and not line.startswith("---"):
            console.print(line.rstrip(), style="red")
        elif line.startswith("@@"):
            console.print(line.rstrip(), style="cyan")
        else:
            console.print(line.rstrip())


# ============================================================================
# CLI Commands
# ============================================================================

prompt_app = typer.Typer()


def _require_git_root() -> Path:
    """Get git root or exit with error."""
    git_root = find_git_root()
    if git_root is None:
        console.print("❌ Not in a git repository.", style="red")
        console.print("💡 Run 'git init' first, then 'pithy init'.", style="dim")
        raise typer.Exit(1)
    return git_root


@prompt_app.command("new")
def prompt_new(
    name: Optional[str] = typer.Option(None, "-n", "--name", help="Prompt name"),
) -> None:
    """Create a new prompt template."""
    git_root = _require_git_root()
    prompts_dir = get_prompts_dir(git_root)

    # Get name interactively if not provided
    if name is None:
        name = typer.prompt("Prompt name (lowercase, hyphens allowed)")

    # Validate name
    if not validate_prompt_name(name):
        console.print(
            f"❌ Invalid name '{name}'. Use lowercase letters, numbers, and hyphens.",
            style="red",
        )
        raise typer.Exit(1)

    # Check if already exists
    file_path = prompts_dir / f"{name}.md"
    if file_path.exists():
        console.print(f"❌ Prompt '{name}' already exists at {file_path}", style="red")
        console.print("💡 Use 'pithy prompt edit' to modify it.", style="dim")
        raise typer.Exit(1)

    # Create starter template
    starter_content = f"""# {name}

Write your prompt here.

Use {{variable_name}} for template variables that will be filled in at runtime.
"""

    prompts_dir.mkdir(parents=True, exist_ok=True)
    file_path.write_text(starter_content, encoding="utf-8")

    console.print(f"📝 Created {file_path}", style="green")
    console.print("Opening in editor...", style="dim")

    exit_code = open_in_editor(file_path)
    if exit_code == 0:
        console.print(f"✨ Prompt '{name}' saved.", style="green")
    else:
        console.print(f"⚠️  Editor exited with code {exit_code}", style="yellow")


@prompt_app.command("list")
def prompt_list() -> None:
    """List all available prompts."""
    git_root = _require_git_root()
    prompts_dir = get_prompts_dir(git_root)

    local_prompts = set(list_prompt_names(prompts_dir))
    default_prompts = set(list_prompt_names(DEFAULT_PROMPTS_DIR))

    all_prompts = sorted(local_prompts | default_prompts)

    if not all_prompts:
        console.print("No prompts found.", style="dim")
        console.print("💡 Run 'pithy prompt new' to create one.", style="dim")
        return

    console.print("\n[bold]Available Prompts:[/bold]")

    for name in all_prompts:
        is_local = name in local_prompts
        is_default = name in default_prompts

        if is_local and is_default:
            status = "[green]✓[/green] (local override)"
        elif is_local:
            status = "[blue]•[/blue] (local)"
        else:
            status = "[dim]○[/dim] (default)"

        console.print(f"  {status} {name}")

    console.print()


@prompt_app.command("show")
def prompt_show(
    name: str = typer.Argument(..., help="Prompt name"),
) -> None:
    """Display prompt content."""
    git_root = _require_git_root()

    try:
        content = load_prompt(name, git_root)
    except FileNotFoundError:
        console.print(f"❌ Prompt '{name}' not found.", style="red")
        console.print("💡 Run 'pithy prompt list' to see available prompts.", style="dim")
        raise typer.Exit(1)

    # Show with syntax highlighting
    syntax = Syntax(content, "markdown", theme="monokai", line_numbers=True)
    console.print(syntax)


@prompt_app.command("edit")
def prompt_edit(
    name: str = typer.Argument(..., help="Prompt name"),
) -> None:
    """Edit a prompt in your default editor."""
    git_root = _require_git_root()
    prompts_dir = get_prompts_dir(git_root)
    local_path = prompts_dir / f"{name}.md"

    # If doesn't exist locally, try to copy from defaults
    if not local_path.exists():
        default_path = DEFAULT_PROMPTS_DIR / f"{name}.md"
        if default_path.exists():
            prompts_dir.mkdir(parents=True, exist_ok=True)
            content = default_path.read_text(encoding="utf-8")
            local_path.write_text(content, encoding="utf-8")
            console.print(f"📋 Copied default prompt to {local_path}", style="dim")
        else:
            console.print(f"❌ Prompt '{name}' not found.", style="red")
            console.print("💡 Run 'pithy prompt new -n {name}' to create it.", style="dim")
            raise typer.Exit(1)

    console.print(f"Opening {local_path}...", style="dim")
    exit_code = open_in_editor(local_path)

    if exit_code == 0:
        console.print(f"✨ Prompt '{name}' saved.", style="green")
    else:
        console.print(f"⚠️  Editor exited with code {exit_code}", style="yellow")


@prompt_app.command("iter")
def prompt_iter(
    name: str = typer.Argument(..., help="Prompt name"),
    instruction: str = typer.Argument(..., help="How to improve the prompt"),
) -> None:
    """Iterate on a prompt using AI assistance."""
    git_root = _require_git_root()
    prompts_dir = get_prompts_dir(git_root)

    # Load current prompt
    try:
        current_content = load_prompt(name, git_root)
    except FileNotFoundError:
        console.print(f"❌ Prompt '{name}' not found.", style="red")
        console.print("💡 Run 'pithy prompt list' to see available prompts.", style="dim")
        raise typer.Exit(1)

    console.print(f"🤖 Improving prompt '{name}'...", style="dim")

    try:
        improved_content = generate_improved_prompt(current_content, instruction)
    except RuntimeError as e:
        console.print(f"❌ {e}", style="red")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"❌ LLM error: {e}", style="red")
        raise typer.Exit(1)

    # Clean up response (remove any markdown fences the LLM might have added)
    improved_content = improved_content.strip()
    if improved_content.startswith("```") and improved_content.endswith("```"):
        lines = improved_content.split("\n")
        improved_content = "\n".join(lines[1:-1])

    # Show diff
    console.print("\n[bold]Proposed changes:[/bold]\n")
    show_diff(current_content, improved_content)

    # Prompt for action
    console.print()
    action = typer.prompt(
        "Apply changes?",
        type=str,
        default="n",
        show_default=False,
        prompt_suffix=" [y/n/e(dit)] ",
    )

    action = action.lower().strip()

    if action in ("y", "yes"):
        save_prompt(name, improved_content, prompts_dir)
        console.print(f"✨ Prompt '{name}' updated.", style="green")
    elif action in ("e", "edit"):
        # Save improved version and open in editor for manual tweaking
        save_prompt(name, improved_content, prompts_dir)
        console.print("Opening in editor for manual adjustments...", style="dim")
        local_path = prompts_dir / f"{name}.md"
        open_in_editor(local_path)
        console.print(f"✨ Prompt '{name}' updated.", style="green")
    else:
        console.print("Discarded changes.", style="dim")

