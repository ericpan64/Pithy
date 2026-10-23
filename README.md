# Pithy
Your pithy python pair programmer

## Dependencies
- uv
- Python version >=3.12
- pipx

## Development Setup

```bash
# Install dev dependencies
uv sync --extra dev

# Install pre-commit hooks
uv run pre-commit install

# Run hooks manually on all files (optional)
uv run pre-commit run --all-files
```

### Pre-commit Hooks

This project uses pre-commit hooks for code quality:

- **File linting**: trailing whitespace, end-of-file fixes, YAML/TOML validation
- **Ruff**: Python linting and formatting
- **Mypy**: Static type checking

Hooks run automatically on `git commit`. To skip hooks temporarily:
```bash
git commit --no-verify -m "your message"
```

## Build steps
- `uv build`
- `pipx install .`

## Features

### API keys

Pithy supports Anthropic, OpenAI, and Together AI. Keys are read from the
provider's environment variable first (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`TOGETHER_API_KEY`), then from the OS keychain (macOS Keychain, Windows
Credential Manager, or Secret Service on Linux).

```bash
pithy keys set anthropic      # or: openai, together
pithy keys list               # which providers have keys, and where from
pithy keys remove anthropic
pithy keys import-legacy      # one-time import from the old ~/.pithy/keys file
```

The first provider with a key is used, in the order anthropic, openai, together.
Override with `PITHY_PROVIDER=together` and, optionally, `PITHY_MODEL=<model id>`.

### AI commit messages

One structured LLM call turns your staged diff into a bulleted summary and
several conventional-commit title options, matching the style of your recent commits.

```bash
pithy ai-commit install            # prepare-commit-msg hook (works in subdirs and worktrees)
pithy ai-commit install --force    # replace an existing non-Pithy hook
pithy ai-commit generate           # pick a message interactively
pithy ai-commit generate --json    # print summary and titles as JSON
pithy ai-commit uninstall
```

Customize the instructions with `pithy skills edit commit-message`.

### Codebase overview

`pithy summarize` sends a path's files (tracked and untracked, minus anything
gitignored) to the model in one call and returns a markdown overview: purpose,
architecture, key flows, commands, dependencies, and gotchas.

```bash
pithy summarize                    # whole repo, printed to stdout
pithy summarize src/ -o AGENTS.md  # write to a file
pithy summarize . -x "tests/*"     # exclude globs (repeatable)
```

Binary files and `*.lock`, `*.min.*`, `package-lock.json` are skipped. File contents
are capped by `--max-chars` (default 400,000); files over the budget are still
listed, and the overview notes they were omitted.

### Skills

Pithy's instructions are [Agent Skills](https://agentskills.io): a folder with a
`SKILL.md` file of YAML frontmatter plus markdown. The skill body is the system
prompt; input (a diff, files, or stdin) is the user message, so there is no
template syntax to learn.

```markdown
---
name: changelog
description: Turns a list of commits into user-facing release notes.
metadata:
  pithy-model: fast   # optional: fast | regular (default)
---

Group changes into Added, Changed, and Fixed. Skip internal refactors.
```

Project skills live in `.agents/skills/<name>/SKILL.md`, so they are committed
with the repo and other agent tools can use them too. A project skill with the same
name as a built-in (`commit-message`, `repo-overview`) overrides it.

```bash
pithy skills list                              # built-in, project, and override skills
pithy skills new changelog -d "Release notes"  # scaffold and open in $EDITOR
pithy skills edit commit-message               # copies the built-in into .agents/skills/ first
pithy skills reset commit-message              # delete the override, back to built-in
git log --oneline -20 | pithy skills run changelog
pithy skills run repo-overview src/app.py src/util.py
```
