"""리밸런싱 전략 서비스 — 팩터 노출도 + 효율적 프론티어를 종합해 전략 방향을 제시한다."""

from __future__ import annotations

import asyncio
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.services.factor_service import get_factor_analysis, get_factor_analysis_for_portfolio
from app.services.portfolio_optimizer import get_efficient_frontier
from app.services.position_aggregator import query_latest_position_map
from app.utils.cache_keys import (
    TTL_REBALANCING_STRATEGY,
    CacheStoreType,
    get_cached_json,
    rebalancing_strategy_key,
    set_cached_json,
)

logger = structlog.get_logger()
_RISK_FREE_RATE = 3.0  # Sharpe 계산 기준 무위험 수익률 (%)

_FACTOR_LABELS: dict[str, str] = {
    "value": "가치",
    "growth": "성장",
    "size": "소형주",
    "momentum": "모멘텀",
}

_ACTION_NEW = "신규 편입"
_ACTION_SELL = "전량 매도"
_ACTION_INCREASE = "비중 확대"
_ACTION_DECREASE = "비중 축소"
_WEIGHT_THRESHOLD_FLOOR = 2.0  # 비중 차이 임계값의 최솟값(%p) — 목표비중이 작은 종목도 이 이하 변화는 노이즈로 간주
_WEIGHT_THRESHOLD_RATIO = 0.1  # 목표비중 대비 임계값 비율 — 목표비중이 큰 종목은 작은 %p 변화도 유의미하므로 비례 상향

_FACTOR_SCORE_LABELS: dict[str, str] = {
    "value_score": "가치",
    "growth_score": "성장",
    "size_score": "소형주",
    "momentum_score": "모멘텀",
}


def _sharpe(ret: float, risk: float) -> float | None:
    if risk <= 0:
        return None
    return (ret - _RISK_FREE_RATE) / risk


def _factor_reason(factor_changes: dict) -> str:
    """팩터 변화에서 핵심 변화 요약 문장 생성(포트폴리오 전체 집계 기준)."""
    positives = [f"{_FACTOR_LABELS.get(k, k)} 팩터 강화" for k, v in factor_changes.items() if v["delta"] > 5]
    negatives = [f"{_FACTOR_LABELS.get(k, k)} 팩터 완화" for k, v in factor_changes.items() if v["delta"] < -5]
    parts = positives + negatives
    return "、".join(parts) if parts else "팩터 구성 변화"


def _drift_threshold(target_weight: float) -> float:
    """목표비중에 비례하는 상대 임계값 — 목표비중이 큰 종목(예: 30%)은 2%p 변화도 포트폴리오
    전체에 미치는 영향이 크므로 절대 임계값(2.0)보다 낮게 반응해야 하지만, 반대로 목표비중이
    아주 작은 종목은 절대 임계값 밑으로는 노이즈로 무시한다 — 그래서 `max(바닥값, 비율)`로 둘 다
    보장한다."""
    return max(_WEIGHT_THRESHOLD_FLOOR, target_weight * _WEIGHT_THRESHOLD_RATIO)


def _per_ticker_factor_reason(
    ticker: str,
    current_holdings_by_ticker: dict[str, dict],
    target_holdings_by_ticker: dict[str, dict],
    fallback: str,
) -> str:
    """종목별 팩터 점수(`factor_service.get_factor_analysis*`의 holdings) 변화에서 가장 크게
    바뀐 1~2개 팩터를 근거 문장으로 만든다 — 포트폴리오 전체 집계(`_factor_reason`)를 모든
    종목에 동일하게 재사용하던 것을 종목 단위로 세분화한다. 종목별 데이터가 없으면(신규 편입
    등 현재/목표 어느 한쪽에 보유가 없는 경우) `fallback`(포트폴리오 전체 요약 또는 고정 문구)을
    그대로 쓴다."""
    cur = current_holdings_by_ticker.get(ticker)
    tgt = target_holdings_by_ticker.get(ticker)
    if cur is None or tgt is None:
        return fallback

    deltas = [(key, tgt[key] - cur[key]) for key in _FACTOR_SCORE_LABELS if abs(tgt[key] - cur[key]) > 5]
    if not deltas:
        return fallback

    deltas.sort(key=lambda kv: abs(kv[1]), reverse=True)
    parts = [f"{_FACTOR_SCORE_LABELS[key]} 팩터 {'강화' if delta > 0 else '완화'}" for key, delta in deltas[:2]]
    return "、".join(parts)


def _build_trade_recommendations(
    current_pos_map: dict[str, dict],
    target_items: list,
    factor_changes: dict,
    current_holdings: list[dict],
    target_holdings: list[dict],
) -> list[dict]:
    """현재 포지션과 목표 포트폴리오 비중 차이에서 거래 추천 생성."""
    factor_summary = _factor_reason(factor_changes)
    # holdings는 ticker 단위로 인덱싱된다(factor_service._build_holdings — market 구분 없음).
    current_holdings_by_ticker = {h["ticker"]: h for h in current_holdings}
    target_holdings_by_ticker = {h["ticker"]: h for h in target_holdings}

    # 목표 포트폴리오를 ticker-market 키로 인덱싱
    target_map: dict[str, dict] = {}
    for item in target_items:
        key = f"{item.ticker}-{item.market}"
        target_map[key] = {
            "ticker": item.ticker,
            "market": item.market,
            "name": item.name,
            "target_weight": float(item.weight),
        }

    # 현재 포지션 총 가치 기준 비중
    total_value = sum(p["value_krw"] for p in current_pos_map.values())
    current_weights: dict[str, float] = {}
    if total_value > 0:
        for key, pos in current_pos_map.items():
            current_weights[key] = pos["value_krw"] / total_value * 100.0

    recommendations: list[dict] = []

    # 목표 포트폴리오 종목 순회
    for key, target in target_map.items():
        cur_w = current_weights.get(key, 0.0)
        tgt_w = target["target_weight"]
        delta = tgt_w - cur_w

        if cur_w == 0.0:
            action = _ACTION_NEW
            reason = f"목표 포트폴리오 신규 구성 · {factor_summary}"
        elif abs(delta) < _drift_threshold(tgt_w):
            continue
        elif delta > 0:
            action = _ACTION_INCREASE
            reason = _per_ticker_factor_reason(
                target["ticker"], current_holdings_by_ticker, target_holdings_by_ticker, factor_summary
            )
        else:
            action = _ACTION_DECREASE
            reason = _per_ticker_factor_reason(
                target["ticker"], current_holdings_by_ticker, target_holdings_by_ticker, "리스크 감소 또는 비중 조정"
            )

        recommendations.append(
            {
                "action": action,
                "ticker": target["ticker"],
                "market": target["market"],
                "name": target["name"],
                "current_weight": round(cur_w, 2),
                "target_weight": round(tgt_w, 2),
                "reason": reason,
            }
        )

    # 현재 보유하지만 목표 포트폴리오에 없는 종목
    for key, cur_w_val in current_weights.items():
        if key not in target_map and cur_w_val >= _drift_threshold(0.0):
            pos = current_pos_map[key]
            recommendations.append(
                {
                    "action": _ACTION_SELL,
                    "ticker": pos["ticker"],
                    "market": pos["market"],
                    "name": pos.get("name", pos["ticker"]),
                    "current_weight": round(cur_w_val, 2),
                    "target_weight": 0.0,
                    "reason": "목표 포트폴리오 미포함",
                }
            )

    # 절대 변화량 기준 정렬 (큰 변화 먼저)
    recommendations.sort(key=lambda r: abs(r["target_weight"] - r["current_weight"]), reverse=True)
    return recommendations[:10]


def _overall_direction(risk_change: float, return_change: float, sharpe_improvement: bool) -> str:
    if risk_change < -2 and sharpe_improvement:
        return "리스크 감소형"
    if return_change > 2 and not sharpe_improvement:
        return "수익 추구형"
    if sharpe_improvement:
        return "효율성 개선형"
    return "균형 조정형"


def _build_summary(
    portfolio_name: str,
    factor_changes: dict,
    risk_change: float,
    return_change: float,
    sharpe_improvement: bool,
    overall_direction: str,
) -> str:
    parts: list[str] = [f"'{portfolio_name}'으로 전환 시"]
    if abs(risk_change) >= 0.5:
        direction = "감소" if risk_change < 0 else "증가"
        parts.append(f"변동성이 {abs(risk_change):.1f}%p {direction}하고")
    improving_factors = [_FACTOR_LABELS.get(k, k) for k, v in factor_changes.items() if v["delta"] > 5]
    if improving_factors:
        parts.append(f"{'·'.join(improving_factors)} 팩터 노출도가 강화됩니다")
    if sharpe_improvement:
        parts.append("위험 대비 수익률(Sharpe)이 개선됩니다")
    parts.append(f"전환 방향: {overall_direction}")
    return " · ".join(parts) + "."


async def get_rebalancing_strategy(
    user_id: uuid.UUID,
    portfolio_id: str,
    db: AsyncSession,
    cache: CacheStoreType = None,
) -> dict:
    """팩터·프론티어 분석을 종합한 리밸런싱 전략 반환."""
    from app.models.portfolio import Portfolio

    portfolio = await db.scalar(
        select(Portfolio)
        .options(
            selectinload(Portfolio.items),
            selectinload(Portfolio.linked_accounts),
        )
        .where(Portfolio.id == portfolio_id)
    )
    if not portfolio:
        return {"error": "포트폴리오를 찾을 수 없습니다"}

    portfolio_acct_ids: list[uuid.UUID] | None = (
        [uuid.UUID(aid) for aid in portfolio.account_ids] if portfolio.account_ids else None
    )
    acct_suffix = "_".join(sorted(str(a) for a in portfolio_acct_ids)) if portfolio_acct_ids else "all"
    cache_key = rebalancing_strategy_key(user_id, portfolio_id, acct_suffix)

    cached = await get_cached_json(cache, cache_key)
    if cached is not None:
        return cached

    # 1+2. 팩터·프론티어 병렬 조회 — 세 호출이 서로 독립적이므로 asyncio.gather로 동시 실행.
    # 캐시 히트(TTL=1h) 시 DB 접근 없이 캐시에서 즉시 반환되어 AsyncSession 경합 없음.
    current_factors_data, target_factors_data, frontier_data = await asyncio.gather(
        get_factor_analysis(user_id, db, cache, account_ids=portfolio_acct_ids),
        get_factor_analysis_for_portfolio(portfolio_id, db, cache),
        get_efficient_frontier(user_id, db, cache, compare_portfolio_id=portfolio_id, account_ids=portfolio_acct_ids),
    )

    current_pf = current_factors_data.get("portfolio_factors", {})
    target_pf = target_factors_data.get("portfolio_factors", {})

    factor_changes: dict[str, dict] = {}
    for key in ("value", "growth", "size", "momentum"):
        cur_val = float(current_pf.get(key, 0))
        tgt_val = float(target_pf.get(key, 0))
        factor_changes[key] = {
            "current": round(cur_val, 1),
            "target": round(tgt_val, 1),
            "delta": round(tgt_val - cur_val, 1),
        }
    cur_pos = frontier_data.get("current")
    tgt_pos = frontier_data.get("target")

    if cur_pos and tgt_pos:
        risk_change = round(tgt_pos["risk"] - cur_pos["risk"], 2)
        return_change = round(tgt_pos["return"] - cur_pos["return"], 2)
        cur_sharpe = _sharpe(cur_pos["return"], cur_pos["risk"])
        tgt_sharpe = _sharpe(tgt_pos["return"], tgt_pos["risk"])
        sharpe_improvement = tgt_sharpe is not None and cur_sharpe is not None and tgt_sharpe > cur_sharpe
        frontier_changes = {
            "current_risk": cur_pos["risk"],
            "current_return": cur_pos["return"],
            "target_risk": tgt_pos["risk"],
            "target_return": tgt_pos["return"],
            "risk_change": risk_change,
            "return_change": return_change,
            "sharpe_improvement": sharpe_improvement,
            "current_sharpe": round(cur_sharpe, 3) if cur_sharpe is not None else None,
            "target_sharpe": round(tgt_sharpe, 3) if tgt_sharpe is not None else None,
        }
    else:
        risk_change = 0.0
        return_change = 0.0
        sharpe_improvement = False
        frontier_changes = {
            "current_risk": cur_pos["risk"] if cur_pos else None,
            "current_return": cur_pos["return"] if cur_pos else None,
            "target_risk": tgt_pos["risk"] if tgt_pos else None,
            "target_return": tgt_pos["return"] if tgt_pos else None,
            "risk_change": None,
            "return_change": None,
            "sharpe_improvement": None,
            "current_sharpe": None,
            "target_sharpe": None,
        }

    # 3. 현재 포지션 map 조회 (거래 추천용) — 포트폴리오 연결 계좌만 포함
    current_pos_map = await query_latest_position_map(user_id, db, include_name=True, account_ids=portfolio_acct_ids)

    # 4. 거래 추천 — 종목별 근거는 두 호출이 이미 반환한 holdings(종목별 팩터 점수)를 재사용한다.
    trade_recommendations = _build_trade_recommendations(
        current_pos_map,
        portfolio.items,
        factor_changes,
        current_factors_data.get("holdings", []),
        target_factors_data.get("holdings", []),
    )

    # 5. 종합 방향 및 요약
    direction = _overall_direction(risk_change, return_change, sharpe_improvement)
    summary = _build_summary(portfolio.name, factor_changes, risk_change, return_change, sharpe_improvement, direction)

    result_data: dict = {
        "portfolio_id": str(portfolio_id),
        "portfolio_name": portfolio.name,
        "factor_changes": factor_changes,
        "frontier_changes": frontier_changes,
        "trade_recommendations": trade_recommendations,
        "overall_direction": direction,
        "summary": summary,
    }

    await set_cached_json(cache, cache_key, result_data, TTL_REBALANCING_STRATEGY)
    return result_data
