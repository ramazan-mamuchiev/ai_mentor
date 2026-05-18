"""PromptRegistry — in-memory TTL cache for prompt templates from DB.

Loads base prompts (role_id IS NULL) and role overrides from the
prompt_templates table. Resolves overrides via parent_id inheritance.
Falls back to file-based prompts if the DB table is empty.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PromptTemplate

logger = logging.getLogger(__name__)

_TTL = 60.0  # seconds


@dataclass(frozen=True)
class ResolvedPrompt:
    query_type: str
    body: str
    classifier_hint: str
    max_response_tokens: int | None
    rag_top_k: int | None


class PromptRegistry:
    """In-memory cache of prompt templates loaded from DB with TTL."""

    def __init__(self) -> None:
        self._base_cache: dict[str, ResolvedPrompt] = {}
        self._role_cache: dict[tuple[int, str], ResolvedPrompt] = {}
        self._last_refresh: float = 0.0
        self._loaded = False

    async def get_prompt(
        self,
        query_type: str,
        role_ids_by_priority: list[int] | None = None,
        db: AsyncSession | None = None,
    ) -> ResolvedPrompt | None:
        """Get prompt for query_type, with role override from highest-priority role.

        role_ids_by_priority must be sorted descending by Role.priority.
        First role_id that has an override for this query_type wins.
        """
        if db:
            await self._maybe_refresh(db)

        if role_ids_by_priority:
            for role_id in role_ids_by_priority:
                key = (role_id, query_type)
                if key in self._role_cache:
                    return self._role_cache[key]

        return self._base_cache.get(query_type)

    def get_base_prompts(self) -> dict[str, ResolvedPrompt]:
        """Return all base (role_id=NULL) prompts — used for classifier."""
        return dict(self._base_cache)

    def get_query_types(self) -> tuple[str, ...]:
        """Return all known query types from base prompts."""
        return tuple(sorted(self._base_cache.keys()))

    async def refresh(self, db: AsyncSession) -> None:
        """Force-refresh the cache from DB."""
        await self._do_refresh(db)

    async def _maybe_refresh(self, db: AsyncSession) -> None:
        now = time.monotonic()
        if self._loaded and (now - self._last_refresh) < _TTL:
            return
        await self._do_refresh(db)

    async def _do_refresh(self, db: AsyncSession) -> None:
        try:
            result = await db.execute(
                select(PromptTemplate).order_by(PromptTemplate.id)
            )
            rows = list(result.scalars().all())
        except Exception:
            logger.warning("Failed to load prompt_templates from DB", exc_info=True)
            if not self._loaded:
                self._load_fallback_from_files()
            return

        if not rows:
            if not self._loaded:
                self._load_fallback_from_files()
            return

        base_map: dict[str, PromptTemplate] = {}
        override_list: list[PromptTemplate] = []

        for row in rows:
            if row.role_id is None:
                base_map[row.query_type] = row
            else:
                override_list.append(row)

        new_base: dict[str, ResolvedPrompt] = {}
        for qt, tmpl in base_map.items():
            new_base[qt] = ResolvedPrompt(
                query_type=qt,
                body=tmpl.body,
                classifier_hint=tmpl.classifier_hint,
                max_response_tokens=tmpl.max_response_tokens,
                rag_top_k=tmpl.rag_top_k,
            )

        new_role: dict[tuple[int, str], ResolvedPrompt] = {}
        for ovr in override_list:
            base = base_map.get(ovr.query_type)
            resolved = _resolve(base, ovr)
            new_role[(ovr.role_id, ovr.query_type)] = resolved

        self._base_cache = new_base
        self._role_cache = new_role
        self._last_refresh = time.monotonic()
        self._loaded = True
        logger.info(
            "PromptRegistry refreshed: %d base, %d overrides",
            len(new_base), len(new_role),
        )

    def _load_fallback_from_files(self) -> None:
        """Load prompts from .md files as fallback when DB is empty."""
        import re
        prompts_dir = Path(__file__).parent / "prompts"
        tag_re = re.compile(r"<(\w+)>(.*?)</\1>", re.DOTALL)
        skip = {"base", "README", "decompose"}

        for md_file in sorted(prompts_dir.glob("*.md")):
            if md_file.stem in skip:
                continue
            content = md_file.read_text(encoding="utf-8").strip()
            tags = {m.group(1): m.group(2).strip() for m in tag_re.finditer(content)}
            qt = tags.get("task_type", md_file.stem)

            max_tokens = None
            if "max_response_tokens" in tags:
                try:
                    max_tokens = int(tags["max_response_tokens"])
                except ValueError:
                    pass

            top_k = None
            if "rag_top_k" in tags:
                try:
                    top_k = int(tags["rag_top_k"])
                except ValueError:
                    pass

            self._base_cache[qt] = ResolvedPrompt(
                query_type=qt,
                body=content,
                classifier_hint=tags.get("classifier_hint", ""),
                max_response_tokens=max_tokens,
                rag_top_k=top_k,
            )

        self._loaded = True
        self._last_refresh = time.monotonic()
        logger.info(
            "PromptRegistry fallback from files: %d types", len(self._base_cache)
        )


def _resolve(base: PromptTemplate | None, override: PromptTemplate) -> ResolvedPrompt:
    """Resolve an override with its parent (base) template via inheritance."""
    if base is None:
        return ResolvedPrompt(
            query_type=override.query_type,
            body=override.body,
            classifier_hint=override.classifier_hint,
            max_response_tokens=override.max_response_tokens,
            rag_top_k=override.rag_top_k,
        )
    return ResolvedPrompt(
        query_type=override.query_type,
        body=override.body or base.body,
        classifier_hint=override.classifier_hint or base.classifier_hint,
        max_response_tokens=override.max_response_tokens or base.max_response_tokens,
        rag_top_k=override.rag_top_k or base.rag_top_k,
    )


prompt_registry = PromptRegistry()
