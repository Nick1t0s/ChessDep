import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

logger = logging.getLogger("app.db")

engine_kwargs: dict = {"pool_pre_ping": True}
if settings.testing:
    engine_kwargs["poolclass"] = NullPool
engine = create_async_engine(settings.database_url, **engine_kwargs)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

AfterCommit = Callable[[], Awaitable[None]]


def after_commit(db: AsyncSession, fn: AfterCommit) -> None:
    # Действия над Redis (публикация событий, ZSET дедлайнов) выполняются
    # только после коммита транзакции.
    db.info.setdefault("after_commit", []).append(fn)


async def run_after_commit(db: AsyncSession) -> None:
    for fn in db.info.pop("after_commit", []):
        try:
            await fn()
        except Exception:
            logger.exception("after_commit hook failed")


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        async with session.begin():
            yield session
        await run_after_commit(session)
