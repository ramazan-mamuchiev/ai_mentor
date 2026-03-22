"""Chat REST API with SSE streaming."""

import json
import logging
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.billing.usage_writer import write_usage_log
from app.chat.rag import build_rag_prompt
from app.chat.schemas import (
    ChatMessageResponse,
    CreateSessionRequest,
    SendMessageRequest,
    SessionDetailResponse,
    SessionListItem,
    SessionResponse,
)
from app.config import settings
from app.database import async_session
from app.llm.client import LLMError, stream_chat_completion
from app.models import ChatMessage, ChatMessageAnalytics, ChatSession

MAX_CONTINUATIONS = settings.llm_max_continuations
CONTINUE_PROMPT = "Continue exactly where you stopped. RULES: 1) Do NOT repeat ANY text, tables, headers, or code blocks already written. 2) Do NOT re-output table column headers. 3) No preamble — continue the text seamlessly."

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])



@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(req: CreateSessionRequest):
    """Create a new chat session."""
    async with async_session() as session:
        chat_session = ChatSession(
            title=req.title,
            product_filter=req.product_filter,
            version_filter=req.version_filter,
        )
        session.add(chat_session)
        await session.commit()
        await session.refresh(chat_session)

        logger.info(
            "Chat session created",
            extra={
                "session_id": chat_session.id,
                "product_filter": req.product_filter,
            },
        )

        return SessionResponse(
            id=chat_session.id,
            title=chat_session.title,
            product_filter=chat_session.product_filter,
            version_filter=chat_session.version_filter,
            doc_context=chat_session.doc_context,
            created_at=chat_session.created_at,
            updated_at=chat_session.updated_at,
            message_count=0,
        )


@router.get("/sessions", response_model=list[SessionListItem])
async def list_sessions():
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
                ChatSession.id,
                ChatSession.title,
                ChatSession.product_filter,
                ChatSession.version_filter,
                ChatSession.doc_context,
                ChatSession.created_at,
                ChatSession.updated_at,
                func.coalesce(subq.c.message_count, 0).label("message_count"),
                subq.c.last_user_msg,
            )
            .outerjoin(subq, ChatSession.id == subq.c.session_id)
            .order_by(ChatSession.updated_at.desc())
        )

        rows = result.all()
        logger.info("Chat sessions listed", extra={"session_count": len(rows)})
        return [
            SessionListItem(
                id=row.id,
                title=row.title,
                product_filter=row.product_filter,
                version_filter=row.version_filter,
                doc_context=row.doc_context,
                created_at=row.created_at,
                updated_at=row.updated_at,
                message_count=row.message_count,
                last_message_preview=(row.last_user_msg[:100] if row.last_user_msg else None),
            )
            for row in rows
        ]


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(session_id: int):
    """Get session with full message history."""
    async with async_session() as session:
        chat_session = await session.get(ChatSession, session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        msgs_result = await session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
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
            id=chat_session.id,
            title=chat_session.title,
            product_filter=chat_session.product_filter,
            version_filter=chat_session.version_filter,
            doc_context=chat_session.doc_context,
            created_at=chat_session.created_at,
            updated_at=chat_session.updated_at,
            messages=[
                ChatMessageResponse(
                    id=m.id,
                    session_id=m.session_id,
                    role=m.role,
                    content=m.content,
                    sources=m.sources,
                    duration_ms=m.duration_ms,
                    debug=analytics_map[m.id].to_debug_dict(
                        product_filter=chat_session.product_filter,
                        version_filter=chat_session.version_filter,
                    ) if m.id in analytics_map else None,
                    created_at=m.created_at,
                )
                for m in messages
            ],
        )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: int):
    """Delete a chat session and all its messages."""
    async with async_session() as session:
        chat_session = await session.get(ChatSession, session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")
        await session.delete(chat_session)
        await session.commit()
        logger.info("Chat session deleted", extra={"session_id": session_id})


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: int, req: SendMessageRequest):
    """Send a message and receive an SSE-streamed response.

    SSE events:
    - {"type": "token", "content": "..."} — incremental text tokens
    - {"type": "sources", "sources": [...]} — retrieved documentation sources
    - {"type": "done", "message_id": N, "duration_ms": F} — stream complete
    - {"type": "error", "error_code": "...", "status_code": N} — error occurred
    """
    async with async_session() as session:
        chat_session = await session.get(ChatSession, session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

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

                t_rag = time.perf_counter()
                messages, sources, rag_debug = await build_rag_prompt(
                    db=db,
                    query=req.content,
                    history=list(history),
                    product_filter=chat_session.product_filter,
                    version_filter=chat_session.version_filter,
                    doc_context=chat_session.doc_context,
                )
                rag_ms = round((time.perf_counter() - t_rag) * 1000, 1)

                if not chat_session.product_filter:
                    auto_prod = rag_debug.get("auto_product")
                    if auto_prod:
                        chat_session.product_filter = auto_prod
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

                query_tokens = rag_debug.get("query_tokens", 0)
                context_tokens = rag_debug.get("context_tokens", 0)
                history_tokens = rag_debug.get("history_tokens", 0)
                system_prompt_tokens = rag_debug.get("system_prompt_tokens", 0)
                prompt_estimate = query_tokens + context_tokens + history_tokens + system_prompt_tokens

                debug_partial = {
                    "session_id": session_id,
                    "user_message_id": user_msg.id,
                    "timestamp": user_msg.created_at.isoformat() if user_msg.created_at else datetime.now(timezone.utc).isoformat(),
                    "model": settings.llm_model,
                    "llm_provider": settings.llm_provider,
                    "temperature": settings.llm_temperature,
                    "max_tokens": settings.llm_max_tokens,
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

                t_llm = time.perf_counter()
                full_response: list[str] = []
                llm_meta: dict = {}
                continuations = 0
                llm_messages = list(messages)

                while True:
                    llm_meta_chunk: dict = {}
                    async for token in stream_chat_completion(llm_messages, metadata=llm_meta_chunk):
                        full_response.append(token)
                        token_count += 1
                        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

                    if not llm_meta:
                        llm_meta.update(llm_meta_chunk)
                    else:
                        llm_meta["first_token_ms"] = llm_meta.get("first_token_ms", 0)

                    if llm_meta_chunk.get("finish_reason") != "length":
                        break

                    continuations += 1
                    if continuations > MAX_CONTINUATIONS:
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
                    "session_id": session_id,
                    "message_id": assistant_msg.id,
                    "user_message_id": user_msg.id,
                    "timestamp": user_msg.created_at.isoformat() if user_msg.created_at else datetime.now(timezone.utc).isoformat(),
                    "model": llm_meta.get("model", ""),
                    "llm_provider": llm_meta.get("provider", ""),
                    "temperature": llm_meta.get("temperature", 0),
                    "max_tokens": llm_meta.get("max_tokens", 0),
                    "first_token_ms": llm_meta.get("first_token_ms", 0),
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

                yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg.id, 'duration_ms': duration_ms, 'request_id': request_id, 'debug': debug_info})}\n\n"

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
                    history_messages=debug_info.get("history_messages", 0),
                    prompt_messages=debug_info.get("prompt_messages", 0),
                    embedding_model=debug_info.get("embedding_model", ""),
                    doc_context=debug_info.get("doc_context"),
                    auto_product=debug_info.get("auto_product"),
                    detected_doc_context=debug_info.get("detected_doc_context"),
                    search_query=debug_info.get("search_query"),
                    user_input_tokens=user_input_tokens,
                    user_output_tokens=user_output_tokens,
                    llm_prompt_tokens=llm_prompt_tokens,
                    llm_completion_tokens=llm_completion_tokens,
                    llm_total_tokens=llm_total_tokens,
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
                )

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
                    },
                )

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
