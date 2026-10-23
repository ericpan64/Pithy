import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from . import ai_commit, git, keys, skills
from .init import run_init
from .summarize import run_summarize

app = typer.Typer()
keys_app = typer.Typer()
ai_commit_app = typer.Typer()
skills_app = typer.Typer()

app.add_typer(keys_app, name="keys", help="API key management")
app.add_typer(ai_commit_app, name="ai-commit", help="AI-powered commit messages")
app.add_typer(skills_app, name="skills", help="Agent Skills management")

console = Console()


def _run(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a command body, turning unexpected errors into 'Error: ...' + exit 1."""
    try:
        return fn(*args, **kwargs)
    except (typer.Exit, typer.Abort):
        raise
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1) from e


@app.command()
def init() -> None:
    """Set up pre-commit config and .gitignore entries."""
    run_init()


@app.command()
def summarize(
    path: str = typer.Argument(".", help="File or directory to summarize"),
    output: str | None = typer.Option(
        None, "--output", "-o", help="Write to file (e.g. AGENTS.md)"
    ),
    exclude: list[str] = typer.Option(
        None, "--exclude", "-x", help="Glob patterns to exclude"
    ),
    max_chars: int = typer.Option(
        400_000, "--max-chars", help="Budget for file contents sent to the model"
    ),
) -> None:
    """Generate a markdown overview of a codebase."""
    _run(run_summarize, path, output, exclude or [], max_chars)


# AI Commit commands


@ai_commit_app.command()
def install(
    titles: int = typer.Option(
        3, "--titles", "-n", help="Number of title options to generate"
    ),
    force: bool = typer.Option(False, "--force", help="Replace an existing hook"),
) -> None:
    """Install git hook for AI commit messages."""
    hook_path = _run(git.install_git_hook, titles=titles, force=force)
    console.print(f"[green]✅ Git hook installed at:[/green] {hook_path}")


@ai_commit_app.command()
def uninstall() -> None:
    """Uninstall git hook."""
    hook_path = _run(git.uninstall_git_hook)
    if hook_path:
        console.print(f"[green]✅ Git hook uninstalled:[/green] {hook_path}")
    else:
        console.print("[yellow]ℹ Pithy hook not found[/yellow]")


@ai_commit_app.command()
def hook(
    file: str = typer.Argument(..., help="Commit message file"),
    source: str | None = typer.Option(None, "--source", help="Commit source"),
    titles: int = typer.Option(3, "--titles", help="Number of titles"),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help="Non-interactive mode"
    ),
) -> None:
    """Hook handler (internal use by git)."""
    ai_commit.run_hook(file, source, titles, non_interactive)


@ai_commit_app.command()
def generate(
    titles: int = typer.Option(3, "--titles", "-n", help="Number of title options"),
    apply: bool = typer.Option(False, "--apply", help="Write to COMMIT_EDITMSG"),
    json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate commit message manually."""
    ai_commit.run_generate(titles, apply, json)


# Key commands


@keys_app.command("set")
def keys_set(
    provider: str = typer.Argument(..., help="anthropic, openai, or together"),
    value: str | None = typer.Option(None, help="Key value (prompts if omitted)"),
) -> None:
    """Store a provider API key in the OS keychain."""
    _run(keys.set_key, provider, value)


@keys_app.command("remove")
def keys_remove(provider: str) -> None:
    """Remove a provider API key from the OS keychain."""
    _run(keys.remove_key, provider)


@keys_app.command("list")
def keys_list() -> None:
    """Show which providers have keys and where they come from."""
    status = _run(keys.key_status)
    console.print("\n[bold]Provider keys:[/bold]")
    for provider, where in status.items():
        mark = "[green]✓[/green]" if where else "[dim]✗[/dim]"
        console.print(
            f"  {mark} {provider}" + (f" [dim]({where})[/dim]" if where else "")
        )


# Skills commands


@skills_app.command("list")
def skills_list() -> None:
    """List built-in and project skills."""
    table = Table("Name", "Source", "Description")
    for name, (path, source) in _run(skills.discover).items():
        try:
            description = skills.parse_skill(path, source).description
        except Exception as e:
            description = f"[red]invalid: {e}[/red]"
        table.add_row(name, source, description)
    console.print(table)


@skills_app.command("new")
def skills_new(
    name: str = typer.Argument(..., help="Skill name (lowercase, hyphens)"),
    description: str = typer.Option(
        "", "--description", "-d", help="What the skill does and when to use it"
    ),
) -> None:
    """Create a skill in .agents/skills/ and open it in your editor."""
    skill_md = _run(skills.new_skill, name, description)
    console.print(f"📝 Created {skill_md}")
    _edit_and_validate(skill_md)


@skills_app.command("edit")
def skills_edit(name: str) -> None:
    """Edit a skill (copies a built-in into .agents/skills/ first)."""
    skill_md = _run(skills.edit_skill, name)
    _edit_and_validate(skill_md)


@skills_app.command("reset")
def skills_reset(name: str) -> None:
    """Delete the project override of a built-in skill."""
    _run(skills.override_path, name)  # fail before asking for confirmation
    typer.confirm(f"Delete your project override of '{name}'?", abort=True)
    path = _run(skills.reset_skill, name)
    console.print(f"✓ Removed {path}; using built-in '{name}'")


@skills_app.command("run")
def skills_run(
    name: str,
    paths: list[Path] = typer.Argument(None, help="Input files (default: stdin)"),
) -> None:
    """Run a skill on files or stdin and print the result."""
    if paths:
        user_input = "\n\n".join(
            skills.format_file(str(p), p.read_text(encoding="utf-8")) for p in paths
        )
    elif not sys.stdin.isatty():
        user_input = sys.stdin.read()
    else:
        typer.echo("Error: provide input files or pipe input on stdin", err=True)
        raise typer.Exit(1)

    typer.echo(_run(skills.run_skill, name, user_input))


def _edit_and_validate(skill_md: Path) -> None:
    exit_code = skills.open_in_editor(skill_md)
    if exit_code != 0:
        console.print(f"⚠️  Editor exited with code {exit_code}", style="yellow")
    try:
        skill = skills.parse_skill(skill_md.parent)
    except ValueError as e:
        console.print(f"⚠️  {e}", style="yellow")
        return
    console.print(f"✨ Skill '{skill.name}' saved.", style="green")


if __name__ == "__main__":
    app()
