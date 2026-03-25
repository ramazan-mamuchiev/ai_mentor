"""Share API — public snapshot links for chat sessions and messages."""

import logging
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.database import async_session
from app.models import ChatMessage, ChatSession, SharedLink
from app.share.schemas import SharedContentResponse, SharedLinkResponse, SharedMessageSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["share"])


def _generate_token() -> str:
    return uuid4().hex[:12]


def _build_url(request: Request, token: str) -> str:
    return str(request.base_url).rstrip("/") + f"/s/{token}"


def _build_message_snapshot(msg: ChatMessage) -> dict:
    return {
        "role": msg.role,
        "content": msg.content,
        "sources": msg.sources,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    }


@router.post("/share/session/{session_id}", response_model=SharedLinkResponse, status_code=201)
async def share_session(session_id: int, request: Request):
    """Create a public snapshot link for an entire chat session."""
    async with async_session() as db:
        chat_session = await db.get(ChatSession, session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

        msgs_result = await db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
        )
        messages = msgs_result.scalars().all()
        if not messages:
            raise HTTPException(status_code=400, detail="Session has no messages")

        snapshot = {
            "version": 1,
            "share_type": "session",
            "session": {
                "id": chat_session.id,
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
            session_id=session_id,
            message_id=None,
            share_type="session",
            title=title,
            snapshot_json=snapshot,
        )
        db.add(link)
        await db.commit()
        await db.refresh(link)

        logger.info("Shared session", extra={"session_id": session_id, "token": token})

        return SharedLinkResponse(
            token=link.token,
            url=_build_url(request, link.token),
            share_type=link.share_type,
            title=link.title,
            view_count=link.view_count,
            is_active=link.is_active,
            created_at=link.created_at,
        )


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

        return SharedLinkResponse(
            token=link.token,
            url=_build_url(request, link.token),
            share_type=link.share_type,
            title=link.title,
            view_count=link.view_count,
            is_active=link.is_active,
            created_at=link.created_at,
        )


@router.get("/s/{token}", response_model=SharedContentResponse)
async def get_shared_content(token: str):
    """Public endpoint: view shared content by token."""
    async with async_session() as db:
        result = await db.execute(
            select(SharedLink).where(SharedLink.token == token)
        )
        link = result.scalar_one_or_none()
        if not link:
            raise HTTPException(status_code=404, detail="Shared link not found")
        if not link.is_active:
            raise HTTPException(status_code=410, detail="This shared link is no longer active")

        link.view_count += 1
        await db.commit()

        snapshot = link.snapshot_json
        session_info = snapshot.get("session", {})

        return SharedContentResponse(
            share_type=link.share_type,
            title=link.title,
            product_filter=session_info.get("product_filter"),
            version_filter=session_info.get("version_filter"),
            messages=[
                SharedMessageSnapshot(**m)
                for m in snapshot.get("messages", [])
            ],
            created_at=link.created_at,
            view_count=link.view_count,
        )


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
async def list_shared_links(request: Request, session_id: int | None = None):
    """List all active shared links, optionally filtered by session_id."""
    async with async_session() as db:
        query = select(SharedLink).where(SharedLink.is_active.is_(True))
        if session_id is not None:
            query = query.where(SharedLink.session_id == session_id)
        query = query.order_by(SharedLink.created_at.desc())

        result = await db.execute(query)
        links = result.scalars().all()

        return [
            SharedLinkResponse(
                token=link.token,
                url=_build_url(request, link.token),
                share_type=link.share_type,
                title=link.title,
                view_count=link.view_count,
                is_active=link.is_active,
                created_at=link.created_at,
            )
            for link in links
        ]
