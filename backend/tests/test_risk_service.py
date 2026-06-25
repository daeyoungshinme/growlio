"""risk_service.py 단위 테스트."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.risk_service import (
    _calc_beta,
    _calc_diversification_score,
    _calc_var,
    _to_yf_symbol,
)

# ── 순수 함수 ──────────────────────────────────────────────────


class TestToYfSymbol:
    def test_kospi(self, override_settings):
        assert _to_yf_symbol("005930", "KOSPI") == "005930.KS"

    def test_krx(self, override_settings):
        assert _to_yf_symbol("069500", "KRX") == "069500.KS"

    def test_kosdaq(self, override_settings):
        assert _to_yf_symbol("035720", "KOSDAQ") == "035720.KQ"

    def test_nasdaq_unchanged(self, override_settings):
        assert _to_yf_symbol("AAPL", "NASDAQ") == "AAPL"

    def test_nyse_unchanged(self, override_settings):
        assert _to_yf_symbol("KO", "NYSE") == "KO"

    def test_ticker_padded_to_six_digits(self, override_settings):
        assert _to_yf_symbol("5930", "KOSPI") == "005930.KS"


class TestCalcVar:
    def test_empty_returns_zero(self, override_settings):
        assert _calc_var([], 0.95) == 0.0

    def test_95_confidence(self, override_settings):
        returns = [-0.05, -0.02, -0.01, 0.01, 0.03, 0.02, -0.04, 0.005, -0.015, 0.025]
        result = _calc_var(returns, 0.95)
        assert result > 0.0

    def test_99_more_conservative_than_95(self, override_settings):
        returns = list(range(-20, 20, 1))
        returns = [r / 100.0 for r in range(-20, 20, 1)]
        var_95 = _calc_var(returns, 0.95)
        var_99 = _calc_var(returns, 0.99)
        assert var_99 >= var_95

    def test_all_positive_returns(self, override_settings):
        returns = [0.01, 0.02, 0.03, 0.04, 0.05]
        result = _calc_var(returns, 0.95)
        assert result >= 0.0


class TestCalcBeta:
    def test_insufficient_data_returns_one(self, override_settings):
        assert _calc_beta([0.01, 0.02], [0.01, 0.02]) == 1.0

    def test_identical_returns_beta_one(self, override_settings):
        rets = [0.01 * (i % 5 - 2) for i in range(50)]
        result = _calc_beta(rets, rets)
        assert abs(result - 1.0) < 0.01

    def test_double_returns_beta_two(self, override_settings):
        bench = [0.01 * (i % 5 - 2) for i in range(50)]
        port = [2 * r for r in bench]
        result = _calc_beta(port, bench)
        assert abs(result - 2.0) < 0.1

    def test_zero_variance_bench_returns_one(self, override_settings):
        port = [0.01] * 20
        bench = [0.0] * 20  # zero variance
        result = _calc_beta(port, bench)
        assert result == 1.0


class TestCalcDiversificationScore:
    def test_single_symbol_returns_20(self, override_settings):
        assert _calc_diversification_score(["AAPL"], [1.0], {}) == 20

    def test_empty_symbols_returns_20(self, override_settings):
        # len < 2 → returns 20 (single/no holding)
        assert _calc_diversification_score([], [], {}) == 20

    def test_insufficient_returns_data_returns_50(self, override_settings):
        # Less than 20 data points → score defaults to 50
        result = _calc_diversification_score(
            ["AAPL", "TSLA"],
            [0.5, 0.5],
            {"AAPL": [0.01] * 5, "TSLA": [-0.01] * 5},
        )
        assert result == 50

    def test_negative_correlation_high_score(self, override_settings):
        # Perfectly negative correlation → high diversification
        r1 = [0.01 * (i % 2 * 2 - 1) for i in range(50)]  # alternating +/-
        r2 = [-r for r in r1]
        result = _calc_diversification_score(["A", "B"], [0.5, 0.5], {"A": r1, "B": r2})
        assert result >= 50

    def test_positive_correlation_low_score(self, override_settings):
        # Perfectly positive correlation → low diversification
        r = [0.01 * (i % 5 - 2) for i in range(50)]
        result = _calc_diversification_score(["A", "B"], [0.5, 0.5], {"A": r, "B": r})
        assert result <= 50


# ── get_portfolio_risk_metrics (DB mock) ──────────────────────


class TestGetPortfolioRiskMetrics:
    @pytest.mark.asyncio
    async def test_no_positions_returns_empty(self, mock_db, override_settings):
        from app.services.risk_service import get_portfolio_risk_metrics

        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await get_portfolio_risk_metrics(uuid.uuid4(), mock_db)

        assert result["data_available"] is False
        assert result["position_count"] == 0
        assert result["var_95_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_redis_cache_hit_skips_db(self, mock_db, override_settings):
        import json

        from app.services.risk_service import get_portfolio_risk_metrics

        cached = {"var_95_pct": 1.5, "data_available": True, "position_count": 5}
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(cached).encode())

        result = await get_portfolio_risk_metrics(uuid.uuid4(), mock_db, redis=redis)

        assert result["var_95_pct"] == 1.5
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_with_positions_and_mocked_executor(self, mock_db, override_settings):
        from types import SimpleNamespace

        from app.services.risk_service import get_portfolio_risk_metrics

        snap = SimpleNamespace(id=uuid.uuid4())
        acc = SimpleNamespace(id=uuid.uuid4(), is_active=True)

        snap_result = MagicMock()
        snap_result.all.return_value = [(snap, acc)]

        pos = SimpleNamespace(
            ticker="AAPL",
            market="NASDAQ",
            snapshot_id=snap.id,
            value_krw=1_000_000,
        )
        pos_result = MagicMock()
        pos_result.scalars.return_value.all.return_value = [pos]

        mock_db.execute = AsyncMock(side_effect=[snap_result, pos_result])

        returns = [0.01 * (i % 5 - 2) for i in range(300)]
        returns_map = {"AAPL": returns, "^GSPC": returns}

        with patch("app.services.risk_service.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=returns_map)
            result = await get_portfolio_risk_metrics(uuid.uuid4(), mock_db)

        assert result["position_count"] == 1
        assert "var_95_pct" in result
        assert "beta_sp500" in result


# ── get_currency_exposure ────────────────────────────────────


class TestGetCurrencyExposure:
    @pytest.mark.asyncio
    async def test_no_positions_returns_zeros(self, mock_db, override_settings):
        from app.services.risk_service import get_currency_exposure

        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await get_currency_exposure(uuid.uuid4(), mock_db)

        assert result["krw_pct"] == 0
        assert result["usd_pct"] == 0

    @pytest.mark.asyncio
    async def test_krw_position_returns_100_krw(self, mock_db, override_settings):
        from types import SimpleNamespace

        from app.services.risk_service import get_currency_exposure

        snap = SimpleNamespace(id=uuid.uuid4())
        acc = SimpleNamespace(id=uuid.uuid4(), is_active=True, deposit_krw=None, deposit_usd=None)
        pos = SimpleNamespace(
            snapshot_id=snap.id,
            value_krw=5_000_000.0,
            currency="KRW",
            ticker="005930",
            market="KOSPI",
        )

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = [(snap, acc)]
            else:
                result.scalars.return_value.all.return_value = [pos]
            return result

        mock_db.execute = mock_execute

        result = await get_currency_exposure(uuid.uuid4(), mock_db)

        assert result["krw_pct"] == pytest.approx(100.0)
        assert result["usd_pct"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_mixed_currencies(self, mock_db, override_settings):
        from types import SimpleNamespace

        from app.services.risk_service import get_currency_exposure

        snap = SimpleNamespace(id=uuid.uuid4())
        acc = SimpleNamespace(id=uuid.uuid4(), is_active=True, deposit_krw=None, deposit_usd=None)
        pos_krw = SimpleNamespace(
            snapshot_id=snap.id,
            value_krw=5_000_000.0,
            currency="KRW",
            ticker="005930",
            market="KOSPI",
        )
        pos_usd = SimpleNamespace(
            snapshot_id=snap.id,
            value_krw=5_000_000.0,
            currency="USD",
            ticker="AAPL",
            market="NASDAQ",
        )

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = [(snap, acc)]
            else:
                result.scalars.return_value.all.return_value = [pos_krw, pos_usd]
            return result

        mock_db.execute = mock_execute

        result = await get_currency_exposure(uuid.uuid4(), mock_db)

        assert result["krw_pct"] == pytest.approx(50.0)
        assert result["usd_pct"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_usd_deposit_included_in_currency_exposure(self, mock_db, override_settings):
        """deposit_usd가 있는 계좌는 Position 없어도 USD 비중에 반영된다."""
        from types import SimpleNamespace
        from unittest.mock import patch

        from app.services.risk_service import get_currency_exposure

        snap = SimpleNamespace(id=uuid.uuid4())
        acc = SimpleNamespace(id=uuid.uuid4(), is_active=True, deposit_krw=None, deposit_usd=1000.0)

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = [(snap, acc)]
            else:
                result.scalars.return_value.all.return_value = []
            return result

        mock_db.execute = mock_execute

        with patch("app.services.risk_service.fetch_usd_krw", AsyncMock(return_value=1300.0)):
            result = await get_currency_exposure(uuid.uuid4(), mock_db)

        assert result["usd_pct"] == pytest.approx(100.0)
        assert result["krw_pct"] == pytest.approx(0.0)
        assert result["usd_value"] == pytest.approx(1_300_000.0)

    @pytest.mark.asyncio
    async def test_mixed_position_and_deposit(self, mock_db, override_settings):
        """KRW 주식 5백만원 + USD 예수금 1000달러(=130만원) → KRW 79%, USD 21%."""
        from types import SimpleNamespace
        from unittest.mock import patch

        from app.services.risk_service import get_currency_exposure

        snap = SimpleNamespace(id=uuid.uuid4())
        acc = SimpleNamespace(id=uuid.uuid4(), is_active=True, deposit_krw=None, deposit_usd=1000.0)
        pos_krw = SimpleNamespace(
            snapshot_id=snap.id,
            value_krw=5_000_000.0,
            currency="KRW",
            ticker="005930",
            market="KOSPI",
        )

        call_count = 0

        async def mock_execute(query, params=None):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.all.return_value = [(snap, acc)]
            else:
                result.scalars.return_value.all.return_value = [pos_krw]
            return result

        mock_db.execute = mock_execute

        with patch("app.services.risk_service.fetch_usd_krw", AsyncMock(return_value=1300.0)):
            result = await get_currency_exposure(uuid.uuid4(), mock_db)

        # 5_000_000 KRW + 1_300_000 USD-as-KRW = 6_300_000 total
        assert result["krw_value"] == pytest.approx(5_000_000.0)
        assert result["usd_value"] == pytest.approx(1_300_000.0)
        assert result["krw_pct"] == pytest.approx(5_000_000 / 6_300_000 * 100, rel=1e-3)
        assert result["usd_pct"] == pytest.approx(1_300_000 / 6_300_000 * 100, rel=1e-3)


# ── _sync_fetch_risk_data ────────────────────────────────────


class TestSyncFetchRiskData:
    def test_empty_symbols_returns_empty(self, override_settings):
        from app.services.risk_service import _sync_fetch_risk_data

        result = _sync_fetch_risk_data([], [])
        assert result == {}

    def test_yfinance_exception_returns_empty(self, override_settings):
        from app.services.risk_service import _sync_fetch_risk_data

        with patch("yfinance.download", side_effect=Exception("network error")):
            result = _sync_fetch_risk_data(["AAPL"], ["^GSPC"])

        assert result == {}

    def test_empty_dataframe_returns_empty(self, override_settings):
        import pandas as pd

        from app.services.risk_service import _sync_fetch_risk_data

        with patch("yfinance.download", return_value=pd.DataFrame()):
            result = _sync_fetch_risk_data(["AAPL"], ["^GSPC"])

        assert result == {}

    def test_returns_returns_data(self, override_settings):
        import pandas as pd

        from app.services.risk_service import _sync_fetch_risk_data

        idx = pd.date_range("2023-01-01", periods=100)
        prices = [100.0 + i * 0.5 for i in range(100)]
        df = pd.DataFrame({"AAPL": prices}, index=idx)

        with patch("yfinance.download", return_value=df):
            result = _sync_fetch_risk_data(["AAPL"], [])

        assert "AAPL" in result
        assert len(result["AAPL"]) > 0
        assert all(isinstance(r, float) for r in result["AAPL"])
