"""app/toss/balance.py 테스트 — accountSeq 해석 · holdings/buying-power 파싱."""

from unittest.mock import AsyncMock, patch

import pytest

from app.exceptions import ProviderCredentialError
from app.toss import balance as toss_balance


@pytest.fixture
def cache():
    c = AsyncMock()
    c.get = AsyncMock(return_value=None)
    c.setex = AsyncMock()
    return c


class TestResolveAccountSeq:
    @pytest.mark.asyncio
    async def test_matches_by_account_no(self, cache):
        accounts = {
            "result": [
                {"accountNo": "111-11", "accountSeq": 1, "accountType": "BROKERAGE"},
                {"accountNo": "222-22", "accountSeq": 2, "accountType": "PENSION_SAVINGS"},
            ]
        }
        with patch("app.toss.balance.toss_request", AsyncMock(return_value=accounts)):
            seq = await toss_balance.resolve_account_seq("t", account_id="a", account_no="22222", cache=cache)
        assert seq == "2"
        cache.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_single_brokerage(self, cache):
        accounts = {
            "result": [
                {"accountNo": "111-11", "accountSeq": 9, "accountType": "BROKERAGE"},
                {"accountNo": "222-22", "accountSeq": 2, "accountType": "PENSION_SAVINGS"},
            ]
        }
        with patch("app.toss.balance.toss_request", AsyncMock(return_value=accounts)):
            seq = await toss_balance.resolve_account_seq("t", account_id="a", account_no="99999", cache=cache)
        assert seq == "9"

    @pytest.mark.asyncio
    async def test_multiple_brokerage_no_match_raises(self, cache):
        accounts = {
            "result": [
                {"accountNo": "111-11", "accountSeq": 1, "accountType": "BROKERAGE"},
                {"accountNo": "222-22", "accountSeq": 2, "accountType": "BROKERAGE"},
            ]
        }
        with (
            patch("app.toss.balance.toss_request", AsyncMock(return_value=accounts)),
            pytest.raises(ProviderCredentialError),
        ):
            await toss_balance.resolve_account_seq("t", account_id="a", account_no="00000", cache=cache)

    @pytest.mark.asyncio
    async def test_uses_cache_when_present(self, cache):
        cache.get = AsyncMock(return_value="42")
        with patch("app.toss.balance.toss_request", AsyncMock()) as req:
            seq = await toss_balance.resolve_account_seq("t", account_id="a", account_no="1", cache=cache)
        assert seq == "42"
        req.assert_not_called()


class TestGetBalance:
    @pytest.mark.asyncio
    async def test_parses_holdings_and_deposits(self, cache):
        holdings = {
            "result": {
                "totalPurchaseAmount": {"krw": 700000, "usd": 500},
                "marketValue": {"amount": {"krw": 750000, "usd": 600}},
                "items": [
                    {
                        "symbol": "005930",
                        "name": "삼성전자",
                        "marketCountry": "KR",
                        "currency": "KRW",
                        "quantity": 10,
                        "lastPrice": 75000,
                        "averagePurchasePrice": 70000,
                    },
                    {
                        "symbol": "AAPL",
                        "name": "Apple",
                        "marketCountry": "US",
                        "currency": "USD",
                        "quantity": 0,  # 0주 → 제외
                        "lastPrice": 200,
                        "averagePurchasePrice": 150,
                    },
                ],
            }
        }

        async def fake_request(method, path, **kwargs):
            if path == toss_balance.TOSS_ACCOUNTS_PATH:
                return {"result": [{"accountNo": "1", "accountSeq": 7, "accountType": "BROKERAGE"}]}
            if path == toss_balance.TOSS_HOLDINGS_PATH:
                return holdings
            if path == toss_balance.TOSS_BUYING_POWER_PATH:
                cur = kwargs["params"]["currency"]
                return {"result": {"currency": cur, "cashBuyingPower": 123 if cur == "KRW" else 45}}
            raise AssertionError(path)

        with patch("app.toss.balance.toss_request", side_effect=fake_request):
            result = await toss_balance.get_balance("t", account_id="a", account_no="1", cache=cache)

        assert cache.get.await_count  # accountSeq 캐시 조회
        assert len(result["positions"]) == 1
        assert result["positions"][0]["ticker"] == "005930"
        assert result["invested"] == {"krw": 700000.0, "usd": 500.0}
        assert result["market_value"] == {"krw": 750000.0, "usd": 600.0}
        assert result["deposit_krw"] == 123.0
        assert result["deposit_usd"] == 45.0

    @pytest.mark.asyncio
    async def test_buying_power_failure_falls_back_to_zero(self, cache):
        from app.toss.client import TossApiError

        async def fake_request(method, path, **kwargs):
            if path == toss_balance.TOSS_ACCOUNTS_PATH:
                return {"result": [{"accountNo": "1", "accountSeq": 7, "accountType": "BROKERAGE"}]}
            if path == toss_balance.TOSS_HOLDINGS_PATH:
                return {"result": {"items": []}}
            raise TossApiError("account-restricted", "no usd")

        with patch("app.toss.balance.toss_request", side_effect=fake_request):
            result = await toss_balance.get_balance("t", account_id="a", account_no="1", cache=cache)

        assert result["deposit_krw"] == 0.0
        assert result["deposit_usd"] == 0.0
        assert result["positions"] == []
