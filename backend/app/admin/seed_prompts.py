"""Seed prompt_templates from .md files in backend/app/chat/prompts/.

Called at application startup (lifespan). Parses the same tag format as
rag.py _load_prompts() and upserts base prompts (role_id=NULL, is_system=true).

- New prompts are inserted.
- Existing prompts that were NOT manually customized (is_customized=false)
  are updated from the file.
- Manually customized prompts (is_customized=true) are left untouched.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "chat" / "prompts"
_TAG_RE = re.compile(r"<(\w+)>(.*?)</\1>", re.DOTALL)

_SKIP_STEMS = {"base", "README", "decompose"}


def _parse_prompt_file(path: Path) -> dict | None:
    """Parse a prompt .md file and extract fields."""
    content = path.read_text(encoding="utf-8").strip()
    tags = {m.group(1): m.group(2).strip() for m in _TAG_RE.finditer(content)}

    query_type = tags.get("task_type", path.stem)
    classifier_hint = tags.get("classifier_hint", "")

    max_tokens: int | None = None
    if "max_response_tokens" in tags:
        try:
            max_tokens = int(tags["max_response_tokens"])
        except ValueError:
            pass

    rag_top_k: int | None = None
    if "rag_top_k" in tags:
        try:
            rag_top_k = int(tags["rag_top_k"])
        except ValueError:
            pass

    return {
        "query_type": query_type,
        "body": content,
        "classifier_hint": classifier_hint,
        "max_response_tokens": max_tokens,
        "rag_top_k": rag_top_k,
    }


async def seed_prompts(db: AsyncSession) -> int:
    """Upsert base prompt templates from .md files. Returns count of upserted rows."""
    if not _PROMPTS_DIR.exists():
        logger.warning("Prompts directory not found: %s", _PROMPTS_DIR)
        return 0

    count = 0
    for md_file in sorted(_PROMPTS_DIR.glob("*.md")):
        if md_file.stem in _SKIP_STEMS:
            continue

        parsed = _parse_prompt_file(md_file)
        if not parsed:
            continue

        await db.execute(
            text("""
                INSERT INTO prompt_templates
                    (query_type, role_id, is_system, is_customized, body,
                     classifier_hint, max_response_tokens, rag_top_k)
                VALUES
                    (:query_type, NULL, TRUE, FALSE, :body,
                     :classifier_hint, :max_response_tokens, :rag_top_k)
                ON CONFLICT (query_type, role_id)
                DO UPDATE SET
                    body = EXCLUDED.body,
                    classifier_hint = EXCLUDED.classifier_hint,
                    max_response_tokens = EXCLUDED.max_response_tokens,
                    rag_top_k = EXCLUDED.rag_top_k,
                    updated_at = NOW()
                WHERE prompt_templates.is_customized = FALSE
            """),
            parsed,
        )
        count += 1

    await db.commit()
    logger.info("Seeded %d base prompt templates from files", count)
    return count
