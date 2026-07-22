"""stock_price_alert_service 단위 테스트."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _make_alert(
    *,
    ticker: str = "005930",
    market: str = "KOSPI",
    name: str = "삼성전자",
    target_price: float = 60000.0,
    direction: str = "BELOW",
    trigger_count: int = 0,
    max_trigger_count: int = 1,
    triggered_at=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        ticker=ticker,
        market=market,
        name=name,
        target_price=target_price,
        direction=direction,
        trigger_count=trigger_count,
        max_trigger_count=max_trigger_count,
        triggered_at=triggered_at,
        is_active=True,
    )


def _make_row(alert, email="user@test.com", notification_email=None, fcm_token=None):
    return (alert, email, notification_email, fcm_token)


class TestCheckAndTriggerStockPriceAlerts:
    @pytest.mark.asyncio
    async def test_no_alerts_returns_early(self, mock_db, mock_cache):
        """활성 알림이 없으면 가격 조회 없이 바로 반환한다."""
        mock_db.execute.return_value.all.return_value = []

        from app.services.alerts.stock_price_service import check_and_trigger_stock_price_alerts

        await check_and_trigger_stock_price_alerts(mock_db, mock_cache)

        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_price_not_in_map_skips_alert(self, mock_db, mock_cache):
        """가격 맵에 해당 종목이 없으면 알림을 스킵한다."""
        alert = _make_alert(ticker="005930")
        mock_db.execute.return_value.all.return_value = [_make_row(alert)]

        with patch(
            "app.services.price_service.fetch_prices_batch",
            new_callable=AsyncMock,
            return_value={},
        ):
            from app.services.alerts.stock_price_service import check_and_trigger_stock_price_alerts

            await check_and_trigger_stock_price_alerts(mock_db, mock_cache)

        mock_db.commit.assert_not_called()
        assert alert.trigger_count == 0

    @pytest.mark.asyncio
    async def test_below_condition_triggers(self, mock_db, mock_cache):
        """BELOW 조건 충족 시 이메일+푸시 발송하고 trigger_count 증가."""
        alert = _make_alert(ticker="005930", target_price=60000.0, direction="BELOW", max_trigger_count=3)
        mock_db.execute.return_value.all.return_value = [_make_row(alert)]

        with (
            patch(
                "app.services.price_service.fetch_prices_batch",
                new_callable=AsyncMock,
                return_value={"005930": 58000.0},
            ),
            patch("app.services.email_service.send_stock_price_alert", new_callable=AsyncMock),
            patch("app.services.push_service.send_push_to_user", new_callable=AsyncMock),
            patch("app.services.alerts.alert_service.save_alert_history", new_callable=AsyncMock),
        ):
            from app.services.alerts.stock_price_service import check_and_trigger_stock_price_alerts

            await check_and_trigger_stock_price_alerts(mock_db, mock_cache)

        mock_db.commit.assert_called_once()
        assert alert.trigger_count == 1
        assert alert.is_active is True  # max=3이므로 유지

    @pytest.mark.asyncio
    async def test_above_condition_triggers(self, mock_db, mock_cache):
        """ABOVE 조건 충족 시 트리거된다."""
        alert = _make_alert(ticker="AAPL", market="NASDAQ", target_price=200.0, direction="ABOVE", max_trigger_count=2)
        mock_db.execute.return_value.all.return_value = [_make_row(alert)]

        with (
            patch(
                "app.services.price_service.fetch_prices_batch",
                new_callable=AsyncMock,
                return_value={"AAPL": 205.0},
            ),
            patch("app.services.email_service.send_stock_price_alert", new_callable=AsyncMock),
            patch("app.services.push_service.send_push_to_user", new_callable=AsyncMock),
            patch("app.services.alerts.alert_service.save_alert_history", new_callable=AsyncMock),
        ):
            from app.services.alerts.stock_price_service import check_and_trigger_stock_price_alerts

            await check_and_trigger_stock_price_alerts(mock_db, mock_cache)

        assert alert.trigger_count == 1

    @pytest.mark.asyncio
    async def test_alert_deactivated_at_max_trigger(self, mock_db, mock_cache):
        """trigger_count가 max에 달하면 is_active=False."""
        alert = _make_alert(ticker="005930", target_price=60000.0, direction="BELOW", max_trigger_count=1)
        mock_db.execute.return_value.all.return_value = [_make_row(alert)]

        with (
            patch(
                "app.services.price_service.fetch_prices_batch",
                new_callable=AsyncMock,
                return_value={"005930": 55000.0},
            ),
            patch("app.services.email_service.send_stock_price_alert", new_callable=AsyncMock),
            patch("app.services.push_service.send_push_to_user", new_callable=AsyncMock),
            patch("app.services.alerts.alert_service.save_alert_history", new_callable=AsyncMock),
        ):
            from app.services.alerts.stock_price_service import check_and_trigger_stock_price_alerts

            await check_and_trigger_stock_price_alerts(mock_db, mock_cache)

        assert alert.trigger_count == 1
        assert alert.is_active is False

    @pytest.mark.asyncio
    async def test_below_condition_not_met_does_not_trigger(self, mock_db, mock_cache):
        """BELOW이지만 현재가가 목표 위에 있으면 트리거 안 됨."""
        alert = _make_alert(ticker="005930", target_price=60000.0, direction="BELOW")
        mock_db.execute.return_value.all.return_value = [_make_row(alert)]

        with patch(
            "app.services.price_service.fetch_prices_batch",
            new_callable=AsyncMock,
            return_value={"005930": 65000.0},
        ):
            from app.services.alerts.stock_price_service import check_and_trigger_stock_price_alerts

            await check_and_trigger_stock_price_alerts(mock_db, mock_cache)

        mock_db.commit.assert_not_called()
        assert alert.trigger_count == 0

    @pytest.mark.asyncio
    async def test_email_failure_skips_alert(self, mock_db, mock_cache):
        """이메일 발송 실패 시 해당 알림을 건너뛰고 commit하지 않는다."""
        alert = _make_alert(ticker="005930", target_price=60000.0, direction="BELOW")
        mock_db.execute.return_value.all.return_value = [_make_row(alert)]

        with (
            patch(
                "app.services.price_service.fetch_prices_batch",
                new_callable=AsyncMock,
                return_value={"005930": 55000.0},
            ),
            patch(
                "app.services.email_service.send_stock_price_alert",
                new_callable=AsyncMock,
                return_value=False,
            ),
        ):
            from app.services.alerts.stock_price_service import check_and_trigger_stock_price_alerts

            await check_and_trigger_stock_price_alerts(mock_db, mock_cache)

        mock_db.commit.assert_not_called()
        assert alert.trigger_count == 0
