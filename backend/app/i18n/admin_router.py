"""Admin i18n API — languages CRUD, translations CRUD, auto-translate triggers."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

import redis as redis_lib
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.config import settings
from app.database import get_session
from app.models import Language, Tenant, Translation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/i18n", tags=["admin-i18n"])


def _get_redis():
    return redis_lib.from_url(settings.redis_url)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class LanguageCreate(BaseModel):
    code: str
    name_native: str
    is_default: bool = False
    sort_order: int = 0

class LanguagePatch(BaseModel):
    name_native: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = None

class TranslationUpsert(BaseModel):
    namespace: str = "ui"
    key: str
    value: str

class BulkTranslationUpsert(BaseModel):
    items: list[TranslationUpsert]


# ---------------------------------------------------------------------------
# Languages CRUD
# ---------------------------------------------------------------------------

@router.get("/languages")
async def list_languages(
    modified_by: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    q = select(Language).order_by(Language.sort_order)
    if modified_by is not None:
        q = q.where(Language.modified_by == modified_by)
    result = await session.execute(q)
    langs = result.scalars().all()

    modifier_ids = {lang.modified_by for lang in langs if lang.modified_by}
    modifiers: dict[uuid.UUID, Tenant] = {}
    if modifier_ids:
        mod_result = await session.execute(
            select(Tenant).where(Tenant.id.in_(modifier_ids))
        )
        modifiers = {t.id: t for t in mod_result.scalars()}

    output = []
    for lang in langs:
        count_result = await session.execute(
            select(func.count()).select_from(Translation).where(
                Translation.language_id == lang.id,
                Translation.namespace != "meta",
            )
        )
        total_keys = count_result.scalar() or 0
        mod = modifiers.get(lang.modified_by)
        output.append({
            "id": lang.id,
            "code": lang.code,
            "name_native": lang.name_native,
            "is_default": lang.is_default,
            "is_active": lang.is_active,
            "is_system": lang.is_system,
            "sort_order": lang.sort_order,
            "total_keys": total_keys,
            "created_at": lang.created_at.isoformat() if lang.created_at else None,
            "modified_by_email": mod.email if mod else None,
            "modified_by_name": mod.name if mod else None,
            "modified_at": lang.modified_at.isoformat() if lang.modified_at else None,
        })
    return output


@router.post("/languages", status_code=201)
async def create_language(
    body: LanguageCreate,
    current_user: Tenant = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    existing = await session.execute(
        select(Language).where(Language.code == body.code)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Language '{body.code}' already exists")

    lang = Language(
        code=body.code,
        name_native=body.name_native,
        is_default=body.is_default,
        sort_order=body.sort_order,
        is_system=False,
        modified_by=current_user.id,
        modified_at=datetime.now(timezone.utc),
    )
    session.add(lang)
    await session.commit()
    await session.refresh(lang)
    return {"id": lang.id, "code": lang.code, "name_native": lang.name_native}


@router.patch("/languages/{language_id}")
async def patch_language(
    language_id: int,
    body: LanguagePatch,
    current_user: Tenant = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    lang = await session.get(Language, language_id)
    if not lang:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Language not found")

    if body.name_native is not None:
        lang.name_native = body.name_native
    if body.is_default is not None:
        lang.is_default = body.is_default
    if body.is_active is not None:
        lang.is_active = body.is_active
    if body.sort_order is not None:
        lang.sort_order = body.sort_order

    lang.modified_by = current_user.id
    lang.modified_at = datetime.now(timezone.utc)

    await session.commit()
    return {"id": lang.id, "code": lang.code, "status": "updated"}


@router.delete("/languages/{language_id}", status_code=204)
async def delete_language(language_id: int, session: AsyncSession = Depends(get_session)):
    lang = await session.get(Language, language_id)
    if not lang:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Language not found")
    if lang.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot delete system language")

    await session.delete(lang)
    await session.commit()

    r = _get_redis()
    for ns in ("ui", "taxonomy"):
        r.delete(f"i18n:{lang.code}:{ns}")
    r.delete(f"i18n:version:{lang.code}")


# ---------------------------------------------------------------------------
# Translations CRUD
# ---------------------------------------------------------------------------

@router.get("/translations/{language_id}")
async def list_translations(
    language_id: int,
    ns: str = Query("ui"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    search: str | None = None,
    missing_only: bool = False,
    modified_by: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    lang = await session.get(Language, language_id)
    if not lang:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Language not found")

    q = select(Translation).where(
        Translation.language_id == language_id,
        Translation.namespace == ns,
    )
    count_q = select(func.count()).select_from(Translation).where(
        Translation.language_id == language_id,
        Translation.namespace == ns,
    )

    if search:
        like = f"%{search}%"
        q = q.where(Translation.key.ilike(like) | Translation.value.ilike(like))
        count_q = count_q.where(Translation.key.ilike(like) | Translation.value.ilike(like))

    if modified_by is not None:
        q = q.where(Translation.modified_by == modified_by)
        count_q = count_q.where(Translation.modified_by == modified_by)

    total_result = await session.execute(count_q)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    q = q.order_by(Translation.key).offset(offset).limit(page_size)
    result = await session.execute(q)
    raw_items = result.scalars().all()

    modifier_ids = {t.modified_by for t in raw_items if t.modified_by}
    modifiers: dict[uuid.UUID, Tenant] = {}
    if modifier_ids:
        mod_result = await session.execute(
            select(Tenant).where(Tenant.id.in_(modifier_ids))
        )
        modifiers = {t.id: t for t in mod_result.scalars()}

    items = []
    for t in raw_items:
        mod = modifiers.get(t.modified_by)
        items.append({
            "id": t.id,
            "key": t.key,
            "value": t.value,
            "is_system": t.is_system,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            "is_modified": t.is_modified,
            "modified_by_email": mod.email if mod else None,
            "modified_by_name": mod.name if mod else None,
            "modified_at": t.modified_at.isoformat() if t.modified_at else None,
        })

    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.put("/translations/{language_id}")
async def upsert_translation(
    language_id: int,
    body: TranslationUpsert,
    current_user: Tenant = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    lang = await session.get(Language, language_id)
    if not lang:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Language not found")

    now = datetime.now(timezone.utc)

    existing = await session.execute(
        select(Translation).where(
            Translation.language_id == language_id,
            Translation.namespace == body.namespace,
            Translation.key == body.key,
        )
    )
    t = existing.scalar_one_or_none()
    if t:
        t.value = body.value
        t.is_modified = True
        t.modified_by = current_user.id
        t.modified_at = now
    else:
        t = Translation(
            language_id=language_id,
            namespace=body.namespace,
            key=body.key,
            value=body.value,
            is_modified=True,
            modified_by=current_user.id,
            modified_at=now,
        )
        session.add(t)

    await session.commit()

    r = _get_redis()
    r.delete(f"i18n:{lang.code}:{body.namespace}")
    r.delete(f"i18n:version:{lang.code}")

    return {"status": "ok"}


@router.post("/translations/{language_id}/bulk")
async def bulk_upsert_translations(
    language_id: int,
    body: BulkTranslationUpsert,
    current_user: Tenant = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    lang = await session.get(Language, language_id)
    if not lang:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Language not found")

    now = datetime.now(timezone.utc)

    for item in body.items:
        existing = await session.execute(
            select(Translation).where(
                Translation.language_id == language_id,
                Translation.namespace == item.namespace,
                Translation.key == item.key,
            )
        )
        t = existing.scalar_one_or_none()
        if t:
            t.value = item.value
            t.is_modified = True
            t.modified_by = current_user.id
            t.modified_at = now
        else:
            session.add(Translation(
                language_id=language_id,
                namespace=item.namespace,
                key=item.key,
                value=item.value,
                is_modified=True,
                modified_by=current_user.id,
                modified_at=now,
            ))

    await session.commit()

    r = _get_redis()
    namespaces = {item.namespace for item in body.items}
    for ns in namespaces:
        r.delete(f"i18n:{lang.code}:{ns}")
    r.delete(f"i18n:version:{lang.code}")

    return {"status": "ok", "count": len(body.items)}


# ---------------------------------------------------------------------------
# Auto-translate triggers
# ---------------------------------------------------------------------------

@router.post("/languages/{language_id}/translate")
async def trigger_auto_translate(language_id: int, session: AsyncSession = Depends(get_session)):
    """Trigger background auto-translation for all missing keys."""
    if not settings.auto_translate_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Auto-translation is disabled")

    lang = await session.get(Language, language_id)
    if not lang:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Language not found")

    from app.celery_app import translate_all_for_language_task
    task = translate_all_for_language_task.delay(language_id)

    return {"task_id": task.id, "status": "started"}


@router.get("/languages/{language_id}/translate/progress")
async def get_translate_progress(language_id: int):
    """Poll translation progress from Redis."""
    r = _get_redis()
    progress_key = f"translate_progress:{language_id}"
    data = r.hgetall(progress_key)
    if not data:
        return {"status": "idle"}
    return {
        "total": int(data.get(b"total", 0)),
        "done": int(data.get(b"done", 0)),
        "errors": int(data.get(b"errors", 0)),
        "status": data.get(b"status", b"unknown").decode(),
    }


# ---------------------------------------------------------------------------
# Export / Import
# ---------------------------------------------------------------------------

@router.get("/translations/{language_id}/export")
async def export_translations(
    language_id: int,
    ns: str = Query("ui"),
    session: AsyncSession = Depends(get_session),
):
    lang = await session.get(Language, language_id)
    if not lang:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Language not found")

    result = await session.execute(
        select(Translation.key, Translation.value).where(
            Translation.language_id == language_id,
            Translation.namespace == ns,
        ).order_by(Translation.key)
    )
    data = {r.key: r.value for r in result}

    from fastapi.responses import Response
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={lang.code}_{ns}.json"},
    )


@router.post("/translations/{language_id}/import")
async def import_translations(
    language_id: int,
    ns: str = Query("ui"),
    session: AsyncSession = Depends(get_session),
):
    """Import translations from JSON body {key: value}."""
    raise HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Use bulk upsert endpoint instead")
