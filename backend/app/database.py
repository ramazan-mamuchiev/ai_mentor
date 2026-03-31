"""SQLAlchemy engine and session factories (async + sync)."""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    pool_size=20,
    max_overflow=10,
    echo=(settings.app_env == "development"),
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


_sync_engine = None


def get_sync_engine():
    """Lazy-initialised synchronous engine for Celery workers and other sync contexts."""
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            settings.database_url_sync,
            pool_size=8,
            max_overflow=4,
        )
    return _sync_engine


def get_sync_session() -> Session:
    """Create a new synchronous session bound to the shared sync engine."""
    return sessionmaker(get_sync_engine(), expire_on_commit=False)()
