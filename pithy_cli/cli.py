import typer
from typing import Optional, List, Callable
from functools import wraps

from .init import run_init
from .ai_commit import run_ai_commit
from .keys import set_key, get_key, list_keys, remove_key, unlock, lock, migrate_legacy_keys, list_providers
from .summarize import run_summarize
from .prompts import add_prompt, list_prompts, improve_prompt


def handle_errors(func: Callable) -> Callable:
    """Decorator to handle errors consistently across all commands."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)
    return wrapper

app = typer.Typer()
keys_app = typer.Typer()
ai_commit_app = typer.Typer()
prompts_app = typer.Typer()

app.add_typer(keys_app, name="keys", help="Key management commands")
app.add_typer(ai_commit_app, name="ai-commit", help="AI-powered commit messages")
app.add_typer(prompts_app, name="prompts", help="Saved prompts management")

@app.command()
@handle_errors
def init() -> None:
    typer.echo("Running `init`")
    run_init()


@app.command()
@handle_errors
def summarize(
    path: str = typer.Argument(".", help="File or directory to summarize"),
    exclude: List[str] = typer.Option(None, "--exclude", "-x", help="Glob patterns to exclude"),
    depth: int = typer.Option(-1, "--depth", help="Max recursion depth (-1 = unlimited)"),
    force: bool = typer.Option(False, "--force", help="Regenerate even if up-to-date"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show actions without writing"),
    max_file_bytes: int = typer.Option(120_000, "--max-file-bytes", help="Read limit per file"),
    quiet: bool = typer.Option(False, "--quiet", help="Reduce output"),
    include_ignored: bool = typer.Option(False, "--include-ignored", help="Process gitignored files"),
) -> None:
    """Generate structured markdown summaries of files and directories."""
    run_summarize(
        target=path,
        excludes=exclude or [],
        depth=depth,
        force=force,
        dry_run=dry_run,
        max_file_bytes=max_file_bytes,
        quiet=quiet,
        include_ignored=include_ignored,
    )


# AI Commit commands

@ai_commit_app.command()
@handle_errors
def install(
    titles: int = typer.Option(3, "--titles", "-n", help="Number of title options to generate"),
) -> None:
    """Install git hook for AI commit messages."""
    run_ai_commit("install", titles=titles)

@ai_commit_app.command()
@handle_errors
def uninstall() -> None:
    """Uninstall git hook."""
    run_ai_commit("uninstall")

@ai_commit_app.command()
@handle_errors
def hook(
    file: str = typer.Argument(..., help="Commit message file"),
    source: Optional[str] = typer.Option(None, "--source", help="Commit source"),
    titles: int = typer.Option(3, "--titles", help="Number of titles"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Non-interactive mode"),
) -> None:
    """Hook handler (internal use by git)."""
    run_ai_commit("hook", file=file, source=source, titles=titles, non_interactive=non_interactive)

@ai_commit_app.command()
@handle_errors
def generate(
    titles: int = typer.Option(3, "--titles", "-n", help="Number of title options"),
    apply: bool = typer.Option(False, "--apply", help="Write to COMMIT_EDITMSG"),
    json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate commit message manually."""
    run_ai_commit("generate", titles=titles, apply=apply, json=json)

# Prompts commands

@prompts_app.command()
@handle_errors
def add(
    prompt_name: str = typer.Argument(..., help="Name of the prompt"),
    prompt_text: str = typer.Argument(..., help="Content of the prompt"),
) -> None:
    """Add a new version of a prompt."""
    add_prompt(prompt_name, prompt_text)

@prompts_app.command("list")
@handle_errors
def list_prompts_cmd() -> None:
    """List all saved prompts."""
    list_prompts()

@prompts_app.command()
@handle_errors
def improve(
    prompt_name: str = typer.Argument(..., help="Name of the prompt to improve"),
    suggestions: str = typer.Argument(..., help="Suggestions for improvement"),
) -> None:
    """Improve an existing prompt using AI."""
    improve_prompt(prompt_name, suggestions)

# Keys commands

@keys_app.command()
@handle_errors
def set(name: str, value: Optional[str] = None) -> None:
    """Set a key."""
    set_key(name, value)

@keys_app.command()
@handle_errors
def get(name: str) -> None:
    """Get a key."""
    value = get_key(name)
    if value:
        typer.echo(value)
    else:
        typer.echo(f"Key '{name}' not found", err=True)
        raise typer.Exit(1)

@keys_app.command("list")
@handle_errors
def list_keys_cmd() -> None:
    """List all keys."""
    list_keys()

@keys_app.command()
@handle_errors
def remove(name: str) -> None:
    """Remove a key."""
    remove_key(name)

@keys_app.command("unlock")
@handle_errors
def unlock_cmd(ttl: float = 8.0) -> None:
    """Unlock keystore."""
    unlock(ttl)

@keys_app.command("lock")
@handle_errors
def lock_cmd() -> None:
    """Lock keystore."""
    lock()

@keys_app.command("migrate")
@handle_errors
def migrate_cmd() -> None:
    """Migrate legacy key names to new standard format."""
    migrate_legacy_keys()

@keys_app.command("providers")
@handle_errors
def providers_cmd() -> None:
    """List all providers and their key status."""
    from rich.console import Console
    console = Console()

    providers = list_providers()
    console.print("\n[bold]Provider Status:[/bold]")
    for provider, has_key in providers.items():
        status = "[green]✓[/green]" if has_key else "[dim]✗[/dim]"
        console.print(f"  {status} {provider.value}")

if __name__ == "__main__":
    app()
