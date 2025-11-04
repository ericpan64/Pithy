# Pithy
Your pithy python pair programmer

## Dependencies
- uv
- Python version >=3.12
- pipx

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

Summaries are written to the `.pithy/` directory at your git repository root, mirroring your source tree structure:

- **File summaries**: `.pithy/<relative_path>.<ext>.md`
  - Example: `src/app.py` → `.pithy/src/app.py.md`
  - Contains AI-generated summary with key points, purpose, dependencies, and notes

- **Directory meta**: `.pithy/<relative_path>/_meta.md`
  - Aggregates immediate files with one-line synopses
  - References subdirectories via links to their `_meta.md` files
  - Generated programmatically (no LLM calls)

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

#### Default Exclusions

The following patterns are automatically excluded:
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
