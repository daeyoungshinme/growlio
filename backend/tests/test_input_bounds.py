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
