"""LLM provider abstraction for commit message generation."""

import json
from enum import Enum
from typing import Protocol
from dataclasses import dataclass


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class LLMClient(Protocol):
    """Protocol for LLM clients."""

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate completion from prompt."""
        ...


@dataclass
class AnthropicClient:
    """Anthropic Claude client."""
    api_key: str

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        from anthropic import Anthropic

        client = Anthropic(api_key=self.api_key)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=max_tokens,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text


@dataclass
class OpenAIClient:
    """OpenAI GPT client."""
    api_key: str

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)

        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=max_tokens,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.choices[0].message.content


def create_llm_client(provider: LLMProvider, api_key: str) -> LLMClient:
    """Factory function to create LLM client."""
    if provider == LLMProvider.ANTHROPIC:
        return AnthropicClient(api_key=api_key)
    elif provider == LLMProvider.OPENAI:
        return OpenAIClient(api_key=api_key)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


# Prompts

SUMMARY_PROMPT = """Analyze the following git diff and provide a concise summary of the changes.

Repository: {repo_name}
Branch: {branch}

Staged changes (git diff):
```
{diff}
```

REQUIREMENTS:
1. Create a bullet-point summary (3-7 points) describing what changed
2. Each bullet point MUST be 50 characters or less for brevity
3. Add sub-bullets (indented with "  - ") for elaboration only if essential
4. Focus on the "what" and "why", not implementation details
5. Be concise but descriptive
6. Use present tense
7. Prefer elegance and brevity over verbose descriptions

Return your response as JSON in this EXACT format:
{{
  "summary": [
    "Brief change description (≤50 chars)",
    "  - Sub-bullet for elaboration if needed",
    "Another brief change (≤50 chars)"
  ]
}}

Return ONLY valid JSON, no other text or markdown."""

TITLES_PROMPT = """Based on the following summary of changes, generate conventional commit message titles.

Summary of changes:
{summary_text}

REQUIREMENTS:
1. Generate exactly {count} conventional commit titles
2. Format: type(scope): lowercase description in present tense
3. Keep titles under 72 characters total
4. Use present tense ("add" not "added")
5. Make each title represent a different aspect or perspective

Conventional commit types:
- feat: A new feature
- fix: A bug fix

Conventional commit annotations:
- docs: Documentation only changes
- style: Code style changes (formatting, etc)
- refactor: Code refactoring
- perf: Performance improvements
- test: Adding or correcting tests
- build: Build system changes
- ci: CI configuration changes
- chore: Other changes
- revert: Reverts a previous commit

Return as JSON:
{{
  "titles": [
    "type(scope): description",
    "type: another description"
  ]
}}

Return ONLY valid JSON."""

FILE_SUMMARY_PROMPT = """Summarize the following source file.

Path: {rel_path}
Language: {language}

CONTENT:
```
{content}
```

REQUIREMENTS:
- Return Markdown ONLY (no code fences, no extra text).
- First line: '## {rel_path}'
- Then a '### Key Points' section with 5–10 bullets, each ≤100 characters.
- Optional '### Notes' section for caveats or TODOs.
- Focus on purpose, responsibilities, key functions/classes, inputs/outputs, dependencies, side effects, and risks.
"""


def generate_summary(
    client: LLMClient,
    diff: str,
    repo_name: str,
    branch: str,
) -> list[str]:
    """
    Generate summary from git diff.

    Pure function - delegates I/O to client.
    """
    prompt = SUMMARY_PROMPT.format(
        repo_name=repo_name,
        branch=branch,
        diff=diff[:120000],  # Truncate to stay within limits
    )

    response = client.complete(prompt, max_tokens=500)

    # Parse JSON response
    try:
        # Remove markdown code blocks if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])

        data = json.loads(cleaned)
        return data.get("summary", ["Changes to the codebase"])
    except json.JSONDecodeError:
        # Fallback if JSON parsing fails
        return ["Changes to the codebase"]


def generate_titles(
    client: LLMClient,
    summary: list[str],
    count: int = 3,
) -> list[str]:
    """
    Generate commit titles from summary.

    Pure function - delegates I/O to client.
    """
    summary_text = "\n".join(f"- {s}" for s in summary)

    prompt = TITLES_PROMPT.format(
        summary_text=summary_text,
        count=count,
    )

    response = client.complete(prompt, max_tokens=500)

    # Parse JSON response
    try:
        # Remove markdown code blocks if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1])

        data = json.loads(cleaned)
        titles = data.get("titles", [])
        return titles[:count]
    except json.JSONDecodeError:
        # Fallback if JSON parsing fails
        return [
            "chore: update staged changes",
            "feat: add new functionality",
            "fix: resolve issues",
        ][:count]


def summarize_source_file(
    client: LLMClient,
    rel_path: str,
    language: str,
    content: str,
) -> str:
    """
    Generate markdown summary of a source file via LLM.

    Pure function - delegates I/O to client.
    """
    prompt = FILE_SUMMARY_PROMPT.format(
        rel_path=rel_path,
        language=language,
        content=content[:120000],  # Truncate to stay within limits
    )

    response = client.complete(prompt, max_tokens=800)

    # Strip surrounding code fences if model added them
    cleaned = response.strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.split("\n")
        if len(lines) > 2:
            cleaned = "\n".join(lines[1:-1]).strip()

    return cleaned
