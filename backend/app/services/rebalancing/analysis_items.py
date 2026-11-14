"""리밸런싱 분석 항목 헬퍼 — 항목 필드 접근(ORM·dict 겸용), 지수 그룹 행 조립, 현재 보유 맵, 배당 정보.

`service.analyze_rebalancing`과 개요 보강(`overview_enrichment`)·라우터가 함께 쓴다.
"""

from __future__ import annotations

from typing import Any

import structlog

from app.schemas.rebalancing import RebalancingItem
from app.schemas.service_dtypes import DividendMapEntry, PositionMapEntry, ReturnsMapEntry
from app.services.rebalancing.group_expansion import ROLE_PRIMARY, allocate_group_trades
from app.utils.numbers import opt_float

logger = structlog.get_logger()


def _item_attr(item: object, field: str) -> Any:
    """PortfolioItem ORM 객체 또는 레거시 dict에서 필드를 통합 조회한다."""
    return item[field] if isinstance(item, dict) else getattr(item, field)


def _item_get(item: object, field: str, default: Any = None) -> Any:
    """`_item_attr`의 선택 필드 버전 — 지수 그룹 필드가 없는 레거시 dict·테스트 stub 대응."""
    return item.get(field, default) if isinstance(item, dict) else getattr(item, field, default)


def _group_member_keys(item: object) -> list[tuple[str, str, str, str, float]]:
    """그룹 항목의 (ticker, market, name, role, 레버리지 배수) 목록 — 대표 종목(1배)이 맨 앞."""
    keys = [
        (
            str(_item_attr(item, "ticker")),
            str(_item_attr(item, "market")),
            str(_item_attr(item, "name")),
            ROLE_PRIMARY,
            1.0,
        )
    ]
    for m in _item_get(item, "members") or []:
        keys.append(
            (
                str(_item_attr(m, "ticker")),
                str(_item_attr(m, "market")),
                str(_item_attr(m, "name")),
                str(_item_attr(m, "role")),
                float(_item_get(m, "leverage") or 1.0),
            )
        )
    return keys


def _build_group_item(
    item: object,
    base_krw: float,
    current_map: dict[tuple[str, str], PositionMapEntry],
    dividend_map: dict[tuple[str, str], DividendMapEntry] | None,
    returns_map: dict[tuple[str, str], ReturnsMapEntry] | None,
) -> RebalancingItem:
    """지수 그룹 항목(plans/74) — 대표 종목+멤버 보유액 합계로 이탈을 보는 그룹 행과 종목별 members를 만든다.

    그룹 행의 현재 가치·비중은 노출 기준(평가액 × 레버리지 배수, QLD 100만원 = 200만원)이고 멤버 행은 실제 평가액이다.

    그룹 행 자체는 매매 수량이 없고(shares_to_trade=None), members에 대표 종목으로 매수한다고 가정한
    배분 결과가 들어간다. 실제 주문은 매수 계좌가 정해진 뒤 `group_expansion.expand_group_items`가 다시 배분한다.
    """
    weight = float(_item_attr(item, "weight"))
    target_value = base_krw * (weight / 100.0)
    members: list[RebalancingItem] = []
    for ticker, market, name, role, leverage in _group_member_keys(item):
        pos = current_map.get((ticker, market))
        value = pos["value_krw"] if pos else 0.0
        qty = pos.get("qty", 0.0) if pos else 0.0
        price = pos.get("current_price") if pos else None
        effective_price = _effective_price(price, value, qty, ticker, market)
        div_yield, annual_div = _div_info(ticker, market, dividend_map)
        ret = returns_map.get((ticker, market)) if returns_map else None
        current_weight = (value / base_krw * 100) if base_krw > 0 else 0.0
        members.append(
            RebalancingItem(
                ticker=ticker,
                name=(pos.get("name") if pos else None) or name,
                market=market,
                target_weight_pct=round(current_weight, 2),
                current_weight_pct=round(current_weight, 2),
                weight_diff_pct=0.0,
                current_value_krw=round(value, 0),
                target_value_krw=round(value, 0),
                diff_krw=0.0,
                shares_to_trade=0.0,
                current_price_krw=opt_float(effective_price),
                current_qty=qty,
                target_qty=qty,
                dividend_yield=div_yield,
                annual_dividend_current_krw=round(annual_div, 0),
                annual_dividend_target_krw=round(annual_div, 0),
                return_10y_pct=ret["cumulative_return_pct"] if ret else None,
                cagr_10y_pct=ret["cagr_pct"] if ret else None,
                actual_years_10y=ret["actual_years"] if ret else None,
                group_role=role,
                leverage=leverage,
            )
        )

    current_value = sum(m.current_value_krw * (m.leverage or 1.0) for m in members)
    current_weight_pct = (current_value / base_krw * 100) if base_krw > 0 else 0.0
    primary = members[0]
    annual_div_current = sum(m.annual_dividend_current_krw for m in members)
    if annual_div_current > 0 and current_value > 0:
        annual_div_target = annual_div_current * (target_value / current_value)
    elif primary.dividend_yield:
        annual_div_target = target_value * (primary.dividend_yield / 100)
    else:
        annual_div_target = 0.0
    label = _item_get(item, "group_label") or str(_item_attr(item, "name"))
    group = RebalancingItem(
        ticker=primary.ticker,
        name=label,
        market=primary.market,
        target_weight_pct=round(weight, 2),
        current_weight_pct=round(current_weight_pct, 2),
        weight_diff_pct=round(weight - current_weight_pct, 2),
        current_value_krw=round(current_value, 0),
        target_value_krw=round(target_value, 0),
        diff_krw=round(target_value - current_value, 0),
        shares_to_trade=None,
        current_price_krw=primary.current_price_krw,
        dividend_yield=primary.dividend_yield,
        annual_dividend_current_krw=round(annual_div_current, 0),
        annual_dividend_target_krw=round(annual_div_target, 0),
        annual_dividend_diff_krw=round(annual_div_target - annual_div_current, 0),
        return_10y_pct=primary.return_10y_pct,
        cagr_10y_pct=primary.cagr_10y_pct,
        actual_years_10y=primary.actual_years_10y,
        group_key=str(_item_get(item, "group_key")),
        group_label=label,
        members=members,
    )
    group.members = allocate_group_trades(group)
    return group


def _effective_price(
    current_price: Any,
    current_value: float,
    current_qty: float,
    ticker: str,
    market: str,
) -> float | None:
    """가격 필드가 비어있을 때 보유 평가금액/수량 비율을 폴백 가격으로 사용한다.

    브로커 동기화 시 current_price/avg_price가 모두 누락돼도 평가금액(value_krw)은
    별도 필드에서 채워지는 경우가 있어, 이 경우 수량 계산이 불가능해 매도 주문이
    통째로 스킵되는 것을 방지한다.
    """
    if current_price and float(current_price) > 0:
        return float(current_price)
    if current_qty and current_qty > 0 and current_value > 0:
        implied = current_value / current_qty
        logger.info(
            "rebalancing_price_fallback_used",
            ticker=ticker,
            market=market,
            current_qty=current_qty,
            implied_price=implied,
        )
        return implied
    return None


def _build_current_map(overview: dict) -> dict[tuple[str, str], PositionMapEntry]:
    """overview의 all_positions에서 (ticker, market) → 현재 보유 현황 맵을 구성한다."""
    current_map: dict[tuple[str, str], PositionMapEntry] = {}
    for p in overview.get("all_positions", []):
        key = (p["ticker"], p["market"])
        if key not in current_map:
            current_map[key] = PositionMapEntry(
                value_krw=0.0,
                current_price=p.get("current_price"),
                name=p.get("name", ""),
                qty=0.0,
            )
        current_map[key]["value_krw"] += float(p.get("value_krw", 0))
        current_map[key]["qty"] += float(p.get("qty", 0))
    return current_map


def _div_info(
    ticker: str,
    market: str,
    dividend_map: dict[tuple[str, str], DividendMapEntry] | None,
) -> tuple[float | None, float]:
    """배당 수익률과 연간 배당 추정액(KRW)을 반환한다."""
    if not dividend_map:
        return None, 0.0
    d = dividend_map.get((ticker, market))
    if not d:
        return None, 0.0
    yp = float(d.get("dividend_yield") or 0)
    estimated_annual = float(d.get("estimated_annual_krw") or 0)
    if yp > 0 or estimated_annual > 0:
        return (yp if yp > 0 else None), estimated_annual
    return None, 0.0
