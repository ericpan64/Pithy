"""Codebase overview: one LLM call over a path's files."""

import fnmatch
import mimetypes
from pathlib import Path

import typer

from .git import git, require_root
from .llm import resolve_client
from .skills import format_file, load_skill

DEFAULT_EXCLUDES = ["*.lock", "*.min.*", "package-lock.json"]


def list_files(target: Path, excludes: list[str]) -> tuple[Path, list[Path]]:
    """
    List tracked and untracked-but-not-ignored files under target.

    Returns:
        Tuple of (git root, absolute file paths)
    """
    root = require_root()
    output = git(
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        str(target),
        cwd=root,
    )
    patterns = excludes + DEFAULT_EXCLUDES

    files = []
    for rel in filter(None, output.split("\0")):
        if any(_excluded(rel, pat) for pat in patterns):
            continue
        path = root / rel
        if path.is_file():
            files.append(path)
    return root, files


def _excluded(rel: str, pattern: str) -> bool:
    """Match a glob against the path or filename; 'dir/' matches a directory anywhere."""
    if pattern.endswith("/"):
        return f"/{pattern}" in f"/{rel}"
    return fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(Path(rel).name, pattern)


def _is_text_file(path: Path, sample_bytes: int = 4096) -> bool:
    """Heuristic to detect if a file is text (not binary)."""
    mime, _ = mimetypes.guess_type(str(path))
    if mime and (mime.startswith("text/") or "json" in mime or "xml" in mime):
        return True

    try:
        with path.open("rb") as f:
            chunk = f.read(sample_bytes)
    except OSError:
        return False
    if b"\0" in chunk:
        return False
    try:
        chunk.decode("utf-8")
    except UnicodeDecodeError as e:
        # Tolerate a multi-byte character cut off at the end of the sample
        return e.start >= len(chunk) - 3
    return True


def build_context(root: Path, files: list[Path], max_chars: int) -> str:
    """File list, then file contents up to max_chars, then any omitted files."""
    rel_paths = [f.relative_to(root).as_posix() for f in files]
    parts = ["Files:\n" + "\n".join(f"- {p}" for p in rel_paths)]
    omitted = []
    used = len(parts[0])

    for path, rel in zip(files, rel_paths, strict=True):
        if not _is_text_file(path):
            continue
        # Read at most one character past the budget to detect overflow
        budget = max_chars - used - len(format_file(rel, ""))
        with path.open(encoding="utf-8", errors="ignore") as f:
            content = f.read(budget + 1) if budget >= 0 else ""
        if budget < 0 or len(content) > budget:
            omitted.append(rel)
            continue
        block = format_file(rel, content)
        parts.append(block)
        used += len(block)

    if omitted:
        parts.append(
            "Contents omitted (over size budget):\n"
            + "\n".join(f"- {p}" for p in omitted)
        )
    return "\n\n".join(parts)


def run_summarize(
    target: str = ".",
    output: str | None = None,
    excludes: list[str] | None = None,
    max_chars: int = 400_000,
) -> None:
    """Write a markdown overview of target to stdout or an output file."""
    src_path = Path(target).resolve()
    if not src_path.exists():
        raise ValueError(f"Path not found: {src_path}")

    root, files = list_files(src_path, excludes or [])
    if not files:
        raise ValueError(f"No files to summarize under {src_path}")

    skill = load_skill("repo-overview")
    client = resolve_client(skill.model_type)
    rel_target = src_path.relative_to(root).as_posix() if src_path != root else "."
    user = f"Path: {rel_target}\n\n{build_context(root, files, max_chars)}"

    typer.echo(f"Summarizing {len(files)} files in {rel_target}...", err=True)
    overview = client.complete(skill.body, user, max_tokens=8000).strip()

    if output:
        Path(output).write_text(overview + "\n", encoding="utf-8")
        typer.echo(f"✓ Wrote {output}", err=True)
    else:
        typer.echo(overview)
