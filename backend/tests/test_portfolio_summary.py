"""portfolio /summary 다계좌 집계 단위 테스트."""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_domestic(value_krw=10_000_000.0, invested=9_000_000.0, pnl=1_000_000.0, deposit=500_000.0):
    return {
        "total_value_krw": value_krw,
        "invested_krw": invested,
        "pnl_krw": pnl,
        "deposit_krw": deposit,
        "positions": [{"ticker": "005930", "qty": 10, "avg_price": 70000}],
    }


def _make_overseas(value_usd=100.0, deposit_usd=50.0):
    return {
        "total_value_usd": value_usd,
        "deposit_usd": deposit_usd,
        "positions": [{"ticker": "AAPL", "qty": 1, "market": "NAS"}],
    }


def _make_kis_account(account_no: str, user_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id or uuid.uuid4(),
        name=f"KIS {account_no}",
        asset_type="STOCK_KIS",
        data_source="KIS_API",
        is_active=True,
        is_mock_mode=True,
        kis_account_no=account_no,
    )


def _make_settings(user_id, encrypted_key=b"enc_key", encrypted_secret=b"enc_secret"):
    return SimpleNamespace(
        user_id=user_id,
        kis_app_key=encrypted_key,
        kis_app_secret=encrypted_secret,
        kis_is_mock=True,
        kis_account_no="12345678-01",
    )


class TestPortfolioSummaryMultiAccount:
    """portfolio_summary: 다계좌 집계 검증."""

    @pytest.mark.asyncio
    async def test_single_account_returns_correct_totals(self, mock_request):
        """단일 KIS 계좌일 때 집계 결과가 해당 계좌 값과 동일해야 한다."""
        from app.api.v1.portfolio_analysis import portfolio_summary

        user_id = uuid.uuid4()
        user = SimpleNamespace(id=user_id)
        account = _make_kis_account("12345678-01", user_id)
        domestic = _make_domestic(10_000_000.0, 9_000_000.0, 1_000_000.0, 500_000.0)
        overseas = _make_overseas(100.0, 50.0)

        mock_db = AsyncMock()

        acc_result = MagicMock()
        acc_result.scalars.return_value.all.return_value = [account]
        mock_db.execute = AsyncMock(return_value=acc_result)

        mock_creds = {"app_key": "key", "app_secret": "secret", "access_token": "token", "is_mock": True}
        with (
            patch("app.api.v1.portfolio_analysis.get_kis_user_credentials", new=AsyncMock(return_value=mock_creds)),
            patch("app.api.v1.portfolio_analysis.get_domestic_balance", new=AsyncMock(return_value=domestic)),
            patch("app.api.v1.portfolio_analysis.get_overseas_balance", new=AsyncMock(return_value=overseas)),
        ):
            result = await portfolio_summary(request=mock_request, current_user=user, db=mock_db)

        assert result["total_value_krw"] == 10_000_000.0
        assert result["total_invested_krw"] == 9_000_000.0
        assert result["unrealized_pnl_krw"] == 1_000_000.0
        assert len(result["accounts"]) == 1
        assert result["accounts"][0]["account_no"] == "12345678-01"

    @pytest.mark.asyncio
    async def test_two_accounts_aggregated_correctly(self, mock_request):
        """두 KIS 계좌의 domestic/overseas 잔고가 합산되어야 한다."""
        from app.api.v1.portfolio_analysis import portfolio_summary

        user_id = uuid.uuid4()
        user = SimpleNamespace(id=user_id)
        acc1 = _make_kis_account("12345678-01", user_id)
        acc2 = _make_kis_account("12345678-02", user_id)

        domestic1 = _make_domestic(10_000_000.0, 9_000_000.0, 1_000_000.0, 500_000.0)
        domestic2 = _make_domestic(5_000_000.0, 4_000_000.0, 1_000_000.0, 200_000.0)
        overseas1 = _make_overseas(100.0, 50.0)
        overseas2 = _make_overseas(200.0, 80.0)

        mock_db = AsyncMock()

        acc_result = MagicMock()
        acc_result.scalars.return_value.all.return_value = [acc1, acc2]
        mock_db.execute = AsyncMock(return_value=acc_result)

        call_count = {"domestic": 0, "overseas": 0}

        async def mock_domestic(app_key, app_secret, token, account_no, is_mock):
            call_count["domestic"] += 1
            return domestic1 if account_no == "12345678-01" else domestic2

        async def mock_overseas(app_key, app_secret, token, account_no, is_mock):
            call_count["overseas"] += 1
            return overseas1 if account_no == "12345678-01" else overseas2

        mock_creds = {"app_key": "key", "app_secret": "secret", "access_token": "token", "is_mock": True}
        with (
            patch("app.api.v1.portfolio_analysis.get_kis_user_credentials", new=AsyncMock(return_value=mock_creds)),
            patch("app.api.v1.portfolio_analysis.get_domestic_balance", side_effect=mock_domestic),
            patch("app.api.v1.portfolio_analysis.get_overseas_balance", side_effect=mock_overseas),
        ):
            result = await portfolio_summary(request=mock_request, current_user=user, db=mock_db)

        assert result["total_value_krw"] == 15_000_000.0
        assert result["total_invested_krw"] == 13_000_000.0
        assert result["unrealized_pnl_krw"] == 2_000_000.0
        assert result["domestic"]["deposit_krw"] == 700_000.0
        assert result["overseas"]["total_value_usd"] == 300.0
        assert result["overseas"]["deposit_usd"] == 130.0
        assert len(result["domestic"]["positions"]) == 2
        assert len(result["overseas"]["positions"]) == 2
        assert len(result["accounts"]) == 2
        assert call_count["domestic"] == 2
        assert call_count["overseas"] == 2

    @pytest.mark.asyncio
    async def test_no_kis_settings_raises_400(self, mock_request):
        """KIS 설정이 없으면 400 에러를 반환해야 한다."""
        from fastapi import HTTPException

        from app.api.v1.portfolio_analysis import portfolio_summary

        user = SimpleNamespace(id=uuid.uuid4())
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await portfolio_summary(request=mock_request, current_user=user, db=mock_db)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_no_active_kis_accounts_raises_400(self, mock_request):
        """KIS 설정은 있지만 등록된 활성 계좌가 없으면 400 에러를 반환해야 한다."""
        from fastapi import HTTPException

        from app.api.v1.portfolio_analysis import portfolio_summary

        user_id = uuid.uuid4()
        user = SimpleNamespace(id=user_id)

        mock_db = AsyncMock()

        acc_result = MagicMock()
        acc_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=acc_result)

        mock_creds = {"app_key": "key", "app_secret": "secret", "access_token": "token", "is_mock": True}
        with (
            patch("app.api.v1.portfolio_analysis.get_kis_user_credentials", new=AsyncMock(return_value=mock_creds)),
            pytest.raises(HTTPException) as exc_info,
        ):
            await portfolio_summary(request=mock_request, current_user=user, db=mock_db)

        assert exc_info.value.status_code == 400
        assert "등록된 KIS 계좌가 없습니다" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_stock_return_pct_calculated_from_aggregated(self, mock_request):
        """수익률은 합산된 invested_krw 기준으로 계산되어야 한다."""
        from app.api.v1.portfolio_analysis import portfolio_summary

        user_id = uuid.uuid4()
        user = SimpleNamespace(id=user_id)
        acc1 = _make_kis_account("12345678-01", user_id)
        acc2 = _make_kis_account("12345678-02", user_id)

        domestic1 = _make_domestic(11_000_000.0, 10_000_000.0, 1_000_000.0)
        domestic2 = _make_domestic(11_000_000.0, 10_000_000.0, 1_000_000.0)
        overseas = _make_overseas(0.0, 0.0)
        overseas["positions"] = []

        mock_db = AsyncMock()
        acc_result = MagicMock()
        acc_result.scalars.return_value.all.return_value = [acc1, acc2]
        mock_db.execute = AsyncMock(return_value=acc_result)

        async def mock_domestic(app_key, app_secret, token, account_no, is_mock):
            return domestic1 if account_no == "12345678-01" else domestic2

        mock_creds = {"app_key": "key", "app_secret": "secret", "access_token": "token", "is_mock": True}
        with (
            patch("app.api.v1.portfolio_analysis.get_kis_user_credentials", new=AsyncMock(return_value=mock_creds)),
            patch("app.api.v1.portfolio_analysis.get_domestic_balance", side_effect=mock_domestic),
            patch("app.api.v1.portfolio_analysis.get_overseas_balance", new=AsyncMock(return_value=overseas)),
        ):
            result = await portfolio_summary(request=mock_request, current_user=user, db=mock_db)

        # 합산: total=22M, invested=20M → 10% 수익률
        assert abs(result["stock_return_pct"] - 10.0) < 0.01
