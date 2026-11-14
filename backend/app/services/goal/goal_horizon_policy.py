"""투자기간 × 세제유형 조합의 추천 정책 — 기간별 자산군·위험성향, 단기 주식 하한, IRP 안전자산 하한,
조합별 후보·시장 필터. 순수 계산이며 진입점(조회·최적화)은 `goal_horizon_recommendation_service.py`.
"""

from __future__ import annotations

from collections.abc import Callable

from app.constants import DEFAULT_GOAL_SHORT_TERM_EQUITY_FLOOR_PCT, DOMESTIC_MARKETS, MAX_GOAL_CANDIDATE_TICKERS
from app.enums import AccountTaxType
from app.models.user import UserSettings
from app.services.goal import _goal_recommendation_common as _grc
from app.services.goal.goal_candidate_service import (
    _TAX_TYPE_MARKET_GROUP,
    _apply_index_region_preference,
    _matches_index_region_preference,
    detect_duplicate_tracking_index_note,
    pension_exclusion_note,
    pension_ineligibility_reason,
)

_HORIZON_RISK_TOLERANCE: dict[str, str] = {
    "SHORT_TERM": "CONSERVATIVE",
    "MID_TERM": "BALANCED",
    "LONG_TERM": "AGGRESSIVE",
}
_HORIZON_ELIGIBLE_ASSET_CLASSES: dict[str, set[str]] = {
    "SHORT_TERM": {"BOND", "EQUITY", "CASH"},
    "MID_TERM": {"BOND", "EQUITY", "CASH"},
    "LONG_TERM": {"EQUITY"},
}

_DEFAULT_SHORT_TERM_EQUITY_FLOOR_PCT = DEFAULT_GOAL_SHORT_TERM_EQUITY_FLOOR_PCT
"""단기(최대 3년) 목표는 안전자산 위주가 아니라 주식을 최소 이 비율까지 담아 다소 공격적으로
구성한다 — 사용자가 UserSettings.goal_short_term_equity_floor_pct로 조정 가능, NULL이면 이 기본값
사용. 등록된 주식 후보가 하나도 없으면 이 제약은 적용하지 않고 기존(안전자산만으로 최소분산)
동작을 유지한다."""

_DEFAULT_IRP_SAFE_ASSET_FLOOR_PCT = 30.0
"""IRP(개인형퇴직연금) 계좌는 실제 퇴직연금 규제(위험자산 투자한도 70%)에 근거해 안전자산
(채권+현금성) 비중을 투자기간과 무관하게 항상 이 비율 이상 유지하도록 강제한다. 법규에 근거한
고정 규칙이라 `_DEFAULT_SHORT_TERM_EQUITY_FLOOR_PCT`와 달리 UserSettings 오버라이드 필드를
두지 않는다. 단기(SHORT_TERM) 조합에서는 이 규칙이 `_DEFAULT_SHORT_TERM_EQUITY_FLOOR_PCT`(주식
최소 80%)와 정면 충돌하므로 IRP가 우선하고 단기 주식 하한 규칙은 적용하지 않는다."""


def _short_term_equity_floor_from_settings(settings_row: UserSettings) -> float:
    raw = getattr(settings_row, "goal_short_term_equity_floor_pct", None)
    return (float(raw) if raw is not None else _DEFAULT_SHORT_TERM_EQUITY_FLOOR_PCT) / 100


def _horizon_equity_bounds(
    is_irp: bool,
    include_cash_equivalent: bool,
    candidates: list[_grc._GoalCandidate],
    short_term_equity_floor: float,
) -> tuple[float | None, float | None]:
    """(주식 비중 하한, 상한) — IRP는 안전자산 하한(=주식 상한), 현금성 합성 후보가 들어간 단기는 주식 하한."""
    if is_irp:
        return None, 1.0 - _DEFAULT_IRP_SAFE_ASSET_FLOOR_PCT / 100
    if include_cash_equivalent and any(c.asset_class == "EQUITY" for c in candidates):
        return short_term_equity_floor, None
    return None, None


def _horizon_policy_note(equity_floor: float | None, equity_ceiling: float | None) -> str | None:
    """옵티마이저 안내가 없을 때 대신 붙이는 단기 주식하한 / IRP 주식상한 설명."""
    if equity_floor is not None:
        return (
            f"단기(최대 3년) 목표는 안정적인 주식 위주로 최소 {equity_floor * 100:.0f}%까지 배분하고, "
            f"안전자산은 {100 - equity_floor * 100:.0f}% 이내로 제한합니다."
        )
    if equity_ceiling is not None:
        return (
            f"IRP(개인형퇴직연금) 계좌는 퇴직연금 규정에 따라 위험자산(주식)을 최대 "
            f"{equity_ceiling * 100:.0f}%로 제한하고, 안전자산(채권·현금성)을 최소 "
            f"{100 - equity_ceiling * 100:.0f}% 이상 배분합니다."
        )
    return None


def _combo_eligible_classes(horizon: str, tax_type: str) -> set[str]:
    eligible_classes = _HORIZON_ELIGIBLE_ASSET_CLASSES[horizon]
    if tax_type == AccountTaxType.IRP.value:
        # IRP는 퇴직연금 규제상 안전자산 최소 30% 하한이 투자기간과 무관하게 적용되므로,
        # LONG_TERM(원래 EQUITY만 허용)에서도 예외적으로 BOND/CASH 후보를 후보군에 포함시킨다.
        eligible_classes = eligible_classes | {"BOND", "CASH"}
    return eligible_classes


def _in_combo_market(c: dict[str, str], eligible_classes: set[str], tax_type: str) -> bool:
    """자산군이 기간에 맞고, 상장시장이 세제유형의 투자 가능 시장(국내/해외)에 맞는지."""
    market_group = _TAX_TYPE_MARKET_GROUP[tax_type]
    return c.get("asset_class", "EQUITY") in eligible_classes and (c["market"].upper() in DOMESTIC_MARKETS) == (
        market_group == "DOMESTIC"
    )


def _combo_market_filter(horizon: str, tax_type: str) -> Callable[[dict[str, str]], bool]:
    """배당 제안 후보 필터 — 조합의 시장·자산군·지역 선호·연금 매수가능 규칙을 그대로 적용한다."""
    eligible_classes = _combo_eligible_classes(horizon, tax_type)

    def _market_filter(c: dict[str, str]) -> bool:
        return (
            _in_combo_market(c, eligible_classes, tax_type)
            and _matches_index_region_preference(c, tax_type)
            and pension_ineligibility_reason(c, tax_type) is None
        )

    return _market_filter


def _select_combo_candidates(
    candidate_dicts: list[dict[str, str]],
    horizon: str,
    tax_type: str,
    existing_items: list[tuple[str, str, str]],
) -> tuple[list[dict[str, str]], str | None, list[dict[str, str]]]:
    """조합 하나의 후보를 고른다 — (적합 후보, 안내 문구, 큐레이션에서 자동 보강한 후보).

    `capacity_remaining`은 **지금까지 누적된** 전체 등록 후보 수 기준이다 — 앞선 조합이 보강한 후보가
    호출측에서 `candidate_dicts`에 이미 합쳐져 있어야 한다(`_compute_horizon_recommendations` 참고).
    """
    eligible_classes = _combo_eligible_classes(horizon, tax_type)
    market_eligible = [c for c in candidate_dicts if _in_combo_market(c, eligible_classes, tax_type)]
    # 연금저축·IRP: 레버리지·인버스·ETN·개별종목은 매수 불가 — 추천에서 제외(계획 37 E1)
    pension_excluded = [c for c in market_eligible if pension_ineligibility_reason(c, tax_type)]
    eligible_candidates = [c for c in market_eligible if c not in pension_excluded]
    capacity_remaining = MAX_GOAL_CANDIDATE_TICKERS - len(candidate_dicts)
    eligible_candidates, preference_fallback_note, added = _apply_index_region_preference(
        eligible_candidates, tax_type, capacity_remaining
    )
    note = _grc._join_notes(
        pension_exclusion_note(pension_excluded, tax_type),
        preference_fallback_note,
        detect_duplicate_tracking_index_note(eligible_candidates, existing_items),
    )
    return eligible_candidates, note, added
