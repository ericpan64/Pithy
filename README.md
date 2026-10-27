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
```

The first provider with a key is used, in the order anthropic, openai, together.

### Models

Each provider has a regular model and a fast model (used by skills with
`pithy-model: fast`). Save a provider and per-provider models with `pithy config`:

```bash
pithy config set provider together                    # always use Together
pithy config set together.model moonshotai/Kimi-K3    # regular model
pithy config set together.fast-model Qwen/Qwen3.5-9B  # fast model
pithy config list                                     # what's in effect, and from where
pithy config unset together.model                     # back to the default
```

Settings live in `~/.config/pithy/config.toml` (or `$XDG_CONFIG_HOME/pithy/`,
or the path in `$PITHY_CONFIG`), so they also apply to the git hook.
Environment variables win over the file: `PITHY_PROVIDER=<provider>` and
`PITHY_MODEL=<model id>` (which replaces both the regular and fast model).

Options tuned for the built-in models, such as OpenAI's `reasoning_effort`,
are not sent with a custom model.

### AI commit messages

One structured LLM call turns your staged diff into a conventional-commit title
and a bulleted summary, matching the style of your recent commits.

With the hook installed, `git commit` drafts the message and then opens your
editor on it as usual, so you review and edit it there. Commits that already have
a message (`-m`, merges, amends) are left alone, and errors never block a commit.

```bash
pithy ai-commit install            # prepare-commit-msg hook (works in subdirs and worktrees)
pithy ai-commit install --force    # replace an existing non-Pithy hook
pithy ai-commit generate -n 3      # print 3 title options and a summary
pithy ai-commit generate --json    # same, as JSON
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

Binary files are listed by path but their contents are not sent; `*.lock`,
`*.min.*`, and `package-lock.json` are skipped entirely. File contents
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
git log --oneline -20 | pithy skills run changelog
pithy skills run repo-overview src/app.py src/util.py
```
