"""alert_service.py 스케줄 브랜치 커버리지 테스트."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_KST = timezone(timedelta(hours=9))


@pytest.mark.asyncio
async def test_check_rebalancing_alerts_skips_when_should_not_fire_today(mock_db):
    """should_fire_today가 False를 반환하면 알림을 건너뛴다 (WEEKLY, 오늘 아닌 요일)."""
    user_id = uuid.uuid4()
    portfolio_id = uuid.uuid4()
    today_dow = datetime.now(tz=_KST).date().weekday()
    wrong_dow = (today_dow + 3) % 7

    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        schedule_type="WEEKLY",
        schedule_day_of_week=wrong_dow,
        schedule_day_of_month=None,
        last_triggered_at=None,
        threshold_pct=5.0,
        only_when_drift=True,
        mode="NOTIFY",
        account_id=None,
    )
    portfolio = SimpleNamespace(id=portfolio_id, name="Test Portfolio", account_ids=None, items=[])
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    with patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email:
        from app.services.alert_service import check_rebalancing_alerts
        await check_rebalancing_alerts(mock_db)

    mock_email.assert_not_called()
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_check_rebalancing_alerts_skips_when_already_fired_today(mock_db):
    """오늘 이미 발송된 알림은 already_fired_today로 건너뛴다."""
    user_id = uuid.uuid4()
    portfolio_id = uuid.uuid4()
    now_kst = datetime.now(tz=_KST)

    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        schedule_type="DAILY",
        schedule_day_of_week=None,
        schedule_day_of_month=None,
        last_triggered_at=now_kst,
        threshold_pct=5.0,
        only_when_drift=True,
        mode="NOTIFY",
        account_id=None,
    )
    portfolio = SimpleNamespace(id=portfolio_id, name="Test Portfolio", account_ids=None, items=[])
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    with patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email:
        from app.services.alert_service import check_rebalancing_alerts
        await check_rebalancing_alerts(mock_db)

    mock_email.assert_not_called()
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_check_rebalancing_alerts_analysis_failure_continues(mock_db):
    """analyze_rebalancing 실패 시 해당 알림을 건너뛰고 계속한다."""
    user_id = uuid.uuid4()
    portfolio_id = uuid.uuid4()

    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        schedule_type="DAILY",
        schedule_day_of_week=None,
        schedule_day_of_month=None,
        last_triggered_at=None,
        threshold_pct=5.0,
        only_when_drift=True,
        mode="NOTIFY",
        account_id=None,
    )
    portfolio = SimpleNamespace(id=portfolio_id, name="Test Portfolio", account_ids=None, items=[])
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

    with (
        patch("app.services.portfolio_service.build_portfolio_overview",
              new=AsyncMock(return_value=overview)),
        patch("app.services.rebalancing_service.analyze_rebalancing",
              side_effect=ValueError("분석 오류")),
        patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email,
    ):
        from app.services.alert_service import check_rebalancing_alerts
        await check_rebalancing_alerts(mock_db)

    mock_email.assert_not_called()
    mock_db.commit.assert_not_called()
