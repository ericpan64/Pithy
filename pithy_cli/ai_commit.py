"""AI-powered git commit message generation."""

import json
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console

from .git import (
    format_commit_message,
    format_summary,
    get_branch_name,
    get_recent_subjects,
    get_repo_name,
    get_staged_diff,
    has_staged_changes,
)
from .llm import resolve_client
from .skills import load_skill

status_console = Console(stderr=True)

COMMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "array", "items": {"type": "string"}},
        "titles": {"type": "array", "items": {"type": "string"}, "minItems": 1},
    },
    "required": ["summary", "titles"],
    "additionalProperties": False,
}

# prepare-commit-msg sources that already have a message
SKIP_SOURCES = {"merge", "squash", "commit", "message"}


@dataclass
class CommitMessage:
    """Generated commit message."""

    summary: list[str]
    titles: list[str]


def build_commit_input(titles_count: int) -> str:
    """Build the user message: repo context, recent subjects, and staged diff."""
    subjects = "\n".join(f"- {s}" for s in get_recent_subjects()) or "(none)"
    return (
        f"Repository: {get_repo_name()}\n"
        f"Branch: {get_branch_name()}\n"
        f"Number of titles: {titles_count}\n\n"
        f"Recent commit subjects:\n{subjects}\n\n"
        f"Staged changes (git diff):\n```\n{get_staged_diff()}\n```"
    )


def generate_commit_message(titles_count: int = 1) -> CommitMessage:
    """Generate a summary and title options from staged changes in one call."""
    if not has_staged_changes():
        raise ValueError("No staged changes detected")

    skill = load_skill("commit-message")
    client = resolve_client(skill.model_type)

    with status_console.status("Generating commit message...", spinner="dots"):
        response = client.complete(
            skill.body,
            build_commit_input(titles_count),
            max_tokens=2000,
            schema=COMMIT_SCHEMA,
        )

    data = json.loads(response)
    if not data["titles"]:
        raise ValueError("Model returned no commit titles")
    return CommitMessage(summary=data["summary"], titles=data["titles"][:titles_count])


def run_hook(file: str, source: str | None = None) -> None:
    """
    prepare-commit-msg handler: prepend a generated message to the commit file.

    git then opens the editor on it for review. Errors are reported but never
    block the commit.
    """
    if source in SKIP_SOURCES or not has_staged_changes():
        return

    try:
        message = generate_commit_message()
        path = Path(file)
        existing = path.read_text() if path.exists() else ""
        text = format_commit_message(message.titles[0], message.summary)
        path.write_text(f"{text}\n{existing}")
    except Exception as e:
        status_console.print(f"[red]Pithy: could not generate a message: {e}[/red]")


def run_generate(titles: int = 3, json_output: bool = False) -> None:
    """Print title options and a summary for the staged changes."""
    message = generate_commit_message(titles_count=titles)

    if json_output:
        typer.echo(json.dumps({"summary": message.summary, "titles": message.titles}))
        return

    for i, title in enumerate(message.titles, 1):
        typer.echo(f"{i}. {title}")
    typer.echo("")
    typer.echo(format_summary(message.summary))
