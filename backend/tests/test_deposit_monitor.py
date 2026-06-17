"""deposit_monitor 단위 테스트 — _notify_deposit_rebalancing 핵심 경로 검증."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_alert(user_id, account_id=None):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        deposit_trigger_account_id=account_id or uuid.uuid4(),
        deposit_trigger_min_amount_krw=10_000,
        last_known_deposit_krw=None,
        mode="NOTIFY",
        market_condition_mode="DISABLED",
    )


def _make_portfolio(items=None):
    port_items = items or [
        SimpleNamespace(ticker="AAPL", name="Apple", market="NASDAQ", weight=70),
        SimpleNamespace(ticker="TSLA", name="Tesla", market="NASDAQ", weight=30),
    ]
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="테스트 포트폴리오",
        account_ids=None,
        items=port_items,
    )


@pytest.mark.asyncio
async def test_notify_deposit_rebalancing_with_underweight(mock_db):
    """underweight 종목 있을 때 분석 기반 배분으로 이메일·푸시 발송."""
    user_id = uuid.uuid4()
    alert = _make_alert(user_id)
    portfolio = _make_portfolio()
    deposit_increment = 500_000.0

    underweight_item = SimpleNamespace(
        ticker="AAPL",
        name="Apple",
        market="NASDAQ",
        diff_krw=-200_000,
        target_weight_pct=70.0,
        weight_diff_pct=-10.0,
        shares_to_trade=2,
    )
    analysis = SimpleNamespace(items=[underweight_item])
    overview = {"total_assets_krw": 2_000_000, "total_stock_krw": 1_500_000, "all_positions": []}

    with (
        patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
        patch("app.services.rebalancing_service.analyze_rebalancing", return_value=analysis),
        patch("app.services.email_service.send_deposit_trigger_alert", new=AsyncMock()) as mock_email,
        patch("app.services.push_service.send_push_to_user", new=AsyncMock()) as mock_push,
    ):
        from app.jobs.deposit_monitor import _notify_deposit_rebalancing

        await _notify_deposit_rebalancing(alert, portfolio, deposit_increment, "user@example.com", None, mock_db)

    mock_email.assert_called_once()
    call_kwargs = mock_email.call_args.kwargs
    assert call_kwargs["deposit_increment"] == deposit_increment
    assert len(call_kwargs["items"]) == 1
    assert call_kwargs["items"][0]["ticker"] == "AAPL"
    mock_push.assert_called_once()


@pytest.mark.asyncio
async def test_notify_deposit_rebalancing_fallback_on_analysis_failure(mock_db):
    """분석 실패 시 단순 비중 배분으로 폴백하여 이메일 발송."""
    user_id = uuid.uuid4()
    alert = _make_alert(user_id)
    portfolio = _make_portfolio()
    deposit_increment = 300_000.0

    with (
        patch(
            "app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(side_effect=Exception("DB 오류"))
        ),
        patch("app.services.email_service.send_deposit_trigger_alert", new=AsyncMock()) as mock_email,
        patch("app.services.push_service.send_push_to_user", new=AsyncMock()),
    ):
        from app.jobs.deposit_monitor import _notify_deposit_rebalancing

        await _notify_deposit_rebalancing(alert, portfolio, deposit_increment, "user@example.com", None, mock_db)

    # 폴백: 포트폴리오 items 비중 배분으로 이메일 발송
    mock_email.assert_called_once()
    call_kwargs = mock_email.call_args.kwargs
    items = call_kwargs["items"]
    assert len(items) == 2
    tickers = [i["ticker"] for i in items]
    assert "AAPL" in tickers
    assert "TSLA" in tickers


@pytest.mark.asyncio
async def test_notify_deposit_rebalancing_no_underweight_uses_fallback(mock_db):
    """underweight 종목 없을 때 (overweight만) 비중 비례 배분으로 폴백."""
    user_id = uuid.uuid4()
    alert = _make_alert(user_id)
    portfolio = _make_portfolio()
    deposit_increment = 200_000.0

    # diff_krw > 0 이면 overweight (매수 불필요)
    overweight_item = SimpleNamespace(
        ticker="AAPL",
        name="Apple",
        market="NASDAQ",
        diff_krw=100_000,
        target_weight_pct=70.0,
        weight_diff_pct=10.0,
        shares_to_trade=1,
    )
    analysis = SimpleNamespace(items=[overweight_item])
    overview = {"total_assets_krw": 2_000_000, "total_stock_krw": 1_500_000, "all_positions": []}

    with (
        patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
        patch("app.services.rebalancing_service.analyze_rebalancing", return_value=analysis),
        patch("app.services.email_service.send_deposit_trigger_alert", new=AsyncMock()) as mock_email,
        patch("app.services.push_service.send_push_to_user", new=AsyncMock()),
    ):
        from app.jobs.deposit_monitor import _notify_deposit_rebalancing

        await _notify_deposit_rebalancing(alert, portfolio, deposit_increment, "user@example.com", "fcm-token", mock_db)

    mock_email.assert_called_once()
    call_kwargs = mock_email.call_args.kwargs
    items = call_kwargs["items"]
    assert len(items) == 2


@pytest.mark.asyncio
async def test_run_deposit_monitor_skips_when_lock_not_acquired():
    """Redis 락 획득 실패 시 처리를 건너뛴다."""
    mock_redis = MagicMock()

    class _FakeLock:
        async def __aenter__(self):
            return False  # not acquired

        async def __aexit__(self, *_):
            pass

    with (
        patch("app.jobs.deposit_monitor.get_redis", new=AsyncMock(return_value=mock_redis)),
        patch("app.jobs.deposit_monitor.redis_lock", return_value=_FakeLock()),
        patch("app.jobs.deposit_monitor._run_deposit_monitor", new=AsyncMock()) as mock_run,
    ):
        from app.jobs.deposit_monitor import run_deposit_monitor

        await run_deposit_monitor()

    mock_run.assert_not_called()


@pytest.mark.asyncio
async def test_run_deposit_monitor_no_rows_returns_early():
    """`_run_deposit_monitor`가 활성 예수금 알림 없으면 조기 반환한다."""
    mock_redis = MagicMock()
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    execute_result = MagicMock()
    execute_result.all.return_value = []
    mock_session.execute = AsyncMock(return_value=execute_result)

    with (
        patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session),
        patch(
            "app.services.market_signal_service.get_market_signal",
            new=AsyncMock(return_value={"composite_level": "GREEN"}),
        ),
        patch("app.jobs.deposit_monitor._process_deposit_alert", new=AsyncMock()) as mock_process,
    ):
        from app.jobs.deposit_monitor import _run_deposit_monitor

        await _run_deposit_monitor(mock_redis)

    mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_run_deposit_monitor_processes_rows():
    """`_run_deposit_monitor`가 rows를 처리하고 완료 로그를 남긴다."""
    mock_redis = MagicMock()
    alert = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    portfolio = SimpleNamespace(id=uuid.uuid4(), name="포트폴리오")

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None)]
    mock_session.execute = AsyncMock(return_value=execute_result)

    with (
        patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session),
        patch(
            "app.services.market_signal_service.get_market_signal",
            new=AsyncMock(return_value={"composite_level": "GREEN"}),
        ),
        patch("app.jobs.deposit_monitor._process_deposit_alert", new=AsyncMock(return_value=True)) as mock_process,
    ):
        from app.jobs.deposit_monitor import _run_deposit_monitor

        await _run_deposit_monitor(mock_redis)

    mock_process.assert_called_once()


@pytest.mark.asyncio
async def test_process_deposit_alert_account_not_found():
    """`_process_deposit_alert`가 계좌를 찾지 못하면 False를 반환한다."""
    user_id = uuid.uuid4()
    account_id = uuid.uuid4()
    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        deposit_trigger_account_id=account_id,
        deposit_trigger_min_amount_krw=10_000,
        last_known_deposit_krw=None,
        mode="NOTIFY",
    )
    portfolio = _make_portfolio()

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.scalar = AsyncMock(return_value=None)  # 계좌 없음

    with patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session):
        from app.jobs.deposit_monitor import _process_deposit_alert

        result = await _process_deposit_alert(alert, portfolio, "user@example.com", None, None, "GREEN", MagicMock())

    assert result is False


@pytest.mark.asyncio
async def test_update_deposit_baseline_updates_fields(mock_db):
    """`_update_deposit_baseline`가 last_known_deposit_krw를 갱신한다."""
    alert_id = uuid.uuid4()
    fresh_alert = SimpleNamespace(
        id=alert_id,
        last_known_deposit_krw=None,
        last_deposit_checked_at=None,
    )
    mock_db.scalar = AsyncMock(return_value=fresh_alert)

    from app.jobs.deposit_monitor import _update_deposit_baseline

    await _update_deposit_baseline(mock_db, alert_id, 750_000.0)

    assert float(fresh_alert.last_known_deposit_krw) == 750_000.0
    assert fresh_alert.last_deposit_checked_at is not None


@pytest.mark.asyncio
async def test_run_deposit_monitor_lock_acquired_calls_inner():
    """Redis 락 획득 성공 시 `_run_deposit_monitor`를 호출한다."""
    mock_redis = MagicMock()

    class _AcquiredLock:
        async def __aenter__(self):
            return True  # acquired

        async def __aexit__(self, *_):
            pass

    with (
        patch("app.jobs.deposit_monitor.get_redis", new=AsyncMock(return_value=mock_redis)),
        patch("app.jobs.deposit_monitor.redis_lock", return_value=_AcquiredLock()),
        patch("app.jobs.deposit_monitor._run_deposit_monitor", new=AsyncMock()) as mock_run,
    ):
        from app.jobs.deposit_monitor import run_deposit_monitor

        await run_deposit_monitor()

    mock_run.assert_called_once_with(mock_redis)


@pytest.mark.asyncio
async def test_run_deposit_monitor_alert_processing_error_continues():
    """`_process_deposit_alert` 예외 발생 시 루프가 계속 진행된다."""
    mock_redis = MagicMock()
    alert = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    portfolio = SimpleNamespace(id=uuid.uuid4(), name="포트폴리오")

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None)]
    mock_session.execute = AsyncMock(return_value=execute_result)

    with (
        patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session),
        patch(
            "app.services.market_signal_service.get_market_signal",
            new=AsyncMock(return_value={"composite_level": "GREEN"}),
        ),
        patch(
            "app.jobs.deposit_monitor._process_deposit_alert", new=AsyncMock(side_effect=Exception("처리 오류"))
        ) as mock_process,
    ):
        from app.jobs.deposit_monitor import _run_deposit_monitor

        await _run_deposit_monitor(mock_redis)  # 예외를 삼키고 정상 완료

    mock_process.assert_called_once()


@pytest.mark.asyncio
async def test_run_deposit_monitor_market_signal_failure_uses_green():
    """`_run_deposit_monitor`에서 시장 신호 조회 실패 시 GREEN으로 폴백한다."""
    mock_redis = MagicMock()
    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    execute_result = MagicMock()
    execute_result.all.return_value = []
    mock_session.execute = AsyncMock(return_value=execute_result)

    with (
        patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session),
        patch(
            "app.services.market_signal_service.get_market_signal",
            new=AsyncMock(side_effect=Exception("Redis timeout")),
        ),
        patch("app.jobs.deposit_monitor._process_deposit_alert", new=AsyncMock()) as mock_process,
    ):
        from app.jobs.deposit_monitor import _run_deposit_monitor

        await _run_deposit_monitor(mock_redis)

    # 시장 신호 실패해도 함수는 정상 완료되어야 함 (rows=[] 이므로 early return)
    mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_process_deposit_alert_notify_mode_triggers_on_sufficient_deposit():
    """NOTIFY 모드 + 충분한 입금 증분 → _notify_deposit_rebalancing 호출 후 True 반환."""
    user_id = uuid.uuid4()
    account_id = uuid.uuid4()
    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        deposit_trigger_account_id=account_id,
        deposit_trigger_min_amount_krw=50_000,
        last_known_deposit_krw=500_000,
        mode="NOTIFY",
        market_condition_mode="DISABLED",
    )
    portfolio = _make_portfolio()

    account = SimpleNamespace(
        id=account_id,
        deposit_krw=700_000,  # 증분 = 200K > min 50K
        is_active=True,
        asset_type="STOCK_KIS",
    )

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.scalar = AsyncMock(return_value=account)
    mock_session.commit = AsyncMock()

    with (
        patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session),
        patch("app.jobs.deposit_monitor._notify_deposit_rebalancing", new=AsyncMock()) as mock_notify,
        patch("app.jobs.deposit_monitor._update_deposit_baseline", new=AsyncMock()),
        patch("app.services.alert_repository.save_alert_history", new=AsyncMock()),
    ):
        from app.jobs.deposit_monitor import _process_deposit_alert

        result = await _process_deposit_alert(alert, portfolio, "user@example.com", None, None, "GREEN", MagicMock())

    assert result is True
    mock_notify.assert_called_once()
    # _notify_deposit_rebalancing(alert, portfolio, deposit_increment, email, fcm_token, db)
    call_args = mock_notify.call_args.args
    assert call_args[2] == 200_000.0  # deposit_increment


@pytest.mark.asyncio
async def test_process_deposit_alert_below_min_amount_skips():
    """입금 증분이 최소 금액 미만이면 알림을 발동하지 않는다."""
    user_id = uuid.uuid4()
    account_id = uuid.uuid4()
    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        deposit_trigger_account_id=account_id,
        deposit_trigger_min_amount_krw=100_000,
        last_known_deposit_krw=500_000,
        mode="NOTIFY",
        market_condition_mode="DISABLED",
    )
    portfolio = _make_portfolio()

    account = SimpleNamespace(
        id=account_id,
        deposit_krw=550_000,  # 증분 = 50K < min 100K
        is_active=True,
        asset_type="STOCK_KIS",
        kis_app_key=None,
        kis_app_secret=None,
        is_mock_mode=False,
    )

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_session.scalar = AsyncMock(return_value=account)
    mock_session.commit = AsyncMock()

    with (
        patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session),
        patch("app.jobs.deposit_monitor._update_deposit_baseline", new=AsyncMock()),
    ):
        from app.jobs.deposit_monitor import _process_deposit_alert

        result = await _process_deposit_alert(alert, portfolio, "user@example.com", None, None, "GREEN", MagicMock())

    assert result is False
