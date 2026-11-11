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
            sql=statement,  # 바인드값은 남기지 않는다 — 이메일·금액·암호문이 그대로 로그에 실린다
        )


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def release_read_connection(db: AsyncSession) -> None:
    """외부 I/O(증권사·시세·배당 소스) 직전에 읽기 트랜잭션을 끝내 커넥션을 풀에 돌려준다.

    풀이 5+2라 외부 응답(수 초~20초)을 기다리는 요청 몇 개가 커넥션을 쥐면 다른 요청이 `get_current_user`에서
    pool_timeout까지 줄을 선다(#260). `expire_on_commit=False`라 이미 읽은 객체는 그대로 쓰고, 이후 쿼리는 새
    트랜잭션을 autobegin한다. 세션에 아직 flush하지 않은 변경이 있으면 호출부의 트랜잭션 경계를 바꾸지 않게
    아무것도 하지 않는다 — 읽기 경로에서만 부른다(flush된 쓰기는 구분할 수 없다).
    """
    if db.new or db.dirty or db.deleted:
        return
    if db.in_transaction():
        await db.commit()
