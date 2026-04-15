"""Public (unauthenticated) share endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.database import async_session
from app.models import SharedLink
from app.share.schemas import SharedContentResponse, SharedDebugContentResponse, SharedDocumentPreviewResponse, SharedLifecycleContentResponse, SharedMessageSnapshot

public_router = APIRouter(tags=["share"])


@public_router.get("/s/{token}", response_model=None)
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
        if link.expires_at and link.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="This shared link has expired")

        link.view_count += 1
        await db.commit()

        snapshot = link.snapshot_json

        if link.share_type.startswith("debug_"):
            return SharedDebugContentResponse(
                share_type=link.share_type,
                title=link.title,
                data=snapshot.get("data", {}),
                created_at=link.created_at,
                view_count=link.view_count,
                expires_at=link.expires_at,
            )

        if link.share_type == "document_preview":
            return SharedDocumentPreviewResponse(
                share_type=link.share_type,
                title=link.title,
                markdown=snapshot.get("markdown", ""),
                source=snapshot.get("source", "unknown"),
                size_bytes=snapshot.get("size_bytes", 0),
                created_at=link.created_at,
                view_count=link.view_count,
            )

        if link.share_type == "lifecycle":
            return SharedLifecycleContentResponse(
                share_type=link.share_type,
                title=link.title,
                product_name=snapshot.get("product_name", ""),
                merged=snapshot.get("merged"),
                document_lifecycles=snapshot.get("document_lifecycles", []),
                doc_issues=snapshot.get("doc_issues", []),
                created_at=link.created_at,
                view_count=link.view_count,
            )

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
