Analyze the following git diff and provide a concise summary of the changes.

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

Return ONLY valid JSON, no other text or markdown.

