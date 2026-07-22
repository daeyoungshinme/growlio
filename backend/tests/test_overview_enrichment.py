"""overview_enrichment 단위 테스트.

QLD(ProShares Ultra QQQ) 397,071주 매수 수량 버그 회귀 방지 — 미보유 해외 종목의
현재가를 원시 USD 그대로 채워 넣으면, 이후 analyze_rebalancing()이 KRW 목표금액을
USD 가격으로 나눠 수량이 환율 배수(~1,300배)만큼 부풀려진다. enrich_overview_with_prices()는
반드시 KRW 환산된 가격(fetch_prices_batch_krw)을 써야 한다.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.rebalancing.overview_enrichment import enrich_overview_with_prices
from app.services.rebalancing.service import analyze_rebalancing


def _make_portfolio(items: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name="해외 ETF 포트폴리오", base_type="STOCK_ONLY", items=items)


class TestEnrichOverviewWithPrices:
    @pytest.mark.asyncio
    async def test_overseas_unheld_ticker_converted_to_krw(self, mock_db, mock_cache, override_settings):
        """QLD처럼 미보유 해외 종목의 현재가는 KRW로 환산되어 overview에 채워져야 한다."""
        portfolio = _make_portfolio(
            [{"ticker": "QLD", "name": "ProShares Ultra QQQ", "market": "NASDAQ", "weight": 100}]
        )
        overview = {"all_positions": []}

        with (
            patch(
                "app.services.price_service.fetch_prices_batch",
                new=AsyncMock(return_value={"QLD": 95.0}),
            ),
            patch(
                "app.services.price_service.get_usd_krw_rate",
                new=AsyncMock(return_value=1385.0),
            ),
        ):
            result = await enrich_overview_with_prices(portfolio, overview, uuid.uuid4(), mock_db, mock_cache)

        qld_position = next(p for p in result["all_positions"] if p["ticker"] == "QLD")
        # 원시 USD(95.0)가 아니라 KRW 환산 가격(95.0 * 1385.0)이어야 한다.
        assert qld_position["current_price"] == pytest.approx(95.0 * 1385.0)

    @pytest.mark.asyncio
    async def test_full_pipeline_produces_sane_share_count(self, mock_db, mock_cache, override_settings):
        """enrich → analyze_rebalancing 전체 경로에서 매수 수량이 환율 배수만큼 부풀려지지 않아야 한다.

        1천만원 목표금액을 QLD(실제 USD가 $95, 환율 1,385원 → 약 131,575원/주)로 매수하면
        수십~수백 주 단위여야 한다 — 수정 전 버그처럼 수만~수십만 주가 나오면 회귀.
        """
        portfolio = _make_portfolio(
            [{"ticker": "QLD", "name": "ProShares Ultra QQQ", "market": "NASDAQ", "weight": 100}]
        )
        overview = {
            "total_assets_krw": 10_000_000,
            "total_stock_krw": 0,
            "all_positions": [],
        }

        with (
            patch(
                "app.services.price_service.fetch_prices_batch",
                new=AsyncMock(return_value={"QLD": 95.0}),
            ),
            patch(
                "app.services.price_service.get_usd_krw_rate",
                new=AsyncMock(return_value=1385.0),
            ),
        ):
            enriched_overview = await enrich_overview_with_prices(
                portfolio, overview, uuid.uuid4(), mock_db, mock_cache
            )

        result = analyze_rebalancing(portfolio, enriched_overview)
        qld_item = next(i for i in result.items if i.ticker == "QLD")

        expected_price_krw = 95.0 * 1385.0
        expected_shares = 10_000_000 // expected_price_krw  # floor(target_value / price)

        assert qld_item.shares_to_trade == pytest.approx(expected_shares)
        # 회귀 방지: 버그가 있었다면 환율(~1,385)배 부풀려져 수만 주 단위가 됐을 것.
        assert qld_item.shares_to_trade < 1_000
