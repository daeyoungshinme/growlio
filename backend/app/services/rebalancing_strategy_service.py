"""리밸런싱 전략 서비스 — 팩터 노출도 + 효율적 프론티어를 종합해 전략 방향을 제시한다."""
from __future__ import annotations

import asyncio
import contextlib
import json
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.services.factor_service import get_factor_analysis, get_factor_analysis_for_portfolio
from app.services.portfolio_optimizer import get_efficient_frontier
from app.services.position_aggregator import query_latest_position_map
from app.utils.cache_keys import TTL_REBALANCING_STRATEGY, RedisType

logger = structlog.get_logger()
_RISK_FREE_RATE = 3.0       # Sharpe 계산 기준 무위험 수익률 (%)

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
_WEIGHT_THRESHOLD = 2.0  # 비중 차이가 이 값 이상일 때만 추천


def _sharpe(ret: float, risk: float) -> float | None:
    if risk <= 0:
        return None
    return (ret - _RISK_FREE_RATE) / risk


def _factor_reason(factor_changes: dict) -> str:
    """팩터 변화에서 핵심 변화 요약 문장 생성."""
    positives = [
        f"{_FACTOR_LABELS.get(k, k)} 팩터 강화"
        for k, v in factor_changes.items()
        if v["delta"] > 5
    ]
    negatives = [
        f"{_FACTOR_LABELS.get(k, k)} 팩터 완화"
        for k, v in factor_changes.items()
        if v["delta"] < -5
    ]
    parts = positives + negatives
    return "、".join(parts) if parts else "팩터 구성 변화"


def _build_trade_recommendations(
    current_pos_map: dict[str, dict],
    target_items: list,
    factor_changes: dict,
) -> list[dict]:
    """현재 포지션과 목표 포트폴리오 비중 차이에서 거래 추천 생성."""
    factor_summary = _factor_reason(factor_changes)

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
        elif abs(delta) < _WEIGHT_THRESHOLD:
            continue
        elif delta > 0:
            action = _ACTION_INCREASE
            reason = factor_summary
        else:
            action = _ACTION_DECREASE
            reason = "리스크 감소 또는 비중 조정"

        recommendations.append({
            "action": action,
            "ticker": target["ticker"],
            "market": target["market"],
            "name": target["name"],
            "current_weight": round(cur_w, 2),
            "target_weight": round(tgt_w, 2),
            "reason": reason,
        })

    # 현재 보유하지만 목표 포트폴리오에 없는 종목
    for key, cur_w_val in current_weights.items():
        if key not in target_map and cur_w_val >= _WEIGHT_THRESHOLD:
            pos = current_pos_map[key]
            recommendations.append({
                "action": _ACTION_SELL,
                "ticker": pos["ticker"],
                "market": pos["market"],
                "name": pos.get("name", pos["ticker"]),
                "current_weight": round(cur_w_val, 2),
                "target_weight": 0.0,
                "reason": "목표 포트폴리오 미포함",
            })

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
    improving_factors = [
        _FACTOR_LABELS.get(k, k)
        for k, v in factor_changes.items()
        if v["delta"] > 5
    ]
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
    redis: RedisType = None,
) -> dict:
    """팩터·프론티어 분석을 종합한 리밸런싱 전략 반환."""
    from app.models.portfolio import Portfolio

    cache_key = f"rebalancing_strategy:{user_id}:{portfolio_id}"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.debug("strategy_cache_read_error", cache_key=cache_key, error=str(e))

    portfolio = await db.scalar(
        select(Portfolio)
        .options(selectinload(Portfolio.items))
        .where(Portfolio.id == portfolio_id)
    )
    if not portfolio:
        return {"error": "포트폴리오를 찾을 수 없습니다"}

    # 1+2. 팩터·프론티어 병렬 조회 — 세 호출이 서로 독립적이므로 asyncio.gather로 동시 실행.
    # 캐시 히트(TTL=1h) 시 DB 접근 없이 Redis에서 즉시 반환되어 AsyncSession 경합 없음.
    current_factors_data, target_factors_data, frontier_data = await asyncio.gather(
        get_factor_analysis(user_id, db, redis),
        get_factor_analysis_for_portfolio(portfolio_id, db, redis),
        get_efficient_frontier(user_id, db, redis, compare_portfolio_id=portfolio_id),
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
        sharpe_improvement = (
            tgt_sharpe is not None
            and cur_sharpe is not None
            and tgt_sharpe > cur_sharpe
        )
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

    # 3. 현재 포지션 map 조회 (거래 추천용)
    current_pos_map = await query_latest_position_map(user_id, db, include_name=True)

    # 4. 거래 추천
    trade_recommendations = _build_trade_recommendations(
        current_pos_map, portfolio.items, factor_changes
    )

    # 5. 종합 방향 및 요약
    direction = _overall_direction(risk_change, return_change, sharpe_improvement)
    summary = _build_summary(
        portfolio.name, factor_changes, risk_change, return_change, sharpe_improvement, direction
    )

    result_data: dict = {
        "portfolio_id": str(portfolio_id),
        "portfolio_name": portfolio.name,
        "factor_changes": factor_changes,
        "frontier_changes": frontier_changes,
        "trade_recommendations": trade_recommendations,
        "overall_direction": direction,
        "summary": summary,
    }

    if redis:
        with contextlib.suppress(Exception):
            await redis.setex(cache_key, TTL_REBALANCING_STRATEGY, json.dumps(result_data))

    return result_data
