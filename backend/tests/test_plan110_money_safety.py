"""계획 110 배치 A — 환율 캐시 오염, 체결 후 재주문, 시장가 현금 초과, 동시 저장, 전술 적용 비중."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from app.exceptions import ConflictError, ProviderApiError, ServiceUnavailableError
from app.schemas.rebalancing import ExecutionOrderItem, OrderResult
from app.services.rebalancing import plan_generation as gen
from app.services.rebalancing._kis_order_executor import _execute_buys_within_budget
from app.services.rebalancing._order_quantity_guard import (
    MARKET_BUY_PRICE_BUFFER,
    clamp_buy_orders_to_budget,
    fit_buy_to_budget,
)
from app.services.tactical import tactical_apply
from app.utils import currency


class _Cache:
    def __init__(self, value: str | None = None) -> None:
        self.value = value
        self.writes: list[tuple[int, str]] = []

    async def get(self, _key: str) -> str | None:
        return self.value

    async def setex(self, _key: str, ttl: int, value: str) -> None:
        self.writes.append((ttl, value))
        self.value = value


def _buy(**kwargs) -> ExecutionOrderItem:
    defaults = {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "side": "BUY", "quantity": 10}
    return ExecutionOrderItem(**{**defaults, **kwargs})


class TestUsdRateCachePoisoning:
    """A1 — fallback 1300이 전역 캐시에 들어가면 이후 모든 경로가 실환율로 믿는다."""

    async def test_failed_fetch_on_cold_cache_writes_nothing(self):
        cache = _Cache()
        with patch("app.services.market_data.yahoo_price.fetch_usdkrw", new=AsyncMock(return_value=0.0)):
            rate, is_live = await currency.refresh_usd_krw(cache)

        assert (rate, is_live) == (currency.settings.usd_krw_fallback_rate, False)
        assert cache.writes == []

    async def test_failed_fetch_does_not_extend_old_cache_ttl(self):
        cache = _Cache("1412.5")
        with patch("app.services.market_data.yahoo_price.fetch_usdkrw", new=AsyncMock(return_value=0.0)):
            rate, is_live = await currency.refresh_usd_krw(cache)

        assert (rate, is_live) == (1412.5, True)
        assert cache.writes == []

    async def test_fresh_rate_is_cached(self):
        cache = _Cache()
        with patch("app.services.market_data.yahoo_price.fetch_usdkrw", new=AsyncMock(return_value=1450.0)):
            rate, is_live = await currency.refresh_usd_krw(cache)

        assert (rate, is_live) == (1450.0, True)
        assert [value for _ttl, value in cache.writes] == ["1450.0"]

    async def test_prices_batch_leaves_cache_empty_when_yahoo_is_down(self):
        """호출부까지 — 이 경로가 실제로 1300을 캐시에 썼다."""
        from app.api.v1 import stocks

        cache = _Cache()
        user = SimpleNamespace(id=uuid.uuid4())
        with (
            patch("app.services.market_data.yahoo_price.fetch_usdkrw", new=AsyncMock(return_value=0.0)),
            patch.object(stocks, "_resolve_batch_prices", new=AsyncMock(return_value={"AAPL": 100.0})),
            patch.object(stocks, "get_cached_json", new=AsyncMock(return_value=None)),
            patch.object(stocks, "set_cached_json", new=AsyncMock()) as price_cache,
        ):
            body = SimpleNamespace(items=[SimpleNamespace(ticker="AAPL", market="NASDAQ", account_id=None)])
            result = await stocks.get_stock_prices_batch.__wrapped__(
                request=MagicMock(), body=body, current_user=user, db=AsyncMock(), cache=cache
            )

        assert cache.value is None
        assert result["AAPL"]["usd_rate"] == currency.settings.usd_krw_fallback_rate
        price_cache.assert_not_awaited()  # 추정 환율로 환산한 금액도 캐시하지 않는다


class TestPersistentRecordsNeedRealRate:
    """A7 — 스냅샷·거래 행은 fallback으로 저장하지 않는다."""

    async def test_require_live_rejects_without_rate(self):
        with (
            patch("app.services.market_data.yahoo_price.fetch_usdkrw", new=AsyncMock(return_value=0.0)),
            pytest.raises(ServiceUnavailableError),
        ):
            await currency.require_live_usd_krw(_Cache())

    async def test_require_live_uses_cached_rate(self):
        assert await currency.require_live_usd_krw(_Cache("1400")) == 1400.0

    async def test_sync_fails_when_usd_assets_have_no_rate(self):
        with (
            patch("app.services.market_data.yahoo_price.fetch_usdkrw", new=AsyncMock(return_value=0.0)),
            pytest.raises(ProviderApiError) as exc,
        ):
            await currency.sync_usd_krw_rate(_Cache(), needs_usd=True)
        assert exc.value.http_status == 503

    async def test_domestic_only_sync_proceeds_without_rate(self):
        with patch("app.services.market_data.yahoo_price.fetch_usdkrw", new=AsyncMock(return_value=0.0)):
            rate = await currency.sync_usd_krw_rate(_Cache(), needs_usd=False)
        assert rate == currency.settings.usd_krw_fallback_rate


def _freshness_db(accounts: list[tuple], executions: list[tuple]) -> AsyncMock:
    accounts_result = MagicMock()
    accounts_result.all.return_value = accounts
    executions_result = MagicMock()
    executions_result.tuples.return_value.all.return_value = executions
    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[accounts_result, executions_result])
    return db


class TestSnapshotFreshnessGate:
    """A2 — 접수된 주문이 스냅샷에 반영되기 전에는 같은 주문을 다시 만들지 않는다."""

    alert = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    portfolio = SimpleNamespace(id=uuid.uuid4())
    now = datetime.now(UTC)

    async def _check(self, db, *, enforce_max_age: bool = False):
        return await gen._check_snapshot_freshness(
            self.alert, self.portfolio, uuid.uuid4(), db, enforce_max_age=enforce_max_age
        )

    async def test_execution_after_last_sync_blocks(self):
        account_id = uuid.uuid4()
        db = _freshness_db(
            [(account_id, "KIS", self.now - timedelta(hours=6))],
            [(str(account_id), self.now - timedelta(minutes=20))],
        )
        result = await self._check(db)
        assert isinstance(result, gen.SyncRequiredAfterExecution)
        assert result.account_name == "KIS"

    async def test_sync_after_execution_passes(self):
        account_id = uuid.uuid4()
        db = _freshness_db(
            [(account_id, "KIS", self.now - timedelta(minutes=5))],
            [(str(account_id), self.now - timedelta(minutes=20))],
        )
        assert await self._check(db) is None

    async def test_no_execution_passes(self):
        db = _freshness_db([(uuid.uuid4(), "KIS", self.now - timedelta(hours=6))], [])
        assert await self._check(db) is None

    async def test_never_synced_account_with_execution_blocks(self):
        account_id = uuid.uuid4()
        db = _freshness_db([(account_id, "KIS", None)], [(str(account_id), self.now)])
        assert isinstance(await self._check(db), gen.SyncRequiredAfterExecution)

    async def test_old_snapshot_blocks_auto_only(self):
        old = self.now - timedelta(days=6)
        accounts = [(uuid.uuid4(), "KIS", old)]

        auto = await self._check(_freshness_db(accounts, []), enforce_max_age=True)
        assert isinstance(auto, gen.SnapshotTooStale)
        assert auto.days_since_sync == 6

        assert await self._check(_freshness_db(accounts, [])) is None

    async def test_no_broker_account_skips_execution_lookup(self):
        db = _freshness_db([], [])
        assert await self._check(db) is None
        assert db.execute.await_count == 1

    async def test_query_ignores_failed_and_canceled_orders(self):
        account_id = uuid.uuid4()
        db = _freshness_db([(account_id, "KIS", self.now)], [])
        await self._check(db)

        sql = str(
            db.execute.await_args_list[1]
            .args[0]
            .compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False})
        )
        assert "rebalancing_execution_results.status" in sql
        assert "cancel_status" in sql

    async def test_generation_stops_before_analysis(self):
        blocked = gen.SyncRequiredAfterExecution(account_name="KIS")
        analysis = AsyncMock()
        with (
            patch.object(gen, "_check_snapshot_freshness", new=AsyncMock(return_value=blocked)),
            patch.object(gen, "_drifting_items_for_alert", new=analysis),
        ):
            result = await gen.build_pending_plan_for_alert(
                SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), account_id=None),
                SimpleNamespace(id=uuid.uuid4(), items=[]),
                AsyncMock(),
                "GREEN",
            )
        assert result is blocked
        analysis.assert_not_awaited()


class TestMarketBuyBudget:
    """A3 — 시장가도 참고 시세로 예산을 맞춘다."""

    def test_market_order_is_fitted_with_buffered_reference_price(self):
        order = _buy(reference_price=10_000.0, quantity=10)
        fitted, leftover = fit_buy_to_budget(order, 51_000.0)

        expected = int(51_000.0 // (10_000.0 * MARKET_BUY_PRICE_BUFFER))
        assert fitted is not None
        assert fitted.quantity == expected
        assert leftover == 10 - expected

    def test_market_order_without_budget_is_held_back(self):
        fitted, leftover = fit_buy_to_budget(_buy(reference_price=10_000.0), 0.0)
        assert fitted is None
        assert leftover == 10

    def test_market_order_without_any_price_passes_through(self):
        order = _buy()
        assert fit_buy_to_budget(order, 0.0) == (order, 0)

    def test_full_strategy_spends_budget_on_market_orders(self):
        """두 번째 주문은 첫 주문이 쓴 예산을 빼고 계산한다."""
        adjusted, skipped = clamp_buy_orders_to_budget(
            [_buy(ticker="A", reference_price=10_000.0, quantity=5), _buy(ticker="B", reference_price=10_000.0)],
            60_000.0,
        )
        # A 5주가 51,000원(여유 2%)을 쓰고 남은 9,000원으로는 B 1주도 못 산다
        assert [(o.ticker, o.quantity) for o in adjusted] == [("A", 5)]
        assert [r.ticker for r in skipped] == ["B"]

    async def test_two_phase_defers_buys_cash_cannot_cover(self):
        """매도 대금이 필요한 시장가 매수가 1단계에서 나가 거부되고 재시도에서도 빠지던 버그."""
        placed = AsyncMock()
        order = _buy(reference_price=10_000.0)
        with patch("app.services.rebalancing._kis_order_executor._execute_single_order", new=placed):
            results, remaining, _ = await _execute_buys_within_budget(
                [order], 0.0, "k", "s", "t", "1", False, defer_unpriced=True
            )
        placed.assert_not_awaited()
        assert results == []
        assert [o.ticker for o in remaining] == [order.ticker]

    async def test_two_phase_defers_unpriced_market_order_to_phase3(self):
        placed = AsyncMock()
        order = _buy()
        with patch("app.services.rebalancing._kis_order_executor._execute_single_order", new=placed):
            _results, remaining, _ = await _execute_buys_within_budget(
                [order], 1_000_000.0, "k", "s", "t", "1", False, defer_unpriced=True
            )
        placed.assert_not_awaited()
        assert remaining == [order]

    async def test_phase3_still_tries_unpriced_order(self):
        order = _buy()
        success = OrderResult.for_order(order, "SUCCESS")
        placed = AsyncMock(return_value=success)
        with patch("app.services.rebalancing._kis_order_executor._execute_single_order", new=placed):
            results, remaining, _ = await _execute_buys_within_budget([order], 0.0, "k", "s", "t", "1", False)
        assert results == [success]
        assert remaining == []


def _compiled(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect()))


class TestPortfolioRowLock:
    """A4 — DELETE+INSERT로 항목을 교체하는 두 경로는 행을 잠근다. 실제 경합은 테스트가 DB를 막아 재현하지 못한다."""

    async def test_tactical_lock_loads_with_for_update_and_fresh_values(self):
        from app.services.tactical import tactical_allocation_service as service

        db = AsyncMock()
        db.scalar = AsyncMock(return_value=SimpleNamespace(items=[]))
        await service.get_owned_portfolio(uuid.uuid4(), uuid.uuid4(), db, lock=True)

        stmt = db.scalar.await_args.args[0]
        assert "FOR UPDATE" in _compiled(stmt)
        assert stmt.get_execution_options().get("populate_existing") is True

    async def test_plain_read_does_not_lock(self):
        from app.services.tactical import tactical_allocation_service as service

        db = AsyncMock()
        db.scalar = AsyncMock(return_value=SimpleNamespace(items=[]))
        await service.get_owned_portfolio(uuid.uuid4(), uuid.uuid4(), db)

        assert "FOR UPDATE" not in _compiled(db.scalar.await_args.args[0])

    async def test_strategy_lock(self):
        from app.services.tactical import tactical_allocation_service as service

        db = AsyncMock()
        db.execute = AsyncMock(return_value=MagicMock())
        await service.get_strategy(uuid.uuid4(), uuid.uuid4(), db, lock=True)

        assert "FOR UPDATE" in _compiled(db.execute.await_args.args[0])

    async def test_update_portfolio_locks_row(self):
        from app.exceptions import NotFoundError
        from app.schemas.portfolio import PortfolioUpdate
        from app.services.portfolio.portfolio_crud_service import update_portfolio

        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=result)

        with pytest.raises(NotFoundError):
            await update_portfolio(db, uuid.uuid4(), uuid.uuid4(), PortfolioUpdate())

        stmt = db.execute.await_args.args[0]
        assert "FOR UPDATE" in _compiled(stmt)
        assert stmt.get_execution_options().get("populate_existing") is True


class TestInterpolateWeights:
    """A5 — 분할 적용 합계가 100을 벗어나면 이후 PUT 검증에 걸린다."""

    def test_rounding_without_cash_stays_at_100(self):
        out = tactical_apply.interpolate_weights(
            {"QQQ": 6.7, "SPY": 93.3}, {"QQQ": 30.0, "SPY": 70.0, "CASH": 0.0}, 0.5
        )
        assert out["CASH"] >= 0
        assert round(sum(out.values()), 1) == 100.0

    @pytest.mark.parametrize("q", [x / 10 for x in range(0, 1001, 7)])
    def test_total_is_always_100_and_never_negative(self, q):
        out = tactical_apply.interpolate_weights(
            {"QQQ": q, "SPY": round(100 - q, 1)}, {"QQQ": 33.3, "SPY": 66.7, "CASH": 0.0}, 0.5
        )
        assert all(v >= 0 for v in out.values())
        assert round(sum(out.values()), 1) == 100.0

    def test_positive_remainder_still_goes_to_cash(self):
        out = tactical_apply.interpolate_weights({"QQQ": 100.0}, {"QQQ": 50.0, "CASH": 50.0}, 0.5)
        assert out == {"QQQ": 75.0, "CASH": 25.0}


class TestTacticalApplyChecks:
    """A6 — 화면에서 본 국면과 다르면 저장하지 않고, 사라질 그룹은 미리 알린다."""

    def _portfolio(self):
        group = SimpleNamespace(
            ticker="379800", name="KODEX", market="KOSPI", weight=30.0, group_key="US_DJIA", group_label="다우 지수"
        )
        return SimpleNamespace(items=[group])

    def test_regime_mismatch_conflicts(self):
        strategy = SimpleNamespace(last_regime="RISK_OFF", partial_regime=None)
        with pytest.raises(ConflictError):
            tactical_apply.check_apply_allowed(self._portfolio(), strategy, 1.0, "NEUTRAL")

    def test_matching_or_missing_regime_passes(self):
        strategy = SimpleNamespace(last_regime="NEUTRAL", partial_regime=None)
        assert tactical_apply.check_apply_allowed(self._portfolio(), strategy, 1.0, "NEUTRAL")[1] == "NEUTRAL"
        assert tactical_apply.check_apply_allowed(self._portfolio(), strategy, 1.0)[1] == "NEUTRAL"

    def test_group_at_zero_weight_is_announced(self):
        assert tactical_apply.groups_removed_on_apply(self._portfolio(), {"DIA": 0.0, "QQQ": 100.0}) == ["다우 지수"]

    def test_group_with_weight_is_not_announced(self):
        assert tactical_apply.groups_removed_on_apply(self._portfolio(), {"DIA": 10.0}) == []

    def test_no_proposal_means_no_notice(self):
        assert tactical_apply.groups_removed_on_apply(self._portfolio(), None) == []


class TestSettingsReprHidesSecrets:
    """assert 실패 출력·예외 로그에 settings가 찍혀도 비밀값이 나가지 않아야 한다."""

    def test_repr_has_no_secret_values(self):
        from app.core.config import Settings

        secret = "ab" * 32
        settings = Settings(
            kis_cred_encryption_key=secret,
            database_url=f"postgresql+asyncpg://user:{secret}@db/x",
            migration_database_url=f"postgresql://user:{secret}@db/x",
            supabase_anon_key=secret,
            supabase_service_role_key=secret,
            dart_api_key=secret,
            fred_api_key=secret,
            resend_api_key=secret,
            sentry_dsn=secret,
            metrics_token=secret,
            firebase_credentials_json=secret,
        )

        assert secret not in repr(settings)
        assert secret not in str(settings)
        assert settings.resend_api_key == secret  # 값 자체는 그대로 쓴다
