"""LLM provider abstraction for commit message generation."""

import json
from enum import Enum
from typing import Protocol
from dataclasses import dataclass

from .prompts import SUMMARY_PROMPT, TITLES_PROMPT, FILE_SUMMARY_PROMPT


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
            model="claude-sonnet-4-5-20250929",
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
            model="gpt-5-mini",
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


# Prompts moved to prompts.py


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
