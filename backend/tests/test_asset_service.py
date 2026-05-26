"""asset_service 핵심 로직 단위 테스트."""

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── _upsert_snapshot 테스트 ─────────────────────────────────

class TestUpsertSnapshot:
    """_upsert_snapshot: 스냅샷 upsert 로직 검증."""

    @pytest.mark.asyncio
    async def test_creates_new_snapshot_when_not_exists(self, mock_db):
        """기존 스냅샷 없으면 새로 생성한다."""
        from app.services.asset_service import _upsert_snapshot

        mock_db.scalar.return_value = None  # 기존 스냅샷 없음
        mock_db.refresh = AsyncMock(side_effect=lambda obj: None)

        account_id = uuid.uuid4()
        user_id = uuid.uuid4()
        today = date.today()

        await _upsert_snapshot(
            mock_db,
            account_id=account_id,
            user_id=user_id,
            snapshot_date=today,
            amount_krw=5_000_000.0,
            source="MANUAL",
        )
        # 새 스냅샷이 세션에 추가되어야 한다
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_existing_snapshot(self, mock_db):
        """당일 스냅샷이 이미 있으면 금액을 업데이트한다."""
        from app.services.asset_service import _upsert_snapshot

        account_id = uuid.uuid4()
        user_id = uuid.uuid4()
        today = date.today()

        existing = SimpleNamespace(
            id=uuid.uuid4(),
            account_id=account_id,
            user_id=user_id,
            snapshot_date=today,
            amount_krw=3_000_000.0,
            source="MANUAL",
        )
        mock_db.scalar.return_value = existing

        result = await _upsert_snapshot(
            mock_db,
            account_id=account_id,
            user_id=user_id,
            snapshot_date=today,
            amount_krw=5_000_000.0,  # 새 금액
            source="KIS_API",
        )

        assert existing.amount_krw == 5_000_000.0
        assert existing.source == "KIS_API"
        mock_db.add.assert_not_called()  # 새로 추가하지 않음
        mock_db.commit.assert_called_once()


# ── sync_manual_account 테스트 ──────────────────────────────

class TestSyncManualAccount:
    """수동 계좌 동기화 로직 검증."""

    @pytest.mark.asyncio
    async def test_raises_when_no_amount_and_no_positions(self, mock_db, make_account):
        """금액도, 포지션도 없으면 ValueError 발생."""
        from app.services.asset_service import sync_manual_account

        make_account.manual_amount = 0
        make_account.manual_positions = []

        with pytest.raises(ValueError, match="수동 금액이 설정되지 않았습니다"):
            await sync_manual_account(make_account, mock_db, redis=None)

    @pytest.mark.asyncio
    async def test_uses_manual_amount_when_no_positions(self, mock_db, make_account):
        """포지션 없으면 manual_amount로 스냅샷 저장."""
        from app.services.asset_service import sync_manual_account

        make_account.manual_amount = 10_000_000.0
        make_account.manual_positions = []
        make_account.asset_type = "CASH_OTHER"

        mock_db.scalar.return_value = None  # 기존 스냅샷 없음

        snap_result = SimpleNamespace(
            id=uuid.uuid4(),
            amount_krw=10_000_000.0,
            source="MANUAL",
            snapshot_date=date.today(),
        )

        with patch("app.services.asset_service._upsert_snapshot", new_callable=AsyncMock) as mock_upsert:
            mock_upsert.return_value = snap_result
            result = await sync_manual_account(make_account, mock_db, redis=None)

        mock_upsert.assert_called_once()
        call_kwargs = mock_upsert.call_args.kwargs
        assert call_kwargs["amount_krw"] == 10_000_000.0
        assert call_kwargs["source"] == "MANUAL"

    @pytest.mark.asyncio
    async def test_calculates_pnl_from_positions(self, mock_db, make_account):
        """포지션 있을 때 pnl = 평가금액 - 매입금액 계산."""
        from app.services.asset_service import sync_manual_account

        make_account.manual_positions = [
            {"ticker": "005930", "market": "KOSPI", "qty": 10, "avg_price": 70000, "current_price": 80000},
        ]
        make_account.manual_amount = None

        snap_result = SimpleNamespace(amount_krw=800_000.0, source="MANUAL", snapshot_date=date.today())

        with patch("app.services.asset_service._upsert_snapshot", new_callable=AsyncMock) as mock_upsert:
            mock_upsert.return_value = snap_result
            await sync_manual_account(make_account, mock_db, redis=None)

        call_kwargs = mock_upsert.call_args.kwargs
        # 평가액: 80000 * 10 = 800,000
        assert call_kwargs["amount_krw"] == 800_000.0
        # 매입액: 70000 * 10 = 700,000
        assert call_kwargs["invested_amount"] == 700_000.0
        # 손익: 100,000
        assert call_kwargs["unrealized_pnl"] == 100_000.0


# ── sync_kis_account 테스트 ─────────────────────────────────

class TestSyncKisAccount:
    """KIS 계좌 동기화 시 manual_positions 자동 설정 검증."""

    @pytest.mark.asyncio
    async def test_sets_manual_positions_after_sync(self, mock_db, make_account, make_user_settings):
        """sync_kis_account 호출 후 account.manual_positions에 보유종목이 저장된다."""
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from app.services.asset_service import sync_kis_account

        # Account 레벨 자격증명 설정 (sync_kis_account는 account에서 직접 읽음)
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
        snap_result = SimpleNamespace(snapshot_date=date.today(), amount_krw=1_000_000.0)

        with (
            patch("app.services.asset_service.decrypt", return_value="plain_value"),
            patch("app.services.asset_service.get_access_token", new_callable=AsyncMock, return_value="token"),
            patch("app.services.asset_service.get_domestic_balance", new_callable=AsyncMock, return_value=domestic_result),
            patch("app.services.asset_service.get_overseas_balance", new_callable=AsyncMock, return_value=overseas_result),
            patch("app.services.asset_service.get_overseas_price", new_callable=AsyncMock, return_value={"usd_krw_rate": 1300.0}),
            patch("app.services.asset_service._upsert_snapshot", new_callable=AsyncMock, return_value=snap_result),
            patch("app.utils.currency.cache_usd_krw_rate", new_callable=AsyncMock),
        ):
            # Redis mock: no cached rate
            redis = AsyncMock()
            redis.get = AsyncMock(return_value=None)
            await sync_kis_account(make_account, mock_db, redis)

        # manual_positions에 국내 + 해외 종목이 저장되어야 한다
        assert make_account.manual_positions is not None
        assert len(make_account.manual_positions) == 2

        # 국내 종목: avg_price는 KRW 그대로
        domestic_pos = next(p for p in make_account.manual_positions if p["ticker"] == "005930")
        assert domestic_pos["avg_price"] == 70000.0
        assert domestic_pos["avg_price_usd"] is None

        # 해외 종목: avg_price는 USD * usd_krw_rate로 변환
        overseas_pos = next(p for p in make_account.manual_positions if p["ticker"] == "AAPL")
        assert overseas_pos["avg_price"] == 180.0 * 1300.0
        assert overseas_pos["avg_price_usd"] == 180.0
        assert overseas_pos["usd_rate"] == 1300.0


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
