"""실 Postgres에서만 확인되는 SQL 경로 — ON CONFLICT upsert·claim, 연도 범위 필터 (plans/118 D1).

다른 테스트는 모두 mock이거나 SQL 컴파일만 확인해서, 제약 이름·ON CONFLICT 대상·타입 캐스트 오류가 운영에서야
드러났다. 여기서는 마이그레이션이 적용된 테스트 DB에 직접 붙는다.

`GROWLIO_TEST_DATABASE_URL`이 있을 때만 돈다(CI는 서비스 컨테이너 DB로 설정). 로컬 `.env`의 `DATABASE_URL`은
공유 Supabase일 수 있으므로 절대 쓰지 않는다. 각 테스트는 바깥 트랜잭션을 롤백해 흔적을 남기지 않는다.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.models.app_state import AppState
from app.models.asset import AssetAccount, AssetSnapshot, Transaction
from app.models.user import User

pytestmark = pytest.mark.db

_TEST_DB_URL = os.environ.get("GROWLIO_TEST_DATABASE_URL")


@pytest.fixture
async def pg() -> AsyncIterator[AsyncSession]:
    if not _TEST_DB_URL:
        if os.environ.get("CI"):
            # CI에서 변수가 빠지면(이름 변경·잡 env 정리) 4건이 조용히 skip되고 녹색이 됐다(plans/119 D1)
            pytest.fail("CI인데 GROWLIO_TEST_DATABASE_URL이 없다 — ci.yml backend 잡 env를 확인할 것")
        pytest.skip("GROWLIO_TEST_DATABASE_URL 미설정 — 실 DB 테스트는 CI 서비스 컨테이너에서만 돈다")
    engine = create_async_engine(_TEST_DB_URL, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            outer = await conn.begin()
            # 코드의 commit()은 savepoint만 확정하고, 바깥 트랜잭션은 끝에 롤백한다
            session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
            try:
                yield session
            finally:
                await session.close()
                await outer.rollback()
    finally:
        await engine.dispose()


async def _user_and_account(db: AsyncSession, tax_type: str = "GENERAL") -> tuple[User, AssetAccount]:
    user = User(id=uuid.uuid4(), email=f"{uuid.uuid4().hex}@test.local")
    db.add(user)
    await db.flush()
    account = AssetAccount(user_id=user.id, name="테스트", asset_type="STOCK_OTHER", data_source="MANUAL")
    account.tax_type = tax_type
    db.add(account)
    await db.flush()
    return user, account


class TestDurableState:
    async def test_set_durable_upserts_and_expires(self, pg: AsyncSession):
        from app.utils.durable_state import get_durable, set_durable

        key = f"test:{uuid.uuid4().hex}"
        await set_durable(pg, key, "1")
        await set_durable(pg, key, "2", ttl=3600)
        assert await get_durable(pg, key) == "2"
        assert await pg.scalar(select(func.count()).select_from(AppState).where(AppState.key == key)) == 1

        await set_durable(pg, key, "3", ttl=-1)
        pg.expire_all()  # core upsert는 identity map을 갱신하지 않는다 — 운영은 요청마다 새 세션
        assert await get_durable(pg, key) is None

    async def test_claim_durable_is_exclusive_until_expired(self, pg: AsyncSession):
        from app.utils.durable_state import claim_durable

        key = f"claim:{uuid.uuid4().hex}"
        assert await claim_durable(pg, key, ttl=3600) is True
        assert await claim_durable(pg, key, ttl=3600) is False

        row = await pg.get(AppState, key)
        assert row is not None
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await pg.flush()
        assert await claim_durable(pg, key, ttl=3600) is True


class TestSnapshotUpsert:
    async def test_same_account_date_updates_single_row(self, pg: AsyncSession):
        from app.services.accounts.snapshot_service import upsert_snapshot

        user, account = await _user_and_account(pg)
        d = date(2026, 11, 7)
        first = await upsert_snapshot(
            pg, account_id=account.id, user_id=user.id, snapshot_date=d, amount_krw=1_000_000, source="MANUAL"
        )
        second = await upsert_snapshot(
            pg,
            account_id=account.id,
            user_id=user.id,
            snapshot_date=d,
            amount_krw=1_200_000,
            source="MANUAL",
            invested_amount=900_000,
        )
        assert second.id == first.id
        await pg.refresh(second)
        count = await pg.scalar(
            select(func.count()).select_from(AssetSnapshot).where(AssetSnapshot.account_id == account.id)
        )
        assert count == 1
        assert float(second.amount_krw) == 1_200_000
        assert second.invested_amount is not None
        assert float(second.invested_amount) == 900_000


class TestYearRangeFilters:
    async def test_pension_contribution_counts_only_that_year(self, pg: AsyncSession):
        """plans/118 B3: extract(year) → 날짜 범위 조건 전환이 연 경계(12/31·1/1)를 그대로 지키는지."""
        from app.services.tax.pension_contribution_service import calc_pension_contribution_status

        user, account = await _user_and_account(pg, tax_type="IRP")
        for d, amount in ((date(2025, 12, 31), 100), (date(2026, 1, 1), 200), (date(2026, 12, 31), 300)):
            pg.add(
                Transaction(
                    user_id=user.id,
                    account_id=account.id,
                    transaction_type="DEPOSIT",
                    amount=amount,
                    transaction_date=d,
                )
            )
        await pg.flush()

        status = await calc_pension_contribution_status(user.id, 2026, pg)
        assert status["irp_deposit_krw"] == 500

    async def test_dividend_year_filters_keep_year_boundaries(self, pg: AsyncSession):
        """plans/129 B4: 배당 집계의 extract(year) → 날짜 범위 전환이 12/31·1/1 경계를 지키는지(date 바인딩 포함)."""
        from app.services.dividend.aggregator import get_annual_dividends_received
        from app.services.dividend.orchestrator import _fetch_received_dividends_by_ticker

        user, account = await _user_and_account(pg)
        for d, amount in ((date(2025, 12, 31), 100), (date(2026, 1, 1), 200), (date(2026, 12, 31), 300)):
            pg.add(
                Transaction(
                    user_id=user.id,
                    account_id=account.id,
                    transaction_type="DIVIDEND",
                    ticker="AAA",
                    amount=amount,
                    transaction_date=d,
                )
            )
        await pg.flush()

        assert await get_annual_dividends_received(user.id, pg, 2026) == 500
        by_ticker = await _fetch_received_dividends_by_ticker(pg, user.id, 2026)
        assert by_ticker == {"AAA": 500}


async def test_release_read_connection_returns_connection_to_pool():
    """plans/125 — 읽기 후 반납하면 풀의 checkedout이 0이 되고, 이후 쿼리는 새로 커넥션을 받는다."""
    if not _TEST_DB_URL:
        if os.environ.get("CI"):
            pytest.fail("CI인데 GROWLIO_TEST_DATABASE_URL이 없다")
        pytest.skip("GROWLIO_TEST_DATABASE_URL 미설정")
    from sqlalchemy import text

    from app.core.database import release_read_connection

    engine = create_async_engine(_TEST_DB_URL, pool_size=2, max_overflow=0)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            await session.execute(text("SELECT 1"))
            assert engine.pool.checkedout() == 1  # type: ignore[attr-defined]
            await release_read_connection(session)
            assert engine.pool.checkedout() == 0  # type: ignore[attr-defined]
            assert (await session.execute(text("SELECT 2"))).scalar() == 2
    finally:
        await engine.dispose()
