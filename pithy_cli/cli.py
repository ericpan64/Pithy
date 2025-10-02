import typer

from .init import run_init
from .ai_commit import run_ai_commit, AiCommitAction

app = typer.Typer()

@app.command()
def init() -> None:
    typer.echo("Running `init`")
    run_init()

@app.command(name="ai-commit")
def ai_commit(action: AiCommitAction) -> None:
    typer.echo("Running `ai-commit`")
    run_ai_commit(action)

if __name__ == "__main__":
    app()
