"""
Skills: Agent Skills-format instructions (https://agentskills.io).

A skill is a directory with a SKILL.md: YAML frontmatter (name, description)
followed by markdown instructions. Pithy sends the instructions as the system
prompt and the input (diff, files, stdin) as the user message.

Project skills in .agents/skills/ override built-ins in pithy_cli/builtin_skills/.
"""

import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from .git import repo_root
from .llm import ModelType, resolve_client

BUILTIN_DIR = Path(__file__).parent / "builtin_skills"
PROJECT_SUBDIR = Path(".agents") / "skills"

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    body: str
    path: Path  # skill directory
    source: str  # "built-in", "project", or "override"
    model_type: ModelType = ModelType.REGULAR


def validate_name(name: object) -> None:
    """Enforce the spec: 1-64 chars, lowercase alphanumerics, single hyphens."""
    if not isinstance(name, str) or len(name) > 64 or not NAME_RE.match(name):
        raise ValueError(
            f"Invalid skill name {name!r}: use 1-64 lowercase letters, digits, "
            "and single hyphens (not at the start or end)"
        )


def parse_skill(skill_dir: Path, source: str = "project") -> Skill:
    """Parse and validate <skill_dir>/SKILL.md."""
    skill_md = skill_dir / "SKILL.md"
    match = FRONTMATTER_RE.match(skill_md.read_text(encoding="utf-8"))
    if not match:
        raise ValueError(f"{skill_md}: missing YAML frontmatter")

    meta = yaml.safe_load(match.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError(f"{skill_md}: frontmatter must be a YAML mapping")

    name = meta.get("name")
    validate_name(name)
    if name != skill_dir.name:
        raise ValueError(
            f"{skill_md}: name '{name}' must match directory '{skill_dir.name}'"
        )

    description = meta.get("description")
    if not isinstance(description, str) or not 1 <= len(description.strip()) <= 1024:
        raise ValueError(f"{skill_md}: description must be 1-1024 characters")

    metadata = meta.get("metadata") or {}
    try:
        model_type = ModelType(metadata.get("pithy-model", "regular"))
    except ValueError as e:
        raise ValueError(f"{skill_md}: pithy-model must be 'regular' or 'fast'") from e

    return Skill(
        name=name,
        description=description.strip(),
        body=match.group(2).strip(),
        path=skill_dir,
        source=source,
        model_type=model_type,
    )


def project_skills_dir(git_root: Path | None = None) -> Path:
    """Return <git root>/.agents/skills, or raise outside a git repository."""
    root = git_root or repo_root()
    if root is None:
        raise ValueError("Not in a git repository")
    return root / PROJECT_SUBDIR


def discover(git_root: Path | None = None) -> dict[str, tuple[Path, str]]:
    """Map skill name → (directory, source); project skills override built-ins."""
    found = {
        d.name: (d, "built-in")
        for d in sorted(BUILTIN_DIR.iterdir())
        if (d / "SKILL.md").exists()
    }

    root = git_root or repo_root()
    project_dir = root / PROJECT_SUBDIR if root else None
    if project_dir and project_dir.is_dir():
        for d in sorted(project_dir.iterdir()):
            if (d / "SKILL.md").exists():
                found[d.name] = (d, "override" if d.name in found else "project")

    return found


def load_skill(name: str, git_root: Path | None = None) -> Skill:
    """Load a skill by name, preferring the project version."""
    found = discover(git_root)
    if name not in found:
        raise ValueError(f"Skill '{name}' not found. Run 'pithy skills list'.")
    path, source = found[name]
    return parse_skill(path, source)


def new_skill(name: str, description: str = "", git_root: Path | None = None) -> Path:
    """Scaffold .agents/skills/<name>/SKILL.md and return its path."""
    validate_name(name)
    skill_dir = project_skills_dir(git_root) / name
    if skill_dir.exists():
        raise ValueError(f"Skill '{name}' already exists at {skill_dir}")

    frontmatter = yaml.safe_dump(
        {
            "name": name,
            "description": description
            or "TODO: what this skill does and when to use it.",
        },
        sort_keys=False,
        allow_unicode=True,
    )
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\n{frontmatter}---\n\n"
        "Write instructions for the model here. Input given to\n"
        f"`pithy skills run {name}` (files or stdin) is sent as the user message.\n",
        encoding="utf-8",
    )
    return skill_md


def edit_skill(name: str, git_root: Path | None = None) -> Path:
    """Return the project SKILL.md to edit, copying a built-in on first edit."""
    found = discover(git_root)
    if name not in found:
        raise ValueError(
            f"Skill '{name}' not found. Run 'pithy skills new {name}' to create it."
        )

    path, source = found[name]
    if source == "built-in":
        target = project_skills_dir(git_root) / name
        shutil.copytree(path, target)
        path = target
    return path / "SKILL.md"


def format_file(label: str, content: str) -> str:
    """Format one input file for a user message."""
    return f"--- {label} ---\n{content}"


def run_skill(name: str, user_input: str, max_tokens: int = 8000) -> str:
    """Run a skill against input text and return the model's response."""
    skill = load_skill(name)
    client = resolve_client(skill.model_type)
    return client.complete(skill.body, user_input, max_tokens=max_tokens)


def open_in_editor(file_path: Path) -> int:
    """Open file in $EDITOR, $VISUAL, or vim. Returns editor exit code."""
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL") or "vim"
    return subprocess.run([*shlex.split(editor), str(file_path)]).returncode
