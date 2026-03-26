"""REST API router for products management."""

import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import case, func, select

from app.database import async_session
from app.models import Chunk, Document, DocumentUsageLog, FirmwareVersion, Product
from app.products.schemas import (
    FormatCount,
    ProductDebugInfo,
    ProductDetail,
    ProductDocumentSummary,
    ProductDocumentUsage,
    ProductListItem,
    ProductUpdate,
    ProductUsageStats,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products"])


async def _get_product_by_slugs(session, manufacturer_slug: str, product_slug: str) -> Product:
    result = await session.execute(
        select(Product).where(
            Product.manufacturer_slug == manufacturer_slug,
            Product.slug == product_slug,
        )
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


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
                Product.manufacturer,
                Product.model,
                Product.category,
                Product.slug,
                Product.manufacturer_slug,
                Product.created_at,
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

            items.append(ProductListItem(
                id=p.id,
                name=p.name,
                manufacturer=p.manufacturer,
                model=p.model,
                category=p.category,
                slug=p.slug,
                manufacturer_slug=p.manufacturer_slug,
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
            ))

        return items


@router.get("/{manufacturer_slug}/{product_slug}", response_model=ProductDetail)
async def get_product(manufacturer_slug: str, product_slug: str):
    """Get product details including firmware versions."""
    async with async_session() as session:
        product = await _get_product_by_slugs(session, manufacturer_slug, product_slug)

        fw_result = await session.execute(
            select(FirmwareVersion.version)
            .where(FirmwareVersion.product_id == product.id)
            .order_by(FirmwareVersion.version)
        )
        versions = [row[0] for row in fw_result.all()]

        return ProductDetail(
            id=product.id,
            name=product.name,
            manufacturer=product.manufacturer,
            model=product.model,
            category=product.category,
            slug=product.slug,
            manufacturer_slug=product.manufacturer_slug,
            created_at=product.created_at,
            firmware_versions=versions,
        )


@router.patch("/{manufacturer_slug}/{product_slug}", response_model=ProductDetail)
async def update_product(manufacturer_slug: str, product_slug: str, body: ProductUpdate):
    """Update product properties (slug is regenerated if name/manufacturer changes)."""
    from app.slugify import slugify

    async with async_session() as session:
        product = await _get_product_by_slugs(session, manufacturer_slug, product_slug)

        if body.name is not None:
            product.name = body.name
            product.slug = slugify(body.name)
        if body.manufacturer is not None:
            product.manufacturer = body.manufacturer
            product.manufacturer_slug = slugify(body.manufacturer) if body.manufacturer else "default"
        if body.model is not None:
            product.model = body.model
        if body.category is not None:
            product.category = body.category

        await session.commit()
        await session.refresh(product)

        fw_result = await session.execute(
            select(FirmwareVersion.version)
            .where(FirmwareVersion.product_id == product.id)
            .order_by(FirmwareVersion.version)
        )
        versions = [row[0] for row in fw_result.all()]

        return ProductDetail(
            id=product.id,
            name=product.name,
            manufacturer=product.manufacturer,
            model=product.model,
            category=product.category,
            slug=product.slug,
            manufacturer_slug=product.manufacturer_slug,
            created_at=product.created_at,
            firmware_versions=versions,
        )


@router.delete("/{manufacturer_slug}/{product_slug}")
async def delete_product(manufacturer_slug: str, product_slug: str):
    """Delete a product and all its documents (cascade)."""
    from app.s3 import delete_file

    async with async_session() as session:
        product = await _get_product_by_slugs(session, manufacturer_slug, product_slug)
        product_id = product.id

        docs_result = await session.execute(
            select(Document).where(Document.product_id == product_id)
        )
        docs = docs_result.scalars().all()
        for doc in docs:
            if doc.s3_key:
                try:
                    delete_file(doc.s3_key)
                except Exception as e:
                    logger.warning("Failed to delete S3 file", extra={"s3_key": doc.s3_key, "error": str(e)})

        await session.delete(product)
        await session.commit()

        logger.info("Product deleted", extra={"product_id": product_id, "documents_deleted": len(docs)})
        return {
            "product_id": product_id,
            "deleted": True,
            "documents_deleted": len(docs),
        }


@router.post("/{manufacturer_slug}/{product_slug}/reingest", status_code=202)
async def reingest_product(manufacturer_slug: str, product_slug: str):
    """Re-run full ingestion for all documents of a product."""
    from app.celery_app import ingest_document_task

    async with async_session() as session:
        product = await _get_product_by_slugs(session, manufacturer_slug, product_slug)
        product_id = product.id

        docs_result = await session.execute(
            select(Document).where(Document.product_id == product_id)
        )
        docs = docs_result.scalars().all()
        if not docs:
            raise HTTPException(status_code=400, detail="Product has no documents")

        queued = 0
        for doc in docs:
            if doc.status in ("ready", "error"):
                chunks = (await session.execute(
                    select(Chunk).where(Chunk.document_id == doc.id)
                )).scalars().all()
                for chunk in chunks:
                    await session.delete(chunk)

                doc.status = "pending"
                doc.total_chunks = 0
                doc.error_message = None

            queued += 1

        await session.commit()

    for doc in docs:
        ingest_document_task.delay(doc.id)

    logger.info(
        "Product reingest queued",
        extra={"product_id": product_id, "product_name": product.name, "documents_queued": queued},
    )
    return {
        "product_id": product_id,
        "product_name": product.name,
        "status": "accepted",
        "documents_queued": queued,
    }


@router.post("/{manufacturer_slug}/{product_slug}/cancel-ingestion", status_code=200)
async def cancel_product_ingestion(manufacturer_slug: str, product_slug: str):
    """Cancel ingestion for all pending/processing documents of a product."""
    async with async_session() as session:
        product = await _get_product_by_slugs(session, manufacturer_slug, product_slug)
        product_id = product.id

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


@router.get("/{manufacturer_slug}/{product_slug}/debug", response_model=ProductDebugInfo)
async def get_product_debug(manufacturer_slug: str, product_slug: str):
    """Get aggregated debug/analytics info for all documents of a product."""
    async with async_session() as session:
        product = await _get_product_by_slugs(session, manufacturer_slug, product_slug)
        product_id = product.id

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
            documents=docs,
        )


@router.get("/{manufacturer_slug}/{product_slug}/usage-stats", response_model=ProductUsageStats)
async def get_product_usage_stats(manufacturer_slug: str, product_slug: str):
    """Get aggregated usage analytics for all documents of a product."""
    async with async_session() as session:
        product = await _get_product_by_slugs(session, manufacturer_slug, product_slug)
        product_id = product.id

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

        doc_agg_result = await session.execute(
            select(
                DocumentUsageLog.document_id,
                Document.title,
                func.count().label("total_usages"),
                func.sum(DocumentUsageLog.context_tokens).label("total_context_tokens"),
                func.sum(DocumentUsageLog.charge_usd).label("total_charge_usd"),
                func.avg(DocumentUsageLog.similarity).label("avg_similarity"),
                func.max(DocumentUsageLog.created_at).label("last_used_at"),
            )
            .join(Document, DocumentUsageLog.document_id == Document.id)
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
            documents=doc_usages,
        )
