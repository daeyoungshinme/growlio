import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

import app.models
from alembic import context
from app.core.config import settings
from app.core.database import Base

config = context.config
_migration_url = (settings.migration_database_url or settings.database_url).replace("%", "%%")
config.set_main_option("sqlalchemy.url", _migration_url)

# growlio 전용 alembic 버전 테이블 — 같은 Supabase DB의 public 스키마를 nestlio와 공유하므로
# 기본 `alembic_version` 을 쓰면 두 앱의 마이그레이션 이력이 서로 포인터를 덮어쓴다.
# 신규 DB 부트스트랩은 scripts/bootstrap_alembic.py 참고.
VERSION_TABLE = "growlio_alembic_version"

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    extra: dict = {}
    if settings.supabase_project_url or settings.app_env == "production":
        # statement_cache_size=0: Transaction Pooler(port 6543)는 prepared statement 캐시 비호환
        extra["connect_args"] = {"ssl": "require", "statement_cache_size": 0}
    else:
        # 로컬/개발 환경도 pooler 경유 시 prepared statement 충돌 방지
        extra["connect_args"] = {"statement_cache_size": 0}
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=NullPool,
        **extra,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
