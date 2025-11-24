"""Source code summarization feature."""

from __future__ import annotations

import fnmatch
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple

import typer
from .init import find_git_root, ensure_pithy_directory
from .ai_commit import get_provider_config
from .llm import create_llm_client, LLMClient, summarize_source_file, ModelType

DEFAULT_EXCLUDES = [
    ".git/",
    ".pithy/",
    "node_modules/",
    "dist/",
    "build/",
    ".venv/",
    "*.lock",
    "*.min.*",
]


def _get_timestamp() -> str:
    """Generate timestamp string in YYYY-MM-DD_HH-MM-SS format."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


@dataclass
class SummarizeOptions:
    """Configuration options for summarization."""

    excludes: List[str]
    depth: int
    force: bool
    dry_run: bool
    max_file_bytes: int
    quiet: bool
    include_ignored: bool


def run_summarize(
    target: str,
    excludes: List[str] | None = None,
    depth: int = -1,
    force: bool = False,
    dry_run: bool = False,
    max_file_bytes: int = 120_000,
    quiet: bool = False,
    include_ignored: bool = False,
) -> None:
    """
    Generate structured markdown summaries of files and directories.

    Args:
        target: File or directory path to summarize
        excludes: Additional glob patterns to exclude
        depth: Maximum recursion depth (-1 for unlimited)
        force: Regenerate even if outputs are up-to-date
        dry_run: Show actions without writing
        max_file_bytes: Maximum bytes to read per file
        quiet: Reduce console output
        include_ignored: Process gitignored files (default: False)
    """
    src_path = Path(target).resolve()

    if not src_path.exists():
        raise ValueError(f"Path not found: {src_path}")

    # Find git root or fallback to current directory
    git_root = find_git_root() or Path.cwd()
    pithy_base = ensure_pithy_directory(git_root)

    # Create timestamped output directory under .pithy/summarize/
    timestamp = _get_timestamp()
    summarize_base = pithy_base / "summarize"
    summarize_base.mkdir(exist_ok=True)
    pithy_root = summarize_base / timestamp
    pithy_root.mkdir(parents=True, exist_ok=True)

    options = SummarizeOptions(
        excludes=(excludes or []) + DEFAULT_EXCLUDES,
        depth=depth,
        force=force,
        dry_run=dry_run,
        max_file_bytes=max_file_bytes,
        quiet=quiet,
        include_ignored=include_ignored,
    )

    # Get LLM client
    provider, api_key = get_provider_config()
    client = create_llm_client(provider, api_key, model_type=ModelType.FAST)

    if not options.quiet:
        typer.echo(f"📍 Git root: {git_root}")
        typer.echo(f"📁 Output directory: {pithy_root}")
        typer.echo(f"🕒 Timestamp: {timestamp}")

    if src_path.is_file():
        rel = _relative_to(src_path, git_root)
        _summarize_file(client, git_root, pithy_root, rel, options, git_root)
        if not options.quiet:
            typer.echo(f"✅ Summarized file: {rel}")
        return

    if src_path.is_dir():
        rel_dir = _relative_to(src_path, git_root)
        _summarize_dir(client, git_root, pithy_root, rel_dir, options, current_depth=0, git_root_for_ignore=git_root)
        if not options.quiet:
            typer.echo(f"✅ Summarized directory: {rel_dir}")
        return


def _relative_to(path: Path, root: Path) -> Path:
    """
    Compute relative path from root to path.

    If path is outside root, return just the basename.
    """
    try:
        return path.relative_to(root)
    except ValueError:
        return Path(path.name)


def _is_gitignored(path: Path, git_root: Path) -> bool:
    """
    Check if path is gitignored using GitPython.

    Args:
        path: Absolute path to check
        git_root: Git repository root

    Returns:
        True if path is gitignored, False otherwise
    """
    try:
        from git import Repo
        repo = Repo(git_root)

        # Get relative path for git check
        try:
            rel_path = str(path.relative_to(git_root))
        except ValueError:
            # Path outside git root - not gitignored
            return False

        # Check if ignored
        # GitPython's ignored() method returns list of paths that match
        ignored = repo.ignored(rel_path)
        return bool(ignored)
    except Exception:
        # No git repo, error reading .gitignore, or other issue
        # Default to not excluding the file
        return False


def _matches_excludes(rel: Path, is_dir: bool, patterns: Iterable[str]) -> bool:
    """
    Check if a path matches any exclusion pattern.

    Args:
        rel: Relative path to check
        is_dir: Whether the path is a directory
        patterns: Glob patterns to match against
    """
    path_str = str(rel.as_posix())
    if is_dir:
        path_str += "/"

    for pat in patterns:
        # Directory pattern: check if any part of the path matches
        if pat.endswith("/"):
            dir_name = pat.rstrip("/")
            # Match if directory name appears anywhere in path
            if f"/{dir_name}/" in f"/{path_str}" or path_str.startswith(f"{dir_name}/"):
                return True
        # File pattern: use fnmatch
        if fnmatch.fnmatch(path_str, pat):
            return True
        # Also try matching just the filename for file patterns
        if not is_dir and fnmatch.fnmatch(rel.name, pat):
            return True

    return False


def _is_text_file(path: Path, sample_bytes: int = 4096) -> bool:
    """
    Heuristic to detect if a file is text (not binary).

    Args:
        path: Path to file
        sample_bytes: Number of bytes to sample for detection
    """
    # Check mimetype first
    mime, _ = mimetypes.guess_type(str(path))
    if mime and (mime.startswith("text/") or "json" in mime or "xml" in mime):
        return True

    # Try to decode a small sample
    try:
        with path.open("rb") as f:
            chunk = f.read(sample_bytes)
        chunk.decode("utf-8")
        return True
    except Exception:
        return False


def _dest_for_file(pithy_root: Path, rel_file: Path) -> Path:
    """
    Compute destination path for a file summary.

    Mirrors the source path and appends .md to the filename.
    """
    return pithy_root / (rel_file.as_posix() + ".md")


def _dest_meta_for_dir(pithy_root: Path, rel_dir: Path) -> Path:
    """Compute destination path for a directory meta summary."""
    return pithy_root / rel_dir / "_meta.md"


def _should_skip_file(src: Path, dest: Path, force: bool) -> bool:
    """
    Check if file summarization should be skipped.

    Skip if destination is newer than source (unless force=True).
    """
    if force:
        return False
    if not dest.exists():
        return False
    try:
        return dest.stat().st_mtime >= src.stat().st_mtime
    except FileNotFoundError:
        return False


def _read_text_truncated(path: Path, max_bytes: int) -> Tuple[str, bool]:
    """
    Read text file with truncation.

    Args:
        path: Path to file
        max_bytes: Maximum bytes to read

    Returns:
        Tuple of (content, was_truncated)
    """
    try:
        content_bytes = path.read_bytes()
    except Exception:
        return "", False

    truncated = False
    if len(content_bytes) > max_bytes:
        content_bytes = content_bytes[:max_bytes]
        truncated = True

    try:
        return content_bytes.decode("utf-8", errors="ignore"), truncated
    except Exception:
        return "", truncated


def _extract_first_bullet(summary_md: str) -> str | None:
    """
    Extract the first bullet point from a file summary's Key Points section.

    Args:
        summary_md: Markdown content of file summary

    Returns:
        First bullet text (without leading dash), or None if not found
    """
    in_key_points = False
    for line in summary_md.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("### key points"):
            in_key_points = True
            continue
        if in_key_points and stripped.startswith("- "):
            return stripped[2:]
        if in_key_points and stripped.startswith("### "):
            # Reached next section
            break
    return None


def _summarize_file(
    client: LLMClient,
    git_root: Path,
    pithy_root: Path,
    rel_file: Path,
    opts: SummarizeOptions,
    git_root_for_ignore: Path,
) -> None:
    """
    Summarize a single file.

    Args:
        client: LLM client for generating summaries
        git_root: Git repository root
        pithy_root: Output directory root
        rel_file: Relative path of file to summarize
        opts: Summarization options
        git_root_for_ignore: Git root for gitignore checks
    """
    src = git_root / rel_file
    dest = _dest_for_file(pithy_root, rel_file)

    # Check exclusions
    if _matches_excludes(rel_file, is_dir=False, patterns=opts.excludes):
        return

    # Check gitignore
    if not opts.include_ignored and _is_gitignored(src, git_root_for_ignore):
        if not opts.quiet:
            typer.echo(f"⏭️  Skipping (gitignored): {rel_file}")
        return

    # Check if binary
    if not _is_text_file(src):
        _write_if_needed(dest, _binary_stub(rel_file), opts)
        return

    # Check if up-to-date
    if _should_skip_file(src, dest, opts.force):
        if not opts.quiet:
            typer.echo(f"⏭️  Skipping (up-to-date): {rel_file}")
        return

    if not opts.quiet:
        typer.echo(f"📝 Summarizing: {rel_file}")

    # Read and summarize
    content, truncated = _read_text_truncated(src, opts.max_file_bytes)
    language = (src.suffix.lstrip(".") or "text").lower()

    summary_md = summarize_source_file(client, str(rel_file.as_posix()), language, content)

    if truncated:
        summary_md += "\n\n> Note: Content truncated for summarization.\n"

    _write_if_needed(dest, summary_md, opts)


def _binary_stub(rel_file: Path) -> str:
    """Generate a stub summary for binary files."""
    return f"## {rel_file.as_posix()}\n\n- Binary or non-text file; summary omitted.\n"


def _write_if_needed(dest: Path, content: str, opts: SummarizeOptions) -> None:
    """
    Write content to destination file.

    Respects dry_run mode and creates parent directories.
    """
    if opts.dry_run:
        if not opts.quiet:
            typer.echo(f"[DRY RUN] Would write: {dest}")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def _summarize_dir(
    client: LLMClient,
    git_root: Path,
    pithy_root: Path,
    rel_dir: Path,
    opts: SummarizeOptions,
    current_depth: int,
    git_root_for_ignore: Path,
) -> None:
    """
    Recursively summarize a directory.

    Processes all files and subdirectories, then generates a _meta.md
    summarizing the directory's contents.

    Args:
        client: LLM client for generating summaries
        git_root: Git repository root
        pithy_root: Output directory root
        rel_dir: Relative path of directory to summarize
        opts: Summarization options
        current_depth: Current recursion depth
        git_root_for_ignore: Git root for gitignore checks
    """
    # Check depth limit
    if opts.depth >= 0 and current_depth > opts.depth:
        return

    # Check exclusions
    if _matches_excludes(rel_dir, is_dir=True, patterns=opts.excludes):
        return

    src_dir = git_root / rel_dir

    # Check gitignore for directory
    if not opts.include_ignored and _is_gitignored(src_dir, git_root_for_ignore):
        if not opts.quiet:
            typer.echo(f"⏭️  Skipping (gitignored): {rel_dir}/")
        return

    if not src_dir.exists() or not src_dir.is_dir():
        return

    # Sort entries: directories first, then files
    try:
        entries = sorted(src_dir.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return

    file_lines: List[str] = []
    subdir_lines: List[str] = []

    # Process all entries
    for entry in entries:
        rel = rel_dir / entry.name

        if entry.is_dir():
            # Recurse into subdirectory first
            _summarize_dir(client, git_root, pithy_root, rel, opts, current_depth + 1, git_root_for_ignore)

            # Add reference to subdirectory meta
            meta_path = _dest_meta_for_dir(pithy_root, rel)
            rel_meta = meta_path.relative_to(pithy_root)
            subdir_lines.append(f"- [{entry.name}/]({rel_meta.as_posix()})")

        elif entry.is_file():
            # Summarize file
            _summarize_file(client, git_root, pithy_root, rel, opts, git_root_for_ignore)

            # Try to extract first bullet for listing
            try:
                summary_path = _dest_for_file(pithy_root, rel)
                if summary_path.exists():
                    summary_text = summary_path.read_text(encoding="utf-8")
                    first = _extract_first_bullet(summary_text)
                else:
                    first = None
            except Exception:
                first = None

            if first:
                file_lines.append(f"- **{entry.name}**: {first}")
            else:
                file_lines.append(f"- {entry.name}")

    # Generate directory meta
    meta_md = _render_dir_meta(rel_dir, file_lines, subdir_lines)
    _write_if_needed(_dest_meta_for_dir(pithy_root, rel_dir), meta_md, opts)


def _render_dir_meta(
    rel_dir: Path,
    file_lines: List[str],
    subdir_lines: List[str],
) -> str:
    """
    Render directory meta markdown.

    Args:
        rel_dir: Relative directory path
        file_lines: Formatted lines for files
        subdir_lines: Formatted lines for subdirectories

    Returns:
        Markdown content for _meta.md
    """
    lines: List[str] = []

    # Heading
    dir_path = rel_dir.as_posix() or "."
    lines.append(f"# {dir_path}")
    lines.append("")

    # Files section
    lines.append("## Files")
    lines.append("")
    if file_lines:
        lines.extend(file_lines)
    else:
        lines.append("- *(none)*")
    lines.append("")

    # Subdirectories section
    lines.append("## Subdirectories")
    lines.append("")
    if subdir_lines:
        lines.extend(subdir_lines)
    else:
        lines.append("- *(none)*")

    return "\n".join(lines) + "\n"
