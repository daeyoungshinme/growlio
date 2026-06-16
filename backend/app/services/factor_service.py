"""팩터 분석 서비스 — Fama-French 3팩터 기반 Value/Size/Momentum/Growth 노출도 계산.

yfinance .info에서 P/E, P/B, 시가총액을 가져와 종목별·포트폴리오 가중 팩터 점수를 반환한다.
Redis 1시간 캐시를 사용한다.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import math
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.services._snapshot_queries import latest_snapshot_subquery
from app.services.yahoo_price import to_yf_symbol as _to_yf_symbol
from app.utils.cache_keys import RedisType

logger = structlog.get_logger()

_FACTOR_CACHE_TTL = 3600  # 1시간


def _sync_fetch_factor_data(symbols: list[str]) -> dict[str, dict]:
    """yfinance .info에서 P/E, P/B, 시가총액, 12-1M 모멘텀 수집. 동기 함수."""
    from datetime import date, timedelta

    import yfinance as yf

    result: dict[str, dict] = {}
    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            info = ticker.info or {}

            pe_ratio = info.get("trailingPE") or info.get("forwardPE")
            pb_ratio = info.get("priceToBook")
            market_cap = info.get("marketCap")

            # 12-1M 모멘텀: 12개월 전 → 1개월 전 구간 수익률
            end_date = date.today() - timedelta(days=21)
            start_date = end_date - timedelta(days=335)
            hist = ticker.history(
                start=start_date.isoformat(),
                end=end_date.isoformat(),
                auto_adjust=True,
            )
            momentum: float | None = None
            if not hist.empty and len(hist) >= 2:
                raw_mom = float(hist["Close"].iloc[-1] / hist["Close"].iloc[0] - 1) * 100
                if math.isfinite(raw_mom):
                    momentum = round(raw_mom, 2)

            def _safe_float(v: object) -> float | None:
                try:
                    f = float(v)  # type: ignore[arg-type]
                    return f if math.isfinite(f) else None
                except (TypeError, ValueError):
                    return None

            result[sym] = {
                "pe_ratio": _safe_float(pe_ratio),
                "pb_ratio": _safe_float(pb_ratio),
                "market_cap": _safe_float(market_cap),
                "momentum_pct": momentum,
            }
        except Exception as e:
            logger.warning("factor_fetch_failed", symbol=sym, error=str(e))
            result[sym] = {
                "pe_ratio": None,
                "pb_ratio": None,
                "market_cap": None,
                "momentum_pct": None,
            }
    return result


# ---------------------------------------------------------------------------
# 팩터 점수 계산 (0-100)
# ---------------------------------------------------------------------------

def _score_value(pb: float | None, pe: float | None) -> float:
    """Value 점수. 낮은 P/B·P/E = 가치주 = 높은 점수."""
    scores: list[float] = []
    if pb is not None and pb > 0:
        # P/B 0.5 이하 → 100점, 5.0 이상 → 0점
        scores.append(max(0.0, min(100.0, (5.0 - pb) / 4.5 * 100)))
    if pe is not None and 0 < pe < 200:
        # P/E 5 이하 → 100점, 50 이상 → 0점
        scores.append(max(0.0, min(100.0, (50.0 - pe) / 45.0 * 100)))
    return round(sum(scores) / len(scores), 1) if scores else 50.0


def _score_growth(pb: float | None, pe: float | None) -> float:
    """Growth 점수. 높은 P/B·P/E = 성장주 = 높은 점수."""
    scores: list[float] = []
    if pb is not None and pb > 0:
        scores.append(max(0.0, min(100.0, (pb - 0.5) / 4.5 * 100)))
    if pe is not None and 0 < pe < 200:
        scores.append(max(0.0, min(100.0, (pe - 5.0) / 45.0 * 100)))
    return round(sum(scores) / len(scores), 1) if scores else 50.0


def _score_size(market_cap: float | None) -> float:
    """Size 점수 (Small-Cap 지향). 작은 시총 = 높은 점수 (Fama-French SMB 개념)."""
    if market_cap is None or market_cap <= 0:
        return 50.0
    cap_b = market_cap / 1e9  # USD 기준 십억 달러
    # 1B 이하 → 100점, 500B 이상 → 0점
    return round(max(0.0, min(100.0, (500.0 - cap_b) / 499.0 * 100)), 1)


def _score_momentum(momentum_pct: float | None) -> float:
    """Momentum 점수. 높은 12-1M 수익률 = 높은 점수."""
    if momentum_pct is None:
        return 50.0
    # -50% → 0점, +50% → 100점
    return round(max(0.0, min(100.0, (momentum_pct + 50.0) / 100.0 * 100)), 1)


def _build_holdings(
    positions: list[dict],
    yf_symbols: list[str],
    weights: list[float],
    factor_data: dict[str, dict],
) -> list[dict]:
    """종목별 팩터 점수를 계산해 holdings 목록을 반환한다."""
    holdings = []
    for pos, sym, w in zip(positions, yf_symbols, weights, strict=False):
        fd = factor_data.get(sym, {})
        pe = fd.get("pe_ratio")
        pb = fd.get("pb_ratio")
        market_cap = fd.get("market_cap")
        momentum = fd.get("momentum_pct")
        holdings.append({
            "ticker": pos["ticker"],
            "name": pos["name"],
            "weight_pct": round(w * 100, 2),
            "pe_ratio": pe,
            "pb_ratio": pb,
            "market_cap": market_cap,
            "momentum_pct": momentum,
            "value_score": _score_value(pb, pe),
            "growth_score": _score_growth(pb, pe),
            "size_score": _score_size(market_cap),
            "momentum_score": _score_momentum(momentum),
        })
    return holdings


def _portfolio_factors(holdings: list[dict]) -> dict:
    """holdings에서 가중 평균 팩터 점수를 계산한다."""
    def _weighted(key: str) -> float:
        return round(sum(h[key] * (h["weight_pct"] / 100) for h in holdings), 1)

    return {
        "value": _weighted("value_score"),
        "growth": _weighted("growth_score"),
        "size": _weighted("size_score"),
        "momentum": _weighted("momentum_score"),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def get_factor_analysis(
    user_id: uuid.UUID,
    db: AsyncSession,
    redis: RedisType = None,
) -> dict:
    """포트폴리오 팩터 노출도 분석 반환."""
    cache_key = f"factor_analysis:{user_id}"

    if redis:
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # 최신 스냅샷 포지션 조회 (risk_service와 동일 패턴)
    subq = latest_snapshot_subquery(user_id=user_id)
    result = await db.execute(
        select(AssetSnapshot, AssetAccount)
        .join(
            subq,
            (AssetSnapshot.account_id == subq.c.account_id)
            & (AssetSnapshot.snapshot_date == subq.c.max_date),
        )
        .join(AssetAccount, AssetAccount.id == AssetSnapshot.account_id)
        .where(AssetAccount.is_active == True)  # noqa: E712
    )
    rows = result.all()

    snap_ids = [snap.id for snap, _ in rows]
    pos_map: dict[str, dict] = {}
    if snap_ids:
        all_pos_result = await db.execute(
            select(Position).where(Position.snapshot_id.in_(snap_ids))
        )
        for pos in all_pos_result.scalars().all():
            key = f"{pos.ticker}-{pos.market}"
            if key not in pos_map:
                pos_map[key] = {
                    "ticker": pos.ticker,
                    "market": pos.market,
                    "name": pos.name,
                    "value_krw": 0.0,
                }
            pos_map[key]["value_krw"] += float(pos.value_krw or 0)

    if not pos_map:
        return _empty_factor_result()

    total_value = sum(p["value_krw"] for p in pos_map.values())
    if total_value <= 0:
        return _empty_factor_result()

    positions = list(pos_map.values())
    yf_symbols = [_to_yf_symbol(p["ticker"], p["market"]) for p in positions]
    weights = [p["value_krw"] / total_value for p in positions]

    loop = asyncio.get_running_loop()
    factor_data = await loop.run_in_executor(None, _sync_fetch_factor_data, yf_symbols)

    holdings = _build_holdings(positions, yf_symbols, weights, factor_data)
    result_data: dict = {
        "holdings": holdings,
        "portfolio_factors": _portfolio_factors(holdings),
        "position_count": len(positions),
        "note": "yfinance 기반 팩터 점수 (0-100, 높을수록 해당 팩터 노출도 높음)",
    }

    if redis:
        with contextlib.suppress(Exception):
            await redis.setex(cache_key, _FACTOR_CACHE_TTL, json.dumps(result_data))

    return result_data


def _empty_factor_result() -> dict:
    return {
        "holdings": [],
        "portfolio_factors": {"value": 0.0, "growth": 0.0, "size": 0.0, "momentum": 0.0},
        "position_count": 0,
        "note": "포지션 데이터 없음",
    }
