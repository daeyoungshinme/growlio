import time
from collections.abc import AsyncGenerator

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.utils.metrics import slow_query_count

logger = structlog.get_logger()

_engine_kwargs: dict = {
    "echo": settings.app_env == "development",
    "pool_size": settings.database_pool_size,
    "max_overflow": settings.database_max_overflow,
    "pool_timeout": settings.database_pool_timeout,
    "pool_pre_ping": True,
    "pool_recycle": 280,  # PostgreSQL 방화벽 300초 idle timeout 대비
}
# Supabase 또는 프로덕션 환경에서는 SSL 필수
# statement_cache_size=0: asyncpg named prepared statements 비활성화 → PgBouncer transaction mode 호환
if settings.app_env == "production" or settings.supabase_project_url:
    _engine_kwargs["connect_args"] = {
        "ssl": "require",
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "command_timeout": 60,
    }
else:
    _engine_kwargs["connect_args"] = {"command_timeout": 60}

engine = create_async_engine(settings.database_url, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info["_qstart"] = time.monotonic()


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    elapsed_ms = (time.monotonic() - conn.info.pop("_qstart", time.monotonic())) * 1000
    if elapsed_ms > settings.slow_query_ms:
        slow_query_count.inc()
        logger.warning(
            "slow_query",
            duration_ms=round(elapsed_ms),
            sql=statement,
            params=str(parameters)[:200] if parameters else None,
        )


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
