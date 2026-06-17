"""factor_service.py 단위 테스트."""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.factor_service import (
    _build_holdings,
    _empty_factor_result,
    _portfolio_factors,
    _safe_float,
    _score_growth,
    _score_momentum,
    _score_size,
    _score_value,
    get_factor_analysis,
    get_factor_analysis_for_portfolio,
)


# ── 팩터 점수 순수 함수 ──────────────────────────────────────

class TestScoreValue:
    def test_low_pb_pe_high_score(self, override_settings):
        score = _score_value(pb=0.5, pe=5.0)
        assert score >= 90.0

    def test_high_pb_pe_low_score(self, override_settings):
        score = _score_value(pb=5.0, pe=50.0)
        assert score <= 10.0

    def test_none_values_returns_50(self, override_settings):
        assert _score_value(None, None) == 50.0

    def test_negative_pe_ignored(self, override_settings):
        score = _score_value(pb=1.0, pe=-5.0)
        assert 0.0 <= score <= 100.0

    def test_very_high_pe_ignored(self, override_settings):
        # pe >= 200 → 무시
        score = _score_value(pb=None, pe=300.0)
        assert score == 50.0

    def test_score_clamped_0_100(self, override_settings):
        score = _score_value(pb=0.0001, pe=0.1)
        assert 0.0 <= score <= 100.0


class TestScoreGrowth:
    def test_high_pb_pe_high_score(self, override_settings):
        score = _score_growth(pb=5.0, pe=50.0)
        assert score >= 90.0

    def test_low_pb_pe_low_score(self, override_settings):
        score = _score_growth(pb=0.5, pe=5.0)
        assert score <= 10.0

    def test_none_values_returns_50(self, override_settings):
        assert _score_growth(None, None) == 50.0


class TestScoreSize:
    def test_small_cap_high_score(self, override_settings):
        score = _score_size(market_cap=5e8)  # 500M USD
        assert score > 90.0

    def test_large_cap_low_score(self, override_settings):
        score = _score_size(market_cap=5e11)  # 500B USD
        assert score < 10.0

    def test_none_returns_50(self, override_settings):
        assert _score_size(None) == 50.0

    def test_zero_returns_50(self, override_settings):
        assert _score_size(0) == 50.0

    def test_negative_returns_50(self, override_settings):
        assert _score_size(-1e9) == 50.0

    def test_clamped_0_100(self, override_settings):
        assert 0.0 <= _score_size(1e15) <= 100.0


class TestScoreMomentum:
    def test_positive_momentum_high_score(self, override_settings):
        score = _score_momentum(50.0)
        assert score == 100.0

    def test_negative_momentum_low_score(self, override_settings):
        score = _score_momentum(-50.0)
        assert score == 0.0

    def test_zero_momentum_fifty(self, override_settings):
        assert _score_momentum(0.0) == 50.0

    def test_none_returns_50(self, override_settings):
        assert _score_momentum(None) == 50.0

    def test_clamped_0_100(self, override_settings):
        assert 0.0 <= _score_momentum(200.0) <= 100.0


# ── 헬퍼 함수 ───────────────────────────────────────────────

class TestBuildHoldings:
    def test_basic(self, override_settings):
        positions = [{"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "value_krw": 1000.0}]
        symbols = ["005930.KS"]
        weights = [1.0]
        factor_data = {
            "005930.KS": {
                "pe_ratio": 10.0,
                "pb_ratio": 1.0,
                "market_cap": 3e11,
                "momentum_pct": 10.0,
            }
        }
        holdings = _build_holdings(positions, symbols, weights, factor_data)
        assert len(holdings) == 1
        h = holdings[0]
        assert h["ticker"] == "005930"
        assert h["weight_pct"] == 100.0
        assert 0.0 <= h["value_score"] <= 100.0
        assert 0.0 <= h["growth_score"] <= 100.0
        assert 0.0 <= h["size_score"] <= 100.0
        assert 0.0 <= h["momentum_score"] <= 100.0

    def test_missing_factor_data_uses_none(self, override_settings):
        positions = [{"ticker": "AAPL", "name": "Apple", "market": "NASDAQ", "value_krw": 1000.0}]
        holdings = _build_holdings(positions, ["AAPL"], [1.0], {})
        assert holdings[0]["pe_ratio"] is None
        assert holdings[0]["value_score"] == 50.0

    def test_empty_positions(self, override_settings):
        assert _build_holdings([], [], [], {}) == []


class TestPortfolioFactors:
    def test_weighted_average(self, override_settings):
        holdings = [
            {"weight_pct": 60.0, "value_score": 80.0, "growth_score": 20.0, "size_score": 40.0, "momentum_score": 60.0},
            {"weight_pct": 40.0, "value_score": 20.0, "growth_score": 80.0, "size_score": 60.0, "momentum_score": 40.0},
        ]
        factors = _portfolio_factors(holdings)
        assert abs(factors["value"] - (80.0 * 0.6 + 20.0 * 0.4)) < 0.2
        assert abs(factors["growth"] - (20.0 * 0.6 + 80.0 * 0.4)) < 0.2


# ── _safe_float ────────────────────────────────────────────

class TestSafeFloat:
    def test_normal_float(self, override_settings):
        assert _safe_float(3.14) == pytest.approx(3.14)

    def test_integer_input(self, override_settings):
        assert _safe_float(42) == pytest.approx(42.0)

    def test_string_number(self, override_settings):
        assert _safe_float("12.5") == pytest.approx(12.5)

    def test_none_returns_none(self, override_settings):
        assert _safe_float(None) is None

    def test_invalid_string_returns_none(self, override_settings):
        assert _safe_float("not_a_number") is None

    def test_infinity_returns_none(self, override_settings):
        assert _safe_float(float("inf")) is None

    def test_nan_returns_none(self, override_settings):
        assert _safe_float(float("nan")) is None


# ── 빈 결과 ────────────────────────────────────────────────

class TestEmptyFactorResult:
    def test_structure(self, override_settings):
        result = _empty_factor_result()
        assert result["holdings"] == []
        assert result["position_count"] == 0
        assert "value" in result["portfolio_factors"]


# ── get_factor_analysis_for_portfolio (DB mock) ────────────

class TestGetFactorAnalysisForPortfolio:
    @pytest.mark.asyncio
    async def test_portfolio_not_found_returns_empty(self, mock_db, override_settings):
        mock_db.scalar = AsyncMock(return_value=None)

        result = await get_factor_analysis_for_portfolio("some-portfolio-id", mock_db)

        assert result["position_count"] == 0
        assert result["holdings"] == []

    @pytest.mark.asyncio
    async def test_portfolio_with_no_items_returns_empty(self, mock_db, override_settings):
        portfolio = MagicMock()
        portfolio.items = []
        mock_db.scalar = AsyncMock(return_value=portfolio)

        result = await get_factor_analysis_for_portfolio("some-portfolio-id", mock_db)

        assert result["position_count"] == 0

    @pytest.mark.asyncio
    async def test_portfolio_with_items_calls_executor(self, mock_db, override_settings):
        item = SimpleNamespace(ticker="005930", market="KOSPI", name="삼성전자", weight=100)
        portfolio = MagicMock()
        portfolio.items = [item]
        portfolio.name = "테스트포트폴리오"
        mock_db.scalar = AsyncMock(return_value=portfolio)

        factor_data = {
            "005930.KS": {"pe_ratio": 12.0, "pb_ratio": 1.2, "market_cap": 3e11, "momentum_pct": 5.0}
        }
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_executor = AsyncMock(return_value=factor_data)
            mock_loop.return_value.run_in_executor = mock_executor

            result = await get_factor_analysis_for_portfolio("some-portfolio-id", mock_db)

        assert result["position_count"] == 1
        assert len(result["holdings"]) == 1
        assert result["holdings"][0]["ticker"] == "005930"
        assert result["portfolio_name"] == "테스트포트폴리오"

    @pytest.mark.asyncio
    async def test_redis_cache_hit_skips_db(self, mock_db, override_settings):
        cached = {
            "holdings": [],
            "portfolio_factors": {"value": 55.0, "growth": 45.0, "size": 50.0, "momentum": 60.0},
            "position_count": 2,
            "note": "cached",
        }
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(cached).encode())

        result = await get_factor_analysis_for_portfolio("some-portfolio-id", mock_db, redis=redis)

        assert result["position_count"] == 2
        mock_db.scalar.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_error_falls_back_to_db(self, mock_db, override_settings):
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=Exception("redis unavailable"))

        item = SimpleNamespace(ticker="005930", market="KOSPI", name="삼성전자", weight=100)
        portfolio = MagicMock()
        portfolio.items = [item]
        portfolio.name = "테스트"
        mock_db.scalar = AsyncMock(return_value=portfolio)

        factor_data = {"005930.KS": {"pe_ratio": 10.0, "pb_ratio": 1.0, "market_cap": 1e11, "momentum_pct": 3.0}}
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_executor = AsyncMock(return_value=factor_data)
            mock_loop.return_value.run_in_executor = mock_executor

            result = await get_factor_analysis_for_portfolio("some-portfolio-id", mock_db, redis=redis)

        assert result["position_count"] == 1

    @pytest.mark.asyncio
    async def test_redis_cache_written_on_success(self, mock_db, override_settings):
        item = SimpleNamespace(ticker="035420", market="KOSPI", name="NAVER", weight=100)
        portfolio = MagicMock()
        portfolio.items = [item]
        portfolio.name = "포트폴리오"
        mock_db.scalar = AsyncMock(return_value=portfolio)

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        factor_data = {
            "035420.KS": {"pe_ratio": 30.0, "pb_ratio": 3.0, "market_cap": 1e11, "momentum_pct": 10.0}
        }
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_executor = AsyncMock(return_value=factor_data)
            mock_loop.return_value.run_in_executor = mock_executor

            await get_factor_analysis_for_portfolio("some-portfolio-id", mock_db, redis=redis)

        redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_zero_total_weight_returns_empty(self, mock_db, override_settings):
        item = SimpleNamespace(ticker="005930", market="KOSPI", name="삼성전자", weight=0)
        portfolio = MagicMock()
        portfolio.items = [item]
        portfolio.name = "포트폴리오"
        mock_db.scalar = AsyncMock(return_value=portfolio)

        result = await get_factor_analysis_for_portfolio("some-portfolio-id", mock_db)

        assert result["position_count"] == 0


# ── get_factor_analysis (DB mock) ─────────────────────────

class TestGetFactorAnalysis:
    @pytest.mark.asyncio
    async def test_no_positions_returns_empty(self, mock_db, override_settings):
        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await get_factor_analysis(uuid.uuid4(), mock_db)

        assert result["position_count"] == 0
        assert result["holdings"] == []

    @pytest.mark.asyncio
    async def test_redis_cache_hit_skips_db(self, mock_db, override_settings):
        cached = {
            "holdings": [],
            "portfolio_factors": {"value": 55.0, "growth": 45.0, "size": 50.0, "momentum": 60.0},
            "position_count": 3,
            "note": "cached",
        }
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps(cached).encode())

        result = await get_factor_analysis(uuid.uuid4(), mock_db, redis=redis)

        assert result["position_count"] == 3
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_error_falls_back_to_db(self, mock_db, override_settings):
        redis = AsyncMock()
        redis.get = AsyncMock(side_effect=Exception("redis error"))

        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        result = await get_factor_analysis(uuid.uuid4(), mock_db, redis=redis)
        assert result["position_count"] == 0

    @pytest.mark.asyncio
    async def test_with_positions_calls_executor(self, mock_db, override_settings):
        snap = SimpleNamespace(id=uuid.uuid4())
        acc = SimpleNamespace(id=uuid.uuid4(), is_active=True)
        pos = SimpleNamespace(
            ticker="005930", market="KOSPI", name="삼성전자",
            value_krw=1_000_000.0, snapshot_id=snap.id,
        )

        snap_result = MagicMock()
        snap_result.all.return_value = [(snap, acc)]
        pos_result = MagicMock()
        pos_result.scalars.return_value.all.return_value = [pos]

        mock_db.execute = AsyncMock(side_effect=[snap_result, pos_result])

        factor_data = {
            "005930.KS": {"pe_ratio": 12.0, "pb_ratio": 1.2, "market_cap": 3e11, "momentum_pct": 5.0}
        }
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_executor = AsyncMock(return_value=factor_data)
            mock_loop.return_value.run_in_executor = mock_executor

            result = await get_factor_analysis(uuid.uuid4(), mock_db)

        assert result["position_count"] == 1
        assert len(result["holdings"]) == 1
        h = result["holdings"][0]
        assert h["ticker"] == "005930"
        assert h["weight_pct"] == 100.0

    @pytest.mark.asyncio
    async def test_redis_no_cache_write_when_no_positions(self, mock_db, override_settings):
        """포지션 없을 때 조기 반환되므로 Redis cache 쓰기 없음."""
        exec_result = MagicMock()
        exec_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=exec_result)

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        await get_factor_analysis(uuid.uuid4(), mock_db, redis=redis)
        redis.setex.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_cache_write_on_success(self, mock_db, override_settings):
        """포지션 있을 때 최종 결과를 Redis에 캐시 저장한다."""
        snap = SimpleNamespace(id=uuid.uuid4())
        acc = SimpleNamespace(id=uuid.uuid4(), is_active=True)
        pos = SimpleNamespace(
            ticker="005930", market="KOSPI", name="삼성전자",
            value_krw=1_000_000.0, snapshot_id=snap.id,
        )

        snap_result = MagicMock()
        snap_result.all.return_value = [(snap, acc)]
        pos_result = MagicMock()
        pos_result.scalars.return_value.all.return_value = [pos]
        mock_db.execute = AsyncMock(side_effect=[snap_result, pos_result])

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)
        redis.setex = AsyncMock()

        factor_data = {"005930.KS": {"pe_ratio": 10.0, "pb_ratio": 1.0, "market_cap": 3e11, "momentum_pct": 5.0}}
        with patch("asyncio.get_running_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=factor_data)
            await get_factor_analysis(uuid.uuid4(), mock_db, redis=redis)

        redis.setex.assert_called_once()
