"""Pydantic 스키마 validator 단위 테스트 — API 진입 없이 모델 인스턴스만 검증."""

from __future__ import annotations

import uuid

import pytest


# ── _account_queries 헬퍼 ────────────────────────────────────


def test_active_accounts_filter_returns_tuple():
    from app.services._account_queries import active_accounts_filter

    result = active_accounts_filter()
    assert isinstance(result, tuple)
    assert len(result) == 1


# ── RebalancingAlertCreate 검증 ──────────────────────────────


def _make_base() -> dict:
    return {"portfolio_id": str(uuid.uuid4())}


def test_validate_dow_returns_valid_value():
    from app.api.v1.rebalancing_alerts import RebalancingAlertCreate

    model = RebalancingAlertCreate(**_make_base(), schedule_day_of_week=3)
    assert model.schedule_day_of_week == 3


def test_validate_dom_valid_value():
    from app.api.v1.rebalancing_alerts import RebalancingAlertCreate

    model = RebalancingAlertCreate(**_make_base(), schedule_day_of_month=15)
    assert model.schedule_day_of_month == 15


def test_validate_dom_out_of_range_raises():
    from app.api.v1.rebalancing_alerts import RebalancingAlertCreate

    with pytest.raises(Exception):
        RebalancingAlertCreate(**_make_base(), schedule_day_of_month=29)


def test_validate_auto_execution_time_none_returns_none():
    from app.api.v1.rebalancing_alerts import RebalancingAlertCreate

    model = RebalancingAlertCreate(**_make_base(), auto_execution_time=None)
    assert model.auto_execution_time is None


def test_validate_auto_execution_time_valid_format():
    from app.api.v1.rebalancing_alerts import RebalancingAlertCreate

    model = RebalancingAlertCreate(**_make_base(), auto_execution_time="09:30")
    assert model.auto_execution_time == "09:30"


def test_validate_auto_execution_time_invalid_format_raises():
    from app.api.v1.rebalancing_alerts import RebalancingAlertCreate

    with pytest.raises(Exception):
        RebalancingAlertCreate(**_make_base(), auto_execution_time="invalid")


def test_validate_auto_execution_time_out_of_range_raises():
    from app.api.v1.rebalancing_alerts import RebalancingAlertCreate

    with pytest.raises(Exception):
        RebalancingAlertCreate(**_make_base(), auto_execution_time="08:00")


# ── AlertCreate (exchange_rate_alerts) 검증 ──────────────────


def test_exchange_rate_alert_validate_count_raise_when_zero():
    from app.api.v1.exchange_rate_alerts import AlertCreate

    with pytest.raises(Exception):
        AlertCreate(target_rate=1300.0, direction="BELOW", max_trigger_count=0)


# ── StockPriceAlertCreate 검증 ───────────────────────────────


def test_stock_price_alert_validate_count_returns_valid():
    from app.api.v1.stock_price_alerts import StockPriceAlertCreate

    model = StockPriceAlertCreate(
        ticker="005930", market="KRX", name="삼성전자", target_price=80000.0, direction="ABOVE", max_trigger_count=3
    )
    assert model.max_trigger_count == 3
