"""AI-powered git commit message generation."""

import sys
from dataclasses import dataclass

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .git import (
    format_commit_message,
    get_branch_name,
    get_recent_subjects,
    get_repo,
    get_repo_name,
    get_staged_diff,
    git_path,
    has_staged_changes,
    read_commit_msg,
    write_commit_msg,
)
from .llm import complete_json, resolve_client
from .skills import load_skill

console = Console()
error_console = Console(file=sys.stderr)

COMMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "array", "items": {"type": "string"}},
        "titles": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "titles"],
    "additionalProperties": False,
}


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


def generate_commit_message(titles_count: int = 3) -> CommitMessage:
    """Generate a summary and title options from staged changes in one call."""
    if not has_staged_changes():
        raise ValueError("No staged changes detected")

    skill = load_skill("commit-message")
    client = resolve_client(skill.model_type)

    with console.status("[bold green]Generating commit message...", spinner="dots"):
        data = complete_json(
            client,
            skill.body,
            build_commit_input(titles_count),
            COMMIT_SCHEMA,
            max_tokens=2000,
        )

    return CommitMessage(summary=data["summary"], titles=data["titles"][:titles_count])


def interactive_selection(message: CommitMessage, existing: str = "") -> str | None:
    """
    Interactive commit message selection with rich UI.

    Returns:
        Selected commit title, or None if cancelled
    """
    console.print()
    console.print(
        Panel.fit(
            "🤖 [bold cyan]AI Commit Message Generator[/bold cyan]", border_style="cyan"
        )
    )

    # Show existing message if present
    if existing.strip():
        console.print("\n[yellow]📝 Existing commit message:[/yellow]")
        for line in existing.split("\n")[:5]:
            if not line.strip().startswith("#"):
                console.print(f"   {line}")

    # Show summary
    console.print("\n[bold]📋 Summary of changes:[/bold]")
    for point in message.summary:
        console.print(f"   • {point}", style="dim")

    # Show title options
    console.print("\n[bold]🎯 Select a commit message:[/bold]")
    for i, title in enumerate(message.titles, 1):
        console.print(f"   [cyan]{i}.[/cyan] {title}")

    console.print()

    # Interactive prompt
    while True:
        choice = Prompt.ask(
            "→ Select",
            choices=[str(i) for i in range(1, len(message.titles) + 1)] + ["e", "q"],
            default="1",
            show_choices=True,
        )

        if choice == "q":
            console.print("[yellow]   Cancelled[/yellow]")
            return None

        if choice == "e":
            custom: str = Prompt.ask("   Enter custom commit message")
            if custom.strip():
                return custom.strip()
            continue

        # Parse as number
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(message.titles):
                return message.titles[idx]
        except ValueError:
            pass


def write_non_interactive_message(file_path: str, message: CommitMessage):
    """Write all options as commented message for non-interactive mode."""
    lines = [
        "# 🤖 AI generated commits - Uncomment one:",
        "#",
    ]

    for title in message.titles:
        full_msg = format_commit_message(title, message.summary)
        for line in full_msg.split("\n"):
            lines.append(f"# {line}")
        lines.append("#")

    write_commit_msg(file_path, "\n".join(lines))


def run_hook(
    file: str,
    source: str | None = None,
    titles: int = 3,
    non_interactive: bool = False,
) -> None:
    """
    Git hook handler - called by prepare-commit-msg hook.

    This is the effect boundary - all I/O happens here.
    """
    # Guard: Skip special commits
    if source in ["merge", "squash", "commit", "message", "template"]:
        return

    # Guard: Skip if no staged changes
    if not has_staged_changes():
        return

    try:
        # Generate commit message
        message = generate_commit_message(titles_count=titles)

        # Interactive or non-interactive mode
        if non_interactive or not sys.stdin.isatty():
            write_non_interactive_message(file, message)
        else:
            existing = read_commit_msg(file) or ""
            selected = interactive_selection(message, existing)

            if selected:
                full_message = format_commit_message(selected, message.summary)
                write_commit_msg(file, full_message)
                console.print("[green]✅ Commit message saved![/green]")

    except Exception as e:
        error_console.print(f"[red]❌ Error: {e}[/red]")
        # Don't fail the git commit - just show error
        return


def run_generate(
    titles: int = 3,
    apply: bool = False,
    json_output: bool = False,
) -> None:
    """
    Generate commit message manually (not from hook).

    Args:
        titles: Number of title options to generate
        apply: Write message to COMMIT_EDITMSG
        json_output: Output as JSON instead of interactive
    """
    try:
        message = generate_commit_message(titles_count=titles)

        if json_output:
            output = {
                "summary": message.summary,
                "titles": message.titles,
            }
            console.print_json(data=output)
            return

        if apply:
            if get_repo() is None:
                error_console.print("[red]Not in a git repository[/red]")
                raise typer.Exit(1)
            commit_msg_file = git_path("COMMIT_EDITMSG")

            selected = interactive_selection(message)
            if selected:
                full_message = format_commit_message(selected, message.summary)
                write_commit_msg(commit_msg_file, full_message)
                console.print(
                    "[green]✅ Message written to .git/COMMIT_EDITMSG[/green]"
                )
            return

        # Interactive mode - just show options
        selected = interactive_selection(message)
        if selected:
            full_message = format_commit_message(selected, message.summary)
            console.print("\n[bold green]Selected message:[/bold green]")
            console.print(Panel(full_message, border_style="green"))

    except typer.Exit:
        raise
    except Exception as e:
        error_console.print(f"[red]❌ Error: {e}[/red]")
        raise typer.Exit(1) from e
