"""LLM provider abstraction for commit message generation."""

import json
from enum import Enum
from typing import Protocol, Optional
from dataclasses import dataclass
from pathlib import Path

from .prompt import load_prompt
from .init import find_git_root


class LLMProvider(str, Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


class ModelType(str, Enum):
    """Model speed/capability trade-off."""
    REGULAR = "regular"  # Higher capability, slower/more expensive
    FAST = "fast"       # Lower capability, faster/cheaper


class LLMClient(Protocol):
    """Protocol for LLM clients."""

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        """Generate completion from prompt."""
        ...


@dataclass
class AnthropicClient:
    """Anthropic Claude client."""
    api_key: str
    model_type: ModelType = ModelType.REGULAR

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        from anthropic import Anthropic

        client = Anthropic(api_key=self.api_key)

        model = "claude-sonnet-4-5-20250929"
        if self.model_type == ModelType.FAST:
            model = "claude-haiku-4-5-20251001"

        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text


@dataclass
class OpenAIClient:
    """OpenAI GPT client."""
    api_key: str
    model_type: ModelType = ModelType.REGULAR

    def complete(self, prompt: str, max_tokens: int = 500) -> str:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)

        model = "gpt-5-mini-2025-08-07"
        if self.model_type == ModelType.FAST:
            model = "gpt-5-nano-2025-08-07"

        response = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.choices[0].message.content


def create_llm_client(
    provider: LLMProvider,
    api_key: str,
    model_type: ModelType = ModelType.REGULAR,
) -> LLMClient:
    """Factory function to create LLM client."""
    if provider == LLMProvider.ANTHROPIC:
        return AnthropicClient(api_key=api_key, model_type=model_type)
    elif provider == LLMProvider.OPENAI:
        return OpenAIClient(api_key=api_key, model_type=model_type)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def generate_summary(
    client: LLMClient,
    diff: str,
    repo_name: str,
    branch: str,
    git_root: Optional[Path] = None,
) -> list[str]:
    """
    Generate summary from git diff.

    Pure function - delegates I/O to client.
    """
    if git_root is None:
        git_root = find_git_root()

    prompt_template = load_prompt("commit-summary", git_root)
    prompt = prompt_template.format(
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
    git_root: Optional[Path] = None,
) -> list[str]:
    """
    Generate commit titles from summary.

    Pure function - delegates I/O to client.
    """
    if git_root is None:
        git_root = find_git_root()

    summary_text = "\n".join(f"- {s}" for s in summary)

    prompt_template = load_prompt("commit-titles", git_root)
    prompt = prompt_template.format(
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
    git_root: Optional[Path] = None,
) -> str:
    """
    Generate markdown summary of a source file via LLM.

    Pure function - delegates I/O to client.
    """
    if git_root is None:
        git_root = find_git_root()

    prompt_template = load_prompt("file-summary", git_root)
    prompt = prompt_template.format(
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
