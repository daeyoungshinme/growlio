"""alert_service 단위 테스트 — 환율/주가/리밸런싱 알림 트리거 로직 검증."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── _should_fire_today 테스트 ────────────────────────────────

class TestShouldFireToday:
    def _make_alert(self, schedule_type="DAILY", **kwargs):
        return SimpleNamespace(
            schedule_type=schedule_type,
            schedule_day_of_week=kwargs.get("schedule_day_of_week"),
            schedule_day_of_month=kwargs.get("schedule_day_of_month"),
            last_triggered_at=kwargs.get("last_triggered_at"),
        )

    def test_daily_always_fires(self):
        from app.services.alert_service import _should_fire_today

        alert = self._make_alert("DAILY")
        assert _should_fire_today(alert) is True

    def test_weekly_fires_on_correct_day(self):
        from app.services.alert_service import _should_fire_today
        from datetime import timezone

        # today의 요일을 구해 schedule_day_of_week로 설정
        today = datetime.now(tz=timezone(timedelta(hours=9))).date()
        alert = self._make_alert("WEEKLY", schedule_day_of_week=today.weekday())
        assert _should_fire_today(alert) is True

    def test_weekly_does_not_fire_on_wrong_day(self):
        from app.services.alert_service import _should_fire_today
        from datetime import timezone

        today = datetime.now(tz=timezone(timedelta(hours=9))).date()
        wrong_day = (today.weekday() + 1) % 7
        alert = self._make_alert("WEEKLY", schedule_day_of_week=wrong_day)
        result = _should_fire_today(alert)
        # 오늘 요일 != wrong_day이면 False여야 함
        if today.weekday() != wrong_day:
            assert result is False

    def test_quarterly_fires_first_time(self):
        from app.services.alert_service import _should_fire_today
        from datetime import timezone
        import calendar

        today = datetime.now(tz=timezone(timedelta(hours=9))).date()
        last_day = calendar.monthrange(today.year, today.month)[1]
        target_day = min(today.day, last_day)

        alert = self._make_alert(
            "QUARTERLY",
            schedule_day_of_month=target_day,
            last_triggered_at=None,  # 최초 발송
        )
        assert _should_fire_today(alert) is True

    def test_quarterly_does_not_fire_before_cooldown(self):
        from app.services.alert_service import _should_fire_today
        from datetime import timezone
        import calendar

        today = datetime.now(tz=timezone(timedelta(hours=9))).date()
        last_day = calendar.monthrange(today.year, today.month)[1]
        target_day = min(today.day, last_day)

        # 마지막 발송이 30일 전 (쿨다운 80일 미만)
        recent_trigger = datetime.now(tz=UTC) - timedelta(days=30)
        alert = self._make_alert(
            "QUARTERLY",
            schedule_day_of_month=target_day,
            last_triggered_at=recent_trigger,
        )
        result = _should_fire_today(alert)
        # 30일은 80일 쿨다운 미만이므로 False
        if today.day == target_day:
            assert result is False


# ── _already_fired_today 테스트 ──────────────────────────────

class TestAlreadyFiredToday:
    def test_returns_false_when_never_triggered(self):
        from app.services.alert_service import _already_fired_today

        alert = SimpleNamespace(last_triggered_at=None)
        assert _already_fired_today(alert) is False

    def test_returns_true_when_fired_today(self):
        from app.services.alert_service import _already_fired_today

        now = datetime.now(tz=UTC)
        alert = SimpleNamespace(last_triggered_at=now)
        assert _already_fired_today(alert) is True

    def test_returns_false_when_fired_yesterday(self):
        from app.services.alert_service import _already_fired_today

        yesterday = datetime.now(tz=UTC) - timedelta(days=1)
        alert = SimpleNamespace(last_triggered_at=yesterday)
        assert _already_fired_today(alert) is False


# ── check_and_trigger_alerts (환율) ─────────────────────────

@pytest.mark.asyncio
async def test_check_and_trigger_alerts_no_rate(mock_db):
    """환율 조회 실패(0 반환) 시 알림을 발송하지 않는다."""
    with patch("app.services.alert_service.fetch_usd_krw", AsyncMock(return_value=0)):
        from app.services.alert_service import check_and_trigger_alerts

        await check_and_trigger_alerts(mock_db)
        mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_trigger_alerts_below_condition(mock_db):
    """BELOW 조건 충족 시 이메일 발송 + AlertHistory 저장 + 비활성화."""
    user_id = uuid.uuid4()
    current_rate = 1290.0

    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        target_rate=1300.0,
        direction="BELOW",
        is_active=True,
        max_trigger_count=1,
        trigger_count=0,
        triggered_at=None,
    )

    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, "user@example.com", None, None)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    # send_exchange_rate_alert는 함수 내부에서 로컬 임포트됨 → 소스 모듈 경로로 패치
    with (
        patch("app.services.alert_service.fetch_usd_krw", AsyncMock(return_value=current_rate)),
        patch("app.services.email_service.send_exchange_rate_alert", AsyncMock()) as mock_email,
    ):
        from app.services.alert_service import check_and_trigger_alerts
        await check_and_trigger_alerts(mock_db)

    mock_email.assert_called_once()
    assert alert.trigger_count == 1
    assert alert.is_active is False
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_check_and_trigger_alerts_above_not_met(mock_db):
    """ABOVE 조건 미충족 시 이메일을 발송하지 않는다."""
    user_id = uuid.uuid4()
    current_rate = 1350.0

    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        target_rate=1400.0,  # 현재 1350 < 목표 1400 → 미충족
        direction="ABOVE",
        is_active=True,
        max_trigger_count=1,
        trigger_count=0,
        triggered_at=None,
    )

    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, "user@example.com", None, None)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    with (
        patch("app.services.alert_service.fetch_usd_krw", AsyncMock(return_value=current_rate)),
        patch("app.services.email_service.send_exchange_rate_alert", AsyncMock()) as mock_email,
    ):
        from app.services.alert_service import check_and_trigger_alerts
        await check_and_trigger_alerts(mock_db)

    mock_email.assert_not_called()
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_trigger_alerts_multi_trigger_cooldown(mock_db):
    """다회 발동 알림은 쿨다운 1시간 이내 재발동하지 않는다."""
    user_id = uuid.uuid4()
    current_rate = 1290.0

    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        target_rate=1300.0,
        direction="BELOW",
        is_active=True,
        max_trigger_count=3,
        trigger_count=1,
        triggered_at=datetime.now(tz=UTC) - timedelta(minutes=30),  # 30분 전 — 쿨다운 내
    )

    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, "user@example.com", None, None)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    with (
        patch("app.services.alert_service.fetch_usd_krw", AsyncMock(return_value=current_rate)),
        patch("app.services.email_service.send_exchange_rate_alert", AsyncMock()) as mock_email,
    ):
        from app.services.alert_service import check_and_trigger_alerts
        await check_and_trigger_alerts(mock_db)

    mock_email.assert_not_called()


@pytest.mark.asyncio
async def test_check_and_trigger_alerts_email_failure_continues(mock_db):
    """이메일 발송 실패 시 다음 알림 처리를 계속한다."""
    user_id = uuid.uuid4()
    current_rate = 1290.0

    alert1 = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        target_rate=1300.0,
        direction="BELOW",
        is_active=True,
        max_trigger_count=1,
        trigger_count=0,
        triggered_at=None,
    )

    execute_result = MagicMock()
    execute_result.all.return_value = [(alert1, "user@example.com", None, None)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    with (
        patch("app.services.alert_service.fetch_usd_krw", AsyncMock(return_value=current_rate)),
        patch(
            "app.services.email_service.send_exchange_rate_alert",
            AsyncMock(side_effect=Exception("SMTP 오류")),
        ),
    ):
        from app.services.alert_service import check_and_trigger_alerts
        await check_and_trigger_alerts(mock_db)

    # 이메일 실패 → commit 없음
    mock_db.commit.assert_not_called()


# ── check_and_trigger_stock_price_alerts ────────────────────

@pytest.mark.asyncio
async def test_check_stock_price_alerts_no_alerts(mock_db, mock_redis):
    """활성 주가 알림이 없으면 조기 반환한다."""
    execute_result = MagicMock()
    execute_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=execute_result)

    # fetch_prices_batch는 함수 내부에서 로컬 임포트됨 → 소스 모듈 경로로 패치
    with patch("app.services.price_service.fetch_prices_batch", AsyncMock(return_value={})):
        from app.services.alert_service import check_and_trigger_stock_price_alerts
        await check_and_trigger_stock_price_alerts(mock_db, mock_redis)

    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_check_stock_price_alerts_triggers_on_below(mock_db, mock_redis):
    """주가가 목표가 이하이면 이메일을 발송하고 알림을 비활성화한다."""
    user_id = uuid.uuid4()
    current_price = 79_000.0

    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        ticker="005930",
        market="KOSPI",
        name="삼성전자",
        target_price=80_000.0,
        direction="BELOW",
        is_active=True,
        max_trigger_count=1,
        trigger_count=0,
        triggered_at=None,
    )

    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, "user@example.com", None, None)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    with (
        patch(
            "app.services.price_service.fetch_prices_batch",
            AsyncMock(return_value={"005930": current_price}),
        ),
        patch("app.services.email_service.send_stock_price_alert", AsyncMock()) as mock_email,
    ):
        from app.services.alert_service import check_and_trigger_stock_price_alerts
        await check_and_trigger_stock_price_alerts(mock_db, mock_redis)

    mock_email.assert_called_once()
    assert alert.trigger_count == 1
    assert alert.is_active is False
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_check_stock_price_alerts_no_price_skips(mock_db, mock_redis):
    """가격 조회 실패(ticker 미포함) 시 해당 알림을 건너뛴다."""
    user_id = uuid.uuid4()

    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        ticker="UNKNOWN",
        market="KOSPI",
        name="미조회 종목",
        target_price=50_000.0,
        direction="BELOW",
        is_active=True,
        max_trigger_count=1,
        trigger_count=0,
        triggered_at=None,
    )

    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, "user@example.com", None, None)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    with (
        patch(
            "app.services.price_service.fetch_prices_batch",
            AsyncMock(return_value={}),  # ticker 없음
        ),
        patch("app.services.email_service.send_stock_price_alert", AsyncMock()) as mock_email,
    ):
        from app.services.alert_service import check_and_trigger_stock_price_alerts
        await check_and_trigger_stock_price_alerts(mock_db, mock_redis)

    mock_email.assert_not_called()
    mock_db.commit.assert_not_called()


# ── _save_alert_history ──────────────────────────────────────

@pytest.mark.asyncio
async def test_save_alert_history_adds_to_session(mock_db):
    """_save_alert_history가 AlertHistory 객체를 session에 추가한다."""
    user_id = uuid.uuid4()

    from app.services.alert_service import _save_alert_history

    await _save_alert_history(mock_db, user_id, "EXCHANGE_RATE", "환율 알림: 1290원")

    mock_db.add.assert_called_once()
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.user_id == user_id
    assert added_obj.alert_type == "EXCHANGE_RATE"
    assert "1290" in added_obj.message
