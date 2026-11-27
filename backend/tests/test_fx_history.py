"""지난 날짜 USD/KRW 종가 — 수기 해외 거래 기록을 거래일 환율로 환산 (plans/156)."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.services.market_data import fx_history
from tests.api_helpers import make_mock_db, make_user, setup_app


def _series(points: dict[str, float]) -> dict[str, pd.Series]:
    return {"USDKRW=X": pd.Series(list(points.values()), index=pd.to_datetime(list(points)))}


class TestCloseOnOrBefore:
    def test_weekend_uses_previous_trading_day(self):
        with patch(
            "app.services.market_data.market_data_fetcher.fetch_yf_close_series",
            return_value=_series({"2026-05-07": 1380.0, "2026-05-08": 1385.5}),
        ):
            # 2026-05-09는 토요일
            assert fx_history._sync_close_on_or_before(date(2026, 5, 9)) == (1385.5, date(2026, 5, 8))

    def test_ignores_rows_after_the_day_and_nan(self):
        with patch(
            "app.services.market_data.market_data_fetcher.fetch_yf_close_series",
            return_value=_series({"2026-05-07": 1380.0, "2026-05-08": float("nan"), "2026-05-11": 1400.0}),
        ):
            assert fx_history._sync_close_on_or_before(date(2026, 5, 8)) == (1380.0, date(2026, 5, 7))

    def test_no_data_is_none(self):
        with patch("app.services.market_data.market_data_fetcher.fetch_yf_close_series", return_value={}):
            assert fx_history._sync_close_on_or_before(date(2026, 5, 8)) is None


class TestFetchUsdKrwOn:
    @pytest.mark.asyncio
    async def test_caches_found_rate(self):
        from app.core.cache_store import CacheStore

        cache = CacheStore()
        with patch.object(fx_history, "_sync_close_on_or_before", return_value=(1385.5, date(2026, 5, 8))) as sync:
            first = await fx_history.fetch_usd_krw_on(date(2026, 5, 9), cache)
            second = await fx_history.fetch_usd_krw_on(date(2026, 5, 9), cache)

        assert first == second == (1385.5, date(2026, 5, 8))
        assert sync.call_count == 1

    @pytest.mark.asyncio
    async def test_failure_is_none_and_not_cached(self, mock_cache):
        with patch.object(fx_history, "_sync_close_on_or_before", side_effect=RuntimeError("yahoo down")):
            assert await fx_history.fetch_usd_krw_on(date(2026, 5, 9), mock_cache) is None
        with patch.object(fx_history, "_sync_close_on_or_before", return_value=(1385.5, date(2026, 5, 8))):
            assert await fx_history.fetch_usd_krw_on(date(2026, 5, 9), mock_cache) == (1385.5, date(2026, 5, 8))


class TestExchangeRateOnEndpoint:
    def _client(self):
        return setup_app(make_user(), make_mock_db())

    def test_returns_rate_and_actual_close_date(self, override_settings):
        app = self._client()
        with (
            patch(
                "app.api.v1.stocks.fetch_usd_krw_on", new=AsyncMock(return_value=(1385.5, date(2026, 5, 8)))
            ) as fetch,
            TestClient(app) as client,
        ):
            resp = client.get("/api/v1/stocks/exchange-rate/on", params={"date": "2026-05-09"})
        app.dependency_overrides.clear()

        assert resp.status_code == 200
        assert resp.json() == {"usd_krw": 1385.5, "rate_date": "2026-05-08"}
        assert fetch.await_args.args[0] == date(2026, 5, 9)

    def test_unavailable_returns_null(self, override_settings):
        app = self._client()
        with (
            patch("app.api.v1.stocks.fetch_usd_krw_on", new=AsyncMock(return_value=None)),
            TestClient(app) as client,
        ):
            resp = client.get("/api/v1/stocks/exchange-rate/on", params={"date": "2026-05-09"})
        app.dependency_overrides.clear()

        assert resp.json() == {"usd_krw": None, "rate_date": None}

    def test_today_or_future_is_rejected(self, override_settings):
        from app.utils.kst import today_kst

        app = self._client()
        with TestClient(app) as client:
            resp = client.get(
                "/api/v1/stocks/exchange-rate/on", params={"date": (today_kst() + timedelta(days=1)).isoformat()}
            )
        app.dependency_overrides.clear()

        assert resp.status_code == 400
