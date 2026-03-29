"""Chat REST API with SSE streaming."""

import asyncio
import json
import logging
import re
import time
import uuid as _uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.auth.dependencies import get_current_tenant
from app.billing.usage_writer import write_usage_log
from app.chat.rag import build_rag_prompt, summarize_history
from app.chat.schemas import (
    ChatMessageResponse,
    CreateSessionRequest,
    FeedbackRequest,
    SendMessageRequest,
    SessionDetailResponse,
    SessionListItem,
    SessionResponse,
    UpdateSessionRequest,
)
from app.config import settings
from app.database import async_session
from app.llm.client import LLMError, stream_chat_completion
from app.models import ChatMessage, ChatMessageAnalytics, ChatSession, DocumentUsageLog, Product, Tenant
from app.search.service import resolve_product

MAX_CONTINUATIONS = settings.llm_max_continuations
CONTINUE_PROMPT = (
    "Continue exactly where you stopped. RULES: "
    "1) Do NOT repeat ANY text, tables, headers, or code blocks already written. "
    "2) Do NOT re-output table column headers. "
    "3) No preamble — continue the text seamlessly. "
    "4) You MUST complete the response fully — finish all lists, tables, and sentences."
)

_NORMAL_ENDING = re.compile(r"[.!?,;:)\]>|`\"'\u2019\u201d*#\u2014\u2013-]\s*$")


def _looks_incomplete(text: str) -> bool:
    """Heuristic: check if the response appears to have been cut off mid-flow.

    A well-formed response ends on punctuation, a closing bracket, a code
    fence, or similar terminal character.  If the last non-whitespace
    character is a regular letter/digit, the response was almost certainly
    truncated.
    """
    if not text or len(text) < 60:
        return False
    trimmed = text.rstrip()
    if not trimmed:
        return False
    if trimmed.count("```") % 2 != 0:
        return True
    if _NORMAL_ENDING.search(trimmed):
        return False
    return True

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


async def _get_session_by_uuid(
    db, session_uuid: _uuid.UUID, tenant_id=None,
) -> ChatSession | None:
    """Look up ChatSession by public UUID, optionally scoped to a tenant."""
    q = select(ChatSession).where(ChatSession.uuid == session_uuid)
    if tenant_id is not None:
        q = q.where(ChatSession.tenant_id == tenant_id)
    return (await db.execute(q)).scalar_one_or_none()


@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    req: CreateSessionRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
):
    """Create a new chat session."""
    api_key_id = getattr(request.state, "api_key_id", None)
    async with async_session() as session:
        chat_session = ChatSession(
            title=req.title,
            tenant_id=tenant.id,
            api_key_id=api_key_id,
            product_id=req.product_id,
            product_filter=req.product_filter,
            product_filter_source=req.product_filter_source or ("explicit" if req.product_id or req.product_filter else None),
            version_filter=req.version_filter,
        )
        session.add(chat_session)
        await session.commit()
        await session.refresh(chat_session)

        logger.info(
            "Chat session created",
            extra={
                "session_id": chat_session.id,
                "product_id": req.product_id,
                "product_filter": req.product_filter,
                "product_filter_source": chat_session.product_filter_source,
            },
        )

        return SessionResponse(
            id=str(chat_session.uuid),
            title=chat_session.title,
            product_id=chat_session.product_id,
            product_filter=chat_session.product_filter,
            product_filter_source=chat_session.product_filter_source,
            version_filter=chat_session.version_filter,
            doc_context=chat_session.doc_context,
            created_at=chat_session.created_at,
            updated_at=chat_session.updated_at,
            message_count=0,
        )


@router.patch("/sessions/{session_uuid}", response_model=SessionResponse)
async def update_session(
    session_uuid: _uuid.UUID,
    req: UpdateSessionRequest,
    tenant: Tenant = Depends(get_current_tenant),
):
    """Update session product/version filter."""
    async with async_session() as session:
        chat_session = await _get_session_by_uuid(session, session_uuid, tenant.id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        product_changed = (
            (req.product_id is not None and req.product_id != chat_session.product_id)
            or (req.product_filter is not None and (req.product_filter or None) != chat_session.product_filter)
        )

        if req.product_id is not None:
            chat_session.product_id = req.product_id or None
            chat_session.product_filter_source = "explicit" if req.product_id else None
        if req.product_filter is not None:
            new_product = req.product_filter or None
            chat_session.product_filter = new_product
            if not req.product_id:
                chat_session.product_filter_source = "explicit" if new_product else None
        if req.product_filter_source is not None:
            chat_session.product_filter_source = req.product_filter_source or None
        if req.version_filter is not None:
            chat_session.version_filter = req.version_filter or None

        if (
            chat_session.product_filter_source == "explicit"
            and chat_session.product_id is None
            and chat_session.product_filter
        ):
            resolve_result = await resolve_product(session, chat_session.product_filter)
            if resolve_result.product_id:
                chat_session.product_id = resolve_result.product_id
                logger.info(
                    "Auto-resolved product_id for explicit lock",
                    extra={
                        "session_id": chat_session.id,
                        "product_filter": chat_session.product_filter,
                        "product_id": resolve_result.product_id,
                        "product_name": resolve_result.product_name,
                    },
                )
            else:
                logger.warning(
                    "Could not resolve product_id for explicit lock - product not found",
                    extra={
                        "session_id": chat_session.id,
                        "product_filter": chat_session.product_filter,
                    },
                )

        if product_changed:
            chat_session.doc_context = None

        await session.commit()
        await session.refresh(chat_session)

        msg_count = await session.scalar(
            select(func.count(ChatMessage.id)).where(
                ChatMessage.session_id == chat_session.id
            )
        )

        logger.info(
            "Chat session updated",
            extra={
                "session_id": chat_session.id,
                "product_id": chat_session.product_id,
                "product_filter": chat_session.product_filter,
                "product_filter_source": chat_session.product_filter_source,
                "version_filter": chat_session.version_filter,
            },
        )

        return SessionResponse(
            id=str(chat_session.uuid),
            title=chat_session.title,
            product_id=chat_session.product_id,
            product_filter=chat_session.product_filter,
            product_filter_source=chat_session.product_filter_source,
            version_filter=chat_session.version_filter,
            doc_context=chat_session.doc_context,
            created_at=chat_session.created_at,
            updated_at=chat_session.updated_at,
            message_count=msg_count or 0,
        )


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions(tenant: Tenant = Depends(get_current_tenant)):
    """List all chat sessions, newest first."""
    async with async_session() as session:
        subq = (
            select(
                ChatMessage.session_id,
                func.count(ChatMessage.id).label("message_count"),
                func.max(ChatMessage.content).filter(
                    ChatMessage.role == "user"
                ).label("last_user_msg"),
            )
            .group_by(ChatMessage.session_id)
            .subquery()
        )

        result = await session.execute(
            select(
                ChatSession.uuid,
                ChatSession.title,
                ChatSession.product_id,
                ChatSession.product_filter,
                ChatSession.product_filter_source,
                ChatSession.version_filter,
                ChatSession.doc_context,
                ChatSession.created_at,
                ChatSession.updated_at,
                func.coalesce(subq.c.message_count, 0).label("message_count"),
                subq.c.last_user_msg,
            )
            .outerjoin(subq, ChatSession.id == subq.c.session_id)
            .where(ChatSession.tenant_id == tenant.id)
            .order_by(ChatSession.updated_at.desc())
        )

        rows = result.all()
        logger.info("Chat sessions listed", extra={"session_count": len(rows)})
        return [
            SessionListItem(
                id=str(row.uuid),
                title=row.title,
                product_id=row.product_id,
                product_filter=row.product_filter,
                product_filter_source=row.product_filter_source,
                version_filter=row.version_filter,
                doc_context=row.doc_context,
                created_at=row.created_at,
                updated_at=row.updated_at,
                message_count=row.message_count,
                last_message_preview=(row.last_user_msg[:100] if row.last_user_msg else None),
            )
            for row in rows
        ]


@router.get("/sessions/{session_uuid}", response_model=SessionDetailResponse)
async def get_session(session_uuid: _uuid.UUID, tenant: Tenant = Depends(get_current_tenant)):
    """Get session with full message history."""
    async with async_session() as session:
        chat_session = await _get_session_by_uuid(session, session_uuid, tenant.id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        msgs_result = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == chat_session.id)
            .order_by(ChatMessage.created_at)
        )
        messages = msgs_result.scalars().all()

        analytics_map: dict[int, ChatMessageAnalytics] = {}
        if messages:
            msg_ids = [m.id for m in messages if m.role == "assistant"]
            if msg_ids:
                analytics_result = await session.execute(
                    select(ChatMessageAnalytics)
                    .where(ChatMessageAnalytics.message_id.in_(msg_ids))
                )
                for a in analytics_result.scalars().all():
                    analytics_map[a.message_id] = a

        return SessionDetailResponse(
            id=str(chat_session.uuid),
            title=chat_session.title,
            product_id=chat_session.product_id,
            product_filter=chat_session.product_filter,
            product_filter_source=chat_session.product_filter_source,
            version_filter=chat_session.version_filter,
            doc_context=chat_session.doc_context,
            created_at=chat_session.created_at,
            updated_at=chat_session.updated_at,
            messages=[
                ChatMessageResponse(
                    id=m.id,
                    session_id=str(chat_session.uuid),
                    role=m.role,
                    content=m.content,
                    sources=m.sources,
                    duration_ms=m.duration_ms,
                    feedback=m.feedback,
                    feedback_comment=m.feedback_comment,
                    debug=analytics_map[m.id].to_debug_dict(
                        product_filter=chat_session.product_filter,
                        version_filter=chat_session.version_filter,
                        session_uuid=str(chat_session.uuid),
                    ) if m.id in analytics_map else None,
                    created_at=m.created_at,
                )
                for m in messages
            ],
        )


@router.delete("/sessions/{session_uuid}", status_code=204)
async def delete_session(session_uuid: _uuid.UUID, tenant: Tenant = Depends(get_current_tenant)):
    """Delete a chat session and all its messages."""
    async with async_session() as session:
        chat_session = await _get_session_by_uuid(session, session_uuid, tenant.id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")
        await session.delete(chat_session)
        await session.commit()
        logger.info("Chat session deleted", extra={"session_id": chat_session.id})


@router.post("/sessions/{session_uuid}/messages/{message_id}/feedback", status_code=200)
async def submit_feedback(
    session_uuid: _uuid.UUID,
    message_id: int,
    req: FeedbackRequest,
    tenant: Tenant = Depends(get_current_tenant),
):
    """Submit thumbs-up/down feedback on an assistant message."""
    async with async_session() as session:
        chat_session = await _get_session_by_uuid(session, session_uuid, tenant.id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")
        msg = await session.get(ChatMessage, message_id)
        if not msg or msg.session_id != chat_session.id:
            raise HTTPException(status_code=404, detail="Message not found")
        if msg.role != "assistant":
            raise HTTPException(status_code=400, detail="Feedback is only allowed on assistant messages")

        msg.feedback = req.feedback
        msg.feedback_comment = req.comment
        await session.commit()

        logger.info(
            "Message feedback submitted",
            extra={
                "session_id": chat_session.id,
                "message_id": message_id,
                "feedback": req.feedback,
                "has_comment": bool(req.comment),
            },
        )
        return {"status": "ok", "message_id": message_id, "feedback": req.feedback}


@router.post("/sessions/{session_uuid}/messages")
async def send_message(
    session_uuid: _uuid.UUID,
    req: SendMessageRequest,
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
):
    """Send a message and receive an SSE-streamed response.

    SSE events:
    - {"type": "progress", "stage": "..."} — pipeline stage indicator
    - {"type": "token", "content": "..."} — incremental text tokens
    - {"type": "sources", "sources": [...]} — retrieved documentation sources
    - {"type": "done", "message_id": N, "duration_ms": F} — stream complete
    - {"type": "error", "error_code": "...", "status_code": N} — error occurred
    """
    api_key_id = getattr(request.state, "api_key_id", None)
    tenant_id_str = str(tenant.id)
    api_key_id_str = str(api_key_id) if api_key_id else None

    async with async_session() as session:
        chat_session = await _get_session_by_uuid(session, session_uuid, tenant.id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")
        session_id = chat_session.id

    async def event_stream() -> AsyncGenerator[str, None]:
        t0 = time.perf_counter()
        token_count = 0
        request_id = str(uuid4())
        try:
            async with async_session() as db:
                chat_session = await db.get(ChatSession, session_id)

                user_msg = ChatMessage(
                    session_id=session_id,
                    role="user",
                    content=req.content,
                )
                db.add(user_msg)
                await db.flush()

                logger.info(
                    "Chat message received",
                    extra={
                        "session_id": session_id,
                        "query_length": len(req.content),
                        "product_filter": chat_session.product_filter,
                    },
                )

                msgs_result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .where(ChatMessage.id != user_msg.id)
                    .order_by(ChatMessage.created_at)
                )
                history = msgs_result.scalars().all()

                current_summary = chat_session.history_summary
                summary_meta: dict = {}
                history_list = list(history)
                if (
                    settings.summary_enabled
                    and len(history_list) > settings.summary_threshold
                ):
                    buffer_size = settings.rag_history_messages
                    old_messages = history_list[:-buffer_size] if buffer_size < len(history_list) else []
                    new_to_summarize = [
                        m for m in old_messages
                        if chat_session.summary_up_to_message_id is None
                        or m.id > chat_session.summary_up_to_message_id
                    ]
                    if new_to_summarize:
                        updated_summary, summary_meta = await summarize_history(
                            new_to_summarize, existing_summary=current_summary,
                        )
                        if updated_summary:
                            chat_session.history_summary = updated_summary
                            chat_session.summary_up_to_message_id = old_messages[-1].id
                            current_summary = updated_summary

                progress_queue: asyncio.Queue[dict | None] = asyncio.Queue()

                async def _on_progress(stage: str, meta: dict) -> None:
                    await progress_queue.put({"type": "progress", "stage": stage, **meta})

                rag_result_holder: dict = {}
                rag_error_holder: list[BaseException] = []

                async def _run_rag() -> None:
                    try:
                        _perms = getattr(request.state, "permissions", {})
                        _roles = getattr(request.state, "tenant_roles", [])
                        _role_ids = [r.id for r in _roles] if _roles else None
                        _allowed_qt = _perms.get("chat_context", {}).get("allowed_query_types")

                        msgs, srcs, dbg = await build_rag_prompt(
                            db=db,
                            query=req.content,
                            history=history_list,
                            product_id=chat_session.product_id,
                            product_filter=chat_session.product_filter,
                            version_filter=chat_session.version_filter,
                            doc_context=chat_session.doc_context,
                            product_filter_source=chat_session.product_filter_source,
                            history_summary=current_summary,
                            progress_callback=_on_progress,
                            role_ids=_role_ids,
                            allowed_query_types=_allowed_qt,
                            tenant_id=tenant_id_str,
                        )
                        rag_result_holder["messages"] = msgs
                        rag_result_holder["sources"] = srcs
                        rag_result_holder["rag_debug"] = dbg
                    except BaseException as exc:
                        rag_error_holder.append(exc)
                    finally:
                        await progress_queue.put(None)

                t_rag = time.perf_counter()
                rag_task = asyncio.create_task(_run_rag())

                while True:
                    event = await progress_queue.get()
                    if event is None:
                        break
                    yield f"data: {json.dumps(event)}\n\n"

                await rag_task
                if rag_error_holder:
                    raise rag_error_holder[0]

                messages = rag_result_holder["messages"]
                sources = rag_result_holder["sources"]
                rag_debug = rag_result_holder["rag_debug"]
                rag_ms = round((time.perf_counter() - t_rag) * 1000, 1)
                if summary_meta:
                    rag_debug.update(summary_meta)

                auto_prod = rag_debug.get("auto_product")
                if auto_prod and chat_session.product_filter != auto_prod:
                    if chat_session.product_filter_source != "explicit":
                        chat_session.product_filter = auto_prod
                        chat_session.product_filter_source = "auto"
                        chat_session.doc_context = None
                if not chat_session.doc_context:
                    detected = rag_debug.get("detected_doc_context")
                    if detected:
                        chat_session.doc_context = detected
                        logger.info(
                            "Session context locked",
                            extra={
                                "session_id": session_id,
                                "doc_context": detected,
                                "product_filter": chat_session.product_filter,
                            },
                        )

                yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

                effective_max_tokens = rag_debug.get("type_max_tokens") or settings.llm_max_tokens

                query_tokens = rag_debug.get("query_tokens", 0)
                context_tokens = rag_debug.get("context_tokens", 0)
                history_tokens = rag_debug.get("history_tokens", 0)
                system_prompt_tokens = rag_debug.get("system_prompt_tokens", 0)
                prompt_estimate = query_tokens + context_tokens + history_tokens + system_prompt_tokens

                debug_partial = {
                    "session_id": str(session_uuid),
                    "user_message_id": user_msg.id,
                    "timestamp": user_msg.created_at.isoformat() if user_msg.created_at else datetime.now(timezone.utc).isoformat(),
                    "model": settings.openai_llm_model if settings.llm_provider == "openai" else settings.llm_model,
                    "llm_provider": settings.llm_provider,
                    "temperature": settings.llm_temperature,
                    "max_tokens": effective_max_tokens,
                    "rag_ms": rag_ms,
                    "user_input_tokens": query_tokens,
                    "llm_prompt_tokens": prompt_estimate,
                    "query_tokens": query_tokens,
                    "context_tokens": context_tokens,
                    "history_tokens": history_tokens,
                    "system_prompt_tokens": system_prompt_tokens,
                    **{k: v for k, v in rag_debug.items() if k not in (
                        "query_tokens", "context_tokens", "history_tokens", "system_prompt_tokens",
                    )},
                }
                yield f"data: {json.dumps({'type': 'debug_partial', 'debug': debug_partial})}\n\n"

                effective_reasoning = rag_debug.get("reasoning_effort")

                t_llm = time.perf_counter()
                full_response: list[str] = []
                llm_meta: dict = {}
                continuations = 0
                llm_messages = list(messages)

                final_finish_reason = "stop"

                _HEARTBEAT_INTERVAL = 10.0

                while True:
                    llm_meta_chunk: dict = {}
                    got_first_token = False
                    token_queue: asyncio.Queue[str | None] = asyncio.Queue()
                    _llm_msgs = llm_messages
                    _eff_max = effective_max_tokens
                    _eff_reas = effective_reasoning

                    async def _fill_queue() -> None:
                        try:
                            async for tok in stream_chat_completion(_llm_msgs, max_tokens=_eff_max, metadata=llm_meta_chunk, reasoning_effort=_eff_reas):
                                await token_queue.put(tok)
                        finally:
                            await token_queue.put(None)

                    fill_task = asyncio.create_task(_fill_queue())
                    try:
                        while True:
                            try:
                                timeout = _HEARTBEAT_INTERVAL if not got_first_token else None
                                token = await asyncio.wait_for(token_queue.get(), timeout=timeout)
                            except asyncio.TimeoutError:
                                if fill_task.done():
                                    exc = fill_task.exception()
                                    if exc:
                                        raise exc
                                yield ": keepalive\n\n"
                                continue
                            if token is None:
                                if fill_task.done():
                                    exc = fill_task.exception()
                                    if exc:
                                        raise exc
                                break
                            got_first_token = True
                            full_response.append(token)
                            token_count += 1
                            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
                    finally:
                        if not fill_task.done():
                            fill_task.cancel()
                            try:
                                await fill_task
                            except (asyncio.CancelledError, Exception):
                                pass

                    if not llm_meta:
                        llm_meta.update(llm_meta_chunk)
                    else:
                        llm_meta["first_token_ms"] = llm_meta.get("first_token_ms", 0)

                    chunk_finish = llm_meta_chunk.get("finish_reason", "stop")
                    needs_continuation = chunk_finish == "length"

                    if not needs_continuation and chunk_finish == "stop":
                        partial_text = "".join(full_response)
                        if _looks_incomplete(partial_text):
                            needs_continuation = True
                            logger.info(
                                "Heuristic detected incomplete response despite finish_reason=stop",
                                extra={
                                    "session_id": session_id,
                                    "tokens_so_far": token_count,
                                    "tail": partial_text[-80:],
                                },
                            )

                    if not needs_continuation:
                        final_finish_reason = chunk_finish
                        break

                    continuations += 1
                    if continuations > MAX_CONTINUATIONS:
                        final_finish_reason = "max_continuations"
                        logger.warning(
                            "Max continuations reached",
                            extra={"session_id": session_id, "continuations": continuations},
                        )
                        break

                    logger.info(
                        "Auto-continuing truncated response",
                        extra={
                            "session_id": session_id,
                            "continuation": continuations,
                            "tokens_so_far": token_count,
                            "reason": chunk_finish,
                        },
                    )
                    partial = "".join(full_response)
                    llm_messages = list(messages) + [
                        {"role": "assistant", "content": partial},
                        {"role": "user", "content": CONTINUE_PROMPT},
                    ]

                llm_ms = round((time.perf_counter() - t_llm) * 1000, 1)

                duration_ms = round((time.perf_counter() - t0) * 1000, 1)
                assistant_content = "".join(full_response)

                assistant_msg = ChatMessage(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_content,
                    sources=sources,
                    duration_ms=duration_ms,
                )
                db.add(assistant_msg)

                if not chat_session.title and assistant_content:
                    chat_session.title = req.content[:80]
                chat_session.updated_at = datetime.now(timezone.utc)

                await db.commit()
                await db.refresh(assistant_msg)

                tokens_per_sec = round(token_count / (llm_ms / 1000), 1) if llm_ms > 0 else 0

                usage = llm_meta.get("usage", {})
                llm_prompt_tokens = usage.get("prompt_tokens", 0) or prompt_estimate
                llm_completion_tokens = usage.get("completion_tokens", 0) or token_count
                llm_total_tokens = usage.get("total_tokens", 0) or (llm_prompt_tokens + llm_completion_tokens)

                user_input_tokens = query_tokens
                user_output_tokens = llm_completion_tokens

                debug_info = {
                    "session_id": str(session_uuid),
                    "message_id": assistant_msg.id,
                    "user_message_id": user_msg.id,
                    "timestamp": user_msg.created_at.isoformat() if user_msg.created_at else datetime.now(timezone.utc).isoformat(),
                    "model": llm_meta.get("model", ""),
                    "llm_provider": llm_meta.get("provider", ""),
                    "temperature": llm_meta.get("temperature", 0),
                    "max_tokens": llm_meta.get("max_tokens", 0),
                    "first_token_ms": llm_meta.get("first_token_ms", 0),
                    "finish_reason": final_finish_reason,
                    "continuations": continuations,
                    "rag_ms": rag_ms,
                    "llm_ms": llm_ms,
                    "total_ms": duration_ms,
                    "token_count": token_count,
                    "tokens_per_sec": tokens_per_sec,
                    "response_length": len(assistant_content),
                    "user_input_tokens": user_input_tokens,
                    "user_output_tokens": user_output_tokens,
                    "llm_prompt_tokens": llm_prompt_tokens,
                    "llm_completion_tokens": llm_completion_tokens,
                    "llm_total_tokens": llm_total_tokens,
                    **rag_debug,
                }

                yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg.id, 'duration_ms': duration_ms, 'request_id': request_id, 'product_filter': chat_session.product_filter, 'product_filter_source': chat_session.product_filter_source, 'version_filter': chat_session.version_filter, 'auto_product': rag_debug.get('auto_product'), 'debug': debug_info})}\n\n"

                analytics = ChatMessageAnalytics(
                    message_id=assistant_msg.id,
                    session_id=session_id,
                    user_message_id=user_msg.id,
                    llm_provider=debug_info.get("llm_provider", ""),
                    model=debug_info.get("model", ""),
                    temperature=debug_info.get("temperature", 0),
                    max_tokens=debug_info.get("max_tokens", 0),
                    token_count=debug_info.get("token_count", 0),
                    tokens_per_sec=debug_info.get("tokens_per_sec", 0),
                    response_length=debug_info.get("response_length", 0),
                    total_ms=debug_info.get("total_ms", 0),
                    rag_ms=debug_info.get("rag_ms", 0),
                    llm_ms=debug_info.get("llm_ms", 0),
                    search_ms=debug_info.get("search_ms", 0),
                    first_token_ms=debug_info.get("first_token_ms", 0),
                    rag_build_ms=debug_info.get("rag_build_ms", 0),
                    chunks_found=debug_info.get("chunks_found", 0),
                    top_similarity=debug_info.get("top_similarity", 0),
                    min_similarity=debug_info.get("min_similarity", 0),
                    context_tokens=debug_info.get("context_tokens", 0),
                    query_tokens=debug_info.get("query_tokens", 0),
                    history_tokens=debug_info.get("history_tokens", 0),
                    system_prompt_tokens=debug_info.get("system_prompt_tokens", 0),
                    effective_top_k=debug_info.get("effective_top_k"),
                    history_messages=debug_info.get("history_messages", 0),
                    prompt_messages=debug_info.get("prompt_messages", 0),
                    embedding_model=debug_info.get("embedding_model", ""),
                    embedding_api_tokens=debug_info.get("embedding_api_tokens", 0),
                    doc_context=debug_info.get("doc_context"),
                    auto_product=debug_info.get("auto_product"),
                    detected_doc_context=debug_info.get("detected_doc_context"),
                    search_query=debug_info.get("search_query"),
                    query_type=debug_info.get("query_type"),
                    prompt_hash=debug_info.get("prompt_hash"),
                    user_input_tokens=user_input_tokens,
                    user_output_tokens=user_output_tokens,
                    llm_prompt_tokens=llm_prompt_tokens,
                    llm_completion_tokens=llm_completion_tokens,
                    llm_total_tokens=llm_total_tokens,
                    finish_reason=final_finish_reason,
                    continuations=continuations,
                    classify_input=debug_info.get("classify_input"),
                    classify_product=debug_info.get("classify_product"),
                    classify_prompt_tokens=debug_info.get("classify_prompt_tokens", 0),
                    classify_completion_tokens=debug_info.get("classify_completion_tokens", 0),
                    classify_total_tokens=debug_info.get("classify_total_tokens", 0),
                    classify_model=debug_info.get("classify_model"),
                    classify_ms=debug_info.get("classify_ms"),
                    resolve_prompt_tokens=debug_info.get("resolve_prompt_tokens", 0),
                    resolve_completion_tokens=debug_info.get("resolve_completion_tokens", 0),
                    resolve_total_tokens=debug_info.get("resolve_total_tokens", 0),
                    resolve_model=debug_info.get("resolve_model"),
                    resolve_ms=debug_info.get("resolve_ms"),
                    rerank_prompt_tokens=debug_info.get("rerank_prompt_tokens", 0),
                    rerank_completion_tokens=debug_info.get("rerank_completion_tokens", 0),
                    rerank_total_tokens=debug_info.get("rerank_total_tokens", 0),
                    rerank_model=debug_info.get("rerank_model"),
                    decompose_used=bool(debug_info.get("decompose_used")),
                    decompose_sub_queries=debug_info.get("decompose_sub_queries"),
                    decompose_sub_products=debug_info.get("decompose_sub_products"),
                    decompose_prompt_tokens=debug_info.get("decompose_prompt_tokens", 0),
                    decompose_completion_tokens=debug_info.get("decompose_completion_tokens", 0),
                    decompose_total_tokens=debug_info.get("decompose_total_tokens", 0),
                    decompose_model=debug_info.get("decompose_model"),
                    decompose_ms=debug_info.get("decompose_ms"),
                    web_search_used=bool(debug_info.get("web_search_used")),
                    web_search_queries=debug_info.get("web_search_queries"),
                    web_search_sources_count=debug_info.get("web_search_sources_count", 0),
                    web_search_prompt_tokens=debug_info.get("web_search_prompt_tokens", 0),
                    web_search_completion_tokens=debug_info.get("web_search_completion_tokens", 0),
                    web_search_total_tokens=debug_info.get("web_search_total_tokens", 0),
                    web_search_model=debug_info.get("web_search_model"),
                    web_search_ms=debug_info.get("web_search_ms"),
                    web_search_context_length=debug_info.get("web_search_context_length", 0),
                    rewrite_prompt_tokens=debug_info.get("rewrite_prompt_tokens", 0),
                    rewrite_completion_tokens=debug_info.get("rewrite_completion_tokens", 0),
                    rewrite_total_tokens=debug_info.get("rewrite_total_tokens", 0),
                    rewrite_model=debug_info.get("rewrite_model"),
                    retry_used=bool(debug_info.get("retry_used")),
                    rephrase_ms=debug_info.get("rephrase_ms"),
                    rephrase_query=debug_info.get("rephrase_query"),
                    rephrase_prompt_tokens=debug_info.get("rephrase_prompt_tokens", 0),
                    rephrase_completion_tokens=debug_info.get("rephrase_completion_tokens", 0),
                    rephrase_total_tokens=debug_info.get("rephrase_total_tokens", 0),
                    rephrase_model=debug_info.get("rephrase_model"),
                    summary_prompt_tokens=debug_info.get("summary_prompt_tokens", 0),
                    summary_completion_tokens=debug_info.get("summary_completion_tokens", 0),
                    summary_total_tokens=debug_info.get("summary_total_tokens", 0),
                    summary_model=debug_info.get("summary_model"),
                    summary_ms=debug_info.get("summary_ms"),
                )
                db.add(analytics)
                await db.commit()

                await write_usage_log(
                    channel="chat",
                    action="chat_completion",
                    request_id=request_id,
                    llm_provider=llm_meta.get("provider"),
                    llm_model=llm_meta.get("model"),
                    prompt_tokens=llm_prompt_tokens,
                    completion_tokens=llm_completion_tokens,
                    context_chunks=rag_debug.get("chunks_found", 0),
                    context_tokens=rag_debug.get("context_tokens", 0),
                    history_messages=rag_debug.get("history_messages", 0),
                    query_tokens=rag_debug.get("query_tokens", 0),
                    history_tokens=rag_debug.get("history_tokens", 0),
                    system_prompt_tokens=rag_debug.get("system_prompt_tokens", 0),
                    query_text=req.content,
                    result_count=len(sources),
                    response_tokens=token_count,
                    response_length=len(assistant_content),
                    top_similarity=rag_debug.get("top_similarity", 0),
                    product_filter=chat_session.product_filter,
                    version_filter=chat_session.version_filter,
                    duration_ms=duration_ms,
                    search_ms=rag_debug.get("search_ms", 0),
                    llm_ms=llm_ms,
                    tenant_id=tenant_id_str,
                    api_key_id=api_key_id_str,
                    chat_session_id=session_id,
                )

                classify_prompt_tokens = rag_debug.get("classify_prompt_tokens", 0)
                classify_completion_tokens = rag_debug.get("classify_completion_tokens", 0)
                if classify_prompt_tokens > 0 or classify_completion_tokens > 0:
                    await write_usage_log(
                        channel="chat",
                        action="query_classify",
                        request_id=request_id,
                        llm_provider="openai",
                        llm_model=rag_debug.get("classify_model", ""),
                        prompt_tokens=classify_prompt_tokens,
                        completion_tokens=classify_completion_tokens,
                        query_text=req.content,
                        product_filter=chat_session.product_filter,
                        duration_ms=rag_debug.get("classify_ms", 0),
                        tenant_id=tenant_id_str,
                        api_key_id=api_key_id_str,
                        chat_session_id=session_id,
                    )

                if rag_debug.get("retry_used"):
                    await write_usage_log(
                        channel="chat",
                        action="search_retry_rephrase",
                        request_id=request_id,
                        llm_provider="openai",
                        llm_model=rag_debug.get("rephrase_model", settings.openai_llm_model),
                        prompt_tokens=rag_debug.get("rephrase_prompt_tokens", 0),
                        completion_tokens=rag_debug.get("rephrase_completion_tokens", 0),
                        query_text=req.content,
                        duration_ms=rag_debug.get("rephrase_ms", 0),
                        tenant_id=tenant_id_str,
                        api_key_id=api_key_id_str,
                        chat_session_id=session_id,
                    )

                if summary_meta.get("summary_total_tokens", 0) > 0:
                    await write_usage_log(
                        channel="chat",
                        action="history_summarize",
                        request_id=request_id,
                        llm_provider="openai",
                        llm_model=summary_meta.get("summary_model", ""),
                        prompt_tokens=summary_meta.get("summary_prompt_tokens", 0),
                        completion_tokens=summary_meta.get("summary_completion_tokens", 0),
                        query_text=req.content,
                        product_filter=chat_session.product_filter,
                        duration_ms=summary_meta.get("summary_ms", 0),
                        tenant_id=tenant_id_str,
                        api_key_id=api_key_id_str,
                        chat_session_id=session_id,
                    )

                decompose_prompt_tokens = rag_debug.get("decompose_prompt_tokens", 0)
                decompose_completion_tokens = rag_debug.get("decompose_completion_tokens", 0)
                if decompose_prompt_tokens > 0 or decompose_completion_tokens > 0:
                    await write_usage_log(
                        channel="chat",
                        action="query_decompose",
                        request_id=request_id,
                        llm_provider="openai",
                        llm_model=rag_debug.get("decompose_model", ""),
                        prompt_tokens=decompose_prompt_tokens,
                        completion_tokens=decompose_completion_tokens,
                        query_text=req.content,
                        product_filter=chat_session.product_filter,
                        duration_ms=rag_debug.get("decompose_ms", 0),
                        tenant_id=tenant_id_str,
                        api_key_id=api_key_id_str,
                        chat_session_id=session_id,
                    )

                web_search_total = rag_debug.get("web_search_total_tokens", 0)
                if web_search_total > 0:
                    await write_usage_log(
                        channel="chat",
                        action="web_search_grounding",
                        request_id=request_id,
                        llm_provider="google",
                        llm_model=rag_debug.get("web_search_model", ""),
                        prompt_tokens=rag_debug.get("web_search_prompt_tokens", 0),
                        completion_tokens=rag_debug.get("web_search_completion_tokens", 0),
                        query_text=req.content,
                        product_filter=chat_session.product_filter,
                        duration_ms=rag_debug.get("web_search_ms", 0),
                        tenant_id=tenant_id_str,
                        api_key_id=api_key_id_str,
                        chat_session_id=session_id,
                    )

                rerank_total = rag_debug.get("rerank_total_tokens", 0)
                if rerank_total > 0:
                    await write_usage_log(
                        channel="chat",
                        action="rerank",
                        request_id=request_id,
                        llm_provider="openai",
                        llm_model=rag_debug.get("rerank_model", ""),
                        prompt_tokens=rag_debug.get("rerank_prompt_tokens", 0),
                        completion_tokens=rag_debug.get("rerank_completion_tokens", 0),
                        query_text=req.content,
                        product_filter=chat_session.product_filter,
                        duration_ms=rag_debug.get("rerank_ms", 0),
                        tenant_id=tenant_id_str,
                        api_key_id=api_key_id_str,
                        chat_session_id=session_id,
                    )

                resolve_total = rag_debug.get("resolve_total_tokens", 0)
                if resolve_total > 0:
                    await write_usage_log(
                        channel="chat",
                        action="product_resolve",
                        request_id=request_id,
                        llm_provider="openai",
                        llm_model=rag_debug.get("resolve_model", ""),
                        prompt_tokens=rag_debug.get("resolve_prompt_tokens", 0),
                        completion_tokens=rag_debug.get("resolve_completion_tokens", 0),
                        query_text=req.content,
                        product_filter=chat_session.product_filter,
                        duration_ms=rag_debug.get("resolve_ms", 0),
                        tenant_id=tenant_id_str,
                        api_key_id=api_key_id_str,
                        chat_session_id=session_id,
                    )

                rewrite_total = rag_debug.get("rewrite_total_tokens", 0)
                if rewrite_total > 0:
                    await write_usage_log(
                        channel="chat",
                        action="query_rewrite",
                        request_id=request_id,
                        llm_provider="openai",
                        llm_model=rag_debug.get("rewrite_model", ""),
                        prompt_tokens=rag_debug.get("rewrite_prompt_tokens", 0),
                        completion_tokens=rag_debug.get("rewrite_completion_tokens", 0),
                        query_text=req.content,
                        product_filter=chat_session.product_filter,
                        duration_ms=rag_debug.get("rewrite_ms", 0),
                        tenant_id=tenant_id_str,
                        api_key_id=api_key_id_str,
                        chat_session_id=session_id,
                    )

                embed_api_tokens = rag_debug.get("embedding_api_tokens", 0)
                if embed_api_tokens > 0:
                    await write_usage_log(
                        channel="chat",
                        action="query_embedding",
                        request_id=request_id,
                        llm_provider="google",
                        llm_model=rag_debug.get("embedding_model", ""),
                        prompt_tokens=embed_api_tokens,
                        completion_tokens=0,
                        query_text=req.content,
                        product_filter=chat_session.product_filter,
                        duration_ms=0,
                        tenant_id=tenant_id_str,
                        api_key_id=api_key_id_str,
                        chat_session_id=session_id,
                    )

                if sources:
                    try:
                        total_ctx = rag_debug.get("context_tokens", 0)
                        for src in sources:
                            doc_id = src.get("document_id")
                            if not doc_id:
                                continue
                            preview_len = len(src.get("content_preview", ""))
                            chunk_tokens = max(1, preview_len // 4)
                            share = chunk_tokens / total_ctx if total_ctx > 0 else 0
                            db.add(DocumentUsageLog(
                                request_id=request_id,
                                session_id=session_id,
                                message_id=assistant_msg.id,
                                document_id=doc_id,
                                product_id=chat_session.product_id,
                                heading_path=src.get("heading_path", ""),
                                similarity=src.get("similarity", 0),
                                context_tokens=chunk_tokens,
                                query_text=req.content[:500],
                                query_type=rag_debug.get("query_type"),
                                sub_query=src.get("sub_query"),
                                charge_usd=Decimal(str(round(
                                    float(debug_info.get("charge_usd", 0) or 0) * share, 8
                                ))),
                                tenant_id=tenant.id,
                                api_key_id=api_key_id,
                            ))
                        await db.commit()
                    except Exception:
                        logger.warning("Failed to write document_usage_log", exc_info=True)

                logger.info(
                    "Chat message completed",
                    extra={
                        "session_id": session_id,
                        "message_id": assistant_msg.id,
                        "duration_ms": duration_ms,
                        "rag_ms": rag_ms,
                        "llm_ms": llm_ms,
                        "token_count": token_count,
                        "tokens_per_sec": tokens_per_sec,
                        "response_length": len(assistant_content),
                        "sources_count": len(sources),
                        "product_filter": chat_session.product_filter,
                        "request_id": request_id,
                        "llm_prompt_tokens": llm_prompt_tokens,
                        "llm_completion_tokens": llm_completion_tokens,
                        "user_input_tokens": user_input_tokens,
                        "user_output_tokens": user_output_tokens,
                        "finish_reason": final_finish_reason,
                        "continuations": continuations,
                    },
                )

        except asyncio.CancelledError:
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            logger.warning(
                "Chat stream cancelled (client disconnected)",
                extra={
                    "session_id": session_id,
                    "duration_ms": duration_ms,
                    "token_count": token_count,
                    "request_id": request_id,
                },
            )
            return
        except LLMError as e:
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            logger.exception(
                "Chat stream error",
                extra={
                    "session_id": session_id,
                    "duration_ms": duration_ms,
                    "token_count": token_count,
                    "error_type": "LLMError",
                    "error_code": e.error_code,
                    "status_code": e.status_code,
                    "request_id": request_id,
                },
            )
            yield f"data: {json.dumps({'type': 'error', 'error_code': e.error_code, 'status_code': e.status_code, 'error_type': 'LLMError', 'detail': e.detail})}\n\n"
        except Exception as e:
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            error_type = type(e).__name__
            detail = str(e)[:300]
            logger.exception(
                "Chat stream error",
                extra={
                    "session_id": session_id,
                    "duration_ms": duration_ms,
                    "token_count": token_count,
                    "error_type": error_type,
                    "request_id": request_id,
                },
            )
            yield f"data: {json.dumps({'type': 'error', 'error_code': 'internal_error', 'error_type': error_type, 'detail': detail})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
