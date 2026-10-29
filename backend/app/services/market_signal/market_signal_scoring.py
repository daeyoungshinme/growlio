"""시장 위험 신호 — 개별 지표 sub_score를 합산해 복합 점수·레벨(GREEN/YELLOW/RED/STALE)을 계산하는 순수 함수.

`market_signal_service.py`에서 분리(docs/plans/41). I/O 없음.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# 복합 신호 계산
# ---------------------------------------------------------------------------


# 가중치(sub_score 상한) 산정 기준 — 신규 지표 추가/조정 시 반드시 아래 3기준으로 재검토할 것
# (docs/plans/21-market-signal-methodology.md 방법론 개선의 일부, 정성적 판단 — 정량 검증은 Phase 3 리서치 예정)
#   Tier A (상한 4): 과거 위기 국면 선행/동행성이 실증적으로 뚜렷한 지표 — VIX, 하이일드 스프레드,
#           고용(실업률 Sahm Rule-lite — 실증적으로 가장 신뢰도 높은 경기침체 선행지표 중 하나)
#   Tier B (상한 3): 방향성은 유효하나 다른 지표와 정보 중복 위험 — 미국 금리 커브, 인플레이션
#           (T10Y2Y+DGS2-FEDFUNDS는 둘 다 "Fed 정책금리 경로 기대"를, CPI+PCE는 둘 다
#            "미국 인플레이션 추세"를 반영해 완전 병합, worst-case만 채택)
#   Tier C (상한 3): 원 지표 부재로 대체한 프록시 — 달러인덱스/환율/유가(20일 이격도 방향성 근사)
#   (구 Tier C였던 Fear & Greed Index는 크립토 시장 전용 API를 일반 주식시장 심리 프록시로 쓰던 것이라
#    태생적 한계가 커 완전 제거됨)
#
# 복합 점수 임계값 — 기존 6개 신호(상한 20, GREEN 23.08%/YELLOW 53.85%) 비율을 그대로 유지해
# 8개 신호(상한 27, 인플레이션+3·고용+4 추가)로 재계산: 27*0.2308≈6.2→6, 27*0.5385≈14.5→15
COMPOSITE_SCORE_MAX = 27
_GREEN_MAX = 6
_YELLOW_MAX = 15

# 신호 8개 중 이 개수 미만만 조회에 성공하면(예: FRED_API_KEY 미설정으로 다수가 한꺼번에 실패)
# 남은 신호만으로는 복합 레벨을 신뢰할 수 없다고 판단해 PARTIAL이 아닌 STALE로 취급한다.
# STALE은 AUTO 실행 게이트(order_builder.is_market_signal_blocking_auto_mode)가
# CAUTIOUS/STRICT 모드에서 보수적으로 차단하는 트리거이기도 하다.
# 신호 수가 6→8로 늘며 기존 50%(6개 중 3개) 기준 비율을 그대로 유지해 4로 조정한다.
_MIN_RELIABLE_SIGNAL_COUNT = 4


def compute_composite_signal(
    vix: dict[str, Any] | None,
    us_rate_curve: dict[str, Any] | None,
    high_yield_spread: dict[str, Any] | None = None,
    dollar_index: dict[str, Any] | None = None,
    exchange_rate: dict[str, Any] | None = None,
    oil_price: dict[str, Any] | None = None,
    inflation: dict[str, Any] | None = None,
    employment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """여덟 신호를 점수화해 GREEN/YELLOW/RED 복합 레벨을 반환한다.

    각 신호 조회 실패 시 해당 점수를 0으로 처리 (안전 방향 처리) — 단, 성공한 신호 수가
    `_MIN_RELIABLE_SIGNAL_COUNT` 미만이면 이 "안전 방향 처리"가 오히려 실제 위험을 가리는
    결과(예: GREEN 오판)를 낳을 수 있어 `data_freshness`를 STALE로 격상시킨다.
    총점 0–6 → GREEN, 7–15 → YELLOW, 16–27 → RED.
    """
    vix_score = vix["sub_score"] if vix else 0
    rate_curve_score = us_rate_curve["sub_score"] if us_rate_curve else 0
    hy_score = high_yield_spread["sub_score"] if high_yield_spread else 0
    usd_score = dollar_index["sub_score"] if dollar_index else 0
    fx_score = exchange_rate["sub_score"] if exchange_rate else 0
    oil_score = oil_price["sub_score"] if oil_price else 0
    inflation_score = inflation["sub_score"] if inflation else 0
    employment_score = employment["sub_score"] if employment else 0
    total = (
        vix_score + rate_curve_score + hy_score + usd_score + fx_score + oil_score + inflation_score + employment_score
    )

    if total <= _GREEN_MAX:
        level = "GREEN"
    elif total <= _YELLOW_MAX:
        level = "YELLOW"
    else:
        level = "RED"

    all_signals = (
        vix,
        us_rate_curve,
        high_yield_spread,
        dollar_index,
        exchange_rate,
        oil_price,
        inflation,
        employment,
    )
    available_count = sum(1 for s in all_signals if s is not None)
    if available_count == 0 or available_count < _MIN_RELIABLE_SIGNAL_COUNT:
        data_freshness = "STALE"
    elif available_count < len(all_signals):
        data_freshness = "PARTIAL"
    else:
        data_freshness = "LIVE"

    return {
        "composite_level": level,
        "composite_score": total,
        "composite_score_max": COMPOSITE_SCORE_MAX,
        "signals": {
            "vix": vix,
            "us_rate_curve": us_rate_curve,
            "high_yield_spread": high_yield_spread,
            "dollar_index": dollar_index,
            "exchange_rate": exchange_rate,
            "oil_price": oil_price,
            "inflation": inflation,
            "employment": employment,
        },
        "computed_at": datetime.now(UTC).isoformat(),
        "data_freshness": data_freshness,
    }
