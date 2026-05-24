"""리밸런싱 분석 서비스."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.portfolio import Portfolio
from app.schemas.rebalancing import CurrentHolding, RebalancingAnalysis, RebalancingItem, TickerAccountInfo


def analyze_rebalancing(
    portfolio: Portfolio,
    overview: dict,
    dividend_map: dict[tuple[str, str], dict] | None = None,
    returns_map: dict[tuple[str, str], dict] | None = None,
) -> RebalancingAnalysis:
    """현재 자산(overview)과 목표 포트폴리오를 비교해 리밸런싱 분석 결과를 반환한다."""
    # 1. 기준 금액 결정
    if portfolio.base_type == "TOTAL_ASSETS":
        base_krw = float(overview.get("total_assets_krw", 0))
    else:  # STOCK_ONLY
        base_krw = float(overview.get("total_stock_krw", 0))

    # 2. 현재 보유 종목 맵 구성: (ticker, market) → {value_krw, current_price, name}
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

    # 3. 목표 항목별 계산
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
            # 현금: 전체자산 - 주식자산
            current_value = float(overview.get("total_assets_krw", 0)) - float(overview.get("total_stock_krw", 0))
            current_price = None
            shares = None
        elif market == "KR_PROPERTY":
            # 부동산: REAL_ESTATE 계좌 순자산 합산 (include_in_total=True인 것만)
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
            if current_price and float(current_price) > 0:
                shares = round(diff_krw / float(current_price), 0)
            else:
                shares = None

        current_weight_pct = (current_value / base_krw * 100) if base_krw > 0 else 0.0
        diff_krw = target_value - current_value

        # 배당 계산 (CASH, KR_PROPERTY 제외)
        div_yield: float | None = None
        annual_div_current = 0.0
        annual_div_target = 0.0
        if ticker != "CASH" and market != "KR_PROPERTY" and dividend_map:
            d = dividend_map.get((ticker, market))
            if d:
                yp = float(d.get("dividend_yield") or 0)
                estimated_annual = float(d.get("estimated_annual_krw") or 0)
                if yp > 0 or estimated_annual > 0:
                    div_yield = yp if yp > 0 else None
                    # dividend_service의 estimated_annual_krw 직접 사용
                    # (국내 일반주식은 DPS×qty, ETF/해외는 value×yield로 각각 정확하게 계산된 값)
                    annual_div_current = estimated_annual
                    if current_value > 0:
                        annual_div_target = annual_div_current * (target_value / current_value)
                    elif yp > 0:
                        annual_div_target = target_value * (yp / 100)

        ret = returns_map.get(key) if (returns_map and ticker != "CASH" and market != "KR_PROPERTY") else None

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

    # 4. 목표 포트폴리오에 없는 보유 종목
    untracked: list[CurrentHolding] = []
    untracked_annual_dividend = 0.0
    for key, data in current_map.items():
        if key not in target_keys:
            weight = (data["value_krw"] / base_krw * 100) if base_krw > 0 else 0.0
            untracked.append(CurrentHolding(
                ticker=key[0],
                name=data["name"],
                market=key[1],
                current_value_krw=round(data["value_krw"], 0),
                current_weight_pct=round(weight, 2),
            ))
            if dividend_map:
                d = dividend_map.get(key)
                if d:
                    untracked_annual_dividend += float(d.get("estimated_annual_krw") or 0)

    target_div_sum = round(sum(i.annual_dividend_current_krw for i in result_items), 0)

    # 10년 가중 CAGR 계산
    items_with_return = [i for i in result_items if i.cagr_10y_pct is not None and i.ticker != "CASH" and i.market != "KR_PROPERTY"]
    target_weighted_cagr: float | None = None
    current_weighted_cagr: float | None = None

    # 목표 포트폴리오 CAGR: 목표 비중으로 가중
    if items_with_return:
        target_w_sum = sum(i.target_weight_pct for i in items_with_return)
        if target_w_sum > 0:
            target_weighted_cagr = round(
                sum(i.target_weight_pct * i.cagr_10y_pct for i in items_with_return) / target_w_sum, 2  # type: ignore[operator]
            )

    # 현재 포트폴리오 CAGR: 실제 보유 종목 전체(current_map) KRW 가중 평균
    # 목표 포트폴리오와 현재 보유가 다를 때(배당 포트폴리오 등)도 정확히 표시
    if returns_map:
        current_holdings_with_cagr = [
            (data["value_krw"], returns_map[(t, m)]["cagr_pct"])
            for (t, m), data in current_map.items()
            if returns_map.get((t, m)) and returns_map[(t, m)].get("cagr_pct") is not None
        ]
        if current_holdings_with_cagr:
            total_val = sum(v for v, _ in current_holdings_with_cagr)
            if total_val > 0:
                current_weighted_cagr = round(
                    sum(v * c for v, c in current_holdings_with_cagr) / total_val, 2
                )

    # ticker별 보유 계좌 맵 구성 (계좌별 수량/금액/모의여부 포함)
    account_meta_map = {
        str(acc.get("id", acc.get("account_id", ""))): {
            "asset_type": acc.get("asset_type", "UNKNOWN"),
            "is_mock_mode": bool(acc.get("is_mock_mode", False)),
        }
        for acc in overview.get("accounts", [])
    }
    # (ticker, account_id) → {name, qty, value} 누적
    holding_map: dict[tuple[str, str], dict] = {}
    for pos in overview.get("all_positions", []):
        pos_ticker = pos.get("ticker", "")
        acc_id = str(pos.get("account_id", ""))
        if not pos_ticker or not acc_id:
            continue
        key = (pos_ticker, acc_id)
        if key not in holding_map:
            holding_map[key] = {
                "account_name": pos.get("account_name", ""),
                "qty": 0.0,
                "val": 0.0,
            }
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

    return RebalancingAnalysis(
        portfolio_id=uuid.UUID(str(portfolio.id)),
        portfolio_name=portfolio.name,
        base_type=portfolio.base_type,
        base_value_krw=round(base_krw, 0),
        items=result_items,
        untracked_holdings=sorted(untracked, key=lambda x: -x.current_value_krw),
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        current_portfolio_annual_dividend=target_div_sum,
        target_portfolio_annual_dividend=round(sum(i.annual_dividend_target_krw for i in result_items), 0),
        total_current_annual_dividend=round(target_div_sum + untracked_annual_dividend, 0),
        target_weighted_cagr_10y_pct=target_weighted_cagr,
        current_weighted_cagr_10y_pct=current_weighted_cagr,
        ticker_account_map=ticker_account_map,
    )
