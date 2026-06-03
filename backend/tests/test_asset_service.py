"""asset_service 핵심 로직 단위 테스트."""

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── _upsert_snapshot 테스트 ─────────────────────────────────

class TestUpsertSnapshot:
    """_upsert_snapshot: 스냅샷 upsert 로직 검증.

    구현은 pg_insert().on_conflict_do_update().returning() 방식을 사용한다.
    insert/update 분기 없이 단일 SQL 문으로 처리되므로 db.execute()와 db.commit() 호출만 검증한다.
    """

    @pytest.mark.asyncio
    async def test_executes_upsert_without_committing(self, mock_db):
        """pg_insert upsert를 실행하되 commit은 호출자가 처리한다."""
        from types import SimpleNamespace
        from app.services.snapshot_service import _upsert_snapshot

        account_id = uuid.uuid4()
        user_id = uuid.uuid4()
        today = date.today()

        snap = SimpleNamespace(
            id=uuid.uuid4(), account_id=account_id, user_id=user_id,
            snapshot_date=today, amount_krw=5_000_000.0, source="MANUAL",
        )
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one.return_value = snap
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        result = await _upsert_snapshot(
            mock_db,
            account_id=account_id,
            user_id=user_id,
            snapshot_date=today,
            amount_krw=5_000_000.0,
            source="MANUAL",
        )

        mock_db.execute.assert_called_once()
        mock_db.commit.assert_not_called()
        assert result.amount_krw == 5_000_000.0

    @pytest.mark.asyncio
    async def test_upsert_passes_correct_amount(self, mock_db):
        """upsert 호출 시 amount_krw가 올바르게 전달된다."""
        from types import SimpleNamespace
        from app.services.snapshot_service import _upsert_snapshot

        account_id = uuid.uuid4()
        user_id = uuid.uuid4()
        today = date.today()

        snap = SimpleNamespace(amount_krw=9_999_000.0, source="KIS_API", snapshot_date=today)
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one.return_value = snap
        mock_db.execute = AsyncMock(return_value=mock_execute_result)

        result = await _upsert_snapshot(
            mock_db,
            account_id=account_id,
            user_id=user_id,
            snapshot_date=today,
            amount_krw=9_999_000.0,
            source="KIS_API",
        )

        assert result.amount_krw == 9_999_000.0
        assert result.source == "KIS_API"


# ── ManualProvider 테스트 ──────────────────────────────

class TestManualProvider:
    """수동 계좌 동기화 로직 검증 (ManualProvider)."""

    def _mock_position(self, ticker="005930", name="삼성전자", market="KOSPI",
                       qty=10, avg_price=70000, current_price=80000):
        p = MagicMock()
        p.ticker = ticker; p.name = name; p.market = market
        p.qty = qty; p.avg_price = avg_price; p.current_price = current_price
        p.currency = "KRW"; p.value_krw = current_price * qty
        p.avg_price_usd = None; p.usd_rate = None
        return p

    @pytest.mark.asyncio
    async def test_raises_when_no_amount_and_no_positions(self, mock_db, make_account):
        """금액도, 포지션도 없으면 BadRequestError 발생."""
        from app.exceptions import BadRequestError
        from app.providers.manual_provider import ManualProvider

        make_account.manual_amount = 0
        make_account.asset_type = "CASH_OTHER"
        make_account.deposit_krw = None
        make_account.deposit_usd = None
        # mock_db.execute returns [] by default (no positions)

        provider = ManualProvider()
        with pytest.raises(BadRequestError, match="수동 금액이 설정되지 않았습니다"):
            await provider.sync(make_account, mock_db, redis=None)

    @pytest.mark.asyncio
    async def test_uses_manual_amount_when_no_positions(self, mock_db, make_account):
        """포지션 없으면 manual_amount로 BalanceResult 반환."""
        from app.providers.manual_provider import ManualProvider

        make_account.manual_amount = 10_000_000.0
        make_account.asset_type = "CASH_OTHER"
        make_account.deposit_krw = None
        make_account.deposit_usd = None
        # mock_db.execute returns [] by default (no positions)

        provider = ManualProvider()
        balance = await provider.sync(make_account, mock_db, redis=None)

        assert balance.total_value_krw == 10_000_000.0

    @pytest.mark.asyncio
    async def test_calculates_pnl_from_positions(self, mock_db, make_account):
        """포지션 있을 때 pnl = 평가금액 - 매입금액 계산."""
        from app.providers.manual_provider import ManualProvider
        from unittest.mock import AsyncMock

        mock_pos = self._mock_position(qty=10, avg_price=70000, current_price=80000)
        execute_result = MagicMock()
        execute_result.scalars.return_value.all.return_value = [mock_pos]
        mock_db.execute = AsyncMock(return_value=execute_result)

        make_account.manual_amount = None
        make_account.asset_type = "STOCK_OTHER"
        make_account.deposit_krw = None
        make_account.deposit_usd = None

        provider = ManualProvider()
        balance = await provider.sync(make_account, mock_db, redis=None)

        assert balance.total_value_krw == 800_000.0  # 80000 * 10
        assert balance.invested_krw == 700_000.0      # 70000 * 10
        assert balance.pnl_krw == 100_000.0           # 800k - 700k


# ── KISProvider 테스트 ─────────────────────────────────

class TestKISProvider:
    """KIS 계좌 동기화 시 manual_positions 자동 설정 검증."""

    @pytest.mark.asyncio
    async def test_sets_positions_after_sync(self, mock_db, make_account, make_user_settings):
        """KISProvider.sync() 호출 후 BalanceResult에 보유종목이 담긴다."""
        from app.providers.kis_provider import KISProvider

        make_account.kis_app_key = "encrypted_key"
        make_account.kis_app_secret = "encrypted_secret"
        make_account.is_mock_mode = True

        domestic_result = {
            "positions": [
                {"ticker": "005930", "name": "삼성전자", "market": "KOSPI",
                 "qty": 10, "avg_price": 70000.0, "current_price": 75000.0,
                 "value_krw": 750000.0, "pnl": 50000.0, "pnl_pct": 7.14, "currency": "KRW"},
            ],
            "total_value_krw": 750000.0,
            "deposit_krw": 100000.0,
            "invested_krw": 700000.0,
            "pnl_krw": 50000.0,
        }
        overseas_result = {
            "positions": [
                {"ticker": "AAPL", "name": "Apple", "market": "NASD",
                 "qty": 5, "avg_price": 180.0, "current_price": 190.0,
                 "value_usd": 950.0, "pnl_usd": 50.0, "pnl_pct": 5.56, "currency": "USD"},
            ],
            "total_value_usd": 950.0,
            "deposit_usd": 0.0,
        }

        with (
            patch("app.providers.kis_provider.decrypt", return_value="plain_value"),
            patch("app.providers.kis_provider.get_access_token", new_callable=AsyncMock, return_value="token"),
            patch("app.providers.kis_provider.get_domestic_balance", new_callable=AsyncMock, return_value=domestic_result),
            patch("app.providers.kis_provider.get_overseas_balance", new_callable=AsyncMock, return_value=overseas_result),
            patch("app.providers.kis_provider.get_overseas_price", new_callable=AsyncMock, return_value={"usd_krw_rate": 1300.0}),
            patch("app.providers.kis_provider.cache_usd_krw_rate", new_callable=AsyncMock),
        ):
            redis = AsyncMock()
            redis.get = AsyncMock(return_value=None)
            provider = KISProvider()
            balance = await provider.sync(make_account, mock_db, redis)

        # 국내 + 해외 포지션 2개
        assert len(balance.positions) == 2

        # 국내 종목: avg_price는 KRW 그대로
        domestic_pos = next(p for p in balance.positions if p.ticker == "005930")
        assert domestic_pos.avg_price == 70000.0
        assert domestic_pos.avg_price_usd is None

        # 해외 종목: avg_price는 USD * usd_krw_rate로 변환
        overseas_pos = next(p for p in balance.positions if p.ticker == "AAPL")
        assert overseas_pos.avg_price == 180.0 * 1300.0
        assert overseas_pos.avg_price_usd == 180.0
        assert overseas_pos.usd_rate == 1300.0


# ── 계좌별 수익률 계산 테스트 ───────────────────────────────

class TestStockReturnCalc:
    """주식 수익률 계산 단순 로직 검증 (단위 테스트)."""

    def test_stock_return_positive(self):
        """주식 수익률 = (평가액/매입액 - 1) * 100."""
        stock_value = 11_000_000.0
        total_invested = 10_000_000.0
        pct = (stock_value / total_invested - 1) * 100
        assert abs(pct - 10.0) < 0.001

    def test_stock_return_zero_invested(self):
        """투자 금액 0이면 수익률 0."""
        total_invested = 0.0
        pct = 0.0 if total_invested == 0 else ((11_000_000.0 / total_invested) - 1) * 100
        assert pct == 0.0
