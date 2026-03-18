"""Chat REST API with SSE streaming."""

import json
import logging
import time
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.chat.rag import build_rag_prompt
from app.chat.schemas import (
    ChatMessageResponse,
    CreateSessionRequest,
    SendMessageRequest,
    SessionDetailResponse,
    SessionListItem,
    SessionResponse,
)
from app.database import async_session
from app.llm.client import stream_chat_completion
from app.models import ChatMessage, ChatSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])



@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(req: CreateSessionRequest):
    """Create a new chat session."""
    async with async_session() as session:
        chat_session = ChatSession(
            title=req.title,
            device_filter=req.device_filter,
            version_filter=req.version_filter,
        )
        session.add(chat_session)
        await session.commit()
        await session.refresh(chat_session)

        logger.info(
            "Chat session created",
            extra={
                "session_id": chat_session.id,
                "device_filter": req.device_filter,
            },
        )

        return SessionResponse(
            id=chat_session.id,
            title=chat_session.title,
            device_filter=chat_session.device_filter,
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
                ChatSession.device_filter,
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
                device_filter=row.device_filter,
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

        return SessionDetailResponse(
            id=chat_session.id,
            title=chat_session.title,
            device_filter=chat_session.device_filter,
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
    - {"type": "error", "content": "..."} — error occurred
    """
    async with async_session() as session:
        chat_session = await session.get(ChatSession, session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

    async def event_stream() -> AsyncGenerator[str, None]:
        t0 = time.perf_counter()
        token_count = 0
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
                        "device_filter": chat_session.device_filter,
                    },
                )

                msgs_result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.created_at)
                )
                history = msgs_result.scalars().all()

                t_rag = time.perf_counter()
                messages, sources, rag_debug = await build_rag_prompt(
                    db=db,
                    query=req.content,
                    history=list(history),
                    device_filter=chat_session.device_filter,
                    version_filter=chat_session.version_filter,
                    doc_context=chat_session.doc_context,
                )
                rag_ms = round((time.perf_counter() - t_rag) * 1000, 1)

                if not chat_session.device_filter:
                    auto_dev = rag_debug.get("auto_device")
                    if auto_dev:
                        chat_session.device_filter = auto_dev
                if not chat_session.doc_context:
                    detected = rag_debug.get("detected_doc_context")
                    if detected:
                        chat_session.doc_context = detected
                        logger.info(
                            "Session context locked",
                            extra={
                                "session_id": session_id,
                                "doc_context": detected,
                                "device_filter": chat_session.device_filter,
                            },
                        )

                yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

                t_llm = time.perf_counter()
                full_response = []
                async for token in stream_chat_completion(messages):
                    full_response.append(token)
                    token_count += 1
                    yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
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

                from app.config import settings as _cfg
                from app.llm.client import _effective_model
                debug_info = {
                    "session_id": session_id,
                    "message_id": assistant_msg.id,
                    "user_message_id": user_msg.id,
                    "model": _effective_model(),
                    "rag_ms": rag_ms,
                    "llm_ms": llm_ms,
                    "total_ms": duration_ms,
                    "token_count": token_count,
                    "tokens_per_sec": tokens_per_sec,
                    "response_length": len(assistant_content),
                    **rag_debug,
                }

                yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_msg.id, 'duration_ms': duration_ms, 'debug': debug_info})}\n\n"

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
                        "device_filter": chat_session.device_filter,
                    },
                )

        except Exception as e:
            duration_ms = round((time.perf_counter() - t0) * 1000, 1)
            logger.exception(
                "Chat stream error",
                extra={
                    "session_id": session_id,
                    "duration_ms": duration_ms,
                    "token_count": token_count,
                    "error_type": type(e).__name__,
                },
            )
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
