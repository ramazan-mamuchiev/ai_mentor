"""Admin taxonomy API — categories, tags, search keywords CRUD."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.database import get_session
from app.models import Product, ProductCategory, ProductTagLink, SearchKeyword, Tag, Tenant, Translation

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/taxonomy", tags=["admin-taxonomy"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CategoryCreate(BaseModel):
    slug: str
    sort_order: int = 0
    labels: dict[str, str] = {}

class CategoryPatch(BaseModel):
    sort_order: int | None = None
    labels: dict[str, str] | None = None

class TagCreate(BaseModel):
    slug: str
    labels: dict[str, str] = {}

class TagPatch(BaseModel):
    labels: dict[str, str] | None = None

class SearchKeywordCreate(BaseModel):
    product_id: int
    keyword: str

class ReorderItem(BaseModel):
    id: int
    sort_order: int

class BulkReorder(BaseModel):
    items: list[ReorderItem]


# ---------------------------------------------------------------------------
# Categories CRUD
# ---------------------------------------------------------------------------

@router.get("/categories")
async def list_categories(
    modified_by: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    q = select(ProductCategory).order_by(ProductCategory.sort_order)
    if modified_by is not None:
        q = q.where(ProductCategory.modified_by == modified_by)
    result = await session.execute(q)
    categories = result.scalars().all()

    modifier_ids = {cat.modified_by for cat in categories if cat.modified_by}
    modifiers: dict[uuid.UUID, Tenant] = {}
    if modifier_ids:
        mod_result = await session.execute(
            select(Tenant).where(Tenant.id.in_(modifier_ids))
        )
        modifiers = {t.id: t for t in mod_result.scalars()}

    output = []
    for cat in categories:
        product_count = await session.execute(
            select(func.count()).select_from(Product).where(Product.category_id == cat.id)
        )
        count = product_count.scalar() or 0

        labels_q = await session.execute(
            text(
                "SELECT l.code, t.value FROM translations t "
                "JOIN languages l ON l.id = t.language_id "
                "WHERE t.namespace = 'taxonomy' AND t.key = :key"
            ),
            {"key": f"category.{cat.slug}"},
        )
        labels = {row.code: row.value for row in labels_q}

        mod = modifiers.get(cat.modified_by)
        output.append({
            "id": cat.id,
            "slug": cat.slug,
            "sort_order": cat.sort_order,
            "is_system": cat.is_system,
            "product_count": count,
            "labels": labels,
            "modified_by_email": mod.email if mod else None,
            "modified_by_name": mod.name if mod else None,
            "modified_at": cat.modified_at.isoformat() if cat.modified_at else None,
        })
    return output


@router.post("/categories", status_code=201)
async def create_category(
    body: CategoryCreate,
    current_user: Tenant = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    existing = await session.execute(
        select(ProductCategory).where(ProductCategory.slug == body.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Category '{body.slug}' already exists")

    cat = ProductCategory(
        slug=body.slug,
        sort_order=body.sort_order,
        is_system=False,
        modified_by=current_user.id,
        modified_at=datetime.now(timezone.utc),
    )
    session.add(cat)
    await session.commit()
    await session.refresh(cat)

    if body.labels:
        await _save_labels(session, "category", body.slug, body.labels, modified_by=current_user.id)

    return {"id": cat.id, "slug": cat.slug}


@router.patch("/categories/{category_id}")
async def patch_category(
    category_id: int,
    body: CategoryPatch,
    current_user: Tenant = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    cat = await session.get(ProductCategory, category_id)
    if not cat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")

    if body.sort_order is not None:
        cat.sort_order = body.sort_order

    cat.modified_by = current_user.id
    cat.modified_at = datetime.now(timezone.utc)

    await session.commit()

    if body.labels is not None:
        await _save_labels(session, "category", cat.slug, body.labels, modified_by=current_user.id)

    return {"id": cat.id, "slug": cat.slug, "status": "updated"}


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: int, session: AsyncSession = Depends(get_session)):
    cat = await session.get(ProductCategory, category_id)
    if not cat:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    if cat.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot delete system category")

    await session.delete(cat)
    await session.execute(
        delete(Translation).where(
            Translation.namespace == "taxonomy",
            Translation.key == f"category.{cat.slug}",
        )
    )
    await session.commit()


@router.post("/categories/reorder")
async def reorder_categories(body: BulkReorder, session: AsyncSession = Depends(get_session)):
    for item in body.items:
        cat = await session.get(ProductCategory, item.id)
        if cat:
            cat.sort_order = item.sort_order
    await session.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Tags CRUD
# ---------------------------------------------------------------------------

@router.get("/tags")
async def list_tags(
    modified_by: uuid.UUID | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    q = select(Tag).order_by(Tag.slug)
    if modified_by is not None:
        q = q.where(Tag.modified_by == modified_by)
    result = await session.execute(q)
    tags = result.scalars().all()

    modifier_ids = {tag.modified_by for tag in tags if tag.modified_by}
    modifiers: dict[uuid.UUID, Tenant] = {}
    if modifier_ids:
        mod_result = await session.execute(
            select(Tenant).where(Tenant.id.in_(modifier_ids))
        )
        modifiers = {t.id: t for t in mod_result.scalars()}

    output = []
    for tag in tags:
        product_count = await session.execute(
            select(func.count()).select_from(ProductTagLink).where(ProductTagLink.tag_id == tag.id)
        )
        count = product_count.scalar() or 0

        labels_q = await session.execute(
            text(
                "SELECT l.code, t.value FROM translations t "
                "JOIN languages l ON l.id = t.language_id "
                "WHERE t.namespace = 'taxonomy' AND t.key = :key"
            ),
            {"key": f"tag.{tag.slug}"},
        )
        labels = {row.code: row.value for row in labels_q}

        mod = modifiers.get(tag.modified_by)
        output.append({
            "id": tag.id,
            "slug": tag.slug,
            "is_system": tag.is_system,
            "product_count": count,
            "labels": labels,
            "modified_by_email": mod.email if mod else None,
            "modified_by_name": mod.name if mod else None,
            "modified_at": tag.modified_at.isoformat() if tag.modified_at else None,
        })
    return output


@router.post("/tags", status_code=201)
async def create_tag(
    body: TagCreate,
    current_user: Tenant = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    existing = await session.execute(select(Tag).where(Tag.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, f"Tag '{body.slug}' already exists")

    tag = Tag(
        slug=body.slug,
        is_system=False,
        modified_by=current_user.id,
        modified_at=datetime.now(timezone.utc),
    )
    session.add(tag)
    await session.commit()
    await session.refresh(tag)

    if body.labels:
        await _save_labels(session, "tag", body.slug, body.labels, modified_by=current_user.id)

    return {"id": tag.id, "slug": tag.slug}


@router.patch("/tags/{tag_id}")
async def patch_tag(
    tag_id: int,
    body: TagPatch,
    current_user: Tenant = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tag not found")

    tag.modified_by = current_user.id
    tag.modified_at = datetime.now(timezone.utc)
    await session.commit()

    if body.labels is not None:
        await _save_labels(session, "tag", tag.slug, body.labels, modified_by=current_user.id)

    return {"id": tag.id, "slug": tag.slug, "status": "updated"}


@router.delete("/tags/{tag_id}", status_code=204)
async def delete_tag(tag_id: int, session: AsyncSession = Depends(get_session)):
    tag = await session.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tag not found")
    if tag.is_system:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot delete system tag")

    await session.delete(tag)
    await session.execute(
        delete(Translation).where(
            Translation.namespace == "taxonomy",
            Translation.key == f"tag.{tag.slug}",
        )
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Search Keywords
# ---------------------------------------------------------------------------

@router.get("/keywords")
async def list_keywords(
    product_id: int | None = None,
    session: AsyncSession = Depends(get_session),
):
    q = select(SearchKeyword)
    if product_id is not None:
        q = q.where(SearchKeyword.product_id == product_id)
    q = q.order_by(SearchKeyword.product_id, SearchKeyword.keyword)

    result = await session.execute(q)
    return [
        {
            "id": kw.id,
            "product_id": kw.product_id,
            "keyword": kw.keyword,
            "is_system": kw.is_system,
        }
        for kw in result.scalars()
    ]


@router.post("/keywords", status_code=201)
async def create_keyword(body: SearchKeywordCreate, session: AsyncSession = Depends(get_session)):
    kw = SearchKeyword(
        product_id=body.product_id,
        keyword=body.keyword,
        is_system=False,
    )
    session.add(kw)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Keyword already exists for this product")
    await session.refresh(kw)
    return {"id": kw.id, "product_id": kw.product_id, "keyword": kw.keyword}


@router.delete("/keywords/{keyword_id}", status_code=204)
async def delete_keyword(keyword_id: int, session: AsyncSession = Depends(get_session)):
    kw = await session.get(SearchKeyword, keyword_id)
    if not kw:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Keyword not found")
    await session.delete(kw)
    await session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _save_labels(
    session: AsyncSession,
    prefix: str,
    slug: str,
    labels: dict[str, str],
    modified_by: uuid.UUID | None = None,
):
    """Save taxonomy translation labels for a category/tag."""
    from app.models import Language

    now = datetime.now(timezone.utc)

    for lang_code, value in labels.items():
        lang_row = await session.execute(
            select(Language).where(Language.code == lang_code)
        )
        lang = lang_row.scalar_one_or_none()
        if not lang:
            continue

        key = f"{prefix}.{slug}"
        existing = await session.execute(
            select(Translation).where(
                Translation.language_id == lang.id,
                Translation.namespace == "taxonomy",
                Translation.key == key,
            )
        )
        t = existing.scalar_one_or_none()
        if t:
            t.value = value
            t.is_modified = True
            t.modified_by = modified_by
            t.modified_at = now
        else:
            session.add(Translation(
                language_id=lang.id,
                namespace="taxonomy",
                key=key,
                value=value,
                is_modified=True,
                modified_by=modified_by,
                modified_at=now,
            ))
    await session.commit()
