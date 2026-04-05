"""Share API — public snapshot links for chat sessions, messages, and debug info."""

import logging
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.auth.dependencies import require_permission

from app.database import async_session
from app.models import ChatMessage, ChatMessageAnalytics, ChatSession, Document, Product, SharedLink
from app.share.schemas import (
    SharedContentResponse,
    SharedDebugContentResponse,
    SharedLinkResponse,
    SharedMessageSnapshot,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["share"])

DEBUG_LINK_TTL_DAYS = 30


def _generate_token() -> str:
    return uuid4().hex[:12]


def _build_url(request: Request, token: str) -> str:
    return str(request.base_url).rstrip("/") + f"/s/{token}"


def _link_response(link: SharedLink, request: Request) -> SharedLinkResponse:
    return SharedLinkResponse(
        token=link.token,
        url=_build_url(request, link.token),
        share_type=link.share_type,
        title=link.title,
        view_count=link.view_count,
        is_active=link.is_active,
        created_at=link.created_at,
        expires_at=link.expires_at,
    )


def _build_message_snapshot(msg: ChatMessage) -> dict:
    return {
        "role": msg.role,
        "content": msg.content,
        "sources": msg.sources,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


@router.post("/share/session/{session_uuid}", response_model=SharedLinkResponse, status_code=201)
async def share_session(session_uuid: _uuid.UUID, request: Request):
    """Create a public snapshot link for an entire chat session."""
    async with async_session() as db:
        chat_session = (await db.execute(
            select(ChatSession).where(ChatSession.uuid == session_uuid)
        )).scalar_one_or_none()
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        msgs_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == chat_session.id)
            .order_by(ChatMessage.created_at)
        )
        messages = msgs_result.scalars().all()
        if not messages:
            raise HTTPException(status_code=400, detail="Session has no messages")

        snapshot = {
            "version": 1,
            "share_type": "session",
            "session": {
                "id": str(chat_session.uuid),
                "title": chat_session.title,
                "product_filter": chat_session.product_filter,
                "version_filter": chat_session.version_filter,
            },
            "messages": [_build_message_snapshot(m) for m in messages],
        }

        token = _generate_token()
        title = chat_session.title or (messages[0].content[:80] if messages else "")

        link = SharedLink(
            token=token,
            session_id=chat_session.id,
            share_type="session",
            title=title,
            snapshot_json=snapshot,
        )
        db.add(link)
        await db.commit()
        await db.refresh(link)

        logger.info("Shared session", extra={"session_id": chat_session.id, "token": token})
        return _link_response(link, request)


@router.post("/share/message/{message_id}", response_model=SharedLinkResponse, status_code=201)
async def share_message(message_id: int, request: Request):
    """Create a public snapshot link for a single answer (user question + assistant response)."""
    async with async_session() as db:
        target_msg = await db.get(ChatMessage, message_id)
        if not target_msg:
            raise HTTPException(status_code=404, detail="Message not found")

        chat_session = await db.get(ChatSession, target_msg.session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        msgs_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == target_msg.session_id)
            .order_by(ChatMessage.created_at)
        )
        all_messages = msgs_result.scalars().all()

        pair: list[ChatMessage] = []
        if target_msg.role == "assistant":
            for i, m in enumerate(all_messages):
                if m.id == target_msg.id:
                    if i > 0 and all_messages[i - 1].role == "user":
                        pair = [all_messages[i - 1], target_msg]
                    else:
                        pair = [target_msg]
                    break
        elif target_msg.role == "user":
            for i, m in enumerate(all_messages):
                if m.id == target_msg.id:
                    if i + 1 < len(all_messages) and all_messages[i + 1].role == "assistant":
                        pair = [target_msg, all_messages[i + 1]]
                    else:
                        pair = [target_msg]
                    break

        if not pair:
            raise HTTPException(status_code=400, detail="Message pair not found")

        snapshot = {
            "version": 1,
            "share_type": "message",
            "session": {
                "id": chat_session.id,
                "title": chat_session.title,
                "product_filter": chat_session.product_filter,
                "version_filter": chat_session.version_filter,
            },
            "messages": [_build_message_snapshot(m) for m in pair],
        }

        user_msg = next((m for m in pair if m.role == "user"), None)
        title = user_msg.content[:80] if user_msg else (pair[0].content[:80] if pair else "")

        token = _generate_token()
        link = SharedLink(
            token=token,
            session_id=target_msg.session_id,
            message_id=message_id,
            share_type="message",
            title=title,
            snapshot_json=snapshot,
        )
        db.add(link)
        await db.commit()
        await db.refresh(link)

        logger.info("Shared message", extra={"message_id": message_id, "token": token})
        return _link_response(link, request)


# ── Debug share endpoints ──


@router.post("/share/debug/message/{message_id}", response_model=SharedLinkResponse, status_code=201, dependencies=[Depends(require_permission("debug"))])
async def share_debug_message(message_id: int, request: Request):
    """Create a public snapshot of chat message debug info."""
    async with async_session() as db:
        analytics_result = await db.execute(
            select(ChatMessageAnalytics).where(ChatMessageAnalytics.message_id == message_id)
        )
        analytics = analytics_result.scalar_one_or_none()
        if not analytics:
            raise HTTPException(status_code=404, detail="Debug info not found for this message")

        session = await db.get(ChatSession, analytics.session_id)
        product_filter = session.product_filter if session else None
        version_filter = session.version_filter if session else None

        debug_data = analytics.to_debug_dict(
            product_filter=product_filter,
            version_filter=version_filter,
        )

        snapshot = {
            "version": 1,
            "share_type": "debug_chat",
            "data": debug_data,
        }

        token = _generate_token()
        title = f"Debug S#{analytics.session_id} M#{message_id}"

        link = SharedLink(
            token=token,
            session_id=analytics.session_id,
            message_id=message_id,
            share_type="debug_chat",
            title=title,
            snapshot_json=snapshot,
            expires_at=datetime.now(timezone.utc) + timedelta(days=DEBUG_LINK_TTL_DAYS),
        )
        db.add(link)
        await db.commit()
        await db.refresh(link)

        logger.info("Shared debug_chat", extra={"message_id": message_id, "token": token})
        return _link_response(link, request)


@router.post("/share/debug/document/{document_id}", response_model=SharedLinkResponse, status_code=201, dependencies=[Depends(require_permission("debug"))])
async def share_debug_document(document_id: int, request: Request):
    """Create a public snapshot of document debug info."""
    from app.documents.router import get_document_debug, get_document_usage_stats

    try:
        debug_info = await get_document_debug(document_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        usage_stats = await get_document_usage_stats(document_id)
        usage_dict = usage_stats.model_dump(mode="json")
    except Exception:
        usage_dict = None

    snapshot = {
        "version": 1,
        "share_type": "debug_document",
        "data": {
            "debug": debug_info.model_dump(mode="json"),
            "usage": usage_dict,
        },
    }

    token = _generate_token()
    title = f"Debug: {debug_info.title or debug_info.original_filename}"

    async with async_session() as db:
        link = SharedLink(
            token=token,
            session_id=None,
            share_type="debug_document",
            title=title[:200],
            snapshot_json=snapshot,
            expires_at=datetime.now(timezone.utc) + timedelta(days=DEBUG_LINK_TTL_DAYS),
        )
        db.add(link)
        await db.commit()
        await db.refresh(link)

    logger.info("Shared debug_document", extra={"document_id": document_id, "token": token})
    return _link_response(link, request)


@router.post(
    "/share/debug/product/{product_id}",
    response_model=SharedLinkResponse,
    status_code=201,
    dependencies=[Depends(require_permission("debug"))],
)
async def share_debug_product(product_id: int, request: Request):
    """Create a public snapshot of product debug info."""
    from app.products.router import get_product_debug, get_product_usage_stats

    try:
        debug_info = await get_product_debug(product_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Product not found")

    try:
        usage_stats = await get_product_usage_stats(product_id)
        usage_dict = usage_stats.model_dump(mode="json")
    except Exception:
        usage_dict = None

    snapshot = {
        "version": 1,
        "share_type": "debug_product",
        "data": {
            "debug": debug_info.model_dump(mode="json"),
            "usage": usage_dict,
        },
    }

    token = _generate_token()
    title = f"Debug: {debug_info.product_name}"

    async with async_session() as db:
        link = SharedLink(
            token=token,
            session_id=None,
            share_type="debug_product",
            title=title[:200],
            snapshot_json=snapshot,
            expires_at=datetime.now(timezone.utc) + timedelta(days=DEBUG_LINK_TTL_DAYS),
        )
        db.add(link)
        await db.commit()
        await db.refresh(link)

    logger.info("Shared debug_product", extra={"product_id": product_id, "token": token})
    return _link_response(link, request)


# ── Document preview share endpoint ──


@router.post("/share/document/{document_id}", response_model=SharedLinkResponse, status_code=201)
async def share_document_preview(document_id: int, request: Request):
    """Create a public snapshot of document markdown preview."""
    from app.documents.router import preview_markdown

    async with async_session() as db:
        doc = await db.get(Document, document_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

    try:
        preview = await preview_markdown(document_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to generate markdown preview")

    snapshot = {
        "version": 1,
        "share_type": "document_preview",
        "document_id": document_id,
        "title": preview.title or doc.original_filename or f"Document {document_id}",
        "markdown": preview.markdown,
        "source": preview.source,
        "size_bytes": preview.size_bytes,
    }

    token = _generate_token()
    title = preview.title or doc.original_filename or f"Document {document_id}"

    async with async_session() as db:
        link = SharedLink(
            token=token,
            session_id=None,
            share_type="document_preview",
            title=title[:200],
            snapshot_json=snapshot,
        )
        db.add(link)
        await db.commit()
        await db.refresh(link)

    logger.info("Shared document_preview", extra={"document_id": document_id, "token": token})
    return _link_response(link, request)


# ── Lifecycle share endpoint ──


@router.post("/share/lifecycle/{product_id}", response_model=SharedLinkResponse, status_code=201)
async def share_lifecycle(product_id: int, request: Request):
    """Create a public snapshot of the full product lifecycle analysis."""
    from app.models import ApiLifecycle, DocIssueAnnotation

    async with async_session() as db:
        product = (await db.execute(
            select(Product).where(Product.id == product_id)
        )).scalar_one_or_none()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        merged = (await db.execute(
            select(ApiLifecycle).where(
                ApiLifecycle.product_id == product_id,
                ApiLifecycle.document_id.is_(None),
            )
        )).scalar_one_or_none()

        doc_lifecycles = (await db.execute(
            select(ApiLifecycle).where(
                ApiLifecycle.product_id == product_id,
                ApiLifecycle.document_id.isnot(None),
            )
        )).scalars().all()

        if not merged and not doc_lifecycles:
            raise HTTPException(status_code=400, detail="No lifecycle analysis found for this product")

        doc_ids = [dl.document_id for dl in doc_lifecycles if dl.document_id]
        doc_names: dict[int, str] = {}
        if doc_ids:
            rows = (await db.execute(
                select(Document.id, Document.title, Document.original_filename)
                .where(Document.id.in_(doc_ids))
            )).all()
            doc_names = {r.id: r.title or r.original_filename or f"Document {r.id}" for r in rows}

        issues = (await db.execute(
            select(DocIssueAnnotation).where(
                DocIssueAnnotation.product_id == product_id,
            )
        )).scalars().all()

        def _lc_dict(lc: ApiLifecycle) -> dict:
            return {
                "status": lc.status,
                "phases": lc.phases or [],
                "unique_patterns": lc.unique_patterns or [],
                "dependency_chains": lc.dependency_chains or [],
                "code_skeleton": lc.code_skeleton or "",
                "code_skeleton_translations": lc.code_skeleton_translations or {},
                "data_models": lc.data_models or [],
                "error_catalog": lc.error_catalog or [],
                "prerequisites": lc.prerequisites or [],
                "data_access_patterns": lc.data_access_patterns or [],
                "endpoint_coverage": lc.endpoint_coverage or [],
                "validation_issues": lc.validation_issues or [],
                "validation_retries": lc.validation_retries,
                "prompt_tokens": lc.prompt_tokens,
                "completion_tokens": lc.completion_tokens,
                "analysis_ms": lc.analysis_ms,
                "model": lc.model,
                "created_at": lc.created_at.isoformat() if lc.created_at else None,
                "updated_at": lc.updated_at.isoformat() if lc.updated_at else None,
            }

        snapshot = {
            "version": 1,
            "share_type": "lifecycle",
            "product_id": product_id,
            "product_name": product.name,
            "merged": _lc_dict(merged) if merged else None,
            "document_lifecycles": [
                {
                    "document_id": dl.document_id,
                    "document_name": doc_names.get(dl.document_id, f"Document {dl.document_id}") if dl.document_id else None,
                    **_lc_dict(dl),
                }
                for dl in doc_lifecycles
            ],
            "doc_issues": [
                {
                    "document_id": i.document_id,
                    "issue_type": i.issue_type,
                    "severity": i.severity,
                    "description": i.description,
                    "affected_entity": i.affected_entity,
                    "suggestion": i.suggestion,
                }
                for i in issues
            ],
        }

        token = _generate_token()
        title = f"API Lifecycle: {product.name}"

        link = SharedLink(
            token=token,
            session_id=None,
            share_type="lifecycle",
            title=title[:200],
            snapshot_json=snapshot,
        )
        db.add(link)
        await db.commit()
        await db.refresh(link)

    logger.info("Shared lifecycle", extra={"product_id": product_id, "token": token})
    return _link_response(link, request)


# Public GET /s/{token} is in app.share.public (no auth required)


@router.delete("/share/{token}", status_code=204)
async def deactivate_shared_link(token: str):
    """Deactivate a shared link (revoke access)."""
    async with async_session() as db:
        result = await db.execute(
            select(SharedLink).where(SharedLink.token == token)
        )
        link = result.scalar_one_or_none()
        if not link:
            raise HTTPException(status_code=404, detail="Shared link not found")

        link.is_active = False
        await db.commit()

        logger.info("Deactivated shared link", extra={"token": token})


@router.get("/share/links", response_model=list[SharedLinkResponse])
async def list_shared_links(request: Request, session_uuid: _uuid.UUID | None = None):
    """List all active shared links, optionally filtered by session UUID."""
    async with async_session() as db:
        query = select(SharedLink).where(SharedLink.is_active.is_(True))
        if session_uuid is not None:
            cs = (await db.execute(
                select(ChatSession.id).where(ChatSession.uuid == session_uuid)
            )).scalar_one_or_none()
            if cs is None:
                return []
            query = query.where(SharedLink.session_id == cs)
        query = query.order_by(SharedLink.created_at.desc())

        result = await db.execute(query)
        links = result.scalars().all()

        return [_link_response(link, request) for link in links]
