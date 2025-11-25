Based on the following summary of changes, generate conventional commit message titles.

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

Return ONLY valid JSON.

