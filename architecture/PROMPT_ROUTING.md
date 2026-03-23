# IPCodex — Prompt Routing Architecture

> Part of [IPCodex Architecture](PLAN.md) | See also: [Data Flows](FLOWS.md), [API Reference](API.md)

---

## Overview

Instead of a single universal system prompt, IPCodex uses **prompt routing** — a lightweight LLM classifier determines the type of user question, and the system selects a specialized prompt optimized for that type.

```
User query: "расскажи про DataLen"
       │
       ▼
┌─────────────────────────────────────────────────┐
│  LLM Classifier (gemini-2.0-flash, ~100ms)      │
│  "Classify into: overview | technical | code..." │
│  → "overview"                                    │
└─────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│  Prompt Assembly                                 │
│  base.md (role + constraints + format rules)     │
│  + overview.md (task-specific instructions)      │
│  = system prompt for main LLM                    │
└─────────────────────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│  Main LLM (gemini-2.5-flash)                     │
│  system: base + overview instructions            │
│  context: documentation chunks                   │
│  query: user question                            │
│  → comprehensive product overview                │
└─────────────────────────────────────────────────┘
```

## Why Not One Prompt?

A single prompt tries to satisfy conflicting goals:
- **Strict grounding** (don't hallucinate) vs **helpful overview** (summarize everything)
- **Concise API answers** vs **thorough product descriptions**
- **Code generation** (use general knowledge) vs **factual answers** (only from docs)

Per-type prompts resolve these conflicts by giving each type its own verbosity, structure, and rules.

## File-Based Auto-Discovery

Prompt types are **not hardcoded**. The system auto-discovers them from `backend/app/chat/prompts/`:

```
prompts/
├── base.md              ← shared: role, constraints, format rules
├── overview.md          ← type: general product/system questions
├── technical.md         ← type: API/protocol specifics
├── code.md              ← type: code generation requests
├── comparison.md        ← type: comparing products/versions
├── troubleshooting.md   ← type: errors and debugging
├── chitchat.md          ← type: greetings, meta-questions
└── README.md            ← documentation (ignored by loader)
```

### How Auto-Discovery Works

At startup, `_load_prompts()` in `chat/rag.py`:

1. Reads `base.md` → shared prompt prefix
2. Scans all `*.md` files (excluding `base.md` and `README.md`)
3. Parses XML tags from each file:
   - `<task_type>` → query type identifier (e.g. `"overview"`)
   - `<classifier_hint>` → description for the LLM classifier
   - `<instructions>` → task-specific LLM instructions
4. Builds `QUERY_TYPES` tuple, `_TYPE_PROMPTS` dict, `_CLASSIFIER_HINTS` dict
5. Generates `_CLASSIFY_PROMPT_TEMPLATE` from all hints

### Adding a New Type

Create one `.md` file. No code changes required. See `prompts/README.md` for the template.

## Classifier

### Model & Cost

| Parameter | Value |
|-----------|-------|
| Model | `gemini-2.0-flash` (configurable via `CLASSIFIER_MODEL`) |
| Temperature | 0 |
| Max tokens | 20 |
| Reasoning | none |
| Typical latency | 80–150ms |
| Typical tokens | ~100 input, ~5 output |
| Cost per call | ~$0.00001 (COGS) |

### Prompt Structure

Generated dynamically from `<classifier_hint>` tags:

```
Classify the user question into exactly ONE category.
Return ONLY the category name, nothing else.

Categories:
- overview: general question about a product, system, or technology (...)
- technical: specific API/protocol/configuration question (...)
- code: request to write or generate code (...)
- comparison: comparing products, versions, or features (...)
- troubleshooting: error, problem, or debugging question (...)
- chitchat: greeting, off-topic, or meta-question (...)

Question: {query}
Category:
```

### Fallback

If the classifier fails (network error, timeout, unexpected response), the system defaults to `"overview"` — the most general and safe type.

### Billing

Each classification call is tracked separately:
- `usage_log.action = "query_classify"` — separate from `"chat_completion"`
- Token counts: `classify_prompt_tokens`, `classify_completion_tokens`
- Model and timing in debug panel

## System Prompt Assembly

```python
system_prompt = base.md + "\n\n" + {query_type}.md
```

### base.md Contents

- `<role>` — IPCodex AI identity and grounding statement
- `<constraints>` — 10 rules (factual grounding, no hallucination, use all sources)
- `<format_rules>` — language matching, markdown formatting, no source citations

### Type-Specific Contents

Each type file adds `<instructions>` that control:
- **Response structure** (e.g. "Overview → Features → Architecture" for overview)
- **Verbosity level** (Low for technical, Medium-High for overview)
- **Special behaviors** (e.g. "MUST generate code" for code type)

## Debug Panel

The debug panel shows classification results:

| Field | Description |
|-------|-------------|
| Query type | Classified type (e.g. "overview") |
| Prompt | Token count for classifier prompt |
| Completion | Token count for classifier response |
| Total classify | Total tokens used |
| Model | Classifier model name |
| Time | Classification latency |

## Configuration

| Env Variable | Default | Description |
|-------------|---------|-------------|
| `CLASSIFIER_ENABLED` | `true` | Enable/disable LLM classification |
| `CLASSIFIER_MODEL` | `gemini-2.0-flash` | Model for classification |

When `CLASSIFIER_ENABLED=false`, all queries use `"overview"` type (backward compatible).

## Future Improvements

1. **Prompt overrides in DB** — table `prompt_templates` for editing without deploy
2. **Admin UI** — edit prompts with live preview and test
3. **A/B testing** — multiple active versions per type, track quality metrics
4. **DSPy optimization** — automatic prompt tuning from example Q&A pairs
5. **Semantic Router** — embedding-based classification without LLM call (~10ms)
