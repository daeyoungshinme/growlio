"""KIS/키움 실주문 함수의 HTTP 요청 형태 고정 (docs/plans/36 #5).

주문 실행기 테스트(`test_kis_order_executor.py` 등)는 `place_*_order`를 AsyncMock으로 바꿔치기하므로
TR id·계좌번호 분리·요청 바디·주문구분 코드가 틀어져도 잡지 못한다. 여기서는 pytest-httpx로 실제
httpx 요청을 가로채 브로커가 받는 요청 그대로를 검증한다 — 실거래 경로라 회귀 비용이 가장 크다.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pytest_httpx import HTTPXMock

from app.kis import order as kis_order
from app.kis.constants import KIS_MOCK_BASE_URL, KIS_REAL_BASE_URL
from app.kiwoom import order as kiwoom_order
from app.kiwoom.constants import KIWOOM_MOCK_BASE_URL, KIWOOM_REAL_BASE_URL

KIS_DOMESTIC_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
KIS_OVERSEAS_PATH = "/uapi/overseas-stock/v1/trading/order"
KIWOOM_DOMESTIC_PATH = "/api/dostk/ordr"
KIWOOM_OVERSEAS_PATH = "/api/us/ordr"


def _body(request: httpx.Request) -> dict:
    return json.loads(request.content)


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """KIS 초당 호출 제한(AsyncRateLimiter)이 케이스마다 ~1초 대기를 넣어 — 요청 형태 검증과 무관하므로 끈다."""
    from app.kis import client as kis_client
    from app.kiwoom import client as kiwoom_client

    monkeypatch.setattr(kis_client._rate_limiter, "acquire", AsyncMock())
    monkeypatch.setattr(kiwoom_client._rate_limiter, "acquire", AsyncMock())


# ── KIS 국내 ─────────────────────────────────────────────────────────────────


class TestKisDomesticOrder:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("side", "is_mock", "tr_id", "base_url"),
        [
            ("BUY", False, "TTTC0802U", KIS_REAL_BASE_URL),
            ("SELL", False, "TTTC0801U", KIS_REAL_BASE_URL),
            ("BUY", True, "VTTC0802U", KIS_MOCK_BASE_URL),
            ("SELL", True, "VTTC0801U", KIS_MOCK_BASE_URL),
        ],
    )
    async def test_market_order_request(self, httpx_mock: HTTPXMock, side, is_mock, tr_id, base_url):
        httpx_mock.add_response(
            method="POST", url=f"{base_url}{KIS_DOMESTIC_PATH}", json={"rt_cd": "0", "output": {"ODNO": "0001"}}
        )

        result = await kis_order.place_domestic_order(
            "key", "secret", "tok", "12345678-01", side=side, ticker="069500", quantity=3, is_mock=is_mock
        )

        assert result["order_no"] == "0001"
        (request,) = httpx_mock.get_requests()
        assert request.headers["tr_id"] == tr_id
        assert request.headers["authorization"] == "Bearer tok"
        assert request.headers["appkey"] == "key"
        body = _body(request)
        assert body["CANO"] == "12345678"
        assert body["ACNT_PRDT_CD"] == "01"
        assert body["PDNO"] == "069500"
        assert body["ORD_DVSN"] == "01"  # 시장가
        assert body["ORD_QTY"] == "3"
        assert body["ORD_UNPR"] == "0"
        assert ("SLL_TYPE" in body) is (side == "SELL")

    @pytest.mark.asyncio
    async def test_limit_order_and_unhyphenated_account(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json={"rt_cd": "0", "output": {"ODNO": "0002"}})

        await kis_order.place_domestic_order(
            "key",
            "secret",
            "tok",
            "1234567822",
            side="BUY",
            ticker="005930",
            quantity=1,
            is_mock=False,
            order_type="LIMIT",
            limit_price=71_500.7,
        )

        body = _body(httpx_mock.get_requests()[0])
        assert (body["CANO"], body["ACNT_PRDT_CD"]) == ("12345678", "22")
        assert body["ORD_DVSN"] == "00"  # 지정가
        assert body["ORD_UNPR"] == "71500"  # 원화는 정수 호가

    @pytest.mark.asyncio
    async def test_rejection_raises(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json={"rt_cd": "7", "msg1": "주문가능금액을 초과했습니다"})

        with pytest.raises(Exception, match="주문가능금액"):
            await kis_order.place_domestic_order(
                "key", "secret", "tok", "12345678-01", side="BUY", ticker="069500", quantity=1, is_mock=False
            )

    @pytest.mark.asyncio
    async def test_network_error_is_not_retried(self, httpx_mock: HTTPXMock):
        """응답 유실 시 같은 주문을 재전송하면 중복 체결될 수 있다 — 한 번만 보내고 실패해야 한다."""
        httpx_mock.add_exception(httpx.ReadTimeout("timeout"))

        with pytest.raises(RuntimeError, match="재시도 비활성화"):
            await kis_order.place_domestic_order(
                "key", "secret", "tok", "12345678-01", side="BUY", ticker="069500", quantity=1, is_mock=False
            )
        assert len(httpx_mock.get_requests()) == 1


# ── KIS 해외 ─────────────────────────────────────────────────────────────────


class TestKisOverseasOrder:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("side", "is_mock", "tr_id"),
        [
            ("BUY", False, "TTTT1002U"),
            ("SELL", False, "TTTT1006U"),
            ("BUY", True, "VTTT1002U"),
            ("SELL", True, "VTTT1006U"),
        ],
    )
    async def test_tr_id_by_side_and_mode(self, httpx_mock: HTTPXMock, side, is_mock, tr_id):
        base_url = KIS_MOCK_BASE_URL if is_mock else KIS_REAL_BASE_URL
        httpx_mock.add_response(
            method="POST", url=f"{base_url}{KIS_OVERSEAS_PATH}", json={"rt_cd": "0", "output": {"ODNO": "9"}}
        )

        await kis_order.place_overseas_order(
            "key",
            "secret",
            "tok",
            "12345678-01",
            side=side,
            ticker="AAPL",
            market="NASDAQ",
            quantity=2,
            is_mock=is_mock,
        )

        request = httpx_mock.get_requests()[0]
        assert request.headers["tr_id"] == tr_id
        body = _body(request)
        assert body["OVRS_EXCG_CD"] == "NASD"
        assert body["PDNO"] == "AAPL"
        assert body["ORD_QTY"] == "2"
        assert body["OVRS_ORD_UNPR"] == "0"
        assert body["ORD_SVR_DVSN_CD"] == "0"
        assert body.get("SLL_TYPE") == ("00" if side == "SELL" else None)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("market", "code"), [("NYSE", "NYSE"), ("amex", "AMEX"), ("UNKNOWN", "NASD")])
    async def test_exchange_code_and_limit_price(self, httpx_mock: HTTPXMock, market, code):
        httpx_mock.add_response(json={"rt_cd": "0", "output": {}})

        await kis_order.place_overseas_order(
            "key",
            "secret",
            "tok",
            "12345678-01",
            side="BUY",
            ticker="SPY",
            market=market,
            quantity=1,
            is_mock=False,
            order_type="LIMIT",
            limit_price=512.345,
        )

        body = _body(httpx_mock.get_requests()[0])
        assert body["OVRS_EXCG_CD"] == code
        assert body["ORD_DVSN"] == "00"
        assert body["OVRS_ORD_UNPR"] == "512.35"  # 달러는 소수 둘째 자리


# ── 키움 국내 ────────────────────────────────────────────────────────────────


class TestKiwoomDomesticOrder:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("side", "api_id", "is_mock", "base_url"),
        [
            ("BUY", "kt10000", False, KIWOOM_REAL_BASE_URL),
            ("SELL", "kt10001", False, KIWOOM_REAL_BASE_URL),
            ("BUY", "kt10000", True, KIWOOM_MOCK_BASE_URL),
        ],
    )
    async def test_market_order_request(self, httpx_mock: HTTPXMock, side, api_id, is_mock, base_url):
        httpx_mock.add_response(
            method="POST", url=f"{base_url}{KIWOOM_DOMESTIC_PATH}", json={"return_code": 0, "ord_no": "K1"}
        )

        result = await kiwoom_order.place_domestic_order(
            "tok", "5012345678", side=side, ticker="069500", quantity=4, is_mock=is_mock
        )

        assert result["order_no"] == "K1"
        request = httpx_mock.get_requests()[0]
        assert request.headers["api-id"] == api_id
        assert request.headers["authorization"] == "Bearer tok"
        assert _body(request) == {
            "acnt_no": "5012345678",  # 키움은 계좌번호를 분리하지 않고 그대로 보낸다
            "dmst_stex_tp": "KRX",
            "stk_cd": "069500",
            "ord_qty": "4",
            "ord_uv": "0",
            "trde_tp": "3",  # 시장가(1자리)
        }

    @pytest.mark.asyncio
    async def test_limit_order(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json={"return_code": 0, "ord_no": "K2"})

        await kiwoom_order.place_domestic_order(
            "tok",
            "5012345678",
            side="SELL",
            ticker="005930",
            quantity=1,
            is_mock=False,
            order_type="LIMIT",
            limit_price=70_100.0,
        )

        body = _body(httpx_mock.get_requests()[0])
        assert (body["trde_tp"], body["ord_uv"]) == ("0", "70100")

    @pytest.mark.asyncio
    async def test_rejection_raises(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json={"return_code": 20, "return_msg": "주문수량이 부족합니다"})

        with pytest.raises(Exception, match="주문수량"):
            await kiwoom_order.place_domestic_order(
                "tok", "5012345678", side="SELL", ticker="005930", quantity=1, is_mock=False
            )

    @pytest.mark.asyncio
    async def test_network_error_is_not_retried(self, httpx_mock: HTTPXMock):
        httpx_mock.add_exception(httpx.ConnectError("reset"))

        with pytest.raises(RuntimeError, match="재시도 비활성화"):
            await kiwoom_order.place_domestic_order(
                "tok", "5012345678", side="BUY", ticker="069500", quantity=1, is_mock=False
            )
        assert len(httpx_mock.get_requests()) == 1


# ── 키움 해외 ────────────────────────────────────────────────────────────────


class TestKiwoomOverseasOrder:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("side", "api_id", "market", "stex_tp"),
        [
            ("BUY", "ust20000", "NASDAQ", "ND"),
            ("SELL", "ust20001", "NYSE", "NY"),
            ("BUY", "ust20000", "AMEX", "NA"),
            ("BUY", "ust20000", "UNKNOWN", "ND"),
        ],
    )
    async def test_market_order_request(self, httpx_mock: HTTPXMock, side, api_id, market, stex_tp):
        httpx_mock.add_response(
            method="POST", url=f"{KIWOOM_REAL_BASE_URL}{KIWOOM_OVERSEAS_PATH}", json={"return_code": 0, "ord_no": "U1"}
        )

        await kiwoom_order.place_overseas_order(
            "tok", "5012345678", side=side, ticker="SPY", market=market, quantity=5, is_mock=False
        )

        request = httpx_mock.get_requests()[0]
        assert request.headers["api-id"] == api_id
        assert _body(request) == {
            "acnt_no": "5012345678",
            "stex_tp": stex_tp,  # 국내 주문의 dmst_stex_tp와 필드명이 다르다
            "stk_cd": "SPY",
            "ord_qty": "5",
            "ord_uv": "0",
            "trde_tp": "03",  # 해외는 2자리 코드
        }

    @pytest.mark.asyncio
    async def test_limit_order(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(json={"return_code": 0, "ord_no": "U2"})

        await kiwoom_order.place_overseas_order(
            "tok",
            "5012345678",
            side="BUY",
            ticker="QQQ",
            market="NASDAQ",
            quantity=1,
            is_mock=False,
            order_type="LIMIT",
            limit_price=431.1,
        )

        body = _body(httpx_mock.get_requests()[0])
        assert (body["trde_tp"], body["ord_uv"]) == ("00", "431.10")
