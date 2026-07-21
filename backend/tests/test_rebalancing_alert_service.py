"""rebalancing_alert_service 단위 테스트 — 리밸런싱 알림 트리거·자동실행 로직 검증."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── check_rebalancing_alerts ─────────────────────────────────


@pytest.mark.asyncio
async def test_check_rebalancing_alerts_no_alerts_nothing_happens(mock_db, override_settings):
    """활성 리밸런싱 알림이 없으면 조기 반환한다."""
    from app.services.rebalancing.alert_check import check_rebalancing_alerts

    exec_result = MagicMock()
    exec_result.all.return_value = []
    mock_db.execute = AsyncMock(return_value=exec_result)

    await check_rebalancing_alerts(mock_db)

    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_check_rebalancing_alerts_notify_with_drift(mock_db):
    """NOTIFY 모드 + 드리프트 초과 시 이메일 발송 및 AlertHistory 저장."""
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
        trigger_condition="DRIFT_ONLY",
        mode="NOTIFY",
        account_id=None,
        strategy="BUY_ONLY",
        order_type="MARKET",
        notify_time=_current_notify_time(),
    )
    portfolio = SimpleNamespace(id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[])
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    drifting_item = SimpleNamespace(
        ticker="AAPL",
        market="NASDAQ",
        name="Apple",
        weight_diff_pct=15.0,
        diff_krw=500_000,
        shares_to_trade=5.0,
    )
    analysis = SimpleNamespace(items=[drifting_item], ticker_account_map={})
    overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

    with (
        patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
        patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
        patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email,
    ):
        from app.services.rebalancing.alert_check import check_rebalancing_alerts

        await check_rebalancing_alerts(mock_db)

    mock_email.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_check_rebalancing_alerts_no_drift_skips(mock_db):
    """드리프트 없을 때 trigger_condition=DRIFT_ONLY이면 이메일 미발송."""
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
        trigger_condition="DRIFT_ONLY",
        mode="NOTIFY",
        account_id=None,
    )
    portfolio = SimpleNamespace(id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[])
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    item = SimpleNamespace(
        ticker="AAPL",
        market="NASDAQ",
        name="Apple",
        weight_diff_pct=2.0,
        diff_krw=100_000,
        shares_to_trade=1.0,
    )
    analysis = SimpleNamespace(items=[item], ticker_account_map={})
    overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

    with (
        patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
        patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
        patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email,
    ):
        from app.services.rebalancing.alert_check import check_rebalancing_alerts

        await check_rebalancing_alerts(mock_db)

    mock_email.assert_not_called()
    mock_db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_check_rebalancing_alerts_overview_failure_continues(mock_db):
    """build_portfolio_overview 실패 시 해당 알림을 건너뛰고 계속한다."""
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
        trigger_condition="DRIFT_ONLY",
        mode="NOTIFY",
        account_id=None,
    )
    portfolio = SimpleNamespace(id=portfolio_id, name="Test Portfolio", account_ids=None, items=[])
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    with (
        patch(
            "app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(side_effect=Exception("DB Error"))
        ),
        patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email,
    ):
        from app.services.rebalancing.alert_check import check_rebalancing_alerts

        await check_rebalancing_alerts(mock_db)

    mock_email.assert_not_called()


@pytest.mark.asyncio
async def test_check_rebalancing_alerts_scheduled_report(mock_db):
    """trigger_condition=SCHEDULE_ONLY + scheduled report 이메일 발송."""
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
        trigger_condition="SCHEDULE_ONLY",
        mode="NOTIFY",
        account_id=None,
        strategy="BUY_ONLY",
        order_type="MARKET",
        notify_time=_current_notify_time(),
    )
    portfolio = SimpleNamespace(id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[])
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    item = SimpleNamespace(
        ticker="AAPL",
        market="NASDAQ",
        name="Apple",
        weight_diff_pct=2.0,
        diff_krw=100_000,
        shares_to_trade=1.0,
    )
    analysis = SimpleNamespace(items=[item], ticker_account_map={})
    overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

    with (
        patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
        patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
        patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email,
    ):
        from app.services.rebalancing.alert_check import check_rebalancing_alerts

        await check_rebalancing_alerts(mock_db)

    mock_email.assert_called_once()
    mock_db.commit.assert_called_once()


# ── _select_items_to_show (extra_trigger) ────────────────────


class TestSelectItemsToShowExtraTrigger:
    def test_drift_only_no_drift_no_extra_trigger_returns_none(self):
        from app.services.rebalancing.alert_check import _select_items_to_show

        assert _select_items_to_show("DRIFT_ONLY", False, [], ["a", "b"]) is None

    def test_drift_only_no_drift_with_extra_trigger_sends_all_items(self):
        from app.services.rebalancing.alert_check import _select_items_to_show

        result = _select_items_to_show("DRIFT_ONLY", False, [], ["a", "b"], extra_trigger=True)
        assert result == (["a", "b"], False, True)

    def test_drift_only_with_drift_ignores_extra_trigger_flag(self):
        """drift가 있으면 extra_trigger 값과 무관하게 기존처럼 drift 항목만 표시(is_composite_triggered=False)."""
        from app.services.rebalancing.alert_check import _select_items_to_show

        result = _select_items_to_show("DRIFT_ONLY", False, ["drift_item"], ["a", "b"], extra_trigger=True)
        assert result == (["drift_item"], False, False)

    def test_both_non_schedule_no_drift_with_extra_trigger_sends(self):
        from app.services.rebalancing.alert_check import _select_items_to_show

        result = _select_items_to_show("BOTH", False, [], ["a", "b"], extra_trigger=True)
        assert result == (["a", "b"], False, True)

    def test_both_non_schedule_no_drift_no_extra_trigger_returns_none(self):
        from app.services.rebalancing.alert_check import _select_items_to_show

        assert _select_items_to_show("BOTH", False, [], ["a", "b"], extra_trigger=False) is None

    def test_schedule_only_ignores_extra_trigger(self):
        """SCHEDULE_ONLY는 스케줄일 여부만으로 결정 — extra_trigger는 관여하지 않는다."""
        from app.services.rebalancing.alert_check import _select_items_to_show

        assert _select_items_to_show("SCHEDULE_ONLY", False, [], ["a"], extra_trigger=True) is None
        result = _select_items_to_show("SCHEDULE_ONLY", True, [], ["a"], extra_trigger=False)
        assert result == (["a"], True, False)


# ── check_rebalancing_alerts 복합 트리거 통합 테스트 ──────────


def _make_no_drift_alert(user_id, portfolio_id):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        schedule_type="DAILY",
        schedule_day_of_week=None,
        schedule_day_of_month=None,
        last_triggered_at=None,
        threshold_pct=5.0,
        trigger_condition="DRIFT_ONLY",
        mode="NOTIFY",
        account_id=None,
        strategy="BUY_ONLY",
        order_type="MARKET",
        notify_time=_current_notify_time(),
    )


def _make_no_drift_item():
    return SimpleNamespace(
        ticker="AAPL",
        market="NASDAQ",
        name="Apple",
        weight_diff_pct=1.0,  # threshold(5.0) 미만 — drift 없음
        diff_krw=10_000,
        shares_to_trade=0.1,
    )


class TestCheckRebalancingAlertsCompositeTrigger:
    @pytest.mark.asyncio
    async def test_composite_trigger_sends_without_drift(self, mock_db):
        """drift는 없지만 리스크/시장 복합 신호가 있으면 추가로 발송된다."""
        user_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        alert = _make_no_drift_alert(user_id, portfolio_id)
        portfolio = SimpleNamespace(
            id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[]
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        analysis = SimpleNamespace(items=[_make_no_drift_item()], ticker_account_map={})
        overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock(return_value=True)) as mock_email,
            patch(
                "app.services.rebalancing.alert_check.fetch_market_and_risk_signal",
                new=AsyncMock(return_value=("GREEN", {"data_available": True, "diversification_score": 20})),
            ),
        ):
            from app.services.rebalancing.alert_check import check_rebalancing_alerts

            await check_rebalancing_alerts(mock_db)

        mock_email.assert_called_once()
        assert mock_email.call_args.kwargs["is_composite_triggered"] is True
        assert "분산도" in mock_email.call_args.kwargs["composite_reason"]
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_drift_no_composite_signal_skips(self, mock_db):
        """drift도 없고 리스크/시장 신호도 정상이면 발송하지 않는다 (기존 동작 유지)."""
        user_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        alert = _make_no_drift_alert(user_id, portfolio_id)
        portfolio = SimpleNamespace(
            id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[]
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        analysis = SimpleNamespace(items=[_make_no_drift_item()], ticker_account_map={})
        overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email,
            patch(
                "app.services.rebalancing.alert_check.fetch_market_and_risk_signal",
                new=AsyncMock(return_value=("GREEN", {"data_available": False})),
            ),
        ):
            from app.services.rebalancing.alert_check import check_rebalancing_alerts

            await check_rebalancing_alerts(mock_db)

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_drift_present_skips_composite_signal_fetch(self, mock_db):
        """drift가 이미 있어 발송이 확정되면 복합신호 조회 자체를 스킵한다 (불필요한 API 호출 절약)."""
        user_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        alert = _make_no_drift_alert(user_id, portfolio_id)
        portfolio = SimpleNamespace(
            id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[]
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        drifting_item = SimpleNamespace(
            ticker="AAPL", market="NASDAQ", name="Apple", weight_diff_pct=15.0, diff_krw=500_000, shares_to_trade=5.0
        )
        analysis = SimpleNamespace(items=[drifting_item], ticker_account_map={})
        overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock(return_value=True)),
            patch("app.services.rebalancing.alert_check.fetch_market_and_risk_signal", new=AsyncMock()) as mock_fetch,
        ):
            from app.services.rebalancing.alert_check import check_rebalancing_alerts

            await check_rebalancing_alerts(mock_db)

        mock_fetch.assert_not_called()

    @pytest.mark.asyncio
    async def test_composite_signal_fetch_failure_does_not_crash_and_skips(self, mock_db):
        """복합신호 조회 실패 시 크래시 없이 발송하지 않는다 (drift 없는 상태에서)."""
        user_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        alert = _make_no_drift_alert(user_id, portfolio_id)
        portfolio = SimpleNamespace(
            id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[]
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        analysis = SimpleNamespace(items=[_make_no_drift_item()], ticker_account_map={})
        overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email,
            patch(
                "app.services.rebalancing.alert_check.fetch_market_and_risk_signal",
                new=AsyncMock(side_effect=RuntimeError("boom")),
            ),
        ):
            from app.services.rebalancing.alert_check import check_rebalancing_alerts

            await check_rebalancing_alerts(mock_db)  # 예외를 던지지 않아야 함

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_composite_trigger_deduped_across_portfolios_same_user(self, mock_db):
        """한 유저의 여러 포트폴리오가 동시에 복합신호만으로 트리거되면, 하루 1건만 발송한다.

        market_level/risk는 포트폴리오와 무관하게 유저 단위로 동일하게 평가되므로,
        두 번째 포트폴리오의 알림은 중복 발송되지 않고 last_triggered_at도 갱신되지 않아야 한다.
        """
        user_id = uuid.uuid4()
        portfolio_id_1 = uuid.uuid4()
        portfolio_id_2 = uuid.uuid4()
        alert1 = _make_no_drift_alert(user_id, portfolio_id_1)
        alert2 = _make_no_drift_alert(user_id, portfolio_id_2)
        portfolio1 = SimpleNamespace(
            id=portfolio_id_1, name="Portfolio One", account_ids=None, base_type="STOCK", items=[]
        )
        portfolio2 = SimpleNamespace(
            id=portfolio_id_2, name="Portfolio Two", account_ids=None, base_type="STOCK", items=[]
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [
            (alert1, portfolio1, "user@example.com", None, None, True),
            (alert2, portfolio2, "user@example.com", None, None, True),
        ]
        mock_db.execute = AsyncMock(return_value=execute_result)

        analysis = SimpleNamespace(items=[_make_no_drift_item()], ticker_account_map={})
        overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

        composite_flag_store: dict[str, bool] = {}

        async def fake_get_cached_json(_redis, key):
            return composite_flag_store.get(key)

        async def fake_set_cached_json(_redis, key, value, ttl):
            composite_flag_store[key] = value

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock(return_value=True)) as mock_email,
            patch(
                "app.services.rebalancing.alert_check.fetch_market_and_risk_signal",
                new=AsyncMock(return_value=("GREEN", {"data_available": True, "diversification_score": 20})),
            ),
            patch("app.services.rebalancing.alert_check.get_cached_json", side_effect=fake_get_cached_json),
            patch("app.services.rebalancing.alert_check.set_cached_json", side_effect=fake_set_cached_json),
        ):
            from app.services.rebalancing.alert_check import check_rebalancing_alerts

            await check_rebalancing_alerts(mock_db)

        mock_email.assert_called_once()
        # 첫 번째 알림만 last_triggered_at이 갱신되고, 두 번째는 dedup으로 스킵된다.
        assert alert1.last_triggered_at is not None
        assert alert2.last_triggered_at is None

    @pytest.mark.asyncio
    async def test_drift_alert_not_deduped_by_composite_flag(self, mock_db):
        """복합신호 dedup 플래그가 이미 세팅되어 있어도, 드리프트 기반 알림은 포트폴리오별로 독립 발송된다."""
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
            trigger_condition="DRIFT_ONLY",
            mode="NOTIFY",
            account_id=None,
            strategy="BUY_ONLY",
            order_type="MARKET",
            notify_time=_current_notify_time(),
        )
        portfolio = SimpleNamespace(
            id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[]
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        drifting_item = SimpleNamespace(
            ticker="AAPL", market="NASDAQ", name="Apple", weight_diff_pct=15.0, diff_krw=500_000, shares_to_trade=5.0
        )
        analysis = SimpleNamespace(items=[drifting_item], ticker_account_map={})
        overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

        # 이미 오늘 이 유저에게 복합신호 알림이 발송된 것처럼 플래그를 세팅해도 drift 알림엔 영향 없어야 함.
        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock(return_value=True)) as mock_email,
            patch("app.services.rebalancing.alert_check.get_cached_json", new=AsyncMock(return_value=True)),
        ):
            from app.services.rebalancing.alert_check import check_rebalancing_alerts

            await check_rebalancing_alerts(mock_db)

        mock_email.assert_called_once()
        assert alert.last_triggered_at is not None

    @pytest.mark.asyncio
    async def test_composite_signal_alerts_disabled_skips_fetch_and_send(self, mock_db):
        """UserSettings.composite_signal_alerts_enabled=False인 유저는 drift가 없으면 복합신호 조회 없이 미발송.

        게이팅은 포트폴리오별 alert 속성이 아니라 유저 단위 설정(쿼리 join 6번째 컬럼)으로 판단한다.
        """
        user_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        alert = _make_no_drift_alert(user_id, portfolio_id)
        portfolio = SimpleNamespace(
            id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[]
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, False)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        analysis = SimpleNamespace(items=[_make_no_drift_item()], ticker_account_map={})
        overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email,
            patch("app.services.rebalancing.alert_check.fetch_market_and_risk_signal", new=AsyncMock()) as mock_fetch,
        ):
            from app.services.rebalancing.alert_check import check_rebalancing_alerts

            await check_rebalancing_alerts(mock_db)

        mock_fetch.assert_not_called()
        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_composite_signal_alerts_enabled_none_falls_back_to_true(self, mock_db):
        """UserSettings 행이 없어(outerjoin NULL) composite_signal_alerts_enabled가 None이면 True로 폴백한다."""
        user_id = uuid.uuid4()
        portfolio_id = uuid.uuid4()
        alert = _make_no_drift_alert(user_id, portfolio_id)
        portfolio = SimpleNamespace(
            id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[]
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, None)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        analysis = SimpleNamespace(items=[_make_no_drift_item()], ticker_account_map={})
        overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock(return_value=True)) as mock_email,
            patch(
                "app.services.rebalancing.alert_check.fetch_market_and_risk_signal",
                new=AsyncMock(return_value=("GREEN", {"data_available": True, "diversification_score": 20})),
            ),
        ):
            from app.services.rebalancing.alert_check import check_rebalancing_alerts

            await check_rebalancing_alerts(mock_db)

        mock_email.assert_called_once()


# ── AUTO 모드 회귀 테스트 (복합 트리거 변경이 AUTO 실행 경로에 영향 없음을 증명) ──


class TestAutoModeUnaffectedByCompositeTrigger:
    @pytest.mark.asyncio
    async def test_auto_mode_daily_report_still_sent_with_drift_regardless_of_composite(self, mock_db):
        """AUTO 모드 알림도 일일 리포트(이메일)는 기존처럼 drift 기준으로 발송되고,
        실제 매매 실행(execute_rebalancing)은 이 daily job에서 전혀 호출되지 않는다."""
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
            trigger_condition="DRIFT_ONLY",
            mode="AUTO",
            account_id=uuid.uuid4(),
            strategy="BUY_ONLY",
            order_type="MARKET",
            notify_time=_current_notify_time(),
            market_condition_mode="DISABLED",
        )
        portfolio = SimpleNamespace(
            id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[]
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        drifting_item = SimpleNamespace(
            ticker="AAPL", market="NASDAQ", name="Apple", weight_diff_pct=15.0, diff_krw=500_000, shares_to_trade=5.0
        )
        analysis = SimpleNamespace(items=[drifting_item], ticker_account_map={})
        overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock(return_value=True)) as mock_email,
            patch("app.services.rebalancing.alert_check.fetch_market_and_risk_signal", new=AsyncMock()) as mock_fetch,
        ):
            from app.services.rebalancing.alert_check import check_rebalancing_alerts

            await check_rebalancing_alerts(mock_db)

        # drift가 있으므로 복합신호 조회는 스킵되고(AUTO도 동일 최적화 경로 적용), 이메일은 기존처럼 발송된다.
        mock_fetch.assert_not_called()
        mock_email.assert_called_once()
        # AUTO는 last_triggered_at을 daily job에서 갱신하지 않는다 (기존 동작 불변).
        assert alert.last_triggered_at is None

    @pytest.mark.asyncio
    async def test_auto_mode_demoted_by_market_signal_gate_carries_reason_in_email_and_history(self, mock_db):
        """AUTO가 시장신호 게이트로 이번만 NOTIFY로 강등되면, 발송되는 드리프트 이메일과
        AlertHistory 메시지에 강등 사유가 함께 담겨야 한다(사유가 서버 로그에만 남던 기존 침묵 방지)."""
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
            trigger_condition="DRIFT_ONLY",
            mode="AUTO",
            account_id=uuid.uuid4(),
            strategy="BUY_ONLY",
            order_type="MARKET",
            notify_time=_current_notify_time(),
            market_condition_mode="CAUTIOUS",
        )
        portfolio = SimpleNamespace(
            id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[]
        )
        execute_result = MagicMock()
        execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
        mock_db.execute = AsyncMock(return_value=execute_result)

        drifting_item = SimpleNamespace(
            ticker="AAPL", market="NASDAQ", name="Apple", weight_diff_pct=15.0, diff_krw=500_000, shares_to_trade=5.0
        )
        analysis = SimpleNamespace(items=[drifting_item], ticker_account_map={})
        overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

        with (
            patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
            patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
            patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock(return_value=True)) as mock_email,
            patch(
                "app.services.market_signal_service.get_market_signal",
                new=AsyncMock(return_value={"composite_level": "RED", "data_freshness": "LIVE"}),
            ),
            patch("app.services.rebalancing.alert_check.save_alert_history", new=AsyncMock()) as mock_history,
        ):
            from app.services.rebalancing.alert_check import check_rebalancing_alerts

            await check_rebalancing_alerts(mock_db)

        mock_email.assert_called_once()
        assert "RED" in mock_email.call_args.kwargs["automation_note"]

        mock_history.assert_called_once()
        history_message = mock_history.call_args.args[3]
        assert "자동실행→알림 전환" in history_message


# ── trigger_condition=BOTH 테스트 ─────────────────────────────


def _current_notify_time() -> str:
    """is_alert_execution_time 게이트를 항상 통과하도록 현재 KST 시각(HH:MM)을 반환."""
    from datetime import timezone

    now = datetime.now(tz=timezone(timedelta(hours=9)))
    return f"{now.hour:02d}:{now.minute:02d}"


def _make_both_alert(user_id, portfolio_id, schedule_type="DAILY"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        schedule_type=schedule_type,
        schedule_day_of_week=None,
        schedule_day_of_month=None,
        last_triggered_at=None,
        threshold_pct=5.0,
        trigger_condition="BOTH",
        mode="NOTIFY",
        account_id=None,
        strategy="BUY_ONLY",
        order_type="MARKET",
        notify_time=_current_notify_time(),
    )


@pytest.mark.asyncio
async def test_check_rebalancing_alerts_both_on_schedule_day_sends_full_report(mock_db):
    """BOTH + 스케줄 날(DAILY) → 드리프트 없어도 전체 리포트 발송."""
    user_id = uuid.uuid4()
    portfolio_id = uuid.uuid4()
    alert = _make_both_alert(user_id, portfolio_id, schedule_type="DAILY")
    portfolio = SimpleNamespace(id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[])
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    item = SimpleNamespace(
        ticker="AAPL",
        market="NASDAQ",
        name="Apple",
        weight_diff_pct=2.0,
        diff_krw=100_000,
        shares_to_trade=1.0,
    )
    analysis = SimpleNamespace(items=[item], ticker_account_map={})
    overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

    with (
        patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
        patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
        patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email,
    ):
        from app.services.rebalancing.alert_check import check_rebalancing_alerts

        await check_rebalancing_alerts(mock_db)

    mock_email.assert_called_once()
    call_kwargs = mock_email.call_args.kwargs
    assert call_kwargs.get("is_scheduled_report") is True
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_check_rebalancing_alerts_both_non_schedule_with_drift(mock_db):
    """BOTH + 비스케줄 날 + 드리프트 → 드리프트 알림 발송."""
    user_id = uuid.uuid4()
    portfolio_id = uuid.uuid4()
    from datetime import timedelta, timezone

    today_weekday = datetime.now(tz=timezone(timedelta(hours=9))).weekday()
    wrong_day = (today_weekday + 1) % 7

    alert = _make_both_alert(user_id, portfolio_id, schedule_type="WEEKLY")
    alert.schedule_day_of_week = wrong_day
    portfolio = SimpleNamespace(id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[])
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    drifting_item = SimpleNamespace(
        ticker="AAPL",
        market="NASDAQ",
        name="Apple",
        weight_diff_pct=15.0,
        diff_krw=500_000,
        shares_to_trade=5.0,
    )
    analysis = SimpleNamespace(items=[drifting_item], ticker_account_map={})
    overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

    with (
        patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
        patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
        patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email,
    ):
        from app.services.rebalancing.alert_check import check_rebalancing_alerts

        await check_rebalancing_alerts(mock_db)

    if today_weekday != wrong_day:
        mock_email.assert_called_once()
        call_kwargs = mock_email.call_args.kwargs
        assert call_kwargs.get("is_scheduled_report") is False


@pytest.mark.asyncio
async def test_check_rebalancing_alerts_both_non_schedule_no_drift_skips(mock_db):
    """BOTH + 비스케줄 날 + 드리프트 없음 → 발송 안 함."""
    user_id = uuid.uuid4()
    portfolio_id = uuid.uuid4()
    from datetime import timedelta, timezone

    today_weekday = datetime.now(tz=timezone(timedelta(hours=9))).weekday()
    wrong_day = (today_weekday + 1) % 7

    alert = _make_both_alert(user_id, portfolio_id, schedule_type="WEEKLY")
    alert.schedule_day_of_week = wrong_day
    portfolio = SimpleNamespace(id=portfolio_id, name="Test Portfolio", account_ids=None, base_type="STOCK", items=[])
    execute_result = MagicMock()
    execute_result.all.return_value = [(alert, portfolio, "user@example.com", None, None, True)]
    mock_db.execute = AsyncMock(return_value=execute_result)

    item = SimpleNamespace(
        ticker="AAPL",
        market="NASDAQ",
        name="Apple",
        weight_diff_pct=2.0,
        diff_krw=100_000,
        shares_to_trade=1.0,
    )
    analysis = SimpleNamespace(items=[item], ticker_account_map={})
    overview = {"total_stock_krw": 10_000_000, "all_positions": [], "total_assets_krw": 10_000_000}

    with (
        patch("app.services.portfolio_service.build_portfolio_overview", new=AsyncMock(return_value=overview)),
        patch("app.services.rebalancing.service.analyze_rebalancing", return_value=analysis),
        patch("app.services.email_service.send_rebalancing_alert", new=AsyncMock()) as mock_email,
    ):
        from app.services.rebalancing.alert_check import check_rebalancing_alerts

        await check_rebalancing_alerts(mock_db)

    if today_weekday != wrong_day:
        mock_email.assert_not_called()


# ── _process_rebalancing_alert 채널 독립성 테스트 ─────────────


def _make_process_alert_args(user_id, portfolio_id):
    """_process_rebalancing_alert 호출에 필요한 공통 인수 생성."""
    alert = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        portfolio_id=portfolio_id,
        schedule_type="DAILY",
        threshold_pct=5.0,
        mode="NOTIFY",
        market_condition_mode="DISABLED",
    )
    portfolio = SimpleNamespace(id=portfolio_id, name="Test Portfolio")
    drifting = []
    items_to_show = []
    return alert, portfolio, drifting, items_to_show


@pytest.mark.asyncio
async def test_process_rebalancing_alert_smtp_not_configured_fcm_succeeds(mock_db):
    """SMTP 미설정 시 이메일은 False 반환 → FCM은 독립 실행되어 성공하면 True 반환."""
    user_id = uuid.uuid4()
    portfolio_id = uuid.uuid4()
    alert, portfolio, drifting, items = _make_process_alert_args(user_id, portfolio_id)

    from app.services.rebalancing.alert_check import _process_rebalancing_alert

    with (
        patch(
            "app.services.email_service.send_rebalancing_alert",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.services.push_service.send_push_to_user",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await _process_rebalancing_alert(
            alert=alert,
            portfolio=portfolio,
            drifting=drifting,
            items_to_show=items,
            is_scheduled_report=True,
            threshold=5.0,
            email="user@example.com",
            composite_level="GREEN",
            db=mock_db,
            fcm_token="fcm-token-xyz",
        )

    assert result is True


@pytest.mark.asyncio
async def test_process_rebalancing_alert_email_fails_fcm_still_runs(mock_db):
    """이메일 전송 예외 발생 시에도 FCM은 독립적으로 실행된다."""
    user_id = uuid.uuid4()
    portfolio_id = uuid.uuid4()
    alert, portfolio, drifting, items = _make_process_alert_args(user_id, portfolio_id)

    from app.services.rebalancing.alert_check import _process_rebalancing_alert

    with (
        patch(
            "app.services.email_service.send_rebalancing_alert",
            new=AsyncMock(side_effect=Exception("SMTP 연결 오류")),
        ),
        patch(
            "app.services.push_service.send_push_to_user",
            new=AsyncMock(return_value=True),
        ) as mock_push,
    ):
        result = await _process_rebalancing_alert(
            alert=alert,
            portfolio=portfolio,
            drifting=drifting,
            items_to_show=items,
            is_scheduled_report=True,
            threshold=5.0,
            email="user@example.com",
            composite_level="GREEN",
            db=mock_db,
            fcm_token="fcm-token-xyz",
        )

    # FCM은 이메일 실패와 무관하게 실행돼야 함
    mock_push.assert_called_once()
    assert result is True


@pytest.mark.asyncio
async def test_process_rebalancing_alert_both_channels_fail_returns_false(mock_db):
    """이메일·FCM 둘 다 실패(False) 시 False 반환."""
    user_id = uuid.uuid4()
    portfolio_id = uuid.uuid4()
    alert, portfolio, drifting, items = _make_process_alert_args(user_id, portfolio_id)

    from app.services.rebalancing.alert_check import _process_rebalancing_alert

    with (
        patch(
            "app.services.email_service.send_rebalancing_alert",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.services.push_service.send_push_to_user",
            new=AsyncMock(return_value=False),
        ),
    ):
        result = await _process_rebalancing_alert(
            alert=alert,
            portfolio=portfolio,
            drifting=drifting,
            items_to_show=items,
            is_scheduled_report=True,
            threshold=5.0,
            email="user@example.com",
            composite_level="GREEN",
            db=mock_db,
            fcm_token=None,
        )

    assert result is False


# ── _execute_auto_rebalancing / _build_sell_orders 테스트 ─────


def _make_auto_alert(**kwargs):
    defaults = {
        "id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "strategy": "FULL",
        "order_type": "MARKET",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_drift_item(ticker="005930", diff_krw=-100000.0, shares_to_trade=-5.0, **kwargs):
    defaults = {
        "ticker": ticker,
        "name": "삼성전자",
        "market": "KOSPI",
        "diff_krw": diff_krw,
        "shares_to_trade": shares_to_trade,
        "current_price_krw": 70000.0,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_ticker_account(account_id, quantity, asset_type="STOCK_KIS", account_name="계좌", tax_type="GENERAL"):
    from app.schemas.rebalancing import TickerAccountInfo

    return TickerAccountInfo(
        account_id=str(account_id),
        account_name=account_name,
        asset_type=asset_type,
        quantity=quantity,
        value_krw=quantity * 70000.0,
        tax_type=tax_type,
    )


class TestBuildSellOrders:
    def test_distributes_across_holding_accounts_largest_first(self):
        from app.services.rebalancing.order_builder import _build_sell_orders

        acc_small = uuid.uuid4()
        acc_large = uuid.uuid4()
        item = _make_drift_item()
        ticker_account_map = {
            "005930": [
                _make_ticker_account(acc_small, quantity=2),
                _make_ticker_account(acc_large, quantity=10),
            ]
        }

        orders = _build_sell_orders(item, 5, ticker_account_map, "MARKET", None)

        assert len(orders) == 1
        assert orders[0].account_id == str(acc_large)
        assert orders[0].quantity == 5

    def test_splits_across_multiple_accounts_when_needed(self):
        from app.services.rebalancing.order_builder import _build_sell_orders

        acc_a = uuid.uuid4()
        acc_b = uuid.uuid4()
        item = _make_drift_item()
        ticker_account_map = {
            "005930": [
                _make_ticker_account(acc_a, quantity=3),
                _make_ticker_account(acc_b, quantity=4),
            ]
        }

        orders = _build_sell_orders(item, 6, ticker_account_map, "MARKET", None)

        assert {o.account_id: o.quantity for o in orders} == {str(acc_b): 4, str(acc_a): 2}

    def test_unallocated_remainder_is_skipped_not_forced(self):
        from app.services.rebalancing.order_builder import _build_sell_orders

        acc = uuid.uuid4()
        item = _make_drift_item()
        ticker_account_map = {"005930": [_make_ticker_account(acc, quantity=2)]}

        orders = _build_sell_orders(item, 10, ticker_account_map, "MARKET", None)

        assert len(orders) == 1
        assert orders[0].quantity == 2

    def test_no_holding_accounts_returns_empty(self):
        from app.services.rebalancing.order_builder import _build_sell_orders

        item = _make_drift_item()
        orders = _build_sell_orders(item, 5, {}, "MARKET", None)

        assert orders == []

    def test_manual_asset_type_account_excluded(self):
        from app.services.rebalancing.order_builder import _build_sell_orders

        acc_manual = uuid.uuid4()
        acc_kis = uuid.uuid4()
        item = _make_drift_item()
        ticker_account_map = {
            "005930": [
                _make_ticker_account(acc_manual, quantity=100, asset_type="STOCK_OTHER"),
                _make_ticker_account(acc_kis, quantity=3, asset_type="STOCK_KIS"),
            ]
        }

        orders = _build_sell_orders(item, 3, ticker_account_map, "MARKET", None)

        assert len(orders) == 1
        assert orders[0].account_id == str(acc_kis)

    def test_tax_deferred_account_sold_last_even_with_larger_quantity(self):
        """ISA/연금 계좌는 보유수량이 더 많아도 일반계좌를 먼저 소진한 뒤에만 매도한다."""
        from app.services.rebalancing.order_builder import _build_sell_orders

        acc_general = uuid.uuid4()
        acc_isa = uuid.uuid4()
        item = _make_drift_item()
        ticker_account_map = {
            "005930": [
                _make_ticker_account(acc_isa, quantity=100, tax_type="ISA"),
                _make_ticker_account(acc_general, quantity=5, tax_type="GENERAL"),
            ]
        }

        orders = _build_sell_orders(item, 5, ticker_account_map, "MARKET", None)

        assert len(orders) == 1
        assert orders[0].account_id == str(acc_general)
        assert orders[0].quantity == 5


class TestBuildRebalancingOrders:
    """공용 build_rebalancing_orders() — AUTO 실행과 quick-execute가 공유하는 주문 생성 로직."""

    def test_sell_distributed_and_buy_uses_given_account(self):
        from app.services.rebalancing.order_builder import build_rebalancing_orders

        buy_account = uuid.uuid4()
        holder_account = uuid.uuid4()
        drifting = [
            _make_drift_item(ticker="005930", diff_krw=-100000.0, shares_to_trade=-5.0),
            _make_drift_item(ticker="000660", diff_krw=100000.0, shares_to_trade=3.0, current_price_krw=50000.0),
        ]
        ticker_account_map = {"005930": [_make_ticker_account(holder_account, quantity=10)]}

        orders = build_rebalancing_orders(drifting, ticker_account_map, "FULL", "MARKET", str(buy_account))

        sell = next(o for o in orders if o.side == "SELL")
        buy = next(o for o in orders if o.side == "BUY")
        assert sell.account_id == str(holder_account)
        assert sell.quantity == 5
        assert buy.account_id == str(buy_account)
        assert buy.quantity == 3

    def test_buy_only_strategy_skips_sell(self):
        from app.services.rebalancing.order_builder import build_rebalancing_orders

        buy_account = uuid.uuid4()
        drifting = [_make_drift_item(ticker="005930", diff_krw=-100000.0, shares_to_trade=-5.0)]
        ticker_account_map = {"005930": [_make_ticker_account(uuid.uuid4(), quantity=10)]}

        orders = build_rebalancing_orders(drifting, ticker_account_map, "BUY_ONLY", "MARKET", str(buy_account))

        assert orders == []

    def test_missing_shares_to_trade_skipped(self):
        from app.services.rebalancing.order_builder import build_rebalancing_orders

        drifting = [_make_drift_item(shares_to_trade=None)]
        orders = build_rebalancing_orders(drifting, {}, "FULL", "MARKET", str(uuid.uuid4()))
        assert orders == []

    def test_limit_order_uses_current_price_as_limit_price(self):
        from app.services.rebalancing.order_builder import build_rebalancing_orders

        buy_account = uuid.uuid4()
        drifting = [
            _make_drift_item(ticker="000660", diff_krw=100000.0, shares_to_trade=3.0, current_price_krw=50000.0)
        ]

        orders = build_rebalancing_orders(drifting, {}, "FULL", "LIMIT", str(buy_account))

        assert orders[0].order_type == "LIMIT"
        assert orders[0].limit_price == 50000.0
        assert orders[0].reference_price == 50000.0

    def test_market_order_still_carries_reference_price(self):
        from app.services.rebalancing.order_builder import build_rebalancing_orders

        buy_account = uuid.uuid4()
        drifting = [
            _make_drift_item(ticker="000660", diff_krw=100000.0, shares_to_trade=3.0, current_price_krw=50000.0)
        ]

        orders = build_rebalancing_orders(drifting, {}, "FULL", "MARKET", str(buy_account))

        assert orders[0].order_type == "MARKET"
        assert orders[0].limit_price is None
        assert orders[0].reference_price == 50000.0

    def test_overseas_buy_into_tax_deferred_account_skipped(self):
        """ISA/연금저축/IRP 계좌로는 해외 개별 종목 매수 주문을 생성하지 않는다(실행 불가능한 주문 방지)."""
        from app.services.rebalancing.order_builder import build_rebalancing_orders

        buy_account = uuid.uuid4()
        drifting = [
            _make_drift_item(
                ticker="AAPL", market="NASDAQ", diff_krw=100000.0, shares_to_trade=3.0, current_price_krw=50000.0
            )
        ]
        # buy_account가 ISA 계좌라는 사실은 ticker_account_map에 등장하는 다른 보유 종목을 통해 알 수 있다.
        ticker_account_map = {"005930": [_make_ticker_account(buy_account, quantity=1, tax_type="ISA")]}

        orders = build_rebalancing_orders(drifting, ticker_account_map, "FULL", "MARKET", str(buy_account))

        assert orders == []

    def test_domestic_buy_into_tax_deferred_account_allowed(self):
        from app.services.rebalancing.order_builder import build_rebalancing_orders

        buy_account = uuid.uuid4()
        drifting = [
            _make_drift_item(
                ticker="005930", market="KOSPI", diff_krw=100000.0, shares_to_trade=3.0, current_price_krw=50000.0
            )
        ]
        ticker_account_map = {"005930": [_make_ticker_account(buy_account, quantity=1, tax_type="ISA")]}

        orders = build_rebalancing_orders(drifting, ticker_account_map, "FULL", "MARKET", str(buy_account))

        assert len(orders) == 1
        assert orders[0].side == "BUY"

    def test_sell_orders_carry_reference_price(self):
        from app.services.rebalancing.order_builder import build_rebalancing_orders

        holder_account = uuid.uuid4()
        drifting = [
            _make_drift_item(ticker="005930", diff_krw=-100000.0, shares_to_trade=-5.0, current_price_krw=70000.0)
        ]
        ticker_account_map = {"005930": [_make_ticker_account(holder_account, quantity=10)]}

        orders = build_rebalancing_orders(drifting, ticker_account_map, "FULL", "LIMIT", str(uuid.uuid4()))

        sell = next(o for o in orders if o.side == "SELL")
        assert sell.limit_price == 70000.0
        assert sell.reference_price == 70000.0


class TestClampOrdersToMaxValue:
    """clamp_orders_to_max_value() — AUTO 대기 플랜 생성 시 1건당 거래대금 상한 안전장치."""

    def test_order_under_cap_passes_through_unchanged(self):
        from app.services.rebalancing.order_builder import build_rebalancing_orders, clamp_orders_to_max_value

        buy_account = uuid.uuid4()
        drifting = [
            _make_drift_item(ticker="000660", diff_krw=100000.0, shares_to_trade=3.0, current_price_krw=50000.0)
        ]
        orders = build_rebalancing_orders(drifting, {}, "FULL", "MARKET", str(buy_account))

        clamped = clamp_orders_to_max_value(orders, 50_000_000.0)

        assert len(clamped) == 1
        assert clamped[0].quantity == 3

    def test_order_over_cap_is_clamped_down(self):
        from app.services.rebalancing.order_builder import build_rebalancing_orders, clamp_orders_to_max_value

        buy_account = uuid.uuid4()
        # 100주 × 50,000원 = 5,000,000원 — 한도 1,000,000원이면 최대 20주까지만 허용
        drifting = [
            _make_drift_item(ticker="000660", diff_krw=5_000_000.0, shares_to_trade=100.0, current_price_krw=50000.0)
        ]
        orders = build_rebalancing_orders(drifting, {}, "FULL", "MARKET", str(buy_account))

        clamped = clamp_orders_to_max_value(orders, 1_000_000.0)

        assert len(clamped) == 1
        assert clamped[0].quantity == 20

    def test_order_that_cannot_afford_even_one_share_is_dropped(self):
        from app.services.rebalancing.order_builder import build_rebalancing_orders, clamp_orders_to_max_value

        buy_account = uuid.uuid4()
        drifting = [
            _make_drift_item(ticker="000660", diff_krw=100000.0, shares_to_trade=3.0, current_price_krw=50000.0)
        ]
        orders = build_rebalancing_orders(drifting, {}, "FULL", "MARKET", str(buy_account))

        clamped = clamp_orders_to_max_value(orders, 10_000.0)  # 1주(50,000원)도 못 사는 한도

        assert clamped == []

    def test_order_without_reference_price_passes_through(self):
        """참조가를 알 수 없는 주문은 검증할 수 없으므로 그대로 통과시킨다(기존 동작 유지)."""
        from app.services.rebalancing.order_builder import build_rebalancing_orders, clamp_orders_to_max_value

        buy_account = uuid.uuid4()
        drifting = [_make_drift_item(ticker="000660", diff_krw=100000.0, shares_to_trade=3.0, current_price_krw=None)]
        orders = build_rebalancing_orders(drifting, {}, "FULL", "MARKET", str(buy_account))
        assert orders[0].reference_price is None

        clamped = clamp_orders_to_max_value(orders, 1.0)

        assert len(clamped) == 1
        assert clamped[0].quantity == 3


class TestIsTaxImpactBlockingAutoMode:
    """is_tax_impact_blocking_auto_mode() — market_condition_mode 게이트와 대칭인 세금영향 게이트 순수함수."""

    def test_disabled_mode_never_blocks(self):
        from app.services.rebalancing.order_builder import is_tax_impact_blocking_auto_mode

        assert is_tax_impact_blocking_auto_mode("DISABLED", 10_000_000.0, 100.0) is False

    def test_enabled_but_no_max_never_blocks(self):
        """상한이 설정 안 됐으면(마이그레이션 직후 등) 안전하게 통과시킨다 — '무제한 차단' 오인 방지."""
        from app.services.rebalancing.order_builder import is_tax_impact_blocking_auto_mode

        assert is_tax_impact_blocking_auto_mode("ENABLED", 10_000_000.0, None) is False

    def test_enabled_under_threshold_passes(self):
        from app.services.rebalancing.order_builder import is_tax_impact_blocking_auto_mode

        assert is_tax_impact_blocking_auto_mode("ENABLED", 400_000.0, 500_000.0) is False

    def test_enabled_over_threshold_blocks(self):
        from app.services.rebalancing.order_builder import is_tax_impact_blocking_auto_mode

        assert is_tax_impact_blocking_auto_mode("ENABLED", 600_000.0, 500_000.0) is True

    def test_enabled_exactly_at_threshold_passes(self):
        """상한과 정확히 같으면 초과가 아니므로 통과 — market_condition_mode의 등급 경계와 동일한 관례(초과만 차단)."""
        from app.services.rebalancing.order_builder import is_tax_impact_blocking_auto_mode

        assert is_tax_impact_blocking_auto_mode("ENABLED", 500_000.0, 500_000.0) is False


class TestRefreshLivePrices:
    """refresh_live_prices() — 자동/원클릭 실행이 수동 실행 모달과 동일하게 실시간 시세를 지정가에 반영하는지 검증."""

    @pytest.mark.asyncio
    async def test_updates_current_price_krw_from_live_quote(self, mock_db):
        from app.services.rebalancing.order_builder import refresh_live_prices

        item = _make_drift_item(ticker="005930", current_price_krw=70000.0)

        with patch(
            "app.services.price_service.fetch_prices_batch",
            new=AsyncMock(return_value={"005930": 71500.0}),
        ):
            await refresh_live_prices([item], uuid.uuid4(), mock_db, MagicMock())

        assert item.current_price_krw == 71500.0

    @pytest.mark.asyncio
    async def test_falls_back_to_existing_price_when_quote_missing(self, mock_db):
        from app.services.rebalancing.order_builder import refresh_live_prices

        item = _make_drift_item(ticker="005930", current_price_krw=70000.0)

        with patch(
            "app.services.price_service.fetch_prices_batch",
            new=AsyncMock(return_value={}),
        ):
            await refresh_live_prices([item], uuid.uuid4(), mock_db, MagicMock())

        assert item.current_price_krw == 70000.0

    @pytest.mark.asyncio
    async def test_falls_back_to_existing_price_when_fetch_raises(self, mock_db):
        from app.services.rebalancing.order_builder import refresh_live_prices

        item = _make_drift_item(ticker="005930", current_price_krw=70000.0)

        with patch(
            "app.services.price_service.fetch_prices_batch",
            new=AsyncMock(side_effect=RuntimeError("network error")),
        ):
            await refresh_live_prices([item], uuid.uuid4(), mock_db, MagicMock())

        assert item.current_price_krw == 70000.0

    @pytest.mark.asyncio
    async def test_skips_cash_and_real_estate_tickers(self, mock_db):
        from app.services.rebalancing.order_builder import refresh_live_prices

        cash_item = _make_drift_item(ticker="CASH", current_price_krw=None)
        stock_item = _make_drift_item(ticker="005930", current_price_krw=70000.0)

        fetch_mock = AsyncMock(return_value={"005930": 71500.0})
        with patch("app.services.price_service.fetch_prices_batch", new=fetch_mock):
            await refresh_live_prices([cash_item, stock_item], uuid.uuid4(), mock_db, MagicMock())

        called_tickers = fetch_mock.call_args.args[1]
        assert called_tickers == [("005930", "KOSPI")]
        assert cash_item.current_price_krw is None

    @pytest.mark.asyncio
    async def test_recomputes_shares_to_trade_when_none_and_live_price_found(self, mock_db):
        """분석 시점엔 가격이 없어 shares_to_trade=None이었던 종목도, 실시간 가격을 새로
        확보하면 수량을 재계산해야 한다 — 그러지 않으면 build_rebalancing_orders()가
        이 항목을 영구히 스킵해 실제 드리프트가 조용히 누락된다."""
        from app.services.rebalancing.order_builder import refresh_live_prices

        item = _make_drift_item(
            ticker="367380",
            shares_to_trade=None,
            current_price_krw=None,
            target_value_krw=1_000_000.0,
            current_qty=0.0,
        )

        with patch(
            "app.services.price_service.fetch_prices_batch",
            new=AsyncMock(return_value={"367380": 50000.0}),
        ):
            await refresh_live_prices([item], uuid.uuid4(), mock_db, MagicMock())

        assert item.current_price_krw == 50000.0
        assert item.shares_to_trade == 20  # floor(1,000,000 / 50,000) - 0

    @pytest.mark.asyncio
    async def test_recomputed_shares_to_trade_subtracts_current_qty(self, mock_db):
        from app.services.rebalancing.order_builder import refresh_live_prices

        item = _make_drift_item(
            ticker="367380",
            shares_to_trade=None,
            current_price_krw=None,
            target_value_krw=1_000_000.0,
            current_qty=5.0,
        )

        with patch(
            "app.services.price_service.fetch_prices_batch",
            new=AsyncMock(return_value={"367380": 50000.0}),
        ):
            await refresh_live_prices([item], uuid.uuid4(), mock_db, MagicMock())

        assert item.shares_to_trade == 15  # floor(1,000,000 / 50,000) - 5

    @pytest.mark.asyncio
    async def test_shares_to_trade_stays_none_when_price_still_unavailable(self, mock_db):
        from app.services.rebalancing.order_builder import refresh_live_prices

        item = _make_drift_item(
            ticker="367380",
            shares_to_trade=None,
            current_price_krw=None,
            target_value_krw=1_000_000.0,
            current_qty=0.0,
        )

        with patch(
            "app.services.price_service.fetch_prices_batch",
            new=AsyncMock(return_value={}),
        ):
            await refresh_live_prices([item], uuid.uuid4(), mock_db, MagicMock())

        assert item.shares_to_trade is None

    @pytest.mark.asyncio
    async def test_does_not_touch_already_computed_shares_to_trade(self, mock_db):
        """이미 shares_to_trade가 계산돼 있던 항목은 실시간 가격 갱신 후에도 재계산하지 않는다
        (기존 동작 회귀 방지 — 재계산 범위는 '분석 시점에 None이었던 경우'로 한정)."""
        from app.services.rebalancing.order_builder import refresh_live_prices

        item = _make_drift_item(
            ticker="005930",
            shares_to_trade=-5.0,
            current_price_krw=70000.0,
            target_value_krw=1_000_000.0,
            current_qty=10.0,
        )

        with patch(
            "app.services.price_service.fetch_prices_batch",
            new=AsyncMock(return_value={"005930": 71500.0}),
        ):
            await refresh_live_prices([item], uuid.uuid4(), mock_db, MagicMock())

        assert item.shares_to_trade == -5.0


# ── resolve_effective_account_ids ─────────────────────────────


class TestResolveEffectiveAccountIds:
    def test_aggregate_scope_uses_portfolio_account_ids(self):
        from app.services.rebalancing.alert_scope import resolve_effective_account_ids

        acc1, acc2 = uuid.uuid4(), uuid.uuid4()
        portfolio = SimpleNamespace(alert_scope="AGGREGATE", account_ids=[str(acc1), str(acc2)])
        alert = SimpleNamespace(account_id=uuid.uuid4())

        result = resolve_effective_account_ids(alert, portfolio)

        assert result == [acc1, acc2]

    def test_aggregate_scope_with_no_linked_accounts_returns_none(self):
        """AGGREGATE + account_ids=None(전체 계좌)은 alert.account_id(AUTO 실행계좌)가 있어도 전체로 취급."""
        from app.services.rebalancing.alert_scope import resolve_effective_account_ids

        portfolio = SimpleNamespace(alert_scope="AGGREGATE", account_ids=None)
        alert = SimpleNamespace(account_id=uuid.uuid4())

        result = resolve_effective_account_ids(alert, portfolio)

        assert result is None

    def test_per_account_scope_returns_single_target_account(self):
        from app.services.rebalancing.alert_scope import resolve_effective_account_ids

        target_acc = uuid.uuid4()
        other_acc = uuid.uuid4()
        portfolio = SimpleNamespace(alert_scope="PER_ACCOUNT", account_ids=[str(target_acc), str(other_acc)])
        alert = SimpleNamespace(account_id=target_acc)

        result = resolve_effective_account_ids(alert, portfolio)

        assert result == [target_acc]

    def test_missing_alert_scope_attribute_defaults_to_aggregate(self):
        """alert_scope 컬럼이 없는 낡은 테스트 더블/객체도 AGGREGATE로 안전하게 폴백해야 한다."""
        from app.services.rebalancing.alert_scope import resolve_effective_account_ids

        portfolio = SimpleNamespace(account_ids=None)  # alert_scope 속성 자체가 없음
        alert = SimpleNamespace(account_id=uuid.uuid4())

        result = resolve_effective_account_ids(alert, portfolio)

        assert result is None


# ── switch_alert_scope ─────────────────────────────────────────


def _make_linked_portfolio(alert_scope: str, linked_account_ids: list) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        alert_scope=alert_scope,
        linked_accounts=[SimpleNamespace(account_id=aid) for aid in linked_account_ids],
    )


class TestSwitchAlertScope:
    @pytest.mark.asyncio
    async def test_rejects_unknown_scope(self, mock_db):
        from fastapi import HTTPException

        from app.services.rebalancing.alert_scope import switch_alert_scope

        portfolio = _make_linked_portfolio("AGGREGATE", [uuid.uuid4(), uuid.uuid4()])

        with pytest.raises(HTTPException) as exc:
            await switch_alert_scope(mock_db, portfolio, "BOGUS")
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_noop_when_target_equals_current_scope(self, mock_db):
        from app.services.rebalancing.alert_scope import switch_alert_scope

        portfolio = _make_linked_portfolio("AGGREGATE", [uuid.uuid4(), uuid.uuid4()])

        await switch_alert_scope(mock_db, portfolio, "AGGREGATE")

        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_to_per_account_rejects_fewer_than_two_linked_accounts(self, mock_db):
        from fastapi import HTTPException

        from app.services.rebalancing.alert_scope import switch_alert_scope

        portfolio = _make_linked_portfolio("AGGREGATE", [uuid.uuid4()])

        with pytest.raises(HTTPException) as exc:
            await switch_alert_scope(mock_db, portfolio, "PER_ACCOUNT")
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_to_per_account_with_no_existing_alert_just_flips_scope(self, mock_db):
        from app.services.rebalancing.alert_scope import switch_alert_scope

        portfolio = _make_linked_portfolio("AGGREGATE", [uuid.uuid4(), uuid.uuid4()])
        mock_db.scalar = AsyncMock(return_value=None)

        await switch_alert_scope(mock_db, portfolio, "PER_ACCOUNT")

        assert portfolio.alert_scope == "PER_ACCOUNT"
        mock_db.delete.assert_not_called()
        mock_db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_to_per_account_converts_existing_auto_alert_in_place(self, mock_db):
        """기존 AGGREGATE AUTO 행의 account_id가 연결 계좌 소속이면 삭제하지 않고 그대로 승계한다."""
        from app.services.rebalancing.alert_scope import switch_alert_scope

        acc1, acc2 = uuid.uuid4(), uuid.uuid4()
        portfolio = _make_linked_portfolio("AGGREGATE", [acc1, acc2])
        existing_alert = SimpleNamespace(account_id=acc1, alert_scope="AGGREGATE")
        mock_db.scalar = AsyncMock(return_value=existing_alert)

        await switch_alert_scope(mock_db, portfolio, "PER_ACCOUNT")

        mock_db.delete.assert_not_called()
        assert portfolio.alert_scope == "PER_ACCOUNT"
        # 회귀 테스트: 승계된 행의 alert_scope 컬럼도 갱신되어야 get_alert_by_portfolio_and_account로
        # 다시 조회 가능해진다 (컬럼을 안 바꾸면 AGGREGATE로 남아 이후 PER_ACCOUNT 조회에서 못 찾음).
        assert existing_alert.alert_scope == "PER_ACCOUNT"

    @pytest.mark.asyncio
    async def test_to_per_account_deletes_existing_notify_alert(self, mock_db):
        """기존 AGGREGATE 행이 NOTIFY라 account_id가 없으면(연결 계좌 밖 포함) 삭제한다."""
        from app.services.rebalancing.alert_scope import switch_alert_scope

        portfolio = _make_linked_portfolio("AGGREGATE", [uuid.uuid4(), uuid.uuid4()])
        existing_alert = SimpleNamespace(account_id=None)
        mock_db.scalar = AsyncMock(return_value=existing_alert)

        await switch_alert_scope(mock_db, portfolio, "PER_ACCOUNT")

        mock_db.delete.assert_awaited_once_with(existing_alert)
        assert portfolio.alert_scope == "PER_ACCOUNT"

    @pytest.mark.asyncio
    async def test_to_aggregate_deletes_all_per_account_rows(self, mock_db):
        from app.services.rebalancing.alert_scope import switch_alert_scope

        portfolio = _make_linked_portfolio("PER_ACCOUNT", [uuid.uuid4(), uuid.uuid4()])
        row1, row2 = SimpleNamespace(id=uuid.uuid4()), SimpleNamespace(id=uuid.uuid4())
        exec_result = MagicMock()
        exec_result.scalars.return_value.all.return_value = [row1, row2]
        mock_db.execute = AsyncMock(return_value=exec_result)

        await switch_alert_scope(mock_db, portfolio, "AGGREGATE")

        assert mock_db.delete.await_count == 2
        assert portfolio.alert_scope == "AGGREGATE"
        mock_db.commit.assert_awaited_once()
