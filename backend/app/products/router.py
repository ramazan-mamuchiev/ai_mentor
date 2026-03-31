"""REST API router for products management."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import case, delete, func, select

from fastapi import Query as QueryParam

from app.auth.dependencies import require_permission
from app.config import settings
from app.database import async_session
from app.models import (
    ChatMessage, Chunk, Document, DocumentUsageLog, FirmwareVersion,
    Product, ProductSearchKey, SuggestionTemplate,
)
from app.products.schemas import (
    DocumentKeysGroup,
    FacetValue,
    Facets,
    FirmwareVersionInfo,
    FormatCount,
    PaginatedProducts,
    ProductDebugInfo,
    ProductDetail,
    ProductDocumentSummary,
    ProductDocumentUsage,
    ProductSearchKeysResponse,
    ProductListItem,
    ProductSuggestion,
    ProductUpdate,
    ProductUsageStats,
    SuggestionChip,
)
from app.products.utils import make_product_slug

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products"])


async def _get_product(session, product_id: int) -> Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/suggestions", response_model=list[SuggestionChip])
async def get_suggestions():
    """Return up to 4 suggestion chips based on top products by RAG usage."""
    async with async_session() as session:
        products_stmt = (
            select(
                Product.id,
                Product.name,
                FirmwareVersion.version,
                func.sum(Document.rag_hit_count).label("hits"),
            )
            .join(FirmwareVersion, FirmwareVersion.product_id == Product.id)
            .join(
                Document,
                (Document.product_id == Product.id)
                & (Document.firmware_version_id == FirmwareVersion.id),
            )
            .where(
                Document.status == "ready",
                func.lower(Product.name) != settings.platform_name.lower(),
            )
            .group_by(
                Product.id,
                Product.name,
                FirmwareVersion.version,
            )
            .order_by(func.sum(Document.rag_hit_count).desc())
            .limit(4)
        )
        product_rows = (await session.execute(products_stmt)).all()
        if not product_rows:
            return []

        need = len(product_rows)

        tpl_base = (
            select(SuggestionTemplate.template)
            .where(
                SuggestionTemplate.role == "default",
                SuggestionTemplate.is_active.is_(True),
            )
        )

        en_rows = (await session.execute(
            tpl_base.where(SuggestionTemplate.lang == "en")
            .order_by(func.random()).limit(need)
        )).scalars().all()

        ru_rows = (await session.execute(
            tpl_base.where(SuggestionTemplate.lang == "ru")
            .order_by(func.random()).limit(need)
        )).scalars().all()

    chips: list[SuggestionChip] = []
    for idx, row in enumerate(product_rows):
        display = f"{row.name} {row.version}".strip()
        tpl_en = en_rows[idx] if idx < len(en_rows) else "Tell me about {product}"
        tpl_ru = ru_rows[idx] if idx < len(ru_rows) else "Расскажи про {product}"
        chips.append(SuggestionChip(
            text_en=tpl_en.format(product=display),
            text_ru=tpl_ru.format(product=display),
            product_filter=str(row.id),
        ))

    return chips


@router.get("/suggest", response_model=list[ProductSuggestion])
async def suggest_products(
    q: str = QueryParam("", description="Search text"),
    limit: int = QueryParam(20, ge=1, le=100),
):
    """Lightweight product search for autocompletes."""
    async with async_session() as session:
        stmt = select(Product).order_by(Product.name)

        if q:
            like = f"%{q}%"
            stmt = stmt.where(Product.name.ilike(like) | Product.manufacturer.ilike(like))

        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        products = result.scalars().all()

        items = []
        for p in products:
            fw_result = await session.execute(
                select(FirmwareVersion.id, FirmwareVersion.version)
                .where(FirmwareVersion.product_id == p.id)
                .order_by(FirmwareVersion.version)
            )
            fws = [FirmwareVersionInfo(id=r.id, version=r.version) for r in fw_result]

            items.append(ProductSuggestion(
                id=p.id,
                name=p.name,
                manufacturer=p.manufacturer,
                firmware_versions=fws,
            ))
        return items


@router.get("", response_model=list[ProductListItem])
async def list_products():
    """List all products with aggregated document stats, one row per (product, firmware_version)."""
    async with async_session() as session:
        agg = (
            select(
                Document.product_id,
                Document.firmware_version_id,
                func.count().label("total_documents"),
                func.sum(case((Document.status == "pending", 1), else_=0)).label("pending_documents"),
                func.sum(case((Document.status == "processing", 1), else_=0)).label("processing_documents"),
                func.sum(case((Document.status == "ready", 1), else_=0)).label("ready_documents"),
                func.sum(case((Document.status == "error", 1), else_=0)).label("error_documents"),
                func.sum(case((Document.status == "cancelled", 1), else_=0)).label("cancelled_documents"),
                func.sum(Document.file_size_bytes).label("total_file_size_bytes"),
                func.sum(Document.total_chunks).label("total_chunks"),
                func.min(Document.uploaded_at).label("uploaded_at"),
                func.max(Document.indexed_at).label("indexed_at"),
                func.sum(Document.progress_percent).label("sum_progress"),
            )
            .group_by(Document.product_id, Document.firmware_version_id)
            .subquery()
        )

        fmt_agg = (
            select(
                Document.product_id,
                Document.firmware_version_id,
                Document.format,
                func.count().label("cnt"),
            )
            .group_by(Document.product_id, Document.firmware_version_id, Document.format)
            .subquery()
        )

        result = await session.execute(
            select(
                Product.id,
                Product.name,
                Product.slug,
                Product.manufacturer,
                Product.category,
                Product.created_at,
                Product.sync_status,
                FirmwareVersion.id.label("firmware_version_id"),
                FirmwareVersion.version.label("version"),
                func.coalesce(agg.c.total_documents, 0).label("total_documents"),
                func.coalesce(agg.c.pending_documents, 0).label("pending_documents"),
                func.coalesce(agg.c.processing_documents, 0).label("processing_documents"),
                func.coalesce(agg.c.ready_documents, 0).label("ready_documents"),
                func.coalesce(agg.c.error_documents, 0).label("error_documents"),
                func.coalesce(agg.c.cancelled_documents, 0).label("cancelled_documents"),
                func.coalesce(agg.c.total_file_size_bytes, 0).label("total_file_size_bytes"),
                func.coalesce(agg.c.total_chunks, 0).label("total_chunks"),
                agg.c.uploaded_at,
                agg.c.indexed_at,
                func.coalesce(agg.c.sum_progress, 0).label("sum_progress"),
            )
            .join(FirmwareVersion, FirmwareVersion.product_id == Product.id)
            .outerjoin(
                agg,
                (Product.id == agg.c.product_id) & (FirmwareVersion.id == agg.c.firmware_version_id),
            )
            .order_by(Product.name, FirmwareVersion.version)
        )
        rows = result.all()

        fmt_result = await session.execute(
            select(
                fmt_agg.c.product_id,
                fmt_agg.c.firmware_version_id,
                fmt_agg.c.format,
                fmt_agg.c.cnt,
            )
        )
        fmt_rows = fmt_result.all()
        fmt_map: dict[tuple[int, int], list[FormatCount]] = {}
        for row in fmt_rows:
            key = (row.product_id, row.firmware_version_id)
            fmt_map.setdefault(key, []).append(
                FormatCount(format=row.format, count=row.cnt)
            )

        reset_product_ids: list[int] = []
        items = []
        for p in rows:
            total = p.total_documents
            progress_pct = round(p.sum_progress / total) if total > 0 else 0

            ready = p.ready_documents
            processing = p.processing_documents
            pending = p.pending_documents
            errors = p.error_documents
            cancelled = p.cancelled_documents
            parts = []
            if ready:
                parts.append(f"{ready}/{total} ready")
            if processing:
                parts.append(f"{processing} processing")
            if pending:
                parts.append(f"{pending} pending")
            if errors:
                parts.append(f"{errors} error")
            if cancelled:
                parts.append(f"{cancelled} cancelled")
            progress_detail = ", ".join(parts) if parts else ""

            version_str = p.version or ""
            display_name = f"{p.name} {version_str}".strip()

            fmt_key = (p.id, p.firmware_version_id)

            sync_st = p.sync_status
            if sync_st not in ("idle", "deleting") and pending == 0 and processing == 0:
                sync_st = "idle"
                reset_product_ids.append(p.id)

            items.append(ProductListItem(
                id=p.id,
                name=p.name,
                slug=p.slug,
                manufacturer=p.manufacturer,
                category=p.category,
                created_at=p.created_at,
                firmware_version_id=p.firmware_version_id,
                version=version_str,
                display_name=display_name,
                total_documents=total,
                pending_documents=pending,
                processing_documents=processing,
                ready_documents=ready,
                error_documents=errors,
                cancelled_documents=cancelled,
                total_file_size_bytes=p.total_file_size_bytes,
                total_chunks=p.total_chunks,
                formats=fmt_map.get(fmt_key, []),
                uploaded_at=p.uploaded_at,
                indexed_at=p.indexed_at,
                progress_percent=progress_pct,
                progress_detail=progress_detail,
                sync_status=sync_st,
            ))

        if reset_product_ids:
            await session.execute(
                Product.__table__.update()
                .where(Product.id.in_(reset_product_ids))
                .values(sync_status="idle")
            )
            await session.commit()

        return items


async def _product_detail(session, product: Product) -> ProductDetail:
    fw_result = await session.execute(
        select(FirmwareVersion.version)
        .where(FirmwareVersion.product_id == product.id)
        .order_by(FirmwareVersion.version)
    )
    versions = [row[0] for row in fw_result.all()]
    return ProductDetail(
        id=product.id,
        name=product.name,
        slug=product.slug,
        manufacturer=product.manufacturer,
        category=product.category,
        created_at=product.created_at,
        firmware_versions=versions,
    )


@router.get("/by-slug/{slug}", response_model=ProductDetail)
async def get_product_by_slug(slug: str):
    """Get product details by URL slug."""
    async with async_session() as session:
        result = await session.execute(
            select(Product).where(Product.slug == slug)
        )
        product = result.scalar_one_or_none()
        if product is None:
            raise HTTPException(status_code=404, detail="Product not found")
        return await _product_detail(session, product)


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(product_id: int):
    """Get product details including firmware versions."""
    async with async_session() as session:
        product = await _get_product(session, product_id)
        return await _product_detail(session, product)


@router.patch("/{product_id}", response_model=ProductDetail, dependencies=[Depends(require_permission("products.edit"))])
async def update_product(product_id: int, body: ProductUpdate):
    """Update product properties."""
    async with async_session() as session:
        product = await _get_product(session, product_id)

        if body.name is not None:
            product.name = body.name
        if body.manufacturer is not None:
            product.manufacturer = body.manufacturer
        if body.category is not None:
            product.category = body.category

        if body.name is not None or body.manufacturer is not None:
            product.slug = make_product_slug(product.manufacturer, product.name)

        if body.version is not None and body.firmware_version_id is not None:
            fw = await session.get(FirmwareVersion, body.firmware_version_id)
            if fw and fw.product_id == product.id:
                fw.version = body.version

        await session.commit()
        await session.refresh(product)
        return await _product_detail(session, product)


@router.delete("/{product_id}", dependencies=[Depends(require_permission("products.delete"))])
async def delete_product(product_id: int):
    """Enqueue async product deletion. Returns 202 immediately."""
    async with async_session() as session:
        product = await _get_product(session, product_id)

        if product.sync_status == "deleting":
            raise HTTPException(status_code=409, detail="Product is already being deleted")

        doc_count = await session.scalar(
            select(func.count()).select_from(Document).where(Document.product_id == product_id)
        ) or 0

        product.sync_status = "deleting"
        await session.commit()

    from app.celery_app import celery
    task = celery.send_task("delete_product", args=[product_id])

    logger.info("Product deletion queued",
                extra={"product_id": product_id, "task_id": task.id, "total_documents": doc_count})
    return JSONResponse(status_code=202, content={
        "product_id": product_id,
        "task_id": task.id,
        "total_documents": doc_count,
    })


_PLACEHOLDER_FORMATS = {"site", "confluence", "url", "github"}
_SAFE_STATUSES = ["ready", "error"]


@router.post("/{product_id}/reingest", status_code=202, dependencies=[Depends(require_permission("documents.reindex"))])
async def reingest_product(product_id: int):
    """Re-index all saved documents of a product (re-chunk + re-embed).

    Only touches documents with saved content (excludes placeholder formats).
    Skips documents already in pending/processing to avoid race conditions.
    """
    from app.celery_app import ingest_document_task

    async with async_session() as session:
        product = await _get_product(session, product_id)

        docs_result = await session.execute(
            select(Document).where(
                Document.product_id == product_id,
                Document.status.in_(_SAFE_STATUSES),
                Document.format.notin_(_PLACEHOLDER_FORMATS),
            )
        )
        docs = docs_result.scalars().all()
        if not docs:
            raise HTTPException(status_code=400, detail="No documents to reingest")

        product.sync_status = "reindexing"

        doc_ids = [doc.id for doc in docs]

        await session.execute(
            delete(Chunk).where(Chunk.document_id.in_(doc_ids))
        )

        for doc in docs:
            doc.status = "pending"
            doc.total_chunks = 0
            doc.error_message = None
            doc.progress_percent = 0
            doc.progress_stage = "queued"

        await session.commit()

    for doc_id in doc_ids:
        ingest_document_task.delay(doc_id)

    logger.info(
        "Product reingest queued",
        extra={"product_id": product_id, "product_name": product.name, "documents_queued": len(doc_ids)},
    )
    return {
        "product_id": product_id,
        "product_name": product.name,
        "status": "accepted",
        "documents_queued": len(doc_ids),
    }


@router.post("/{product_id}/sync", status_code=202, dependencies=[Depends(require_permission("documents.sync"))])
async def sync_product(product_id: int):
    """Sync product: re-crawl all linked sources and re-index file documents.

    For placeholder documents (site, confluence, url, github): deletes child
    documents and dispatches the appropriate crawl task.
    For file-based documents: re-indexes via ingest_document_task.
    Skips documents already in pending/processing to avoid race conditions.
    """
    from app.celery_app import ingest_document_task
    from app.s3 import delete_file

    placeholder_ids: list[int] = []
    file_doc_ids: list[int] = []

    async with async_session() as session:
        product = await _get_product(session, product_id)
        product.sync_status = "syncing"

        # --- Placeholder documents: re-crawl from source ---
        ph_result = await session.execute(
            select(Document).where(
                Document.product_id == product_id,
                Document.status.in_(_SAFE_STATUSES),
                Document.format.in_(_PLACEHOLDER_FORMATS),
            )
        )
        placeholders = ph_result.scalars().all()

        for ph in placeholders:
            if not ph.source_path:
                continue

            children = (await session.execute(
                select(Document).where(
                    Document.source_container == ph.source_path,
                    Document.id != ph.id,
                )
            )).scalars().all()
            for child in children:
                child_chunks = (await session.execute(
                    select(Chunk).where(Chunk.document_id == child.id)
                )).scalars().all()
                for ch in child_chunks:
                    await session.delete(ch)
                if child.s3_key:
                    try:
                        delete_file(child.s3_key)
                    except Exception:
                        pass
                await session.delete(child)

            ph_chunks = (await session.execute(
                select(Chunk).where(Chunk.document_id == ph.id)
            )).scalars().all()
            for ch in ph_chunks:
                await session.delete(ch)

            ph.status = "pending"
            ph.total_chunks = 0
            ph.total_tokens = 0
            ph.file_size_bytes = 0
            ph.error_message = None
            ph.progress_percent = 0
            ph.progress_stage = "queued"
            ph.title = ph.source_path[:200]
            if ph.format == "site":
                ph.crawl_checkpoint = None
            placeholder_ids.append(ph.id)

        # --- File-based documents: re-index ---
        file_result = await session.execute(
            select(Document).where(
                Document.product_id == product_id,
                Document.status.in_(_SAFE_STATUSES),
                Document.format.notin_(_PLACEHOLDER_FORMATS),
            )
        )
        file_docs = file_result.scalars().all()
        file_doc_ids = [doc.id for doc in file_docs]

        if file_doc_ids:
            await session.execute(
                delete(Chunk).where(Chunk.document_id.in_(file_doc_ids))
            )

        for doc in file_docs:
            doc.status = "pending"
            doc.total_chunks = 0
            doc.error_message = None
            doc.progress_percent = 0
            doc.progress_stage = "queued"

        await session.commit()

        if not placeholder_ids and not file_doc_ids:
            raise HTTPException(status_code=400, detail="No documents to sync")

        for ph in placeholders:
            if ph.id not in placeholder_ids:
                continue
            if ph.format == "site":
                from app.celery_app import ingest_site_task
                ingest_site_task.delay(document_id=ph.id)
            elif ph.format == "github":
                from app.celery_app import ingest_github_task
                from app.ingestion.converters.github import parse_github_url
                _branch = "main"
                try:
                    _, _, url_branch = parse_github_url(ph.source_path)
                    if url_branch:
                        _branch = url_branch
                except ValueError:
                    pass
                ingest_github_task.delay(document_id=ph.id, branch=_branch)
            elif ph.format == "confluence":
                from app.celery_app import ingest_confluence_task
                ingest_confluence_task.delay(document_id=ph.id)
            elif ph.format == "url":
                from app.celery_app import ingest_single_url_task
                ingest_single_url_task.delay(document_id=ph.id)

    for doc_id in file_doc_ids:
        ingest_document_task.delay(doc_id)

    logger.info(
        "Product sync queued",
        extra={
            "product_id": product_id,
            "product_name": product.name,
            "documents_queued": len(file_doc_ids),
            "placeholders_queued": len(placeholder_ids),
        },
    )
    return {
        "product_id": product_id,
        "product_name": product.name,
        "status": "accepted",
        "documents_queued": len(file_doc_ids),
        "placeholders_queued": len(placeholder_ids),
    }


@router.post("/{product_id}/cancel-ingestion", status_code=200)
async def cancel_product_ingestion(product_id: int):
    """Cancel ingestion for all pending/processing documents of a product."""
    async with async_session() as session:
        product = await _get_product(session, product_id)

        docs_result = await session.execute(
            select(Document).where(
                Document.product_id == product_id,
                Document.status.in_(["pending", "processing"]),
            )
        )
        docs = docs_result.scalars().all()
        if not docs:
            raise HTTPException(status_code=400, detail="No pending or processing documents to cancel")

        task_ids: list[str] = []
        for doc in docs:
            if doc.celery_task_id:
                task_ids.append(doc.celery_task_id)
            doc.status = "cancelled"
            doc.progress_percent = 0
            doc.progress_stage = ""
            doc.error_message = None

            chunks = (await session.execute(
                select(Chunk).where(Chunk.document_id == doc.id)
            )).scalars().all()
            for chunk in chunks:
                await session.delete(chunk)
            doc.total_chunks = 0

        await session.commit()

    if task_ids:
        try:
            from app.celery_app import celery
            for tid in task_ids:
                celery.control.revoke(tid, terminate=True)
        except Exception:
            logger.warning("Failed to revoke Celery tasks", extra={"task_ids": task_ids, "product_id": product_id})

    logger.info(
        "Product ingestion cancelled",
        extra={"product_id": product_id, "documents_cancelled": len(docs), "tasks_revoked": len(task_ids)},
    )
    return {
        "product_id": product_id,
        "status": "cancelled",
        "documents_cancelled": len(docs),
    }


@router.get("/{product_id}/debug", response_model=ProductDebugInfo, dependencies=[Depends(require_permission("debug"))])
async def get_product_debug(product_id: int):
    """Get aggregated debug/analytics info for all documents of a product."""
    async with async_session() as session:
        product = await _get_product(session, product_id)

        agg_result = await session.execute(
            select(
                func.count().label("total_documents"),
                func.sum(Document.file_size_bytes).label("total_file_size_bytes"),
                func.sum(Document.ingest_duration_ms).label("sum_ingest_duration_ms"),
                func.avg(Document.ingest_duration_ms).label("avg_ingest_duration_ms"),
                func.sum(Document.read_ms).label("sum_read_ms"),
                func.sum(Document.convert_ms).label("sum_convert_ms"),
                func.sum(Document.parse_ms).label("sum_parse_ms"),
                func.sum(Document.embed_ms).label("sum_embed_ms"),
                func.sum(Document.db_ms).label("sum_db_ms"),
                func.sum(Document.total_chunks).label("total_chunks"),
                func.sum(Document.total_tokens).label("total_tokens"),
                func.min(Document.min_chunk_tokens).label("min_chunk_tokens"),
                func.max(Document.max_chunk_tokens).label("max_chunk_tokens"),
                func.avg(Document.avg_chunk_tokens).label("avg_chunk_tokens"),
                func.sum(Document.embedding_tokens).label("total_embedding_tokens"),
                func.sum(Document.rag_hit_count).label("total_rag_hit_count"),
                func.avg(Document.rag_avg_similarity).label("avg_rag_similarity"),
                func.max(Document.rag_last_used_at).label("last_rag_used_at"),
                func.sum(Document.extract_ms).label("sum_extract_ms"),
                func.sum(Document.extract_prompt_tokens + Document.extract_completion_tokens).label("total_extract_tokens"),
            )
            .where(Document.product_id == product_id)
        )
        agg = agg_result.one()

        fw_count_result = await session.execute(
            select(func.count())
            .select_from(FirmwareVersion)
            .where(FirmwareVersion.product_id == product_id)
        )
        fw_count = fw_count_result.scalar() or 0

        emb_result = await session.execute(
            select(Document.embedding_model)
            .where(Document.product_id == product_id, Document.embedding_model.isnot(None))
            .distinct()
            .limit(2)
        )
        emb_models = [row[0] for row in emb_result.all()]
        embedding_model = emb_models[0] if len(emb_models) == 1 else (", ".join(emb_models) if emb_models else None)

        docs_result = await session.execute(
            select(
                Document.id,
                Document.title,
                Document.format,
                Document.file_size_bytes,
                Document.total_chunks,
                Document.status,
                Document.indexed_at,
            )
            .where(Document.product_id == product_id)
            .order_by(Document.uploaded_at.desc())
        )
        docs = [
            ProductDocumentSummary(**dict(row._mapping))
            for row in docs_result.all()
        ]

        keys_result = await session.execute(
            select(
                func.count().label("total"),
                func.count().filter(ProductSearchKey.source == "llm").label("llm"),
                func.count().filter(ProductSearchKey.source == "chunk").label("chunk"),
            ).where(ProductSearchKey.product_id == product_id)
        )
        keys_agg = keys_result.one()

        return ProductDebugInfo(
            product_id=product.id,
            product_name=product.name,
            total_documents=agg.total_documents or 0,
            firmware_version_count=fw_count,
            total_file_size_bytes=agg.total_file_size_bytes or 0,
            sum_ingest_duration_ms=agg.sum_ingest_duration_ms,
            avg_ingest_duration_ms=float(agg.avg_ingest_duration_ms) if agg.avg_ingest_duration_ms else None,
            sum_read_ms=agg.sum_read_ms,
            sum_convert_ms=agg.sum_convert_ms,
            sum_parse_ms=agg.sum_parse_ms,
            sum_embed_ms=agg.sum_embed_ms,
            sum_db_ms=agg.sum_db_ms,
            total_chunks=agg.total_chunks or 0,
            total_tokens=agg.total_tokens or 0,
            min_chunk_tokens=agg.min_chunk_tokens,
            max_chunk_tokens=agg.max_chunk_tokens,
            avg_chunk_tokens=float(agg.avg_chunk_tokens) if agg.avg_chunk_tokens else None,
            embedding_model=embedding_model,
            total_embedding_tokens=agg.total_embedding_tokens or 0,
            total_rag_hit_count=agg.total_rag_hit_count or 0,
            avg_rag_similarity=float(agg.avg_rag_similarity) if agg.avg_rag_similarity else None,
            last_rag_used_at=agg.last_rag_used_at,
            search_keys_total=keys_agg.total or 0,
            search_keys_llm=keys_agg.llm or 0,
            search_keys_chunk=keys_agg.chunk or 0,
            documents=docs,
        )


@router.get("/{product_id}/search-keys", response_model=ProductSearchKeysResponse)
async def get_product_search_keys(product_id: int):
    """Get all search keys for a product, grouped by source."""
    async with async_session() as session:
        product = await _get_product(session, product_id)

        from sqlalchemy import text
        llm_rows = (await session.execute(
            select(ProductSearchKey.key)
            .where(ProductSearchKey.product_id == product_id, ProductSearchKey.source == "llm")
            .order_by(ProductSearchKey.key)
        )).scalars().all()

        chunk_rows = (await session.execute(text("""
            SELECT psk.document_id, d.title, array_agg(psk.key ORDER BY psk.key) AS keys
            FROM product_search_keys psk
            JOIN documents d ON psk.document_id = d.id
            WHERE psk.product_id = :pid AND psk.source = 'chunk'
            GROUP BY psk.document_id, d.title
            ORDER BY d.title
        """), {"pid": product_id})).mappings().all()

        chunk_groups = [
            DocumentKeysGroup(
                document_id=row["document_id"],
                title=row["title"] or "",
                keys=list(row["keys"]) if row["keys"] else [],
            )
            for row in chunk_rows
        ]

        total = len(llm_rows) + sum(len(g.keys) for g in chunk_groups)

        return ProductSearchKeysResponse(
            product_id=product.id,
            product_name=product.name,
            total_keys=total,
            llm_keys=list(llm_rows),
            chunk_keys_by_document=chunk_groups,
        )


@router.get("/{product_id}/usage-stats", response_model=ProductUsageStats)
async def get_product_usage_stats(product_id: int):
    """Get aggregated usage analytics for all documents of a product."""
    async with async_session() as session:
        product = await _get_product(session, product_id)

        agg_result = await session.execute(
            select(
                func.count().label("total_usages"),
                func.count(func.distinct(DocumentUsageLog.session_id)).label("unique_sessions"),
                func.count(func.distinct(DocumentUsageLog.document_id)).label("unique_documents"),
                func.sum(DocumentUsageLog.context_tokens).label("total_context_tokens"),
                func.sum(DocumentUsageLog.charge_usd).label("total_charge_usd"),
                func.avg(DocumentUsageLog.similarity).label("avg_similarity"),
                func.min(DocumentUsageLog.created_at).label("first_used_at"),
                func.max(DocumentUsageLog.created_at).label("last_used_at"),
            ).where(DocumentUsageLog.product_id == product_id)
        )
        agg = agg_result.one()

        fb_result = await session.execute(
            select(
                func.count().filter(ChatMessage.feedback == "up").label("thumbs_up"),
                func.count().filter(ChatMessage.feedback == "down").label("thumbs_down"),
                func.count(func.distinct(ChatMessage.id)).filter(
                    ChatMessage.feedback.is_not(None)
                ).label("total_rated"),
            )
            .select_from(DocumentUsageLog)
            .join(ChatMessage, ChatMessage.id == DocumentUsageLog.message_id)
            .where(DocumentUsageLog.product_id == product_id)
        )
        fb = fb_result.one()

        doc_agg_result = await session.execute(
            select(
                DocumentUsageLog.document_id,
                Document.title,
                func.count().label("total_usages"),
                func.sum(DocumentUsageLog.context_tokens).label("total_context_tokens"),
                func.sum(DocumentUsageLog.charge_usd).label("total_charge_usd"),
                func.avg(DocumentUsageLog.similarity).label("avg_similarity"),
                func.max(DocumentUsageLog.created_at).label("last_used_at"),
                func.count().filter(ChatMessage.feedback == "up").label("thumbs_up"),
                func.count().filter(ChatMessage.feedback == "down").label("thumbs_down"),
            )
            .join(Document, DocumentUsageLog.document_id == Document.id)
            .outerjoin(ChatMessage, ChatMessage.id == DocumentUsageLog.message_id)
            .where(DocumentUsageLog.product_id == product_id)
            .group_by(DocumentUsageLog.document_id, Document.title)
            .order_by(func.count().desc())
        )
        doc_usages = [
            ProductDocumentUsage(
                document_id=row.document_id,
                title=row.title,
                total_usages=row.total_usages,
                total_context_tokens=row.total_context_tokens or 0,
                total_charge_usd=float(row.total_charge_usd or 0),
                avg_similarity=float(row.avg_similarity) if row.avg_similarity else None,
                last_used_at=row.last_used_at,
                thumbs_up=row.thumbs_up or 0,
                thumbs_down=row.thumbs_down or 0,
            )
            for row in doc_agg_result.all()
        ]

        return ProductUsageStats(
            product_id=product_id,
            product_name=product.name,
            total_usages=agg.total_usages or 0,
            unique_sessions=agg.unique_sessions or 0,
            unique_documents=agg.unique_documents or 0,
            total_context_tokens=agg.total_context_tokens or 0,
            total_charge_usd=float(agg.total_charge_usd or 0),
            avg_similarity=float(agg.avg_similarity) if agg.avg_similarity else None,
            first_used_at=agg.first_used_at,
            last_used_at=agg.last_used_at,
            thumbs_up=fb.thumbs_up or 0,
            thumbs_down=fb.thumbs_down or 0,
            total_rated=fb.total_rated or 0,
            documents=doc_usages,
        )
