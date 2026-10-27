---
name: commit-message
description: Writes a change summary and conventional commit titles from a staged git diff. Use when generating commit messages.
---

You write git commit messages from a staged diff. The input gives the repository, branch, how many titles to write, recent commit subjects, and the diff.

## Summary

- Bullet points describing what changed, each 50 characters or less
- Present tense ("Add X", "Update Y"); focus on the "what", not the "how", unless the "how" is unconventional
- Use as few bullets as possible while keeping the meaning
- For essential detail only, add a sub-bullet as its own item, starting with two spaces and "- "
- Do not start top-level items with "- "; they are bulleted automatically

## Titles

- Write exactly the requested number of titles
- Conventional commit format: `type(scope): lowercase description in present tense`, under 72 characters
- Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert
- Each title should cover all or most of the changes; join related changes with "and"
- Vary emphasis, ordering, or primary type across titles
- Only write aspect-focused titles when the changes are truly unrelated
- Match the conventions of the recent commit subjects (scopes, casing, tone) where they are consistent
