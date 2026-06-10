"""backtest_service.run_backtest 및 compute_correlation 통합 테스트."""
from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.backtest import BacktestRunRequest, CorrelationRequest


def _exec_result(items):
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    result.all.return_value = [(row,) for row in items] if items else []
    return result


def _make_portfolio(port_id=None, name="포트폴리오", base_type="STOCK_ONLY", items=None):
    if items is None:
        items = [SimpleNamespace(ticker="AAPL", market="NASDAQ", weight=100.0, name="Apple")]
    return SimpleNamespace(id=port_id or uuid.uuid4(), name=name, base_type=base_type, items=items)


class TestRunBacktestEmptyPortfolio:
    @pytest.mark.asyncio
    async def test_empty_portfolios_returns_empty_result(self, mock_db, override_settings):
        """포트폴리오 없으면 빈 BacktestResult."""
        from app.services.backtest_service import run_backtest

        mock_db.execute = AsyncMock(return_value=_exec_result([]))

        req = BacktestRunRequest(
            portfolio_ids=[uuid.uuid4()],
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
            include_spy=False,
            include_real_portfolio=False,
        )

        with patch("app.services.backtest_service.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value={})
            result = await run_backtest(uuid.uuid4(), req, mock_db)

        # Empty portfolios → no series/metrics, but calendar dates still generated
        assert result.series == []
        assert result.metrics == []


class TestRunBacktestWithPortfolio:
    @pytest.mark.asyncio
    async def test_single_portfolio_no_price_data_uses_calendar_dates(self, mock_db, override_settings):
        """가격 데이터 없으면 달력 기반 날짜 사용 (주말 제외)."""
        from app.services.backtest_service import run_backtest

        port = _make_portfolio()
        exec_res = MagicMock()
        exec_res.scalars.return_value.all.return_value = [port]
        mock_db.execute = AsyncMock(return_value=exec_res)

        req = BacktestRunRequest(
            portfolio_ids=[port.id],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 10),
            include_spy=False,
            include_real_portfolio=False,
        )

        with patch("app.services.backtest_service.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value={})
            result = await run_backtest(uuid.uuid4(), req, mock_db)

        assert len(result.dates) > 0
        assert len(result.series) == 1
        assert result.series[0].name == port.name

    @pytest.mark.asyncio
    async def test_single_portfolio_with_price_data(self, mock_db, override_settings):
        """가격 데이터 있으면 날짜는 해당 가격 기준으로 설정."""
        from app.services.backtest_service import run_backtest

        port = _make_portfolio()
        exec_res = MagicMock()
        exec_res.scalars.return_value.all.return_value = [port]
        mock_db.execute = AsyncMock(return_value=exec_res)

        price_data = {
            "AAPL": [
                ("2024-01-02", 185.0),
                ("2024-01-03", 190.0),
                ("2024-01-04", 187.0),
            ]
        }

        req = BacktestRunRequest(
            portfolio_ids=[port.id],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 10),
            include_spy=False,
            include_real_portfolio=False,
        )

        with patch("app.services.backtest_service.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=price_data)
            result = await run_backtest(uuid.uuid4(), req, mock_db)

        assert len(result.dates) == 3
        assert result.series[0].name == port.name

    @pytest.mark.asyncio
    async def test_include_spy_adds_spy_series(self, mock_db, override_settings):
        """include_spy=True이면 SPY 시리즈 포함."""
        from app.services.backtest_service import run_backtest

        port = _make_portfolio()
        exec_res = MagicMock()
        exec_res.scalars.return_value.all.return_value = [port]
        mock_db.execute = AsyncMock(return_value=exec_res)

        price_data = {
            "AAPL": [("2024-01-02", 185.0), ("2024-01-03", 190.0)],
            "SPY": [("2024-01-02", 475.0), ("2024-01-03", 480.0)],
        }

        req = BacktestRunRequest(
            portfolio_ids=[port.id],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 10),
            include_spy=True,
            include_real_portfolio=False,
        )

        with patch("app.services.backtest_service.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=price_data)
            result = await run_backtest(uuid.uuid4(), req, mock_db)

        names = [s.name for s in result.series]
        assert "S&P 500" in names

    @pytest.mark.asyncio
    async def test_include_real_portfolio_with_holdings(self, mock_db, override_settings):
        """include_real_portfolio=True + 보유 포지션이 있으면 실제 포트폴리오 시리즈 추가."""
        from app.services.backtest_service import run_backtest

        port = _make_portfolio()
        portfolio_exec = MagicMock()
        portfolio_exec.scalars.return_value.all.return_value = [port]

        # _get_real_portfolio_holdings: snap_ids 쿼리 → [(snap_id,)]
        snap_id = uuid.uuid4()
        snap_exec = MagicMock()
        snap_exec.all.return_value = [(snap_id,)]

        pos = SimpleNamespace(
            ticker="AAPL", market="NASDAQ", value_krw=500_000,
            current_price=None, qty=5,
        )
        pos_exec = MagicMock()
        pos_exec.scalars.return_value.all.return_value = [pos]

        mock_db.execute = AsyncMock(side_effect=[
            portfolio_exec,   # portfolios
            snap_exec,        # snap_ids
            pos_exec,         # positions
        ])

        price_data = {
            "AAPL": [("2024-01-02", 185.0), ("2024-01-03", 190.0)],
        }

        req = BacktestRunRequest(
            portfolio_ids=[port.id],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 10),
            include_spy=False,
            include_real_portfolio=True,
        )

        with patch("app.services.backtest_service.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=price_data)
            result = await run_backtest(uuid.uuid4(), req, mock_db)

        names = [s.name for s in result.series]
        assert "실제 포트폴리오" in names

    @pytest.mark.asyncio
    async def test_include_real_portfolio_no_holdings(self, mock_db, override_settings):
        """include_real_portfolio=True이지만 보유 포지션 없으면 실제 포트폴리오 없음."""
        from app.services.backtest_service import run_backtest

        port = _make_portfolio()
        portfolio_exec = MagicMock()
        portfolio_exec.scalars.return_value.all.return_value = [port]

        # No snap_ids
        snap_exec = MagicMock()
        snap_exec.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[
            portfolio_exec,
            snap_exec,  # snap_ids query returns empty
        ])

        price_data = {
            "AAPL": [("2024-01-02", 185.0), ("2024-01-03", 190.0)],
        }

        req = BacktestRunRequest(
            portfolio_ids=[port.id],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 10),
            include_spy=False,
            include_real_portfolio=True,
        )

        with patch("app.services.backtest_service.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=price_data)
            result = await run_backtest(uuid.uuid4(), req, mock_db)

        names = [s.name for s in result.series]
        assert "실제 포트폴리오" not in names

    @pytest.mark.asyncio
    async def test_cash_ticker_skipped_in_symbols(self, mock_db, override_settings):
        """CASH 티커는 yfinance 조회에서 제외."""
        from app.services.backtest_service import run_backtest

        port = _make_portfolio(items=[
            SimpleNamespace(ticker="CASH", market="KRW", weight=50.0, name="현금"),
            SimpleNamespace(ticker="AAPL", market="NASDAQ", weight=50.0, name="Apple"),
        ])
        exec_res = MagicMock()
        exec_res.scalars.return_value.all.return_value = [port]
        mock_db.execute = AsyncMock(return_value=exec_res)

        req = BacktestRunRequest(
            portfolio_ids=[port.id],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 5),
            include_spy=False,
            include_real_portfolio=False,
        )

        captured_symbols = []

        async def capture_executor(pool, fn, *args):
            captured_symbols.extend(args[0] if args else [])
            return {}

        with patch("app.services.backtest_service.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = capture_executor
            await run_backtest(uuid.uuid4(), req, mock_db)

        assert "CASH" not in captured_symbols


class TestComputeCorrelation:
    @pytest.mark.asyncio
    async def test_empty_portfolios_returns_empty(self, mock_db, override_settings):
        """포트폴리오 없으면 빈 결과."""
        from app.services.backtest_service import compute_correlation

        mock_db.execute = AsyncMock(return_value=_exec_result([]))

        req = CorrelationRequest(
            portfolio_ids=[uuid.uuid4()],
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
        )

        result = await compute_correlation(uuid.uuid4(), req, mock_db)
        assert result.labels == []
        assert result.matrix == []

    @pytest.mark.asyncio
    async def test_portfolio_with_items_calls_executor(self, mock_db, override_settings):
        """종목이 있으면 executor를 통해 상관관계 계산."""
        from app.services.backtest_service import compute_correlation

        port = _make_portfolio()
        exec_res = MagicMock()
        exec_res.scalars.return_value.all.return_value = [port]
        mock_db.execute = AsyncMock(return_value=exec_res)

        req = CorrelationRequest(
            portfolio_ids=[port.id],
            start_date=date(2023, 1, 1),
            end_date=date(2023, 12, 31),
        )

        with patch("app.services.backtest_service.asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=(["AAPL"], [[1.0]]))
            result = await compute_correlation(uuid.uuid4(), req, mock_db)

        assert result.labels == ["AAPL"]
        assert result.matrix == [[1.0]]
