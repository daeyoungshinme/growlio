"""추천 비중 변화 판정 — 프론트 `utils/recommendationDrift.ts`와 같은 규칙(임계값 함께 맞출 것).

주간 추천 변화 알림(`alerts/recommendation_drift_alert_service`)이 쓴다. 순수 계산.
"""

from __future__ import annotations

from typing import Any

from app.services.rebalancing.group_expansion import group_owner_map

RECOMMENDATION_DRIFT_THRESHOLD_PCT = 3.0
"""`frontend/src/utils/recommendationDrift.ts`의 RECOMMENDATION_DRIFT_THRESHOLD_PCT와 동일하게
유지 — 프론트(화면을 열었을 때 배지)와 백엔드(주간 알림 job)가 같은 기준으로 "유의미한 변화"를
판단하게 하기 위함. 한쪽만 바꾸면 배지와 알림의 민감도가 어긋나므로 항상 함께 바꿀 것."""


def compute_recommendation_drift(
    recommended: list[tuple[str, str, float]],  # (ticker, market, weight 0~100)
    current: list[tuple[str, str, float]],
) -> tuple[float, int]:
    """`frontend/src/utils/recommendationDrift.ts`의 `computeRecommendationDrift()`와 동일한 로직을
    백엔드에 포팅한 것 — ticker+market 키로 매칭해 (최대 비중차이%p, 신규후보개수)를 반환한다.
    "유의미한 변화" 판정(`RECOMMENDATION_DRIFT_THRESHOLD_PCT` 이상 또는 신규후보 존재)은
    호출측(`recommendation_drift_alert_service.py`)이 담당한다.
    """
    current_by_key = {(t, m): w for t, m, w in current}
    max_delta_pct = 0.0
    new_candidate_count = 0
    for t, m, w in recommended:
        current_weight = current_by_key.get((t, m))
        if current_weight is None:
            new_candidate_count += 1
            continue
        max_delta_pct = max(max_delta_pct, abs(w - current_weight))
    return round(max_delta_pct, 1), new_candidate_count


def fold_into_portfolio_groups(
    recommended: list[tuple[str, str, float]], portfolio_items: list[Any]
) -> list[tuple[str, str, float]]:
    """추천 종목 중 포트폴리오 지수 그룹(plans/74)에 속한 종목은 그 그룹(대표 종목 키)으로 합산한다.

    그룹 항목은 대표 종목 키 하나로 목표 비중을 가지므로, 추천이 같은 지수의 다른 종목(예: SPY ↔ 그룹 대표 VOO)을
    내도 "신규 후보"로 세지 않는다. 프론트 `recommendationDrift.ts`의 `foldIntoPortfolioGroups()`와 같은 규칙.
    """
    # 추천·저장 비중은 투자금 기준이라 레버리지 배수는 곱하지 않는다(그룹 합산 키만 사용)
    owner = group_owner_map(portfolio_items)
    if not owner:
        return recommended
    folded: dict[tuple[str, str], float] = {}
    for t, m, w in recommended:
        key = owner[(t, m)][0] if (t, m) in owner else (t, m)
        folded[key] = folded.get(key, 0.0) + w
    return [(t, m, w) for (t, m), w in folded.items()]
