"""AI-powered git commit message generation."""

import sys
from typing import Literal, Optional
from dataclasses import dataclass
from pathlib import Path

import typer
from rich.console import Console
from rich.prompt import Prompt
from rich.panel import Panel

from .git import (
    has_staged_changes,
    get_staged_diff,
    get_repo_name,
    get_branch_name,
    read_commit_msg,
    write_commit_msg,
    install_git_hook,
    uninstall_git_hook,
    format_commit_message,
)
from .llm import (
    create_llm_client,
    generate_summary,
    generate_titles,
    LLMProvider,
    ModelType,
)
from .keys import get_provider_key, Provider

console = Console()

AiCommitAction = Literal["install", "uninstall", "hook", "generate"]


@dataclass
class CommitMessage:
    """Generated commit message."""
    summary: list[str]
    titles: list[str]


def get_provider_config() -> tuple[LLMProvider, str]:
    """
    Get LLM provider and API key from keystore or environment.

    Returns:
        Tuple of (provider, api_key)
    """
    # Map Provider enum to LLMProvider enum
    provider_map = {
        Provider.ANTHROPIC: LLMProvider.ANTHROPIC,
        Provider.OPENAI: LLMProvider.OPENAI,
    }

    # Try each provider in order
    for provider, llm_provider in provider_map.items():
        if key := get_provider_key(provider):
            return llm_provider, key

    # Check environment as fallback
    import os
    if key := os.environ.get("ANTHROPIC_API_KEY"):
        return LLMProvider.ANTHROPIC, key
    if key := os.environ.get("OPENAI_API_KEY"):
        return LLMProvider.OPENAI, key

    from .keys import PROVIDER_KEYS
    raise ValueError(
        "No API key found. Set one with:\n"
        f"  pithy keys set {PROVIDER_KEYS[Provider.ANTHROPIC]}\n"
        "  or\n"
        f"  pithy keys set {PROVIDER_KEYS[Provider.OPENAI]}"
    )


def generate_commit_message(
    titles_count: int = 3,
    max_diff_bytes: int = 120_000,
) -> CommitMessage:
    """
    Generate commit message from staged changes.

    Pure business logic - delegates all effects to helper functions.
    """
    # Validate preconditions
    if not has_staged_changes():
        raise ValueError("No staged changes detected")

    # Get git context
    diff = get_staged_diff(max_diff_bytes)
    repo_name = get_repo_name()
    branch = get_branch_name()

    # Get LLM configuration
    provider, api_key = get_provider_config()
    client = create_llm_client(provider, api_key, model_type=ModelType.REGULAR)

    # Phase 1: Generate summary from diff
    with console.status("[bold green]Analyzing changes...", spinner="dots"):
        summary = generate_summary(
            client=client,
            diff=diff,
            repo_name=repo_name,
            branch=branch,
        )

    # Phase 2: Generate commit titles from summary
    with console.status("[bold green]Generating commit messages...", spinner="dots"):
        titles = generate_titles(
            client=client,
            summary=summary,
            count=titles_count,
        )

    return CommitMessage(summary=summary, titles=titles)


def interactive_selection(message: CommitMessage, existing: str = "") -> Optional[str]:
    """
    Interactive commit message selection with rich UI.

    Returns:
        Selected commit title, or None if cancelled
    """
    console.print()
    console.print(Panel.fit(
        "🤖 [bold cyan]AI Commit Message Generator[/bold cyan]",
        border_style="cyan"
    ))

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
            custom = Prompt.ask("   Enter custom commit message")
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
    source: Optional[str] = None,
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
        console.print(f"[red]❌ Error: {e}[/red]", file=sys.stderr)
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
            # Write to git commit message file
            commit_msg_file = Path(".git/COMMIT_EDITMSG")
            if not commit_msg_file.exists():
                console.print("[red]Not in a git repository[/red]", file=sys.stderr)
                raise typer.Exit(1)

            selected = interactive_selection(message)
            if selected:
                full_message = format_commit_message(selected, message.summary)
                write_commit_msg(str(commit_msg_file), full_message)
                console.print("[green]✅ Message written to .git/COMMIT_EDITMSG[/green]")
            return

        # Interactive mode - just show options
        selected = interactive_selection(message)
        if selected:
            full_message = format_commit_message(selected, message.summary)
            console.print("\n[bold green]Selected message:[/bold green]")
            console.print(Panel(full_message, border_style="green"))

    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]", file=sys.stderr)
        raise typer.Exit(1)


def run_ai_commit(action: AiCommitAction, **kwargs) -> None:
    """
    Main entry point for ai-commit command.

    Routes to appropriate handler based on action.
    """
    if action == "install":
        titles = kwargs.get("titles", 3)

        hook_path = install_git_hook(titles=titles)
        console.print(f"[green]✅ Git hook installed at:[/green] {hook_path}")

    elif action == "uninstall":
        hook_path = uninstall_git_hook()
        if hook_path:
            console.print(f"[green]✅ Git hook uninstalled:[/green] {hook_path}")
        else:
            console.print("[yellow]ℹ Hook not found[/yellow]")

    elif action == "hook":
        # Called by git hook
        file = kwargs["file"]
        source = kwargs.get("source")
        titles = kwargs.get("titles", 3)
        non_interactive = kwargs.get("non_interactive", False)

        run_hook(file, source, titles, non_interactive)

    elif action == "generate":
        titles = kwargs.get("titles", 3)
        apply = kwargs.get("apply", False)
        json_output = kwargs.get("json", False)

        run_generate(titles, apply, json_output)

    else:
        console.print(f"[red]Unknown action: {action}[/red]", file=sys.stderr)
        raise typer.Exit(1)
