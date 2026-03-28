"""Public i18n API — mounted WITHOUT auth (like share_public_router).

Endpoints:
  GET /i18n/languages          — active languages list
  GET /i18n/translations/{lang} — translations for a language+namespace
  GET /i18n/version/{lang}     — translation version (for cache busting)
"""

from __future__ import annotations

import hashlib
import json
import logging

import redis as redis_lib
from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Language, Translation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/i18n", tags=["i18n"])

_CACHE_TTL = 3600


def _get_redis():
    return redis_lib.from_url(settings.redis_url)


@router.get("/languages")
async def list_languages():
    """Return active languages, ordered by sort_order."""
    async with async_session() as session:
        result = await session.execute(
            select(Language)
            .where(Language.is_active.is_(True))
            .order_by(Language.sort_order)
        )
        langs = result.scalars().all()
        return [
            {
                "id": lang.id,
                "code": lang.code,
                "name_native": lang.name_native,
                "is_default": lang.is_default,
                "is_system": lang.is_system,
            }
            for lang in langs
        ]


@router.get("/translations/{lang}")
async def get_translations(
    lang: str,
    ns: str = Query(default="ui", description="Namespace: ui or taxonomy"),
    response: Response = None,
):
    """Return translations dict {key: value} for a language and namespace.

    Cached in Redis with ETag support.
    """
    r = _get_redis()
    cache_key = f"i18n:{lang}:{ns}"

    cached = r.get(cache_key)
    if cached:
        data = json.loads(cached)
        etag = hashlib.md5(cached).hexdigest()
        response.headers["ETag"] = f'"{etag}"'
        response.headers["Cache-Control"] = f"public, max-age={_CACHE_TTL}"
        return data

    async with async_session() as session:
        lang_row = await session.execute(
            select(Language).where(Language.code == lang, Language.is_active.is_(True))
        )
        language = lang_row.scalar_one_or_none()
        if not language:
            return {}

        rows = await session.execute(
            select(Translation.key, Translation.value).where(
                Translation.language_id == language.id,
                Translation.namespace == ns,
            )
        )
        data = {row.key: row.value for row in rows}

    serialized = json.dumps(data, ensure_ascii=False)
    r.setex(cache_key, _CACHE_TTL, serialized)

    etag = hashlib.md5(serialized.encode()).hexdigest()
    response.headers["ETag"] = f'"{etag}"'
    response.headers["Cache-Control"] = f"public, max-age={_CACHE_TTL}"

    return data


@router.get("/version/{lang}")
async def get_translation_version(lang: str):
    """Return a version hash for cache busting on the frontend."""
    r = _get_redis()
    version_key = f"i18n:version:{lang}"

    cached_version = r.get(version_key)
    if cached_version:
        return {"version": cached_version.decode()}

    async with async_session() as session:
        lang_row = await session.execute(
            select(Language).where(Language.code == lang, Language.is_active.is_(True))
        )
        language = lang_row.scalar_one_or_none()
        if not language:
            return {"version": "0"}

        from sqlalchemy import func
        result = await session.execute(
            select(func.max(Translation.updated_at)).where(
                Translation.language_id == language.id
            )
        )
        max_updated = result.scalar_one_or_none()
        version = hashlib.md5(str(max_updated).encode()).hexdigest()[:8] if max_updated else "0"

    r.setex(version_key, _CACHE_TTL, version)
    return {"version": version}
