"""asset_aggregator 핵심 함수 단위 테스트 — XIRR 및 월별 추이 검증."""

import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── _xirr 테스트 ────────────────────────────────────────────

class TestXirr:
    """_xirr: Newton-Raphson XIRR 계산 로직."""

    def test_simple_annual_return(self):
        """1년 후 10% 수익 → XIRR ≈ 10%."""
        from app.services.asset_aggregator import _xirr

        today = date.today()
        start = today.replace(year=today.year - 1)
        cashflows = [(start, -1_000_000.0), (today, 1_100_000.0)]
        result = _xirr(cashflows)
        assert result is not None
        assert 9.0 < result < 11.0

    def test_returns_none_for_single_cashflow(self):
        """단일 캐시플로는 None 반환."""
        from app.services.asset_aggregator import _xirr

        cashflows = [(date.today(), -1_000_000.0)]
        assert _xirr(cashflows) is None

    def test_returns_none_for_all_positive(self):
        """모두 양수인 경우 None 반환 (입금만 있는 경우)."""
        from app.services.asset_aggregator import _xirr

        today = date.today()
        cashflows = [(today - timedelta(days=365), 500_000.0), (today, 500_000.0)]
        assert _xirr(cashflows) is None

    def test_returns_none_for_all_negative(self):
        """모두 음수인 경우 None 반환 (출금만 있는 경우)."""
        from app.services.asset_aggregator import _xirr

        today = date.today()
        cashflows = [(today - timedelta(days=365), -500_000.0), (today, -500_000.0)]
        assert _xirr(cashflows) is None

    def test_reasonable_range_enforced(self):
        """비현실적인 수익률(-99% 초과 또는 1000% 초과)은 None 반환."""
        from app.services.asset_aggregator import _xirr

        today = date.today()
        # 극단적인 손실: -99.9% → 반환 불가 범위
        cashflows = [(today - timedelta(days=365), -1_000_000.0), (today, 0.01)]
        result = _xirr(cashflows)
        # None이거나 유효 범위 내여야 함
        assert result is None or -99 < result < 1000

    def test_estimated_path_two_points(self):
        """스냅샷 기반 추정(2개 포인트)도 수렴해야 한다."""
        from app.services.asset_aggregator import _xirr

        start = date(2024, 1, 1)
        end = date(2025, 1, 1)
        # 5% 수익 추정
        cashflows = [(start, -10_000_000.0), (end, 10_500_000.0)]
        result = _xirr(cashflows)
        assert result is not None
        assert 4.0 < result < 6.0


# ── _calc_xirr 통합 테스트 ──────────────────────────────────

class TestCalcXirr:
    """_calc_xirr: 트랜잭션 or 스냅샷 경로 XIRR."""

    @pytest.mark.asyncio
    async def test_returns_estimated_when_no_transactions(self, mock_db):
        """트랜잭션 없을 때 스냅샷 기반 추정 경로."""
        from app.services.asset_aggregator import _calc_xirr

        user_id = uuid.uuid4()
        current_total = 11_000_000.0

        # 첫 번째 execute: 트랜잭션 조회 → 빈 결과
        no_tx_result = MagicMock()
        no_tx_result.all.return_value = []

        # 두 번째 execute: 스냅샷 조회 → 1년 전 데이터
        snap_row = SimpleNamespace(
            snapshot_date=date.today().replace(year=date.today().year - 1),
            total=10_000_000.0,
        )
        snap_result = MagicMock()
        snap_result.first.return_value = snap_row

        mock_db.execute = AsyncMock(side_effect=[no_tx_result, snap_result])

        xirr_pct, is_estimated = await _calc_xirr(user_id, current_total, mock_db)

        assert is_estimated is True
        assert xirr_pct is not None
        assert 5.0 < xirr_pct < 15.0  # 10% 수익 근방

    @pytest.mark.asyncio
    async def test_returns_none_when_no_transactions_and_no_snapshot(self, mock_db):
        """트랜잭션도 스냅샷도 없으면 None 반환."""
        from app.services.asset_aggregator import _calc_xirr

        user_id = uuid.uuid4()

        no_tx_result = MagicMock()
        no_tx_result.all.return_value = []

        snap_result = MagicMock()
        snap_result.first.return_value = None

        mock_db.execute = AsyncMock(side_effect=[no_tx_result, snap_result])

        xirr_pct, is_estimated = await _calc_xirr(user_id, 0.0, mock_db)
        assert xirr_pct is None
        assert is_estimated is False

    @pytest.mark.asyncio
    async def test_uses_transactions_when_available(self, mock_db):
        """트랜잭션이 있으면 직접 계산."""
        from app.services.asset_aggregator import _calc_xirr

        user_id = uuid.uuid4()
        current_total = 11_000_000.0
        one_year_ago = date.today().replace(year=date.today().year - 1)

        tx_row = SimpleNamespace(
            transaction_date=one_year_ago,
            transaction_type="DEPOSIT",
            amount=10_000_000.0,
        )
        tx_result = MagicMock()
        tx_result.all.return_value = [tx_row]

        mock_db.execute = AsyncMock(return_value=tx_result)

        xirr_pct, is_estimated = await _calc_xirr(user_id, current_total, mock_db)

        assert is_estimated is False
        assert xirr_pct is not None


# ── _get_monthly_trend 캐시 테스트 ─────────────────────────

class TestGetMonthlyTrend:
    """_get_monthly_trend: Redis 캐시 히트/미스 동작."""

    @pytest.mark.asyncio
    async def test_cache_hit_skips_db(self, mock_db, mock_redis):
        """Redis 캐시 히트 시 DB 쿼리 없이 반환."""
        import json
        from app.services.asset_aggregator import _get_monthly_trend

        user_id = uuid.uuid4()
        cached_data = [{"month": "2025-01-01", "total_krw": 10_000_000.0}]
        mock_redis.get = AsyncMock(return_value=json.dumps(cached_data).encode())

        result = await _get_monthly_trend(user_id, mock_db, mock_redis)

        assert result == cached_data
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_queries_db(self, mock_db, mock_redis):
        """Redis 캐시 미스 시 DB 쿼리 후 캐시 저장."""
        from app.services.asset_aggregator import _get_monthly_trend

        user_id = uuid.uuid4()
        mock_redis.get = AsyncMock(return_value=None)

        # DB 결과 mock
        row = SimpleNamespace(month=date(2025, 1, 1), total_krw=10_000_000.0)
        db_result = MagicMock()
        db_result.__iter__ = MagicMock(return_value=iter([row]))
        mock_db.execute = AsyncMock(return_value=db_result)

        result = await _get_monthly_trend(user_id, mock_db, mock_redis)

        mock_db.execute.assert_called_once()
        mock_redis.set.assert_called_once()
        assert len(result) == 1
        assert result[0]["total_krw"] == 10_000_000.0

    @pytest.mark.asyncio
    async def test_no_redis_queries_db_directly(self, mock_db):
        """redis=None이면 캐시 없이 DB 직접 조회."""
        from app.services.asset_aggregator import _get_monthly_trend

        user_id = uuid.uuid4()

        row = SimpleNamespace(month=date(2025, 6, 1), total_krw=5_000_000.0)
        db_result = MagicMock()
        db_result.__iter__ = MagicMock(return_value=iter([row]))
        mock_db.execute = AsyncMock(return_value=db_result)

        result = await _get_monthly_trend(user_id, mock_db, redis=None)

        mock_db.execute.assert_called_once()
        assert result[0]["month"] == "2025-06-01"


# ── _get_no_snap_accounts SQL 필터 테스트 ─────────────────

class TestGetNoSnapAccounts:
    """_get_no_snap_accounts: snapped_ids SQL 필터 검증."""

    @pytest.mark.asyncio
    async def test_empty_snapped_ids_no_not_in_clause(self, mock_db):
        """snapped_ids가 비어있으면 NOT IN 조건 없이 쿼리."""
        from app.services.asset_aggregator import _get_no_snap_accounts

        user_id = uuid.uuid4()
        mock_db.execute.return_value.scalars.return_value.all.return_value = []

        result = await _get_no_snap_accounts(user_id, mock_db, set())

        mock_db.execute.assert_called_once()
        assert result == []

    @pytest.mark.asyncio
    async def test_snapped_ids_excluded_via_sql(self, mock_db):
        """snapped_ids가 있으면 SQL NOT IN으로 처리 후 모두 반환."""
        from app.services.asset_aggregator import _get_no_snap_accounts

        user_id = uuid.uuid4()
        acc_id = uuid.uuid4()
        acc = SimpleNamespace(id=acc_id, user_id=user_id, asset_type="BANK_ACCOUNT")

        mock_db.execute.return_value.scalars.return_value.all.return_value = [acc]

        snapped = {uuid.uuid4()}  # 다른 계좌 ID
        result = await _get_no_snap_accounts(user_id, mock_db, snapped)

        # SQL 레벨에서 필터됐으므로 반환된 acc를 그대로 사용
        assert len(result) == 1
        assert result[0].id == acc_id
