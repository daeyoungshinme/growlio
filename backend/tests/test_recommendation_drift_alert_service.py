"""recommendation_drift_alert_service.py 테스트 — 추천 비중 변화 자동 알림(Phase B)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.rebalancing import (
    GoalRecommendation,
    GoalRecommendationItem,
    HorizonGoalRecommendation,
    HorizonRecommendationResponse,
)
from app.services.alerts.recommendation_drift_alert_service import (
    _already_sent_this_week,
    _find_drifted_portfolios,
    _get_subscribers,
    _is_full_target,
    send_recommendation_drift_alerts,
)

_MODULE = "app.services.alerts.recommendation_drift_alert_service"


def _account(account_id: uuid.UUID, target_portfolio_id: uuid.UUID | None) -> SimpleNamespace:
    return SimpleNamespace(id=account_id, target_portfolio_id=target_portfolio_id)


def _portfolio(
    portfolio_id: uuid.UUID,
    name: str,
    items: list[tuple[str, str, float]],
    account_ids: list[str] | None = None,
    investment_horizon: str | None = None,
    tax_type: str | None = None,
) -> SimpleNamespace:
    portfolio_items = [SimpleNamespace(ticker=t, market=m, weight=w) for t, m, w in items]
    return SimpleNamespace(
        id=portfolio_id,
        name=name,
        items=portfolio_items,
        account_ids=account_ids,
        investment_horizon=investment_horizon,
        tax_type=tax_type,
    )


class TestIsFullTarget:
    def test_true_when_all_relevant_accounts_target_this_portfolio(self):
        pid = uuid.uuid4()
        acc1, acc2 = uuid.uuid4(), uuid.uuid4()
        portfolio = _portfolio(pid, "포트폴리오1", [], account_ids=[str(acc1), str(acc2)])
        stock_accounts = [_account(acc1, pid), _account(acc2, pid)]

        assert _is_full_target(portfolio, stock_accounts) is True

    def test_false_when_only_partial(self):
        pid = uuid.uuid4()
        acc1, acc2 = uuid.uuid4(), uuid.uuid4()
        portfolio = _portfolio(pid, "포트폴리오1", [], account_ids=[str(acc1), str(acc2)])
        stock_accounts = [_account(acc1, pid), _account(acc2, uuid.uuid4())]

        assert _is_full_target(portfolio, stock_accounts) is False

    def test_false_when_no_relevant_accounts(self):
        pid = uuid.uuid4()
        portfolio = _portfolio(pid, "포트폴리오1", [], account_ids=[str(uuid.uuid4())])
        stock_accounts = [_account(uuid.uuid4(), pid)]  # 연결되지 않은 계좌뿐

        assert _is_full_target(portfolio, stock_accounts) is False

    def test_falls_back_to_all_stock_accounts_when_unlinked(self):
        """account_ids가 없으면(전체 자산 기준 포트폴리오) 전체 주식 계좌를 대상으로 판정한다."""
        pid = uuid.uuid4()
        acc1 = uuid.uuid4()
        portfolio = _portfolio(pid, "포트폴리오1", [], account_ids=None)
        stock_accounts = [_account(acc1, pid)]

        assert _is_full_target(portfolio, stock_accounts) is True


class TestGetSubscribers:
    @pytest.mark.asyncio
    async def test_returns_subscribed_active_users(self, mock_db):
        user = SimpleNamespace(id=uuid.uuid4(), is_active=True)
        settings_row = SimpleNamespace(recommendation_drift_alert_enabled=True)
        result_mock = MagicMock()
        result_mock.all.return_value = [(user, settings_row)]
        mock_db.execute = AsyncMock(return_value=result_mock)

        subscribers = await _get_subscribers(mock_db)

        assert subscribers == [(user, settings_row)]


class TestAlreadySentThisWeek:
    @pytest.mark.asyncio
    async def test_returns_false_when_no_history(self, mock_db):
        result_mock = MagicMock()
        result_mock.scalar.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        assert await _already_sent_this_week(mock_db, uuid.uuid4()) is False

    @pytest.mark.asyncio
    async def test_returns_true_when_history_exists(self, mock_db):
        result_mock = MagicMock()
        result_mock.scalar.return_value = uuid.uuid4()
        mock_db.execute = AsyncMock(return_value=result_mock)

        assert await _already_sent_this_week(mock_db, uuid.uuid4()) is True


class TestFindDriftedPortfolios:
    @pytest.mark.asyncio
    async def test_no_linked_portfolios_returns_empty(self, mock_db):
        with patch(f"{_MODULE}.get_linked_portfolios", AsyncMock(return_value=[])):
            result = await _find_drifted_portfolios(uuid.uuid4(), mock_db, None, SimpleNamespace())

        assert result == []

    @pytest.mark.asyncio
    async def test_overall_drift_significant_includes_target_portfolio(self, mock_db):
        pid = uuid.uuid4()
        acc_id = uuid.uuid4()
        # 현재 목표 비중(SPY 50%) vs 추천 비중(SPY 80%) — 30%p 차이로 임계값(3%p) 초과
        portfolio = _portfolio(pid, "전체목표포트폴리오", [("SPY", "NYSE", 50.0)], account_ids=[str(acc_id)])
        stock_accounts_result = MagicMock()
        stock_accounts_result.scalars.return_value.all.return_value = [_account(acc_id, pid)]
        mock_db.execute = AsyncMock(return_value=stock_accounts_result)

        overall_rec = GoalRecommendation(
            generated_at="2026-01-01T00:00:00Z",
            is_configured=True,
            recommended_items=[GoalRecommendationItem(ticker="SPY", name="SPDR S&P 500", market="NYSE", weight=80.0)],
        )
        empty_horizon = HorizonRecommendationResponse(generated_at="2026-01-01T00:00:00Z", recommendations=[])

        with (
            patch(f"{_MODULE}.get_linked_portfolios", AsyncMock(return_value=[portfolio])),
            patch(f"{_MODULE}.build_portfolio_overview", AsyncMock(return_value={"total_assets_krw": 1_000_000.0})),
            patch(f"{_MODULE}.query_latest_position_map", AsyncMock(return_value={})),
            patch(f"{_MODULE}.existing_items_from_positions", return_value=[]),
            patch(f"{_MODULE}.get_goal_recommendation", AsyncMock(return_value=overall_rec)),
            patch(f"{_MODULE}.get_horizon_recommendations", AsyncMock(return_value=empty_horizon)),
        ):
            result = await _find_drifted_portfolios(uuid.uuid4(), mock_db, None, SimpleNamespace())

        assert result == ["전체목표포트폴리오"]

    @pytest.mark.asyncio
    async def test_overall_drift_insignificant_excluded(self, mock_db):
        pid = uuid.uuid4()
        acc_id = uuid.uuid4()
        # 현재 79% vs 추천 80% — 1%p 차이로 임계값(3%p) 미만
        portfolio = _portfolio(pid, "전체목표포트폴리오", [("SPY", "NYSE", 79.0)], account_ids=[str(acc_id)])
        stock_accounts_result = MagicMock()
        stock_accounts_result.scalars.return_value.all.return_value = [_account(acc_id, pid)]
        mock_db.execute = AsyncMock(return_value=stock_accounts_result)

        overall_rec = GoalRecommendation(
            generated_at="2026-01-01T00:00:00Z",
            is_configured=True,
            recommended_items=[GoalRecommendationItem(ticker="SPY", name="SPDR S&P 500", market="NYSE", weight=80.0)],
        )
        empty_horizon = HorizonRecommendationResponse(generated_at="2026-01-01T00:00:00Z", recommendations=[])

        with (
            patch(f"{_MODULE}.get_linked_portfolios", AsyncMock(return_value=[portfolio])),
            patch(f"{_MODULE}.build_portfolio_overview", AsyncMock(return_value={"total_assets_krw": 1_000_000.0})),
            patch(f"{_MODULE}.query_latest_position_map", AsyncMock(return_value={})),
            patch(f"{_MODULE}.existing_items_from_positions", return_value=[]),
            patch(f"{_MODULE}.get_goal_recommendation", AsyncMock(return_value=overall_rec)),
            patch(f"{_MODULE}.get_horizon_recommendations", AsyncMock(return_value=empty_horizon)),
        ):
            result = await _find_drifted_portfolios(uuid.uuid4(), mock_db, None, SimpleNamespace())

        assert result == []

    @pytest.mark.asyncio
    async def test_horizon_drift_significant_includes_matching_portfolio(self, mock_db):
        pid = uuid.uuid4()
        portfolio = _portfolio(
            pid,
            "단기일반포트폴리오",
            [("SPY", "NYSE", 50.0)],
            account_ids=None,
            investment_horizon="SHORT_TERM",
            tax_type="GENERAL",
        )
        stock_accounts_result = MagicMock()
        stock_accounts_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=stock_accounts_result)

        overall_rec = GoalRecommendation(generated_at="2026-01-01T00:00:00Z", is_configured=False)
        horizon_rec = HorizonRecommendationResponse(
            generated_at="2026-01-01T00:00:00Z",
            recommendations=[
                HorizonGoalRecommendation(
                    investment_horizon="SHORT_TERM",
                    tax_type="GENERAL",
                    base_krw=1_000_000.0,
                    account_count=1,
                    recommended_items=[
                        GoalRecommendationItem(ticker="SPY", name="SPDR S&P 500", market="NYSE", weight=90.0)
                    ],
                    risk_tolerance="CONSERVATIVE",
                    max_weight_pct=40.0,
                    includes_cash_equivalent=False,
                )
            ],
        )

        with (
            patch(f"{_MODULE}.get_linked_portfolios", AsyncMock(return_value=[portfolio])),
            patch(f"{_MODULE}.build_portfolio_overview", AsyncMock(return_value={"total_assets_krw": 1_000_000.0})),
            patch(f"{_MODULE}.query_latest_position_map", AsyncMock(return_value={})),
            patch(f"{_MODULE}.existing_items_from_positions", return_value=[]),
            patch(f"{_MODULE}.get_goal_recommendation", AsyncMock(return_value=overall_rec)),
            patch(f"{_MODULE}.get_horizon_recommendations", AsyncMock(return_value=horizon_rec)),
        ):
            result = await _find_drifted_portfolios(uuid.uuid4(), mock_db, None, SimpleNamespace())

        assert result == ["단기일반포트폴리오"]

    @pytest.mark.asyncio
    async def test_horizon_cash_equivalent_only_skipped(self, mock_db):
        """현금성 자산 합성 후보만 있는 기간별 추천은 실제 매수 대상이 없으므로 건너뛴다."""
        pid = uuid.uuid4()
        portfolio = _portfolio(
            pid,
            "단기일반포트폴리오",
            [],
            account_ids=None,
            investment_horizon="SHORT_TERM",
            tax_type="GENERAL",
        )
        stock_accounts_result = MagicMock()
        stock_accounts_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=stock_accounts_result)

        overall_rec = GoalRecommendation(generated_at="2026-01-01T00:00:00Z", is_configured=False)
        horizon_rec = HorizonRecommendationResponse(
            generated_at="2026-01-01T00:00:00Z",
            recommendations=[
                HorizonGoalRecommendation(
                    investment_horizon="SHORT_TERM",
                    tax_type="GENERAL",
                    base_krw=1_000_000.0,
                    account_count=1,
                    recommended_items=[
                        GoalRecommendationItem(
                            ticker="CASH_EQUIVALENT", name="현금성 자산", market="CASH", weight=100.0
                        )
                    ],
                    risk_tolerance="CONSERVATIVE",
                    max_weight_pct=40.0,
                    includes_cash_equivalent=True,
                )
            ],
        )

        with (
            patch(f"{_MODULE}.get_linked_portfolios", AsyncMock(return_value=[portfolio])),
            patch(f"{_MODULE}.build_portfolio_overview", AsyncMock(return_value={"total_assets_krw": 1_000_000.0})),
            patch(f"{_MODULE}.query_latest_position_map", AsyncMock(return_value={})),
            patch(f"{_MODULE}.existing_items_from_positions", return_value=[]),
            patch(f"{_MODULE}.get_goal_recommendation", AsyncMock(return_value=overall_rec)),
            patch(f"{_MODULE}.get_horizon_recommendations", AsyncMock(return_value=horizon_rec)),
        ):
            result = await _find_drifted_portfolios(uuid.uuid4(), mock_db, None, SimpleNamespace())

        assert result == []


class TestSendRecommendationDriftAlerts:
    @pytest.mark.asyncio
    async def test_no_subscribers_sends_nothing(self, mock_db):
        execute_result = MagicMock()
        execute_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=execute_result)

        with patch("app.services.email_service.send_recommendation_drift_alert_email", new=AsyncMock()) as mock_email:
            await send_recommendation_drift_alerts(mock_db)

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_no_drifted_portfolios(self, mock_db):
        user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", is_active=True)
        user_settings = SimpleNamespace(notification_email=None, fcm_token=None)

        subscribers_result = MagicMock()
        subscribers_result.all.return_value = [(user, user_settings)]
        mock_db.execute = AsyncMock(return_value=subscribers_result)

        history_result = MagicMock()
        history_result.scalar.return_value = None
        per_user_session = AsyncMock()
        per_user_session.execute = AsyncMock(return_value=history_result)
        per_user_session.__aenter__ = AsyncMock(return_value=per_user_session)
        per_user_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(f"{_MODULE}.AsyncSessionLocal", return_value=per_user_session),
            patch("app.core.cache_store.get_cache_store", AsyncMock(return_value=None)),
            patch(f"{_MODULE}._find_drifted_portfolios", AsyncMock(return_value=[])),
            patch("app.services.email_service.send_recommendation_drift_alert_email", new=AsyncMock()) as mock_email,
        ):
            await send_recommendation_drift_alerts(mock_db)

        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_email_and_push_and_saves_history(self, mock_db):
        user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", is_active=True)
        user_settings = SimpleNamespace(notification_email=None, fcm_token="token-abc")

        subscribers_result = MagicMock()
        subscribers_result.all.return_value = [(user, user_settings)]
        mock_db.execute = AsyncMock(return_value=subscribers_result)

        history_result = MagicMock()
        history_result.scalar.return_value = None
        per_user_session = AsyncMock()
        per_user_session.execute = AsyncMock(return_value=history_result)
        per_user_session.add = MagicMock()
        per_user_session.commit = AsyncMock()
        per_user_session.__aenter__ = AsyncMock(return_value=per_user_session)
        per_user_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(f"{_MODULE}.AsyncSessionLocal", return_value=per_user_session),
            patch("app.core.cache_store.get_cache_store", AsyncMock(return_value=None)),
            patch(f"{_MODULE}._find_drifted_portfolios", AsyncMock(return_value=["내포트폴리오"])),
            patch(
                "app.services.email_service.send_recommendation_drift_alert_email",
                new=AsyncMock(return_value=True),
            ) as mock_email,
            patch(
                "app.services.push_service.send_push_to_user",
                new=AsyncMock(return_value=True),
            ) as mock_push,
        ):
            await send_recommendation_drift_alerts(mock_db)

        mock_email.assert_called_once_with("user@example.com", ["내포트폴리오"])
        mock_push.assert_called_once()
        push_kwargs = mock_push.call_args.kwargs
        assert push_kwargs["fcm_token"] == "token-abc"
        assert push_kwargs["data"] == {"type": "RECOMMENDATION_DRIFT"}
        per_user_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_skips_user_already_notified_this_week(self, mock_db):
        user = SimpleNamespace(id=uuid.uuid4(), email="user@example.com", is_active=True)
        user_settings = SimpleNamespace(notification_email=None, fcm_token=None)

        subscribers_result = MagicMock()
        subscribers_result.all.return_value = [(user, user_settings)]
        mock_db.execute = AsyncMock(return_value=subscribers_result)

        history_result = MagicMock()
        history_result.scalar.return_value = uuid.uuid4()  # 이미 발송됨
        per_user_session = AsyncMock()
        per_user_session.execute = AsyncMock(return_value=history_result)
        per_user_session.__aenter__ = AsyncMock(return_value=per_user_session)
        per_user_session.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(f"{_MODULE}.AsyncSessionLocal", return_value=per_user_session),
            patch("app.services.email_service.send_recommendation_drift_alert_email", new=AsyncMock()) as mock_email,
        ):
            await send_recommendation_drift_alerts(mock_db)

        mock_email.assert_not_called()
