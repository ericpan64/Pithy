"""
Unit tests for pithy_cli.skills module.

Run with: pytest tests/test_skills.py -v
"""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from pithy_cli.cli import app
from pithy_cli.llm import ModelType
from pithy_cli.skills import (
    discover,
    edit_skill,
    load_skill,
    new_skill,
    parse_skill,
    run_skill,
    validate_name,
)

runner = CliRunner()


def _write_skill(
    parent: Path, name: str, frontmatter: str, body: str = "Do it."
) -> Path:
    skill_dir = parent / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n\n{body}\n")
    return skill_dir


# validate_name


@pytest.mark.parametrize("name", ["a", "code-review", "pdf2text", "a" * 64])
def test_validate_name_valid(name):
    validate_name(name)


@pytest.mark.parametrize(
    "name", ["", "Code", "-pdf", "pdf-", "pdf--x", "a_b", "a" * 65, None]
)
def test_validate_name_invalid(name):
    with pytest.raises(ValueError, match="Invalid skill name"):
        validate_name(name)


# parse_skill


def test_parse_skill(tmp_path):
    skill_dir = _write_skill(
        tmp_path,
        "review",
        "name: review\ndescription: Reviews code.\nmetadata:\n  pithy-model: fast",
        "Be thorough.",
    )

    skill = parse_skill(skill_dir)

    assert skill.name == "review"
    assert skill.description == "Reviews code."
    assert skill.body == "Be thorough."
    assert skill.model_type == ModelType.FAST


def test_parse_skill_missing_frontmatter(tmp_path):
    skill_dir = tmp_path / "x"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("No frontmatter here")

    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        parse_skill(skill_dir)


def test_parse_skill_name_must_match_dir(tmp_path):
    skill_dir = _write_skill(tmp_path, "review", "name: other\ndescription: x")

    with pytest.raises(ValueError, match="must match directory"):
        parse_skill(skill_dir)


def test_parse_skill_requires_description(tmp_path):
    skill_dir = _write_skill(tmp_path, "review", "name: review")

    with pytest.raises(ValueError, match="description"):
        parse_skill(skill_dir)


def test_parse_skill_bad_model(tmp_path):
    skill_dir = _write_skill(
        tmp_path,
        "review",
        "name: review\ndescription: x\nmetadata:\n  pithy-model: huge",
    )

    with pytest.raises(ValueError, match="pithy-model"):
        parse_skill(skill_dir)


def test_builtin_skills_are_valid(tmp_path):
    for name, (path, source) in discover(tmp_path).items():
        assert source == "built-in"
        assert parse_skill(path, source).name == name


# Resolution


def test_discover_project_and_override(git_repo):
    skills_dir = git_repo / ".agents" / "skills"
    _write_skill(skills_dir, "mine", "name: mine\ndescription: Mine.")
    _write_skill(
        skills_dir, "commit-message", "name: commit-message\ndescription: Custom."
    )

    found = discover()

    assert found["mine"][1] == "project"
    assert found["commit-message"][1] == "override"
    assert found["repo-overview"][1] == "built-in"
    assert load_skill("commit-message").description == "Custom."


def test_load_skill_not_found(git_repo):
    with pytest.raises(ValueError, match="not found"):
        load_skill("missing")


# new / edit


def test_new_skill(git_repo):
    skill_md = new_skill("demo", "Says hi: politely")

    assert skill_md == git_repo / ".agents/skills/demo/SKILL.md"
    skill = parse_skill(skill_md.parent)
    assert skill.description == "Says hi: politely"


def test_new_skill_already_exists(git_repo):
    new_skill("demo")

    with pytest.raises(ValueError, match="already exists"):
        new_skill("demo")


def test_new_skill_invalid_name(git_repo):
    with pytest.raises(ValueError, match="Invalid skill name"):
        new_skill("Bad Name")


def test_edit_builtin_copies_to_project(git_repo):
    skill_md = edit_skill("commit-message")

    assert skill_md == git_repo / ".agents/skills/commit-message/SKILL.md"
    assert discover()["commit-message"][1] == "override"


def test_edit_project_skill_in_place(git_repo):
    skill_md = new_skill("demo")

    assert edit_skill("demo") == skill_md


# run


def test_run_skill_uses_body_as_system_prompt(git_repo):
    _write_skill(
        git_repo / ".agents/skills",
        "shout",
        "name: shout\ndescription: Shouts.\nmetadata:\n  pithy-model: fast",
        "Reply in capitals.",
    )
    client = Mock()
    client.complete.return_value = "HI"

    with patch("pithy_cli.skills.resolve_client", return_value=client) as resolve:
        assert run_skill("shout", "hi") == "HI"

    resolve.assert_called_once_with(ModelType.FAST)
    assert client.complete.call_args.args == ("Reply in capitals.", "hi")


def test_cli_skills_run_with_files(git_repo):
    (git_repo / "a.txt").write_text("alpha")
    with patch("pithy_cli.skills.run_skill", return_value="done") as run:
        result = runner.invoke(app, ["skills", "run", "repo-overview", "a.txt"])

    assert result.exit_code == 0
    assert "done" in result.stdout
    assert run.call_args.args == ("repo-overview", "--- a.txt ---\nalpha")


def test_cli_skills_run_with_stdin(git_repo):
    with patch("pithy_cli.skills.run_skill", return_value="done") as run:
        result = runner.invoke(app, ["skills", "run", "repo-overview"], input="piped")

    assert result.exit_code == 0
    assert run.call_args.args == ("repo-overview", "piped")


def test_cli_skills_new_opens_editor(git_repo):
    with patch("pithy_cli.skills.open_in_editor", return_value=0) as editor:
        result = runner.invoke(app, ["skills", "new", "demo", "-d", "Demo skill"])

    assert result.exit_code == 0
    editor.assert_called_once()
    assert "saved" in result.stdout


def test_cli_skills_list_shows_invalid(git_repo):
    _write_skill(git_repo / ".agents/skills", "broken", "name: wrong\ndescription: x")

    result = runner.invoke(app, ["skills", "list"])

    assert result.exit_code == 0
    assert "broken" in result.stdout
    assert "invalid" in result.stdout
