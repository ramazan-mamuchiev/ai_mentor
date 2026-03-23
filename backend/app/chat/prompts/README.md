# Prompt Templates

This directory contains prompt templates for the IPCodex RAG chat. The system automatically scans all `.md` files at startup and registers them as query types.

## Adding a New Query Type

**One step**: create a `<type_name>.md` file in this directory.

### Required File Structure

```xml
<task_type>type_name</task_type>

<classifier_hint>description for the LLM classifier with example queries in parentheses</classifier_hint>

<instructions>
Instructions for the LLM when answering this type of question.
</instructions>
```

### Tags

| Tag | Required | Description |
|-----|:---:|---|
| `<task_type>` | Yes | Unique type name (latin, snake_case). Used as identifier in code, debug panel, and billing |
| `<classifier_hint>` | Yes | Single line — category description for the LLM classifier. Include example queries in both RU and EN |
| `<instructions>` | Yes | Instructions for the LLM. Define response style, structure, and verbosity level |

### Example: Adding a `migration` Type

Create file `migration.md`:

```xml
<task_type>migration</task_type>

<classifier_hint>question about upgrading, migrating between versions, or API changes ("how to migrate from v1 to v2", "что изменилось в новой версии")</classifier_hint>

<instructions>
The user is asking about migrating between API versions, firmware upgrades, or system transitions.

- Focus on breaking changes, deprecated endpoints, and migration paths.
- Structure: What changed → Migration steps → Code changes needed → Warnings.
- If the documentation contains changelogs or migration guides, reference them.
- Verbosity: Medium-High. Be thorough about breaking changes.
</instructions>
```

After creating the file, restart the backend. No code changes required.

## Special Files

| File | Purpose |
|------|---------|
| `base.md` | Shared prompt prefix (role, constraints, format rules). Prepended to every type-specific prompt |
| `README.md` | This file. Ignored by the loader |

## How It Works

```
User query
  │
  ├─ 1. LLM Classifier (gemini-2.0-flash, ~100ms)
  │     Classifier prompt is built automatically
  │     from <classifier_hint> tags in all files in this directory
  │     → Result: "overview" / "technical" / "code" / ...
  │
  └─ 2. System Prompt Assembly
        base.md + {query_type}.md → system prompt for the main LLM
```

## Guidelines for Writing Prompts

1. **`<classifier_hint>`** — keep it short, with 2-3 example queries. Include examples in both languages (RU/EN)
2. **`<instructions>`** — write in English (LLMs follow English instructions more reliably)
3. **Response structure** — specify explicitly (e.g. "Structure: Overview → Details → Summary")
4. **Verbosity** — specify the level: Low, Medium, High
5. **Do not duplicate** rules from `base.md` — they are already prepended automatically

## Current Types

| Type | File | When Used |
|------|------|-----------|
| `overview` | `overview.md` | General questions about a product/system |
| `technical` | `technical.md` | Specific API/protocol questions |
| `code` | `code.md` | Code generation requests |
| `comparison` | `comparison.md` | Comparing products/versions |
| `troubleshooting` | `troubleshooting.md` | Errors and debugging |
| `chitchat` | `chitchat.md` | Greetings and meta-questions |
