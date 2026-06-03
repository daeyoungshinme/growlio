"""price_service 단위 테스트 — Yahoo Finance 우선순위 체인 검증."""

import pytest

from app.services.yahoo_price import _to_yahoo_symbol


# ── Yahoo 심볼 변환 테스트 ──────────────────────────────────

class TestToYahooSymbol:
    """_to_yahoo_symbol: 시장별 티커 변환 로직."""

    @pytest.mark.parametrize("ticker,market,expected", [
        ("005930", "KOSPI", "005930.KS"),
        ("5930", "KOSPI", "005930.KS"),   # zero-padding
        ("5930", "KRX", "005930.KS"),
        ("035720", "KOSDAQ", "035720.KQ"),
        ("35720", "KOSDAQ", "035720.KQ"),  # zero-padding
        ("AAPL", "NYSE", "AAPL"),           # 해외: 그대로
        ("TSLA", "NASDAQ", "TSLA"),
        ("NVDA", "nasdaq", "NVDA"),         # 소문자 market도 처리
    ])
    def test_symbol_conversion(self, ticker, market, expected):
        assert _to_yahoo_symbol(ticker, market) == expected


# ── fetch_current_price 우선순위 체인 테스트 ────────────────

class TestFetchCurrentPrice:
    """Yahoo 실패 → KIS → LS 순서로 fallback 되는지 검증."""

    @pytest.mark.asyncio
    async def test_returns_yahoo_price_when_available(self, mock_db, mock_redis, override_settings):
        """Yahoo Finance 가격 조회 성공 시 바로 반환."""
        from unittest.mock import AsyncMock, patch

        import uuid
        user_id = uuid.uuid4()

        with patch("app.services.price_service._sync_yahoo_price", return_value=75000.0):
            with patch("asyncio.get_event_loop") as mock_loop:
                mock_executor = AsyncMock(return_value=75000.0)
                mock_loop.return_value.run_in_executor = mock_executor

                from app.services.price_service import fetch_current_price
                # DB 조회 없이 Yahoo가 성공하면 DB 없어도 됨
                # (실제 내부 구현상 DB 조회 후 KIS/LS 체인이므로 mock 필요)
                mock_db.scalar.return_value = None  # UserSettings 없음 → KIS/LS skip

                price = await fetch_current_price(user_id, "005930", "KOSPI", mock_db, mock_redis)
                # Yahoo가 성공했으므로 75000 반환
                assert price == 75000.0

    @pytest.mark.asyncio
    async def test_returns_none_when_all_providers_fail(self, mock_db, mock_redis, override_settings):
        """모든 provider 실패 시 None 반환 (예외 없음)."""
        import uuid
        from unittest.mock import AsyncMock, patch

        user_id = uuid.uuid4()
        mock_db.scalar.return_value = None  # UserSettings 없음

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock(return_value=None)

            from app.services.price_service import fetch_current_price
            price = await fetch_current_price(user_id, "UNKNOWN", "NYSE", mock_db, mock_redis)
            assert price is None


# ── 배치 조회 테스트 ────────────────────────────────────────

class TestFetchPricesBatch:
    """fetch_prices_batch: 여러 종목 일괄 조회."""

    @pytest.mark.asyncio
    async def test_empty_tickers_returns_empty(self, mock_db, mock_redis, override_settings):
        """빈 목록 입력 시 빈 딕셔너리 반환."""
        import uuid
        from app.services.price_service import fetch_prices_batch

        result = await fetch_prices_batch(uuid.uuid4(), [], mock_db, mock_redis)
        assert result == {}
