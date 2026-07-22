"""Pydantic 스키마 validator 단위 테스트 — API 진입 없이 모델 인스턴스만 검증."""

from __future__ import annotations

import uuid

import pytest

# ── RebalancingAlertCreate 검증 ──────────────────────────────


def _make_base() -> dict:
    return {"portfolio_id": str(uuid.uuid4())}


def test_validate_dow_returns_valid_value():
    from app.schemas.rebalancing import RebalancingAlertCreate

    model = RebalancingAlertCreate(**_make_base(), schedule_day_of_week=3)
    assert model.schedule_day_of_week == 3


def test_validate_dom_valid_value():
    from app.schemas.rebalancing import RebalancingAlertCreate

    model = RebalancingAlertCreate(**_make_base(), schedule_day_of_month=15)
    assert model.schedule_day_of_month == 15


def test_validate_dom_out_of_range_raises():
    from pydantic import ValidationError

    from app.schemas.rebalancing import RebalancingAlertCreate

    with pytest.raises(ValidationError, match="schedule_day_of_month"):
        RebalancingAlertCreate(**_make_base(), schedule_day_of_month=29)


def test_validate_auto_execution_time_none_returns_none():
    from app.schemas.rebalancing import RebalancingAlertCreate

    model = RebalancingAlertCreate(**_make_base(), auto_execution_time=None)
    assert model.auto_execution_time is None


def test_validate_auto_execution_time_valid_format():
    from app.schemas.rebalancing import RebalancingAlertCreate

    model = RebalancingAlertCreate(**_make_base(), auto_execution_time="09:30")
    assert model.auto_execution_time == "09:30"


def test_validate_auto_execution_time_invalid_format_raises():
    from pydantic import ValidationError

    from app.schemas.rebalancing import RebalancingAlertCreate

    with pytest.raises(ValidationError, match="auto_execution_time"):
        RebalancingAlertCreate(**_make_base(), auto_execution_time="invalid")


def test_validate_auto_execution_time_out_of_range_raises():
    from pydantic import ValidationError

    from app.schemas.rebalancing import RebalancingAlertCreate

    with pytest.raises(ValidationError, match="auto_execution_time"):
        RebalancingAlertCreate(**_make_base(), auto_execution_time="24:00")

    with pytest.raises(ValidationError, match="auto_execution_time"):
        RebalancingAlertCreate(**_make_base(), auto_execution_time="12:60")


def test_validate_auto_execution_time_accepts_full_day_range():
    """해외(NYSE) 시간대 지원 이후 KRX 정규장(09:00~15:00) 밖 시각도 허용된다 — 시장 개장 여부는
    종목별 소속 시장(KR/US)에 맞춰 leg 단위로 판단하므로 스키마는 형식만 검증한다."""
    from app.schemas.rebalancing import RebalancingAlertCreate

    for value in ("00:00", "23:59", "22:30", "20:00"):
        model = RebalancingAlertCreate(**_make_base(), auto_execution_time=value)
        assert model.auto_execution_time == value


# ── AlertCreate (exchange_rate_alerts) 검증 ──────────────────


def test_exchange_rate_alert_validate_count_raise_when_zero():
    from pydantic import ValidationError

    from app.api.v1.exchange_rate_alerts import AlertCreate

    with pytest.raises(ValidationError, match="max_trigger_count"):
        AlertCreate(target_rate=1300.0, direction="BELOW", max_trigger_count=0)


# ── StockPriceAlertCreate 검증 ───────────────────────────────


def test_stock_price_alert_validate_count_returns_valid():
    from app.api.v1.stock_price_alerts import StockPriceAlertCreate

    model = StockPriceAlertCreate(
        ticker="005930", market="KRX", name="삼성전자", target_price=80000.0, direction="ABOVE", max_trigger_count=3
    )
    assert model.max_trigger_count == 3
