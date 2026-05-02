from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


@asynccontextmanager
async def worker_session():
    """Async DB session for Celery tasks.

    Uses NullPool so connections are never reused across asyncio.run() calls,
    which would bind them to a stale event loop and raise RuntimeError.
    """
    from shared.config import get_settings

    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
    await engine.dispose()
