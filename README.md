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

### Code Summarization

Generate structured markdown summaries of your source code files and directories using AI.

#### Quick Start

```bash
# Summarize a single file
pithy summarize path/to/file.py

# Summarize an entire directory
pithy summarize src/

# Summarize current directory
pithy summarize .
```

#### Output Structure

Summaries are written to timestamped subdirectories under `.pithy/summarize/` at your git repository root. Each run creates a new timestamp directory in the format `YYYY-MM-DD_HH-MM-SS`:

```
.pithy/
└── summarize/
    ├── 2025-01-15_14-30-22/
    │   ├── src/
    │   │   ├── app.py.md
    │   │   ├── utils.py.md
    │   │   └── _meta.md
    │   └── README.md.md
    └── 2025-01-15_15-45-10/
        └── ...
```

- **File summaries**: `.pithy/summarize/<timestamp>/<relative_path>.<ext>.md`
  - Example: `src/app.py` → `.pithy/summarize/2025-01-15_14-30-22/src/app.py.md`
  - Contains AI-generated summary with key points, purpose, dependencies, and notes

- **Directory meta**: `.pithy/summarize/<timestamp>/<relative_path>/_meta.md`
  - Aggregates immediate files with one-line synopses
  - References subdirectories via links to their `_meta.md` files
  - Generated programmatically (no LLM calls)

**Benefits of timestamped directories:**
- Track evolution of your codebase over time
- Compare summaries from different points in development
- Never overwrite previous summaries
- Easy to identify when summaries were generated

#### Options

| Option | Default | Description |
|--------|---------|-------------|
| `path` | `.` | File or directory to summarize |
| `--exclude`, `-x` | *(none)* | Glob patterns to exclude (repeatable) |
| `--depth` | `-1` | Maximum recursion depth (-1 = unlimited) |
| `--force` | `False` | Regenerate even if outputs are up-to-date |
| `--dry-run` | `False` | Show planned actions without writing files |
| `--max-file-bytes` | `120000` | Read limit per file (caps token usage) |
| `--quiet` | `False` | Reduce console output |
| `--include-ignored` | `False` | Process gitignored files |

#### Default Exclusions

**Gitignored files** are automatically excluded by default. The summarize command respects your `.gitignore` file(s) and skips any files or directories that git would ignore. Use `--include-ignored` to override this behavior.

Additionally, the following patterns are always excluded:
- `.git/`, `.pithy/`
- `node_modules/`, `dist/`, `build/`, `.venv/`
- `*.lock`, `*.min.*`

#### Examples

**Exclude specific files or patterns:**
```bash
pithy summarize . --exclude "tests/*" --exclude "*.tmp"
```

**Limit recursion depth:**
```bash
pithy summarize src/ --depth 2
```

**Force regeneration of all summaries:**
```bash
pithy summarize . --force
```

**Preview actions without writing:**
```bash
pithy summarize src/ --dry-run
```

**Quiet mode for scripting:**
```bash
pithy summarize . --quiet
```

**Include gitignored files:**
```bash
pithy summarize . --include-ignored
# Processes everything, including files matched by .gitignore
```

#### Gitignore Integration

By default, `pithy summarize` respects your `.gitignore` files:
- Files and directories matched by `.gitignore` patterns are automatically skipped
- Nested `.gitignore` files are respected (follows git's hierarchy)
- Works seamlessly with your existing git workflow
- Use `--include-ignored` to process ignored files when needed (e.g., for documentation of build artifacts)

**Example:**
```bash
# .gitignore contains:
# build/
# *.pyc
# .env

# Default behavior - skips build/, *.pyc, .env
pithy summarize .

# Process everything, including gitignored files
pithy summarize . --include-ignored
```

#### Incremental Updates

By default, summaries are only regenerated when the source file is newer than the existing summary. This saves API calls and time on repeated runs. Use `--force` to override this behavior.

#### Cost Control

- Only file-level summaries invoke the LLM
- Directory `_meta.md` files are generated programmatically (deterministic, free)
- `--max-file-bytes` caps the amount of content sent per file (default: 120KB)
- Binary files are detected and skipped automatically

#### API Key Setup

Before using summarization, configure your LLM provider API key:

```bash
# For Anthropic Claude
pithy keys set anthropic

# For OpenAI GPT
pithy keys set openai

# Check provider status
pithy keys providers
```
