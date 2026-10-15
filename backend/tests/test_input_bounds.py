"""요청 스키마 입력 범위 — DB 컬럼 길이·수치 범위를 넘는 값은 500이 아니라 422로 거부한다(계획 57 C5)."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError


def test_amount_validators_reject_nan_and_infinity():
    from app.schemas._validators import validate_non_negative_amount, validate_positive_amount

    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="올바른 숫자"):
            validate_positive_amount(bad)
        with pytest.raises(ValueError, match="올바른 숫자"):
            validate_non_negative_amount(bad)


def test_portfolio_name_and_item_lengths_follow_columns():
    from app.schemas.portfolio import PortfolioCreate

    item = {"ticker": "005930", "name": "삼성전자", "market": "KOSPI", "weight": 100}
    with pytest.raises(ValidationError):
        PortfolioCreate(name="x" * 101, items=[item])
    with pytest.raises(ValidationError):
        PortfolioCreate(name="ok", items=[{**item, "ticker": "X" * 21}])
    assert PortfolioCreate(name="x" * 100, items=[item]).name == "x" * 100


def test_credential_length_fits_encrypted_column():
    # AES-GCM hex 저장값이 String(512)를 넘지 않는 평문 길이까지만 받는다
    from app.schemas.asset import MAX_CREDENTIAL_LENGTH, AssetAccountUpdate
    from app.services.credential_service import encrypt

    with pytest.raises(ValidationError):
        AssetAccountUpdate(kis_app_secret="s" * (MAX_CREDENTIAL_LENGTH + 1))
    assert AssetAccountUpdate(kis_app_secret="s" * MAX_CREDENTIAL_LENGTH)
    assert len(encrypt("s" * MAX_CREDENTIAL_LENGTH)) <= 512


def test_manual_position_rejects_negative_current_price():
    from app.schemas.asset import ManualPosition

    with pytest.raises(ValidationError):
        ManualPosition(ticker="005930", name="삼성전자", qty=1, avg_price=70000, current_price=-1)


def test_execution_order_side_must_be_buy_or_sell():
    from app.schemas.rebalancing.execution import ExecutionOrderItem

    with pytest.raises(ValidationError):
        ExecutionOrderItem(ticker="005930", name="삼성전자", market="KOSPI", side="buy", quantity=1)


def test_alert_inputs_bounded_by_columns():
    from app.api.v1.exchange_rate_alerts import AlertCreate
    from app.api.v1.stock_price_alerts import StockPriceAlertCreate

    with pytest.raises(ValidationError):
        StockPriceAlertCreate(ticker="X" * 21, market="KOSPI", name="n", target_price=1000, direction="ABOVE")
    with pytest.raises(ValidationError):
        AlertCreate(target_rate=1e9, direction="ABOVE")


def test_backtest_start_date_and_portfolio_count_bounded():
    from datetime import date

    from app.schemas.backtest import BacktestRunRequest

    with pytest.raises(ValidationError):
        BacktestRunRequest(portfolio_ids=[], start_date=date(1900, 1, 1), end_date=date(2020, 1, 1))
    # 빈 목록은 SPY·실포트폴리오만 비교하는 정상 요청
    assert BacktestRunRequest(portfolio_ids=[], start_date=date(2015, 1, 1), end_date=date(2020, 1, 1))


def test_public_error_message_hides_unexpected_and_keeps_domain_messages():
    import httpx
    from fastapi import HTTPException

    from app.core.logging import public_error_message
    from app.exceptions import BrokerOrderRejectedError, ProviderApiError
    from app.providers.http_client import BrokerRequestError

    assert public_error_message(HTTPException(status_code=400, detail="잘못된 요청")) == "잘못된 요청"
    assert public_error_message(ProviderApiError("KIS API 오류: 잔고 없음")) == "KIS API 오류: 잔고 없음"
    assert public_error_message(BrokerOrderRejectedError("주문가능금액 부족")) == "주문가능금액 부족"
    assert "실제 접수 여부 불명" in public_error_message(BrokerRequestError("서버 오류 500(실제 접수 여부 불명)"))
    request = httpx.Request("GET", "https://broker.example/inquire?CANO=12345678")
    leaked = httpx.HTTPStatusError("400", request=request, response=httpx.Response(400, request=request))
    assert "12345678" not in public_error_message(leaked)


def test_http_status_fallback_does_not_include_url():
    import httpx

    from app.providers._error_mapping import map_http_status_error

    request = httpx.Request("GET", "https://broker.example/inquire?CANO=12345678")
    err = httpx.HTTPStatusError(
        "400 for url ...CANO=12345678", request=request, response=httpx.Response(400, request=request)
    )
    mapped = map_http_status_error(err, broker_name="KIS", message_key="msg1")
    assert "12345678" not in mapped.detail
    assert "HTTP 400" in mapped.detail
