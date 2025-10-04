import typer
from typing import Optional

from .init import run_init
from .ai_commit import run_ai_commit
from .keys import set_key, get_key, list_keys, remove_key, unlock, lock, migrate_legacy_keys, list_providers

app = typer.Typer()
keys_app = typer.Typer()
ai_commit_app = typer.Typer()

app.add_typer(keys_app, name="keys", help="Key management commands")
app.add_typer(ai_commit_app, name="ai-commit", help="AI-powered commit messages")

@app.command()
def init() -> None:
    typer.echo("Running `init`")
    run_init()

# AI Commit commands

@ai_commit_app.command()
def install(
    titles: int = typer.Option(3, "--titles", "-n", help="Number of title options to generate"),
) -> None:
    """Install git hook for AI commit messages."""
    try:
        run_ai_commit("install", titles=titles)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@ai_commit_app.command()
def uninstall() -> None:
    """Uninstall git hook."""
    try:
        run_ai_commit("uninstall")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@ai_commit_app.command()
def hook(
    file: str = typer.Argument(..., help="Commit message file"),
    source: Optional[str] = typer.Option(None, "--source", help="Commit source"),
    titles: int = typer.Option(3, "--titles", help="Number of titles"),
    non_interactive: bool = typer.Option(False, "--non-interactive", help="Non-interactive mode"),
) -> None:
    """Hook handler (internal use by git)."""
    try:
        run_ai_commit("hook", file=file, source=source, titles=titles, non_interactive=non_interactive)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@ai_commit_app.command()
def generate(
    titles: int = typer.Option(3, "--titles", "-n", help="Number of title options"),
    apply: bool = typer.Option(False, "--apply", help="Write to COMMIT_EDITMSG"),
    json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Generate commit message manually."""
    try:
        run_ai_commit("generate", titles=titles, apply=apply, json=json)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@keys_app.command()
def set(name: str, value: Optional[str] = None) -> None:
    """Set a key."""
    try:
        set_key(name, value)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@keys_app.command()
def get(name: str) -> None:
    """Get a key."""
    try:
        value = get_key(name)
        if value:
            typer.echo(value)
        else:
            typer.echo(f"Key '{name}' not found", err=True)
            raise typer.Exit(1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@keys_app.command("list")
def list_keys_cmd() -> None:
    """List all keys."""
    try:
        list_keys()
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@keys_app.command()
def remove(name: str) -> None:
    """Remove a key."""
    try:
        remove_key(name)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@keys_app.command("unlock")
def unlock_cmd(ttl: float = 8.0) -> None:
    """Unlock keystore."""
    try:
        unlock(ttl)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@keys_app.command("lock")
def lock_cmd() -> None:
    """Lock keystore."""
    try:
        lock()
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@keys_app.command("migrate")
def migrate_cmd() -> None:
    """Migrate legacy key names to new standard format."""
    try:
        migrate_legacy_keys()
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

@keys_app.command("providers")
def providers_cmd() -> None:
    """List all providers and their key status."""
    try:
        from rich.console import Console
        console = Console()

        providers = list_providers()
        console.print("\n[bold]Provider Status:[/bold]")
        for provider, has_key in providers.items():
            status = "[green]✓[/green]" if has_key else "[dim]✗[/dim]"
            console.print(f"  {status} {provider.value}")
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
