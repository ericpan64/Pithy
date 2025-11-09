"""Prompt management feature for Pithy CLI."""

from pathlib import Path
from typing import List, Tuple, Optional
import typer
from rich.console import Console
from rich.table import Table

from .init import find_git_root, ensure_pithy_directory
from .ai_commit import get_provider_config
from .llm import create_llm_client

console = Console()


def ensure_prompts_directory(git_root: Path) -> Path:
    """
    Create .pithy/prompts directory if it doesn't exist.

    Args:
        git_root: Path to git repository root

    Returns:
        Path to prompts directory
    """
    pithy_dir = ensure_pithy_directory(git_root)
    prompts_dir = pithy_dir / "prompts"
    prompts_dir.mkdir(exist_ok=True)
    return prompts_dir


def get_prompt_directory(prompts_dir: Path, prompt_name: str) -> Path:
    """
    Get or create directory for a specific prompt.

    Args:
        prompts_dir: Path to prompts directory
        prompt_name: Name of the prompt

    Returns:
        Path to prompt's directory
    """
    prompt_dir = prompts_dir / prompt_name
    return prompt_dir


def get_latest_version(prompt_dir: Path) -> int:
    """
    Get the latest version number for a prompt.

    Args:
        prompt_dir: Path to prompt's directory

    Returns:
        Latest version number (0 if no versions exist)
    """
    if not prompt_dir.exists():
        return 0

    versions = []
    for file in prompt_dir.iterdir():
        if file.is_file() and file.name.startswith("v") and file.suffix == ".txt":
            try:
                version = int(file.stem[1:])  # Remove 'v' prefix
                versions.append(version)
            except ValueError:
                continue

    return max(versions) if versions else 0


def get_prompt_content(prompt_dir: Path, version: Optional[int] = None) -> Optional[str]:
    """
    Read prompt content from a specific version.

    Args:
        prompt_dir: Path to prompt's directory
        version: Version number (None for latest)

    Returns:
        Prompt content or None if not found
    """
    if not prompt_dir.exists():
        return None

    if version is None:
        version = get_latest_version(prompt_dir)

    if version == 0:
        return None

    version_file = prompt_dir / f"v{version}.txt"
    if not version_file.exists():
        return None

    return version_file.read_text(encoding="utf-8")


def save_prompt_version(prompt_dir: Path, content: str) -> int:
    """
    Save a new version of a prompt.

    Args:
        prompt_dir: Path to prompt's directory
        content: Prompt content to save

    Returns:
        Version number of saved prompt
    """
    prompt_dir.mkdir(parents=True, exist_ok=True)

    latest_version = get_latest_version(prompt_dir)
    new_version = latest_version + 1

    version_file = prompt_dir / f"v{new_version}.txt"
    version_file.write_text(content, encoding="utf-8")

    return new_version


def list_all_prompts(prompts_dir: Path) -> List[Tuple[str, int]]:
    """
    List all prompts with their version counts.

    Args:
        prompts_dir: Path to prompts directory

    Returns:
        List of tuples (prompt_name, version_count)
    """
    if not prompts_dir.exists():
        return []

    prompts = []
    for item in prompts_dir.iterdir():
        if item.is_dir():
            latest_version = get_latest_version(item)
            if latest_version > 0:
                prompts.append((item.name, latest_version))

    return sorted(prompts)


def improve_prompt_with_ai(prompt_content: str, suggestions: str) -> str:
    """
    Use AI to improve a prompt based on suggestions.

    Args:
        prompt_content: Original prompt content
        suggestions: Suggestions for improvement

    Returns:
        Improved prompt content
    """
    provider, api_key = get_provider_config()
    client = create_llm_client(provider, api_key)

    improvement_prompt = f"""You are an expert prompt engineer. Improve the following prompt based on the user's suggestions.

ORIGINAL PROMPT:
```
{prompt_content}
```

USER SUGGESTIONS:
{suggestions}

REQUIREMENTS:
- Incorporate the user's suggestions thoughtfully
- Improve clarity, specificity, and effectiveness
- Maintain the core intent of the original prompt
- Return ONLY the improved prompt text, no explanations or meta-commentary
- Do NOT wrap the response in code fences or quotes

Improved prompt:"""

    with console.status("[bold green]Improving prompt with AI...", spinner="dots"):
        improved = client.complete(improvement_prompt, max_tokens=1000)

    # Clean up the response - remove any markdown formatting
    improved = improved.strip()
    if improved.startswith("```") and improved.endswith("```"):
        lines = improved.split("\n")
        if len(lines) > 2:
            improved = "\n".join(lines[1:-1]).strip()

    return improved


# Command implementations

def add_prompt(prompt_name: str, prompt_text: str) -> None:
    """
    Add a new version of a prompt.

    Args:
        prompt_name: Name of the prompt
        prompt_text: Content of the prompt
    """
    git_root = find_git_root()
    if git_root is None:
        console.print("[red]❌ Error: Not in a git repository.[/red]", err=True)
        console.print("[yellow]💡 Hint: Run 'git init' or navigate to a git repository.[/yellow]", err=True)
        raise typer.Exit(1)

    prompts_dir = ensure_prompts_directory(git_root)
    prompt_dir = get_prompt_directory(prompts_dir, prompt_name)

    version = save_prompt_version(prompt_dir, prompt_text)

    console.print(f"[green]✅ Saved prompt '{prompt_name}' as version {version}[/green]")
    console.print(f"[dim]   Location: {prompt_dir / f'v{version}.txt'}[/dim]")


def list_prompts() -> None:
    """List all saved prompts."""
    git_root = find_git_root()
    if git_root is None:
        console.print("[red]❌ Error: Not in a git repository.[/red]", err=True)
        console.print("[yellow]💡 Hint: Run 'git init' or navigate to a git repository.[/yellow]", err=True)
        raise typer.Exit(1)

    prompts_dir = ensure_prompts_directory(git_root)
    prompts = list_all_prompts(prompts_dir)

    if not prompts:
        console.print("[yellow]No prompts found.[/yellow]")
        console.print("[dim]Add a prompt with: pithy prompts add <name> \"prompt text\"[/dim]")
        return

    table = Table(title="Saved Prompts", show_header=True, header_style="bold cyan")
    table.add_column("Prompt Name", style="green")
    table.add_column("Versions", justify="right", style="yellow")
    table.add_column("Latest Version Preview", style="dim")

    for prompt_name, version_count in prompts:
        prompt_dir = get_prompt_directory(prompts_dir, prompt_name)
        content = get_prompt_content(prompt_dir)
        preview = content[:60] + "..." if content and len(content) > 60 else content or ""
        table.add_row(prompt_name, str(version_count), preview)

    console.print(table)
    console.print(f"\n[dim]Total: {len(prompts)} prompt(s)[/dim]")


def improve_prompt(prompt_name: str, suggestions: str) -> None:
    """
    Improve an existing prompt using AI.

    Args:
        prompt_name: Name of the prompt to improve
        suggestions: Suggestions for improvement
    """
    git_root = find_git_root()
    if git_root is None:
        console.print("[red]❌ Error: Not in a git repository.[/red]", err=True)
        console.print("[yellow]💡 Hint: Run 'git init' or navigate to a git repository.[/yellow]", err=True)
        raise typer.Exit(1)

    prompts_dir = ensure_prompts_directory(git_root)
    prompt_dir = get_prompt_directory(prompts_dir, prompt_name)

    # Get current version
    current_content = get_prompt_content(prompt_dir)
    if current_content is None:
        console.print(f"[red]❌ Error: Prompt '{prompt_name}' not found.[/red]", err=True)
        console.print("[dim]Use 'pithy prompts list' to see available prompts.[/dim]", err=True)
        raise typer.Exit(1)

    current_version = get_latest_version(prompt_dir)
    console.print(f"[cyan]📝 Improving prompt '{prompt_name}' (current: v{current_version})[/cyan]")

    try:
        # Use AI to improve the prompt
        improved_content = improve_prompt_with_ai(current_content, suggestions)

        # Save as new version
        new_version = save_prompt_version(prompt_dir, improved_content)

        console.print(f"[green]✅ Created improved version {new_version}[/green]")
        console.print(f"[dim]   Location: {prompt_dir / f'v{new_version}.txt'}[/dim]")

        # Show the improved prompt
        console.print("\n[bold]Improved prompt:[/bold]")
        console.print(f"[dim]{improved_content}[/dim]")

    except Exception as e:
        console.print(f"[red]❌ Error improving prompt: {e}[/red]", err=True)
        raise typer.Exit(1)
