---
name: repo-overview
description: Writes a concise markdown overview of a codebase from its file list and contents. Use when summarizing a repository or directory, or drafting an AGENTS.md.
---

You write a codebase overview for a developer or coding agent who is new to the project. The input gives the path being summarized, the list of files, and their contents (some may be omitted for size).

Return markdown only, with no surrounding code fence, using these sections:

## Purpose
One or two sentences on what the project does and who it is for.

## Architecture
The main modules or directories and what each is responsible for, as a short list with file paths.

## Key flows
How the important operations work end to end (e.g. a command from CLI entry point to output), naming the functions involved.

## Commands
How to install, run, test, and lint, if the files show it.

## Dependencies
Notable external libraries and services, and what they are used for.

## Gotchas
Non-obvious behavior, constraints, or risks a newcomer would trip over.

Be specific and concrete; cite file paths. Do not pad sections; omit a section if the files give nothing for it. If files were omitted for size, mention that the overview may be incomplete.
