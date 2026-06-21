"""deposit_monitor 단위 테스트 — _notify_deposit_rebalancing 핵심 경로 검증."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_alert(user_id):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=uuid.uuid4(),  # AUTO 모드 실행 계좌
        deposit_trigger_min_amount_krw=10_000,
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


def _make_deposit_row(alert_id, account_id=None, last_known=None, current_deposit=700_000):
    """(RebalancingAlertDepositAccount, AssetAccount) 튜플 반환."""
    da = SimpleNamespace(
        id=uuid.uuid4(),
        alert_id=alert_id,
        account_id=account_id or uuid.uuid4(),
        last_known_deposit_krw=last_known,
    )
    account = SimpleNamespace(
        id=da.account_id,
        deposit_krw=current_deposit,
        is_active=True,
        asset_type="STOCK_KIS",
        kis_app_key=None,
        kis_app_secret=None,
        is_mock_mode=False,
    )
    return da, account


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
async def test_process_deposit_alert_no_accounts_returns_false():
    """`_process_deposit_alert`가 감시 계좌를 찾지 못하면 False를 반환한다."""
    user_id = uuid.uuid4()
    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=uuid.uuid4(),
        deposit_trigger_min_amount_krw=10_000,
        mode="NOTIFY",
        market_condition_mode="DISABLED",
    )
    portfolio = _make_portfolio()

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    execute_result = MagicMock()
    execute_result.all.return_value = []  # 감시 계좌 없음
    mock_session.execute = AsyncMock(return_value=execute_result)

    with patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session):
        from app.jobs.deposit_monitor import _process_deposit_alert

        result = await _process_deposit_alert(alert, portfolio, "user@example.com", None, None, "GREEN", MagicMock())

    assert result is False


@pytest.mark.asyncio
async def test_update_deposit_baselines_updates_fields(mock_db):
    """`_update_deposit_baselines`가 계좌별 last_known_deposit_krw를 갱신한다."""
    from app.jobs.deposit_monitor import _update_deposit_baselines

    alert_id = uuid.uuid4()
    da1 = SimpleNamespace(id=uuid.uuid4(), last_known_deposit_krw=None)
    da2 = SimpleNamespace(id=uuid.uuid4(), last_known_deposit_krw=None)
    fresh_alert = SimpleNamespace(id=alert_id, last_deposit_checked_at=None)

    fresh_da1 = SimpleNamespace(id=da1.id, last_known_deposit_krw=None)
    fresh_da2 = SimpleNamespace(id=da2.id, last_known_deposit_krw=None)

    # scalar: [da1, da2, alert] 순서로 반환
    mock_db.scalar = AsyncMock(side_effect=[fresh_da1, fresh_da2, fresh_alert])

    updates = [(da1, 500_000.0), (da2, 1_200_000.0)]
    await _update_deposit_baselines(mock_db, alert_id, updates)

    assert float(fresh_da1.last_known_deposit_krw) == 500_000.0
    assert float(fresh_da2.last_known_deposit_krw) == 1_200_000.0
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

    mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_process_deposit_alert_notify_mode_triggers_on_sufficient_deposit():
    """NOTIFY 모드 + 충분한 합산 입금 증분 → _notify_deposit_rebalancing 호출 후 True 반환."""
    user_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    alert = SimpleNamespace(
        id=alert_id,
        user_id=user_id,
        account_id=uuid.uuid4(),
        deposit_trigger_min_amount_krw=50_000,
        mode="NOTIFY",
        market_condition_mode="DISABLED",
    )
    portfolio = _make_portfolio()

    # 계좌 1: 500K → 700K (증분 +200K)
    da1, acc1 = _make_deposit_row(alert_id, last_known=500_000, current_deposit=700_000)
    da1_fresh = SimpleNamespace(id=da1.id, last_known_deposit_krw=da1.last_known_deposit_krw)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    # 첫 번째 execute: 감시 계좌 JOIN 결과
    deposit_result = MagicMock()
    deposit_result.all.return_value = [(da1, acc1)]
    # 이후 scalar 호출: da1_fresh, alert_fresh (베이스라인 업데이트용)
    fresh_alert = SimpleNamespace(id=alert_id, last_deposit_checked_at=None)
    mock_session.execute = AsyncMock(return_value=deposit_result)
    mock_session.scalar = AsyncMock(side_effect=[da1_fresh, fresh_alert])
    mock_session.commit = AsyncMock()

    with (
        patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session),
        patch("app.jobs.deposit_monitor._notify_deposit_rebalancing", new=AsyncMock()) as mock_notify,
        patch("app.services.alert_repository.save_alert_history", new=AsyncMock()),
    ):
        from app.jobs.deposit_monitor import _process_deposit_alert

        result = await _process_deposit_alert(alert, portfolio, "user@example.com", None, None, "GREEN", MagicMock())

    assert result is True
    mock_notify.assert_called_once()
    call_args = mock_notify.call_args.args
    assert call_args[2] == 200_000.0  # total_increment


@pytest.mark.asyncio
async def test_process_deposit_alert_below_min_amount_skips():
    """합산 입금 증분이 최소 금액 미만이면 알림을 발동하지 않는다."""
    user_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    alert = SimpleNamespace(
        id=alert_id,
        user_id=user_id,
        account_id=uuid.uuid4(),
        deposit_trigger_min_amount_krw=100_000,
        mode="NOTIFY",
        market_condition_mode="DISABLED",
    )
    portfolio = _make_portfolio()

    # 계좌 1: 500K → 550K (증분 +50K < min 100K)
    da1, acc1 = _make_deposit_row(alert_id, last_known=500_000, current_deposit=550_000)
    da1_fresh = SimpleNamespace(id=da1.id, last_known_deposit_krw=da1.last_known_deposit_krw)
    fresh_alert = SimpleNamespace(id=alert_id, last_deposit_checked_at=None)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    deposit_result = MagicMock()
    deposit_result.all.return_value = [(da1, acc1)]
    mock_session.execute = AsyncMock(return_value=deposit_result)
    mock_session.scalar = AsyncMock(side_effect=[da1_fresh, fresh_alert])
    mock_session.commit = AsyncMock()

    with patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session):
        from app.jobs.deposit_monitor import _process_deposit_alert

        result = await _process_deposit_alert(alert, portfolio, "user@example.com", None, None, "GREEN", MagicMock())

    assert result is False


@pytest.mark.asyncio
async def test_process_deposit_alert_multi_account_sum_triggers():
    """복수 계좌의 증분 합산이 min_amount 이상이면 트리거된다."""
    user_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    alert = SimpleNamespace(
        id=alert_id,
        user_id=user_id,
        account_id=uuid.uuid4(),
        deposit_trigger_min_amount_krw=150_000,
        mode="NOTIFY",
        market_condition_mode="DISABLED",
    )
    portfolio = _make_portfolio()

    # 계좌 1: 증분 +80K, 계좌 2: 증분 +90K → 합 170K > min 150K
    da1, acc1 = _make_deposit_row(alert_id, last_known=200_000, current_deposit=280_000)
    da2, acc2 = _make_deposit_row(alert_id, last_known=300_000, current_deposit=390_000)
    fresh_alert = SimpleNamespace(id=alert_id, last_deposit_checked_at=None)
    da1_fresh = SimpleNamespace(id=da1.id, last_known_deposit_krw=da1.last_known_deposit_krw)
    da2_fresh = SimpleNamespace(id=da2.id, last_known_deposit_krw=da2.last_known_deposit_krw)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    deposit_result = MagicMock()
    deposit_result.all.return_value = [(da1, acc1), (da2, acc2)]
    mock_session.execute = AsyncMock(return_value=deposit_result)
    mock_session.scalar = AsyncMock(side_effect=[da1_fresh, da2_fresh, fresh_alert])
    mock_session.commit = AsyncMock()

    with (
        patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session),
        patch("app.jobs.deposit_monitor._notify_deposit_rebalancing", new=AsyncMock()) as mock_notify,
        patch("app.services.alert_repository.save_alert_history", new=AsyncMock()),
    ):
        from app.jobs.deposit_monitor import _process_deposit_alert

        result = await _process_deposit_alert(alert, portfolio, "user@example.com", None, None, "GREEN", MagicMock())

    assert result is True
    call_args = mock_notify.call_args.args
    assert call_args[2] == 170_000.0  # 80K + 90K


@pytest.mark.asyncio
async def test_process_deposit_alert_multi_account_below_min_skips():
    """복수 계좌의 증분 합산이 min_amount 미만이면 스킵된다."""
    user_id = uuid.uuid4()
    alert_id = uuid.uuid4()
    alert = SimpleNamespace(
        id=alert_id,
        user_id=user_id,
        account_id=uuid.uuid4(),
        deposit_trigger_min_amount_krw=200_000,
        mode="NOTIFY",
        market_condition_mode="DISABLED",
    )
    portfolio = _make_portfolio()

    # 계좌 1: 증분 +50K, 계좌 2: 증분 +60K → 합 110K < min 200K
    da1, acc1 = _make_deposit_row(alert_id, last_known=200_000, current_deposit=250_000)
    da2, acc2 = _make_deposit_row(alert_id, last_known=300_000, current_deposit=360_000)
    fresh_alert = SimpleNamespace(id=alert_id, last_deposit_checked_at=None)
    da1_fresh = SimpleNamespace(id=da1.id, last_known_deposit_krw=da1.last_known_deposit_krw)
    da2_fresh = SimpleNamespace(id=da2.id, last_known_deposit_krw=da2.last_known_deposit_krw)

    mock_session = MagicMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    deposit_result = MagicMock()
    deposit_result.all.return_value = [(da1, acc1), (da2, acc2)]
    mock_session.execute = AsyncMock(return_value=deposit_result)
    mock_session.scalar = AsyncMock(side_effect=[da1_fresh, da2_fresh, fresh_alert])
    mock_session.commit = AsyncMock()

    with patch("app.jobs.deposit_monitor.AsyncSessionLocal", return_value=mock_session):
        from app.jobs.deposit_monitor import _process_deposit_alert

        result = await _process_deposit_alert(alert, portfolio, "user@example.com", None, None, "GREEN", MagicMock())

    assert result is False
