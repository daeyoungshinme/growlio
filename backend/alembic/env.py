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


def include_name(name, type_, parent_names):
    """autogenerate 비교 대상을 growlio 모델 테이블로 한정한다.

    public 스키마를 nestlio와 공유하므로 필터가 없으면 autogenerate가 nestlio 테이블 드롭을 제안한다.
    growlio 테이블의 인덱스는 이 필터로 걸러지지 않는다 — 모델에 선언하지 않은 인덱스는 여전히 드롭 대상으로
    잡히므로(a64e36a53a40이 그렇게 인덱스 2개를 지웠다) DB 인덱스는 모델에도 선언해야 한다.
    대가: 모델에서 지운 growlio 테이블도 비교에서 빠지므로 테이블 드롭은 마이그레이션을 직접 쓴다.
    """
    if type_ == "table":
        return name in target_metadata.tables
    return True


# 정렬(DESC) 인덱스 — alembic이 반영된 정렬을 모델 선언과 같다고 판정하지 못해 autogenerate마다
# drop/create를 반복 제안한다. 비교에서만 제외한다(52 G squash에서 중복 인덱스와 함께 정리).
_DESC_INDEXES = frozenset(
    {"idx_snapshots_account_date_desc", "idx_asset_snapshots_user_account_date", "idx_snapshots_user_date_desc"}
)


def include_object(obj, name, type_, reflected, compare_to):
    """include_name은 growlio 테이블만 남길 뿐 그 테이블의 인덱스는 전부 비교한다.

    모델에 없는 인덱스는 여전히 드롭 대상으로 잡히므로, DB에 있는 인덱스는 모델 `__table_args__`에도
    선언해야 한다. 여기서는 정렬 인덱스의 반복 diff만 거른다.
    """
    return not (type_ == "index" and name in _DESC_INDEXES)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        version_table=VERSION_TABLE,
        include_name=include_name,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=VERSION_TABLE,
        include_name=include_name,
        include_object=include_object,
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
