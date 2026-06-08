"""리밸런싱 분석 서비스."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.portfolio import Portfolio
from app.schemas.rebalancing import RebalancingAnalysis, RebalancingItem, TickerAccountInfo


def _build_current_map(overview: dict) -> dict[tuple[str, str], dict]:
    """overview의 all_positions에서 (ticker, market) → 현재 보유 현황 맵을 구성한다."""
    current_map: dict[tuple[str, str], dict] = {}
    for p in overview.get("all_positions", []):
        key = (p["ticker"], p["market"])
        if key not in current_map:
            current_map[key] = {
                "value_krw": 0.0,
                "current_price": p.get("current_price"),
                "name": p.get("name", ""),
            }
        current_map[key]["value_krw"] += float(p.get("value_krw", 0))
    return current_map


def _div_info(
    ticker: str,
    market: str,
    dividend_map: dict[tuple[str, str], dict] | None,
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


def _build_target_items(
    portfolio: Portfolio,
    base_krw: float,
    overview: dict,
    current_map: dict[tuple[str, str], dict],
    dividend_map: dict[tuple[str, str], dict] | None,
    returns_map: dict[tuple[str, str], dict] | None,
) -> tuple[list[RebalancingItem], set[tuple[str, str]]]:
    """목표 포트폴리오 항목별 RebalancingItem 리스트와 대상 키 집합을 반환한다."""
    result_items: list[RebalancingItem] = []
    target_keys: set[tuple[str, str]] = set()

    for item in portfolio.items:
        ticker = item["ticker"] if isinstance(item, dict) else item.ticker
        name = item["name"] if isinstance(item, dict) else item.name
        market = item["market"] if isinstance(item, dict) else item.market
        weight = float(item["weight"] if isinstance(item, dict) else item.weight)

        key = (ticker, market)
        target_keys.add(key)
        target_value = base_krw * (weight / 100.0)

        if ticker == "CASH":
            current_value = (
                float(overview.get("total_assets_krw", 0))
                - float(overview.get("total_stock_krw", 0))
            )
            current_price = None
            shares = None
        elif market == "KR_PROPERTY":
            current_value = sum(
                float(acc.get("amount_krw", 0))
                for acc in overview.get("accounts", [])
                if acc.get("asset_type") == "REAL_ESTATE"
                and acc.get("include_in_total", True)
            )
            current_price = None
            shares = None
        else:
            pos = current_map.get(key, {"value_krw": 0.0, "current_price": None, "name": name})
            current_value = pos["value_krw"]
            current_price = pos.get("current_price")
            diff_krw = target_value - current_value
            shares = (
                round(diff_krw / float(current_price), 0)
                if current_price and float(current_price) > 0
                else None
            )

        current_weight_pct = (current_value / base_krw * 100) if base_krw > 0 else 0.0
        diff_krw = target_value - current_value

        div_yield: float | None = None
        annual_div_current = 0.0
        annual_div_target = 0.0
        if ticker != "CASH" and market != "KR_PROPERTY":
            div_yield, annual_div_current = _div_info(ticker, market, dividend_map)
            if annual_div_current > 0 and current_value > 0:
                annual_div_target = annual_div_current * (target_value / current_value)
            elif div_yield and div_yield > 0:
                annual_div_target = target_value * (div_yield / 100)

        ret = (
            returns_map.get(key)
            if (returns_map and ticker != "CASH" and market != "KR_PROPERTY")
            else None
        )

        result_items.append(RebalancingItem(
            ticker=ticker,
            name=name,
            market=market,
            target_weight_pct=round(weight, 2),
            current_weight_pct=round(current_weight_pct, 2),
            weight_diff_pct=round(weight - current_weight_pct, 2),
            current_value_krw=round(current_value, 0),
            target_value_krw=round(target_value, 0),
            diff_krw=round(diff_krw, 0),
            shares_to_trade=shares,
            current_price_krw=float(current_price) if current_price is not None else None,
            dividend_yield=div_yield,
            annual_dividend_current_krw=round(annual_div_current, 0),
            annual_dividend_target_krw=round(annual_div_target, 0),
            annual_dividend_diff_krw=round(annual_div_target - annual_div_current, 0),
            return_10y_pct=ret["cumulative_return_pct"] if ret else None,
            cagr_10y_pct=ret["cagr_pct"] if ret else None,
            actual_years_10y=ret["actual_years"] if ret else None,
        ))

    return result_items, target_keys


def _build_untracked_items(
    current_map: dict[tuple[str, str], dict],
    target_keys: set[tuple[str, str]],
    base_krw: float,
    dividend_map: dict[tuple[str, str], dict] | None,
    returns_map: dict[tuple[str, str], dict] | None,
) -> list[RebalancingItem]:
    """목표 포트폴리오에 없는 보유 종목을 target=0 매도 아이템으로 반환한다."""
    items: list[RebalancingItem] = []
    for key, data in current_map.items():
        if key in target_keys:
            continue
        ticker_u, market_u = key
        current_value_u = data["value_krw"]
        current_price_u = data.get("current_price")
        weight_u = (current_value_u / base_krw * 100) if base_krw > 0 else 0.0
        diff_u = -current_value_u
        shares_u: float | None = (
            round(diff_u / float(current_price_u), 0)
            if current_price_u and float(current_price_u) > 0
            else None
        )

        div_yield_u, annual_div_current_u = _div_info(ticker_u, market_u, dividend_map)
        ret_u = returns_map.get(key) if (returns_map and market_u != "KR_PROPERTY") else None

        items.append(RebalancingItem(
            ticker=ticker_u,
            name=data["name"],
            market=market_u,
            target_weight_pct=0.0,
            current_weight_pct=round(weight_u, 2),
            weight_diff_pct=round(-weight_u, 2),
            current_value_krw=round(current_value_u, 0),
            target_value_krw=0.0,
            diff_krw=round(diff_u, 0),
            shares_to_trade=shares_u,
            current_price_krw=float(current_price_u) if current_price_u is not None else None,
            dividend_yield=div_yield_u,
            annual_dividend_current_krw=round(annual_div_current_u, 0),
            annual_dividend_target_krw=0.0,
            annual_dividend_diff_krw=round(-annual_div_current_u, 0),
            return_10y_pct=ret_u["cumulative_return_pct"] if ret_u else None,
            cagr_10y_pct=ret_u["cagr_pct"] if ret_u else None,
            actual_years_10y=ret_u["actual_years"] if ret_u else None,
        ))
    return items


def _calc_portfolio_cagrs(
    result_items: list[RebalancingItem],
    current_map: dict[tuple[str, str], dict],
    returns_map: dict[tuple[str, str], dict] | None,
) -> tuple[float | None, float | None]:
    """목표 포트폴리오와 현재 보유 포트폴리오의 가중 CAGR을 계산한다."""
    items_with_return = [
        i for i in result_items
        if i.cagr_10y_pct is not None and i.ticker != "CASH" and i.market != "KR_PROPERTY"
    ]

    target_weighted_cagr: float | None = None
    if items_with_return:
        target_w_sum = sum(i.target_weight_pct for i in items_with_return)
        if target_w_sum > 0:
            target_weighted_cagr = round(
                sum(i.target_weight_pct * i.cagr_10y_pct for i in items_with_return)  # type: ignore[operator]
                / target_w_sum,
                2,
            )

    current_weighted_cagr: float | None = None
    if returns_map:
        holdings = [
            (data["value_krw"], returns_map[(t, m)]["cagr_pct"])
            for (t, m), data in current_map.items()
            if returns_map.get((t, m)) and returns_map[(t, m)].get("cagr_pct") is not None
        ]
        if holdings:
            total_val = sum(v for v, _ in holdings)
            if total_val > 0:
                current_weighted_cagr = round(
                    sum(v * c for v, c in holdings) / total_val, 2
                )

    return target_weighted_cagr, current_weighted_cagr


def _build_ticker_account_map(overview: dict) -> dict[str, list[TickerAccountInfo]]:
    """보유 종목별 계좌 정보 맵을 구성한다."""
    account_meta_map = {
        str(acc.get("id", acc.get("account_id", ""))): {
            "asset_type": acc.get("asset_type", "UNKNOWN"),
            "is_mock_mode": bool(acc.get("is_mock_mode", False)),
        }
        for acc in overview.get("accounts", [])
    }

    holding_map: dict[tuple[str, str], dict] = {}
    for pos in overview.get("all_positions", []):
        pos_ticker = pos.get("ticker", "")
        acc_id = str(pos.get("account_id", ""))
        if not pos_ticker or not acc_id:
            continue
        key = (pos_ticker, acc_id)
        if key not in holding_map:
            holding_map[key] = {"account_name": pos.get("account_name", ""), "qty": 0.0, "val": 0.0}
        holding_map[key]["qty"] += float(pos.get("qty", 0))
        holding_map[key]["val"] += float(pos.get("value_krw", 0))

    ticker_account_map: dict[str, list[TickerAccountInfo]] = {}
    for (pos_ticker, acc_id), data in holding_map.items():
        meta = account_meta_map.get(acc_id, {})
        ticker_account_map.setdefault(pos_ticker, []).append(TickerAccountInfo(
            account_id=acc_id,
            account_name=data["account_name"],
            asset_type=meta.get("asset_type", "UNKNOWN"),
            quantity=round(data["qty"], 4),
            value_krw=round(data["val"], 0),
            is_mock_mode=meta.get("is_mock_mode", False),
        ))
    return ticker_account_map


def analyze_rebalancing(
    portfolio: Portfolio,
    overview: dict,
    dividend_map: dict[tuple[str, str], dict] | None = None,
    returns_map: dict[tuple[str, str], dict] | None = None,
) -> RebalancingAnalysis:
    """현재 자산(overview)과 목표 포트폴리오를 비교해 리밸런싱 분석 결과를 반환한다."""
    base_krw = float(
        overview.get("total_assets_krw", 0)
        if portfolio.base_type == "TOTAL_ASSETS"
        else overview.get("total_stock_krw", 0)
    )

    current_map = _build_current_map(overview)
    result_items, target_keys = _build_target_items(
        portfolio, base_krw, overview, current_map, dividend_map, returns_map
    )
    result_items += _build_untracked_items(
        current_map, target_keys, base_krw, dividend_map, returns_map
    )

    target_div_sum = round(sum(i.annual_dividend_current_krw for i in result_items), 0)
    target_weighted_cagr, current_weighted_cagr = _calc_portfolio_cagrs(
        result_items, current_map, returns_map
    )
    ticker_account_map = _build_ticker_account_map(overview)

    return RebalancingAnalysis(
        portfolio_id=uuid.UUID(str(portfolio.id)),
        portfolio_name=portfolio.name,
        base_type=portfolio.base_type,
        base_value_krw=round(base_krw, 0),
        items=result_items,
        untracked_holdings=[],
        analyzed_at=datetime.now(UTC).isoformat(),
        current_portfolio_annual_dividend=target_div_sum,
        target_portfolio_annual_dividend=round(
            sum(i.annual_dividend_target_krw for i in result_items), 0
        ),
        total_current_annual_dividend=target_div_sum,
        target_weighted_cagr_10y_pct=target_weighted_cagr,
        current_weighted_cagr_10y_pct=current_weighted_cagr,
        ticker_account_map=ticker_account_map,
    )
