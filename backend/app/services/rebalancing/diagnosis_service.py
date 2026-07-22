"""리밸런싱 진단 화면의 부가 설명(시장상황·리스크·세금영향)을 조합하는 서비스.

주의: needs_rebalancing 판정/알림 트리거 로직과 완전히 분리됨. 여기서 계산되는 값은
화면 설명(부가 인사이트) 용도로만 사용되며, 실패해도 기존 리밸런싱 판단에 영향을 주지 않는다.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import CASH_EQUIVALENT_TICKER
from app.models.user import UserSettings
from app.schemas.rebalancing import DiagnosisContext, RebalancingAnalysis, TaxImpactItem
from app.services.market_signal_service import get_market_signal
from app.services.risk_service import get_portfolio_risk_metrics
from app.services.tax_service import _OVERSEAS_MARKETS, _TAX_DEFERRED_TYPES, estimate_overseas_transfer_tax
from app.utils.cache_keys import CacheStoreType

logger = structlog.get_logger()

# 리스크 이상 판단 임계값 — rebalancing/alert_check._evaluate_composite_trigger와 동일 기준 공유(단일 소스)
RISK_DIVERSIFICATION_MIN = 40
RISK_TOP_HOLDING_MAX_PCT = 40.0
RISK_VOLATILITY_MAX_PCT = 20.0

_ASSUMED_FEE_RATE_DOMESTIC = 0.00015  # 국내 온라인 매매 수수료 대략치 (참고용, 증권사별 상이)
_ASSUMED_FEE_RATE_OVERSEAS = 0.0025  # 해외 온라인 매매 수수료 대략치 (참고용)
_TAX_DETAIL_LIMIT = 5
_EXCLUDED_TICKERS = {"CASH", CASH_EQUIVALENT_TICKER}
_EXCLUDED_MARKETS = {"KR_PROPERTY"}

_MARKET_NOTES: dict[str, str | None] = {
    "GREEN": None,  # 평시엔 굳이 문구 노출 안 함 (노이즈 감소)
    "YELLOW": "시장 변동성이 확대되는 국면입니다 — 분할 실행을 고려해보세요.",
    "RED": "시장 위험 신호가 높은 국면입니다 — 리밸런싱을 신중하게 진행하세요.",
}


def _aggregate_position_costs(overview: dict) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """overview.all_positions에서 (ticker, market)별 계좌 단위 보유 목록(lot)을 구한다.

    각 lot은 계좌의 tax_type을 포함하며, 매도 우선순위(rebalancing/order_builder._build_sell_orders와
    동일 기준 — 과세이연 계좌 후순위, 그 다음 보유수량 큰 순)로 정렬해 반환한다. 세금 미리보기가
    실제 매도 실행 시 계좌 선택 순서와 동일한 가정으로 실현손익을 추정하도록 하기 위함이다.
    """
    tax_type_map = {row["id"]: row.get("tax_type", "GENERAL") for row in overview.get("accounts", [])}

    lots: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for p in overview.get("all_positions", []):
        key = (p["ticker"], p["market"])
        tax_type = tax_type_map.get(p.get("account_id"), "GENERAL")
        lots.setdefault(key, []).append(
            {
                "account_id": p.get("account_id"),
                "is_tax_deferred": tax_type in _TAX_DEFERRED_TYPES,
                "qty": float(p.get("qty", 0)),
                "value_krw": float(p.get("value_krw", 0)),
                "invested_krw": float(p.get("invested_krw", 0)),
            }
        )

    for lot_list in lots.values():
        lot_list.sort(key=lambda lot: (lot["is_tax_deferred"], -lot["qty"]))
    return lots


def _consume_lots(lots: list[dict[str, Any]], sell_qty: float) -> tuple[float, float, float]:
    """매도 우선순위(lots 정렬 순서)대로 sell_qty를 소진하며 실현손익/매도금액/과세이연 수량을 계산한다.

    Returns: (realized_gain, sell_notional, deferred_qty) — realized_gain은 과세이연 lot을 제외한 합계.
    """
    remaining = sell_qty
    realized_gain = 0.0
    sell_notional = 0.0
    deferred_qty = 0.0
    for lot in lots:
        if remaining <= 0:
            break
        if lot["qty"] <= 0:
            continue
        take = min(remaining, lot["qty"])
        avg_cost_per_share = lot["invested_krw"] / lot["qty"]
        current_price_per_share = lot["value_krw"] / lot["qty"]
        sell_notional += take * current_price_per_share
        if lot["is_tax_deferred"]:
            deferred_qty += take
        else:
            realized_gain += take * (current_price_per_share - avg_cost_per_share)
        remaining -= take
    return realized_gain, sell_notional, deferred_qty


def _build_tax_preview(
    analysis: RebalancingAnalysis, overview: dict
) -> tuple[float, float, float, list[str], list[TaxImpactItem]]:
    """diff_krw < 0 항목(CASH·KR_PROPERTY 제외)에 대해 대략적 실현손익/세금/수수료를 추정한다.

    참고용 근사치 — 정확한 세액은 /tax/summary의 연간 집계를 따른다.
    """
    cost_map = _aggregate_position_costs(overview)

    total_gain = 0.0
    overseas_gain_sum = 0.0
    total_fee = 0.0
    tax_items: list[TaxImpactItem] = []

    for item in analysis.items:
        if item.diff_krw >= 0:
            continue
        if item.ticker in _EXCLUDED_TICKERS or item.market in _EXCLUDED_MARKETS:
            continue

        lots = cost_map.get((item.ticker, item.market), [])
        total_qty = sum(lot["qty"] for lot in lots)
        is_overseas = item.market in _OVERSEAS_MARKETS

        # shares_to_trade가 None(가격 데이터 누락)이면 보유수량 전체를 매도한다고 가정해 폴백한다.
        if item.shares_to_trade is not None:
            sell_qty = abs(item.shares_to_trade)
        elif total_qty > 0:
            sell_qty = total_qty
        else:
            tax_items.append(
                TaxImpactItem(
                    ticker=item.ticker,
                    name=item.name,
                    market=item.market,
                    is_overseas=is_overseas,
                    sell_qty=0.0,
                    estimated_realized_gain_krw=0.0,
                    excluded_reason="가격/평단가 정보 부족으로 추정 제외",
                )
            )
            continue

        if not lots or total_qty <= 0:
            tax_items.append(
                TaxImpactItem(
                    ticker=item.ticker,
                    name=item.name,
                    market=item.market,
                    is_overseas=is_overseas,
                    sell_qty=sell_qty,
                    estimated_realized_gain_krw=0.0,
                    excluded_reason="평단가 정보 부족으로 추정 제외",
                )
            )
            continue

        # lots는 _aggregate_position_costs에서 실제 매도 우선순위(과세이연 계좌 후순위)로 정렬되어 있다 —
        # 여기서도 동일 순서로 소진해 실제 실행 결과와 세금 추정치가 어긋나지 않도록 한다.
        realized_gain, sell_notional, deferred_qty = _consume_lots(lots, sell_qty)

        total_gain += realized_gain
        if is_overseas:
            overseas_gain_sum += realized_gain
            total_fee += sell_notional * _ASSUMED_FEE_RATE_OVERSEAS
        else:
            total_fee += sell_notional * _ASSUMED_FEE_RATE_DOMESTIC

        tax_items.append(
            TaxImpactItem(
                ticker=item.ticker,
                name=item.name,
                market=item.market,
                is_overseas=is_overseas,
                sell_qty=sell_qty,
                estimated_realized_gain_krw=round(realized_gain, 0),
                is_tax_deferred=deferred_qty > 0,
            )
        )

    tax_notes: list[str] = []
    overseas_tax = 0.0
    if overseas_gain_sum > 0:
        estimate = estimate_overseas_transfer_tax(overseas_gain_sum)
        overseas_tax = estimate["estimated_tax_krw"]
        if overseas_tax > 0:
            tax_notes.append(
                f"해외 매도 실현손익 추정 {round(overseas_gain_sum):,.0f}원, "
                f"예상 양도세 약 {overseas_tax:,.0f}원 (참고용, 연간 다른 손익과 합산 시 달라질 수 있습니다)"
            )
    elif overseas_gain_sum < 0:
        tax_notes.append(
            f"해외 매도로 약 {abs(round(overseas_gain_sum)):,.0f}원의 손실이 실현됩니다 — "
            "같은 해 다른 매도 이익과 상계하면 절세 효과가 있습니다."
        )

    excluded_count = sum(1 for t in tax_items if t.excluded_reason)
    if excluded_count:
        tax_notes.append(f"{excluded_count}개 종목은 가격/평단가 정보 부족으로 세금 영향 추정에서 제외되었습니다.")

    deferred_count = sum(1 for t in tax_items if t.is_tax_deferred)
    if deferred_count:
        tax_notes.append(
            f"{deferred_count}개 종목은 매도 수량 중 일부/전부가 ISA·연금저축·IRP 계좌 보유분으로, "
            "과세이연되어 위 세금 추정에서 제외되었습니다."
        )

    tax_items.sort(key=lambda t: abs(t.estimated_realized_gain_krw), reverse=True)
    return total_gain, overseas_tax, total_fee, tax_notes, tax_items[:_TAX_DETAIL_LIMIT]


def check_composite_signal(
    market_level: str | None,
    risk_available: bool,
    diversification_score: int | None,
    top_holding_weight_pct: float | None,
    annualized_volatility_pct: float | None,
) -> tuple[bool, str | None]:
    """market_level RED 또는 리스크 이상 신호가 있으면 (True, 사유문구)를 반환한다.

    drift-summary 배지, 알림(이메일/푸시) 추가 발송 트리거가 공유하는 단일 소스 함수 —
    두 곳이 서로 다른 기준으로 판단하지 않도록 임계값을 여기 한 곳에서만 정의한다.
    """
    reasons: list[str] = []

    if market_level == "RED":
        reasons.append("시장 위험 신호가 RED 단계입니다")

    if risk_available:
        if diversification_score is not None and diversification_score < RISK_DIVERSIFICATION_MIN:
            reasons.append(f"분산도 점수가 낮습니다 ({diversification_score}점)")
        if top_holding_weight_pct is not None and top_holding_weight_pct >= RISK_TOP_HOLDING_MAX_PCT:
            reasons.append(f"특정 종목 비중이 {top_holding_weight_pct:.0f}%로 과집중되어 있습니다")
        if annualized_volatility_pct is not None and annualized_volatility_pct >= RISK_VOLATILITY_MAX_PCT:
            reasons.append(f"연환산 변동성이 {annualized_volatility_pct:.1f}%로 높습니다")

    if not reasons:
        return False, None
    return True, " / ".join(reasons)


def _risk_note(risk: dict) -> str | None:
    """분산도/변동성/최대비중 중 이상 신호가 있을 때만 문구를 생성한다. 전부 정상이면 None."""
    notes: list[str] = []
    diversification_score = risk.get("diversification_score", 100)
    top_holding_weight_pct = risk.get("top_holding_weight_pct", 0.0)
    annualized_volatility_pct = risk.get("annualized_volatility_pct", 0.0)

    if diversification_score < RISK_DIVERSIFICATION_MIN:
        notes.append(f"분산도 점수가 낮습니다 ({diversification_score}점)")
    if top_holding_weight_pct >= RISK_TOP_HOLDING_MAX_PCT:
        notes.append(f"특정 종목 비중이 {top_holding_weight_pct:.0f}%로 과집중되어 있습니다")
    if annualized_volatility_pct >= RISK_VOLATILITY_MAX_PCT:
        notes.append(f"연환산 변동성이 {annualized_volatility_pct:.1f}%로 높습니다")

    if not notes:
        return None
    return " / ".join(notes)


async def fetch_market_and_risk_signal(
    user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType
) -> tuple[str | None, dict]:
    """market_level과 risk 지표(dict)를 안전하게 조회한다. 실패한 항목은 None/빈 dict로 폴백.

    drift-summary 배지, 알림 복합 트리거 등 tax 미리보기가 필요 없는 가벼운 호출부가 공용으로 쓴다.
    """
    market_signal_result, risk_result = await asyncio.gather(
        get_market_signal(cache),
        get_portfolio_risk_metrics(user_id, db, cache, portfolio_id=None),
        return_exceptions=True,
    )

    market_level: str | None = None
    if isinstance(market_signal_result, BaseException):
        logger.warning("diagnosis_market_signal_failed", error=str(market_signal_result))
    else:
        market_level = market_signal_result.get("composite_level")

    risk: dict = {}
    if isinstance(risk_result, BaseException):
        logger.warning("diagnosis_risk_metrics_failed", error=str(risk_result))
    else:
        risk = risk_result

    return market_level, risk


async def build_diagnosis_context(
    user_id: uuid.UUID,
    db: AsyncSession,
    cache: CacheStoreType,
    analysis: RebalancingAnalysis,
    overview: dict,
    enable_composite_signals: bool = True,
    settings_row: UserSettings | None = None,
) -> DiagnosisContext:
    """시장상황·리스크·세금영향을 조합한 진단 부가 설명을 생성한다.

    market_signal_service.get_market_signal()과 risk_service.get_portfolio_risk_metrics()를
    각각 try/except로 감싸 실패 시 안전 폴백(None/False)한다 — 정직한 실패 표시이며 GREEN으로
    지어내지 않는다. 세금 미리보기는 외부 API 없이 overview 데이터만으로 항상 계산 가능하다.

    enable_composite_signals(UserSettings.composite_signal_alerts_enabled)가 True이고
    check_composite_signal 조건이 충족되면 진단탭 상단 배너(CompositeSignalBanner)가 이미
    같은 내용을 보여주므로 market_note/risk_note는 생략해 중복 문구를 피한다.
    """
    market_level, risk = await fetch_market_and_risk_signal(user_id, db, cache)

    risk_available = bool(risk.get("data_available"))
    annualized_volatility_pct: float | None = None
    beta_sp500: float | None = None
    diversification_score: int | None = None
    top_holding_weight_pct: float | None = None
    if risk_available:
        annualized_volatility_pct = risk.get("annualized_volatility_pct")
        beta_sp500 = risk.get("beta_sp500")
        diversification_score = risk.get("diversification_score")
        top_holding_weight_pct = risk.get("top_holding_weight_pct")

    composite_triggered = False
    composite_reason: str | None = None
    if enable_composite_signals:
        composite_triggered, composite_reason = check_composite_signal(
            market_level, risk_available, diversification_score, top_holding_weight_pct, annualized_volatility_pct
        )

    if composite_triggered:
        market_note: str | None = None
        risk_note: str | None = None
    else:
        market_note = _MARKET_NOTES.get(market_level) if market_level else None
        risk_note = _risk_note(risk) if risk_available else None

    total_gain, overseas_tax, total_fee, tax_notes, tax_items = _build_tax_preview(analysis, overview)

    return DiagnosisContext(
        generated_at=datetime.now(UTC).isoformat(),
        market_level=market_level,
        market_note=market_note,
        risk_available=risk_available,
        annualized_volatility_pct=annualized_volatility_pct,
        beta_sp500=beta_sp500,
        diversification_score=diversification_score,
        risk_note=risk_note,
        composite_signal_triggered=composite_triggered,
        composite_signal_reason=composite_reason,
        estimated_sell_realized_gain_krw=round(total_gain, 0),
        estimated_overseas_tax_krw=round(overseas_tax, 0),
        estimated_fee_krw=round(total_fee, 0),
        tax_notes=tax_notes,
        tax_detail_items=tax_items,
        goal_annual_return_pct=settings_row.goal_annual_return_pct if settings_row else None,
        goal_annual_dividend_krw=settings_row.annual_dividend_goal if settings_row else None,
    )
