import typer
from typing import Optional

from .init import run_init
from .ai_commit import run_ai_commit, AiCommitAction
from .keys import set_key, get_key, list_keys, remove_key, unlock, lock

app = typer.Typer()
keys_app = typer.Typer()
app.add_typer(keys_app, name="keys", help="Key management commands")

@app.command()
def init() -> None:
    typer.echo("Running `init`")
    run_init()

@app.command(name="ai-commit")
def ai_commit(action: AiCommitAction) -> None:
    typer.echo("Running `ai-commit`")
    run_ai_commit(action)

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

if __name__ == "__main__":
    app()
