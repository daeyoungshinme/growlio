"""growlio 전용 alembic 버전 테이블(`growlio_alembic_version`) 부트스트랩.

같은 Supabase DB의 `public` 스키마를 nestlio와 공유하기 때문에 growlio는 기본
`alembic_version` 대신 `growlio_alembic_version` 을 쓴다(`alembic/env.py`의 `VERSION_TABLE`).
전환 시점에 기존 DB에는 이 테이블이 없으므로, `alembic upgrade head` 가 전체 체인을
처음부터(001~) 돌리려다 "relation already exists" 로 실패한다.

이 스크립트는 그 상황을 멱등하게 방지한다:

* `growlio_alembic_version` 이 이미 있으면            → 아무것도 안 함
* 없고 `asset_accounts` 가 있으면 (= 기존 growlio DB) → 테이블 생성 + `_BASELINE_REVISION` seed
* 없고 `asset_accounts` 도 없으면 (= 완전 신규 DB)   → 아무것도 안 함 (alembic 이 001부터 생성)

`alembic upgrade head` 직전에 실행한다 (`render.yaml` preDeployCommand, 로컬 최초 1회).
"""

from __future__ import annotations

import asyncio

import asyncpg

from app.core.config import settings

# alembic/env.py 의 VERSION_TABLE 과 일치해야 한다.
VERSION_TABLE = "growlio_alembic_version"

# 전환 시점의 growlio 마이그레이션 head (토스 마이그레이션 f0551a2b3c4d 의 down_revision).
# 기존 DB 스키마가 이 리비전까지 반영돼 있음을 컬럼 대조로 확인한 값.
_BASELINE_REVISION = "17f4ddd81cae"


def _asyncpg_url() -> str:
    url = settings.migration_database_url or settings.database_url
    return url.replace("postgresql+asyncpg://", "postgresql://")


def _connect_args() -> dict:
    # env.py 와 동일한 규칙: pooler(6543)는 prepared statement 캐시 비호환.
    args: dict = {"statement_cache_size": 0}
    if settings.supabase_project_url or settings.app_env == "production":
        args["ssl"] = "require"
    return args


async def _run() -> None:
    conn = await asyncpg.connect(_asyncpg_url(), **_connect_args())
    try:
        has_version_table = await conn.fetchval("SELECT to_regclass('public.' || $1) IS NOT NULL", VERSION_TABLE)
        if has_version_table:
            current = await conn.fetchval(f"SELECT version_num FROM {VERSION_TABLE}")
            print(f"bootstrap_alembic: {VERSION_TABLE} already exists (version_num={current}) - skip")
            return

        has_growlio_schema = await conn.fetchval("SELECT to_regclass('public.asset_accounts') IS NOT NULL")
        if not has_growlio_schema:
            print("bootstrap_alembic: fresh database (no asset_accounts) - alembic will build from base")
            return

        async with conn.transaction():
            await conn.execute(
                f"CREATE TABLE IF NOT EXISTS {VERSION_TABLE} "
                "(version_num VARCHAR(255) NOT NULL, "
                f"CONSTRAINT {VERSION_TABLE}_pkc PRIMARY KEY (version_num))"
            )
            already = await conn.fetchval(f"SELECT count(*) FROM {VERSION_TABLE}")
            if already:
                print(f"bootstrap_alembic: {VERSION_TABLE} already seeded - skip")
                return
            await conn.execute(
                f"INSERT INTO {VERSION_TABLE} (version_num) VALUES ($1)",
                _BASELINE_REVISION,
            )
        print(f"bootstrap_alembic: existing growlio DB - seeded {VERSION_TABLE} at {_BASELINE_REVISION}")
    finally:
        await conn.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
