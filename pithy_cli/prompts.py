SUMMARY_PROMPT = """Analyze the following git diff and provide a concise summary of the changes.

Repository: {repo_name}
Branch: {branch}

Staged changes (git diff):
```
{diff}
```

REQUIREMENTS:
1. Create bullet points describing what was changed or done
2. Each bullet point MUST be 50 characters or less
3. Add sub-bullets (indented with "  - ") for essential details only
4. Focus on concrete changes and their purpose
5. Use present tense (e.g., "Add feature X", "Update config Y")
6. Prioritize clarity and brevity
7. Minimize the number of bullet points while retaining semantic context
8. Focus on the "what" of the change, not the "how", unless "how" is unconventional
9. Describe the change precisely on what it does

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
5. Each title should capture ALL or MOST changes when possible
6. Vary the emphasis, ordering, or primary type across titles
7. Use "and" to combine related changes (e.g., "add X and update Y")
8. Only generate separate aspect-focused titles if changes are truly unrelated

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
