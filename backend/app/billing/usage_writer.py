"""Async fire-and-forget writer for the usage_log billing audit table."""

import asyncio
import logging
from decimal import Decimal

from sqlalchemy.exc import InterfaceError, OperationalError

from app.billing.pricing import (
    calculate_llm_charge,
    calculate_llm_cogs,
    calculate_search_charge,
    calculate_search_cogs,
)
from app.database import async_session, get_sync_session
from app.models import UsageLog

logger = logging.getLogger(__name__)

_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.1


async def write_usage_log(
    channel: str,
    action: str,
    request_id: str,
    *,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    context_chunks: int = 0,
    context_tokens: int = 0,
    history_messages: int = 0,
    query_tokens: int = 0,
    history_tokens: int = 0,
    system_prompt_tokens: int = 0,
    query_text: str | None = None,
    result_count: int = 0,
    response_tokens: int = 0,
    response_length: int = 0,
    top_similarity: float = 0.0,
    product_filter: str | None = None,
    version_filter: str | None = None,
    duration_ms: float = 0.0,
    embedding_ms: float = 0.0,
    search_ms: float = 0.0,
    llm_ms: float = 0.0,
    cogs_usd: Decimal | None = None,
    charge_usd: Decimal | None = None,
    tenant_id: str | None = None,
    api_key_id: str | None = None,
    chat_session_id: int | None = None,
) -> None:
    """Persist a usage_log record for billing audit.

    Errors are logged but never propagate — billing telemetry must not
    break the main request flow.
    """
    try:
        if cogs_usd is None or charge_usd is None:
            if channel == "chat" and llm_model:
                if cogs_usd is None:
                    cogs_usd = calculate_llm_cogs(llm_model, prompt_tokens, completion_tokens)
                if charge_usd is None:
                    charge_usd = calculate_llm_charge(llm_model, prompt_tokens, completion_tokens)
                if (cogs_usd == Decimal("0") or charge_usd == Decimal("0")) and (prompt_tokens > 0 or completion_tokens > 0):
                    logger.warning(
                        "Unknown model for cost calculation",
                        extra={"llm_model": llm_model, "prompt_tokens": prompt_tokens},
                    )
            elif action in ("search_documentation", "get_api_endpoint"):
                if cogs_usd is None:
                    cogs_usd = calculate_search_cogs()
                if charge_usd is None:
                    charge_usd = calculate_search_charge()
            else:
                if cogs_usd is None:
                    cogs_usd = Decimal("0")
                if charge_usd is None:
                    charge_usd = Decimal("0")

        total_tokens = prompt_tokens + completion_tokens

        row = UsageLog(
            channel=channel,
            action=action,
            request_id=request_id,
            llm_provider=llm_provider,
            llm_model=llm_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            context_chunks=context_chunks,
            context_tokens=context_tokens,
            history_messages=history_messages,
            query_tokens=query_tokens,
            history_tokens=history_tokens,
            system_prompt_tokens=system_prompt_tokens,
            query_text=query_text,
            result_count=result_count,
            response_tokens=response_tokens,
            response_length=response_length,
            top_similarity=top_similarity,
            product_filter=product_filter,
            version_filter=version_filter,
            duration_ms=duration_ms,
            embedding_ms=embedding_ms,
            search_ms=search_ms,
            llm_ms=llm_ms,
            cogs_usd=cogs_usd,
            charge_usd=charge_usd,
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            chat_session_id=chat_session_id,
        )

        last_exc: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                async with async_session() as session:
                    session.add(row)
                    await session.commit()
                break
            except (InterfaceError, OperationalError) as exc:
                last_exc = exc
                if attempt < _RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(_RETRY_BASE_DELAY * (2 ** attempt))
                    from sqlalchemy.orm import make_transient
                    make_transient(row)
        else:
            logger.warning(
                "Failed to write usage_log after retries",
                extra={"attempts": _RETRY_ATTEMPTS, "last_error": str(last_exc)},
            )
            return

        logger.debug(
            "Usage log written",
            extra={
                "channel": channel,
                "action": action,
                "request_id": request_id,
                "cogs_usd": str(cogs_usd),
                "charge_usd": str(charge_usd),
                "total_tokens": total_tokens,
            },
        )
    except Exception:
        logger.warning("Failed to write usage_log", exc_info=True)


def write_usage_log_sync(
    channel: str,
    action: str,
    request_id: str,
    **kwargs,
) -> None:
    """Synchronous writer for Celery workers and other sync contexts.

    Uses a dedicated sync SQLAlchemy session to avoid asyncpg
    InterfaceError when called from non-async code.
    """
    try:
        _write_usage_log_sync_impl(channel, action, request_id, **kwargs)
    except Exception:
        logger.warning("Failed to write usage_log (sync)", exc_info=True)


def _write_usage_log_sync_impl(
    channel: str,
    action: str,
    request_id: str,
    *,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    context_chunks: int = 0,
    context_tokens: int = 0,
    history_messages: int = 0,
    query_tokens: int = 0,
    history_tokens: int = 0,
    system_prompt_tokens: int = 0,
    query_text: str | None = None,
    result_count: int = 0,
    response_tokens: int = 0,
    response_length: int = 0,
    top_similarity: float = 0.0,
    product_filter: str | None = None,
    version_filter: str | None = None,
    duration_ms: float = 0.0,
    embedding_ms: float = 0.0,
    search_ms: float = 0.0,
    llm_ms: float = 0.0,
    cogs_usd: Decimal | None = None,
    charge_usd: Decimal | None = None,
    tenant_id: str | None = None,
    api_key_id: str | None = None,
    chat_session_id: int | None = None,
) -> None:
    if cogs_usd is None or charge_usd is None:
        if channel == "chat" and llm_model:
            if cogs_usd is None:
                cogs_usd = calculate_llm_cogs(llm_model, prompt_tokens, completion_tokens)
            if charge_usd is None:
                charge_usd = calculate_llm_charge(llm_model, prompt_tokens, completion_tokens)
            if (cogs_usd == Decimal("0") or charge_usd == Decimal("0")) and (prompt_tokens > 0 or completion_tokens > 0):
                logger.warning(
                    "Unknown model for cost calculation",
                    extra={"llm_model": llm_model, "prompt_tokens": prompt_tokens},
                )
        elif action in ("search_documentation", "get_api_endpoint"):
            if cogs_usd is None:
                cogs_usd = calculate_search_cogs()
            if charge_usd is None:
                charge_usd = calculate_search_charge()
        else:
            if cogs_usd is None:
                cogs_usd = Decimal("0")
            if charge_usd is None:
                charge_usd = Decimal("0")

    total_tokens = prompt_tokens + completion_tokens

    session = get_sync_session()
    try:
        session.add(UsageLog(
            channel=channel,
            action=action,
            request_id=request_id,
            llm_provider=llm_provider,
            llm_model=llm_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            context_chunks=context_chunks,
            context_tokens=context_tokens,
            history_messages=history_messages,
            query_tokens=query_tokens,
            history_tokens=history_tokens,
            system_prompt_tokens=system_prompt_tokens,
            query_text=query_text,
            result_count=result_count,
            response_tokens=response_tokens,
            response_length=response_length,
            top_similarity=top_similarity,
            product_filter=product_filter,
            version_filter=version_filter,
            duration_ms=duration_ms,
            embedding_ms=embedding_ms,
            search_ms=search_ms,
            llm_ms=llm_ms,
            cogs_usd=cogs_usd,
            charge_usd=charge_usd,
            tenant_id=tenant_id,
            api_key_id=api_key_id,
            chat_session_id=chat_session_id,
        ))
        session.commit()
    finally:
        session.close()

    logger.debug(
        "Usage log written (sync)",
        extra={
            "channel": channel,
            "action": action,
            "request_id": request_id,
            "cogs_usd": str(cogs_usd),
            "charge_usd": str(charge_usd),
            "total_tokens": total_tokens,
        },
    )
