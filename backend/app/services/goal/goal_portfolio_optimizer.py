"""목표 역산 추천 전용 MVO(Mean-Variance Optimization) 최적화 엔진.

`portfolio_optimizer.py`의 SLSQP 골격을 재사용하되, 기대수익률로 CAGR을 쓰고 목표수익률
이상을 제약으로 둔다는 점이 다르다 — 일반 효율적 프론티어 최적화는 `portfolio_optimizer.py`
참고. DB 의존 없는 순수 계산이라 `goal_recommendation_service.py`에서 분리했다.
"""

from __future__ import annotations

from app.constants import DEFAULT_GOAL_MAX_WEIGHT_PCT
from app.services.goal.goal_portfolio_weights import (
    _MIN_RETURN_DAYS,
    _annualized_covariance,
    _class_bounds_violated,
    _weights_to_items,
)

# 종목당 최대 비중 상한 (과도한 집중 방지) — UserSettings.goal_max_weight_pct로 조정 가능
_MAX_WEIGHT = DEFAULT_GOAL_MAX_WEIGHT_PCT / 100
_MIN_CANDIDATES = 2
_RISK_TOLERANCE_FRONTIER_FRACTION = {"CONSERVATIVE": 0.0, "BALANCED": 0.4, "AGGRESSIVE": 0.8}

_SIGNAL_FRONTIER_DAMPENING = {"RED": 0.3, "YELLOW": 0.7}
"""시장 위험 신호가 YELLOW/RED일 때 frontier_frac(리스크 성향 보간 비율)을 감쇠시켜 추천 비중을
최소분산(보수적) 쪽으로 당긴다 — GREEN/신호 조회 실패/STALE은 감쇠 없음(1.0, 기존 동작 유지).
IRP `equity_ceiling`/단기 `equity_floor` 같은 규제·정책성 하드 제약과는 별개 축이라 함께 건드리지
않는다 — 시장 신호는 "선택한 리스크 성향 내에서 얼마나 공격적으로 갈지"만 조정한다."""


def _dividend_floor_constraint(
    bounds: list[tuple[float, float]],
    dividend_list: tuple[float, ...],
    required_dividend_yield_pct: float,
    asset_classes: tuple[str, ...] | None = None,
    group_budget: dict[str, float] | None = None,
) -> tuple[dict | None, str | None]:
    """종목당 비중 상한(bounds) 하에서 목표 배당수익률 달성 가능 여부를 그리디하게 판정한다.

    `asset_classes`+`group_budget`이 함께 주어지면(`class_bounds`가 적용된 호출) 종목당
    상한뿐 아니라 자산군별 그룹 예산도 함께 반영한다 — `_optimize_goal_portfolio`의
    `max_achievable_return` 계산과 동일한 방식. 이걸 빠뜨리면 실제로는 자산군 하한 제약이
    저배당 종목에 비중을 강제로 배분시켜 달성 불가능한데도 "달성 가능"으로 오판해 SLSQP에
    불충족 제약을 넘기고 최적화 전체가 실패하는 버그가 생긴다(단기 추천의 주식비중 하한
    80%처럼 그룹 제약이 걸린 조합에서 실제로 재현됨).

    달성 가능하면 (SLSQP 부등식 제약 dict, None)을, 불가능하면 (None, 안내 note)를 반환한다
    — `_optimize_goal_portfolio`의 순환 복잡도를 낮추기 위해 분리한 헬퍼(로직 자체는 동일).
    """
    import numpy as np

    divs = np.array(dividend_list, dtype=float)
    group_used: dict[str, float] = {}
    achievable = 0.0
    remaining = 1.0
    for idx in np.argsort(-divs):
        cap = bounds[idx][1]
        if asset_classes is not None and group_budget is not None:
            cls = asset_classes[idx]
            cap = min(cap, group_budget[cls] - group_used.get(cls, 0.0))
        take = max(min(cap, remaining), 0.0)
        achievable += take * float(divs[idx])
        remaining -= take
        if asset_classes is not None and group_budget is not None:
            cls = asset_classes[idx]
            group_used[cls] = group_used.get(cls, 0.0) + take
        if remaining <= 1e-9:
            break

    if achievable + 1e-9 < required_dividend_yield_pct:
        note = (
            f"배당 목표(연 {required_dividend_yield_pct:.1f}%)를 충족하는 조합을 찾지 못해 "
            "자산 목표 기준으로만 계산했습니다"
        )
        return None, note

    constraint = {"type": "ineq", "fun": lambda w: float(w @ divs) - required_dividend_yield_pct}
    return constraint, None


def _apply_dividend_floor(
    constraints: list[dict],
    note: str | None,
    bounds: list[tuple[float, float]],
    dividend_list: tuple[float, ...],
    required_dividend_yield_pct: float | None,
    asset_classes: tuple[str, ...] | None = None,
    group_budget: dict[str, float] | None = None,
) -> tuple[list[dict], str | None]:
    """`_dividend_floor_constraint()` 결과를 constraints/note에 병합한다 — 호출부(`_optimize_goal_portfolio`)의
    순환 복잡도를 낮추기 위해 분기 처리를 이 헬퍼로 옮겼다. required_dividend_yield_pct가 없거나
    0 이하면(배당 목표 미설정) 아무것도 하지 않고 그대로 반환한다."""
    if required_dividend_yield_pct is None or required_dividend_yield_pct <= 0:
        return constraints, note

    constraint, dividend_note = _dividend_floor_constraint(
        bounds, dividend_list, required_dividend_yield_pct, asset_classes=asset_classes, group_budget=group_budget
    )
    if constraint is not None:
        constraints = [*constraints, constraint]
    if dividend_note:
        note = f"{note} {dividend_note}" if note else dividend_note
    return constraints, note


def _solve_with_dividend_fallback(
    objective,
    x0,
    bounds: list[tuple[float, float]],
    constraints: list[dict],
    constraints_without_dividend: list[dict],
    required_dividend_yield_pct: float | None,
    note: str | None,
):
    """SLSQP를 풀고, 배당 제약이 추가된 상태로 실패하면 배당 제약만 뺀 채로 한 번 더 시도한다
    (호출부 `_optimize_goal_portfolio`의 순환 복잡도를 낮추기 위해 분리한 헬퍼).

    배당 목표 사전검증(`_dividend_floor_constraint`)은 종목당 상한·주식/비주식 그룹예산만 보고
    판정하므로, BALANCED/AGGRESSIVE의 "가중평균 CAGR = target" 등식 제약처럼 사전검증이 모르는
    다른 제약과 배당 제약이 동시에는 충족 불가능한 조합을 예측하지 못할 수 있다 — 배당 하나만
    보면 달성 가능해도 수익률 목표와 동시에는 불가능한 경우가 실제로 있다(장기=AGGRESSIVE +
    배당목표 조합에서 재현됨). 이 경우도 배당 목표 미달성은 fail-soft여야 하므로, SLSQP가
    실패했고 그 원인이 배당 제약 추가일 수 있으면(제약 개수가 늘었으면) 배당 제약만 뺀 채로
    재시도한다.
    """
    from scipy.optimize import minimize

    options = {"ftol": 1e-9, "maxiter": 500}
    res = minimize(objective, x0=x0, method="SLSQP", bounds=bounds, constraints=constraints, options=options)
    if res.success or len(constraints) <= len(constraints_without_dividend):
        return res, note

    retry_res = minimize(
        objective, x0=x0, method="SLSQP", bounds=bounds, constraints=constraints_without_dividend, options=options
    )
    if not retry_res.success:
        return res, note

    dividend_note = (
        f"배당 목표(연 {required_dividend_yield_pct:.1f}%)를 다른 조건과 함께 만족하는 "
        "포트폴리오를 찾지 못해 자산 목표 기준으로만 계산했습니다"
    )
    return retry_res, (f"{note} {dividend_note}" if note else dividend_note)


def _resolve_class_bounds(
    classes: tuple[str, ...],
    class_bounds: dict[str, tuple[float, float]] | None,
    n: int,
    max_weight_used: float,
) -> tuple[list[tuple[float, float]], dict[str, float], list[str]]:
    """자산군별 종목당 상한(bounds)·그룹 예산(group_budget)·활성 자산군 목록을 계산한다 —
    `_optimize_goal_portfolio`의 순환 복잡도를 낮추기 위해 분리한 헬퍼.

    자산군이 후보 전부이거나 전무하면 비교 대상이 없어 제약이 무의미하므로 무시한다
    (equity_floor/ceiling의 "0 < n_equity < n" 가드를 N개 자산군으로 일반화).

    각 자산군의 "유효 하한"·"유효 상한"은 자기 자신의 명시적 범위와, 다른 모든 자산군의 명시적
    범위로부터 총합=1 제약을 통해 유도되는 묵시적 범위(다른 자산군 상한 합이 작을수록 이
    자산군의 하한이 올라가고, 다른 자산군 하한 합이 클수록 이 자산군의 상한이 내려간다) 중
    더 타이트한 쪽이다 — equity_ceiling이 "안전자산 하한"을, equity_floor가 "안전자산 상한"을
    자동 함의하던 기존 대칭 로직을 N개 자산군으로 일반화한 것. 다른 자산군 중 범위가 지정되지
    않은 것이 있으면(기본값 (0,1)) 묵시적 범위는 자연스럽게 무력화된다(기존과 동일하게 안전).
    유효 하한은 종목당 상한(bounds) 완화에, 유효 상한은 `group_budget`(그리디 max_achievable_return·
    배당 달성가능성 검증 공용)에 쓰인다 — 둘 다 실제 SLSQP 부등식 제약으로는 추가하지 않고
    (명시적으로 지정된 자산군에 대해서만 호출부에서 별도로 추가한다) box 제약·예산 계산에만
    반영한다. 묵시적 범위를 SLSQP 제약으로 다시 추가하면 총합=1 제약과 선형종속돼 야코비안이
    특이해질 위험이 있다.
    """
    bounds_in = class_bounds or {}

    def _class_bound(cls: str) -> tuple[float, float]:
        return bounds_in.get(cls, (0.0, 1.0))

    class_counts: dict[str, int] = {}
    for cls in classes:
        class_counts[cls] = class_counts.get(cls, 0) + 1
    present_classes = list(class_counts.keys())
    active_classes = [c for c in present_classes if 0 < class_counts[c] < n]

    effective_lower: dict[str, float] = {}
    effective_upper: dict[str, float] = {}
    for c in active_classes:
        explicit_lower, explicit_upper = _class_bound(c)
        other_upper_sum = sum(_class_bound(c2)[1] for c2 in present_classes if c2 != c)
        other_lower_sum = sum(_class_bound(c2)[0] for c2 in present_classes if c2 != c)
        effective_lower[c] = max(explicit_lower, 1.0 - other_upper_sum, 0.0)
        effective_upper[c] = min(explicit_upper, 1.0 - other_lower_sum, 1.0)

    bounds = [
        (
            0.0,
            max(max_weight_used, effective_lower[cls] / class_counts[cls])
            if effective_lower.get(cls, 0.0) > 0
            else max_weight_used,
        )
        for cls in classes
    ]
    group_budget = {c: (effective_upper[c] if c in active_classes else _class_bound(c)[1]) for c in present_classes}
    return bounds, group_budget, active_classes


def _class_range_constraints(
    classes: tuple[str, ...],
    class_bounds: dict[str, tuple[float, float]] | None,
    active_classes: list[str],
) -> list[dict]:
    """명시적으로 범위가 지정된 자산군에 대해서만 SLSQP 부등식 제약을 만든다 —
    `_optimize_goal_portfolio`의 순환 복잡도를 낮추기 위해 분리한 헬퍼(로직은 `_resolve_class_bounds`의
    독스트링 참고)."""
    import numpy as np

    bounds_in = class_bounds or {}
    constraints: list[dict] = []
    for c in active_classes:
        lower_c, upper_c = bounds_in.get(c, (0.0, 1.0))
        if lower_c <= 0 and upper_c >= 1.0:
            continue
        mask = np.array([cls == c for cls in classes], dtype=bool)
        if lower_c > 0:
            constraints.append({"type": "ineq", "fun": lambda w, m=mask, lo=lower_c: float(w[m].sum()) - lo})
        if upper_c < 1.0:
            constraints.append({"type": "ineq", "fun": lambda w, m=mask, up=upper_c: up - float(w[m].sum())})
    return constraints


def _optimize_goal_portfolio(
    symbols: list[str],
    tickers: list[tuple[str, str, str]],  # (ticker, name, market)
    cagr_pct: list[float],
    returns_map: dict[str, list[float]],
    required_return_pct: float,
    max_weight: float = _MAX_WEIGHT,
    risk_tolerance: str = "CONSERVATIVE",
    asset_classes: list[str] | None = None,
    class_bounds: dict[str, tuple[float, float]] | None = None,
    market_signal_level: str | None = None,
    dividend_yields: list[float] | None = None,
    required_dividend_yield_pct: float | None = None,
) -> tuple[list[dict], float | None, float | None, str | None]:
    """분산 최소화 + 목표수익률 제약(SLSQP). 동기 함수.

    반환: (recommended_items, expected_return_pct, expected_volatility_pct, note).

    `required_return_pct`는 실행가능성 하드체크(달성 불가 판정)에 쓰이는 필요수익률이다.

    CONSERVATIVE(기본값)는 오늘까지의 동작과 동일하게 "필요수익률 이상"이라는 부등식 제약만
    사용해 순수 최소분산 포트폴리오를 찾는다. BALANCED/AGGRESSIVE는 제약 없는 최소분산
    포트폴리오의 "자연 수익률"과 종목당 최대 비중 제약 하에서 달성 가능한 최대 가중평균
    CAGR 사이를 성향 비율(`_RISK_TOLERANCE_FRONTIER_FRACTION`)로 보간한 지점을 **등식 제약**으로
    고정한다 — 부등식과 달리 이미 자연 수익률이 목표를 넘는 경우에도 항상 실제로 비중이
    달라짐을 보장한다.

    `asset_classes`(종목별 EQUITY/BOND/CASH 등 자산군 태그)+`class_bounds`(자산군별
    `(하한, 상한)` 비율, 0~1)가 함께 주어지면 각 자산군의 비중 합이 그 범위 안에 들도록 부등식
    제약을 추가한다. 자산군이 후보 전부이거나 전무하면(비교 대상이 없어 제약이 무의미) 그
    자산군은 무시한다. 과거의 이분법(`is_equity`+`equity_floor`/`equity_ceiling`)은 이 함수의
    N개 자산군 일반화 버전이다 — 호출측은 `class_bounds={"EQUITY": (equity_floor, 1.0)}`
    (단기 추천, 주식 하한) 또는 `class_bounds={"EQUITY": (0.0, equity_ceiling)}`(IRP, 주식
    상한)로 그대로 대응시키면 이전과 동일하게 동작한다.

    한 자산군에만 명시적 범위를 지정해도(예: EQUITY 하한만) 총합=1 제약으로부터 나머지
    자산군들의 묵시적 범위가 자동으로 유도된다 — 예를 들어 EQUITY 하한이 있으면 "나머지
    자산군 합 ≤ 1-EQUITY하한"이 자동 성립한다(반대로 EQUITY 상한이 있으면 "나머지 합 ≥
    1-EQUITY상한"). 이런 묵시적 범위는 별도 SLSQP 제약으로 추가하지 않고(총합=1 제약과
    선형종속이 되어 SLSQP 야코비안이 특이(singular)해질 위험이 있다) 종목당 비중 상한(bounds)만
    넉넉히 완화해 옵티마이저가 실제로 그 지점에 도달할 수 있게 한다 — 명시적으로 지정된
    자산군의 범위만 실제 SLSQP 부등식 제약으로 추가된다.

    `market_signal_level`(GREEN/YELLOW/RED)이 주어지면 `_SIGNAL_FRONTIER_DAMPENING`에 따라
    `frontier_frac`을 감쇠시켜 최소분산 쪽으로 결과를 당긴다 — `class_bounds` 같은 규제·정책성
    하드 제약과는 별개 축이라 함께 조정하지 않는다.

    `dividend_yields`+`required_dividend_yield_pct`가 함께 주어지면 "가중평균 배당수익률 ≥
    required_dividend_yield_pct" 부등식 제약을 추가한다 — 배당 목표(`UserSettings.annual_dividend_goal`)를
    실제 비중 계산에 반영하기 위함(과거에는 표시용으로만 사후 계산되고 최적화 입력으로 쓰이지
    않았음). 종목당 비중 상한(bounds) 하에서, `class_bounds`가 걸려 있으면 그 그룹 예산까지
    함께 반영해 그리디하게 계산한 달성 가능 최대 배당수익률이 목표에 못 미치면 제약을
    적용하지 않고(자산 목표 기준으로만 계산) note에 안내를 남긴다 — 배당 목표를 못 채운다고
    전체 추천 자체를 실패시키지 않는다(fail-soft). 그룹 예산을 무시하고 종목당 상한만으로
    판정하면, 자산군 하한 제약이 저배당 종목에 비중을 강제로 배분시켜 실제로는 불가능한데도
    "달성 가능"으로 오판해 SLSQP에 불충족 제약을 넘기고 최적화 전체가 실패(빈 추천)하는 버그가
    생긴다(단기/IRP 추천에서 실제 재현됨).
    """
    import numpy as np

    from app.services.estimation import shrink_expected_returns

    valid = _valid_optimizer_inputs(symbols, tickers, cagr_pct, returns_map, asset_classes, dividend_yields)
    if len(valid) < _MIN_CANDIDATES:
        return [], None, None, f"추천에 충분한 시세 데이터가 있는 종목이 {_MIN_CANDIDATES}개 미만입니다"

    syms, tks, cagrs_list, classes, dividend_list = zip(*valid, strict=False)
    cagrs_raw = np.array(cagrs_list, dtype=float)
    n = len(syms)

    # 상한이 걸린 자산군만 남으면 지킬 수 없다 — 제약을 조용히 버리면 "안전자산 30%" 안내와 100% 주식이 함께 나온다
    for cls, (_lower, upper) in (class_bounds or {}).items():
        if upper < 1.0 and all(c == cls for c in classes):
            return (
                [],
                None,
                None,
                "자산군 비중 상한을 지킬 수 없습니다 — 다른 자산군(채권/현금성 등) 후보를 추가해주세요",
            )

    if float(cagrs_raw.max()) < required_return_pct:
        return [], None, None, f"큐레이션 종목만으로는 목표 수익률(연 {required_return_pct:.1f}%)을 달성하기 어렵습니다"

    # 축소추정(shrinkage estimation) — 표본 평균·표본 공분산을 그대로 쓰면 추정오차가 최적화
    # 결과에 그대로 반영돼 과최적화된 극단적 비중을 만들기 쉽다. 실행가능성 판정(위 max() 비교)은
    # "이론상 최선의 경우"를 봐야 하므로 축소 전 원본값을 쓰고, 이후 실제 최적화 입력으로는
    # 축소추정치를 쓴다.
    cagrs = shrink_expected_returns(cagrs_raw)
    cov_annual = _annualized_covariance(syms, returns_map)

    max_weight_used = max(max_weight, 1.0 / n)  # n이 작아 상한 합이 100%를 못 채우면 완화

    bounds, group_budget, active_classes = _resolve_class_bounds(classes, class_bounds, n, max_weight_used)
    x0 = np.full(n, 1.0 / n)

    class_constraints = _class_range_constraints(classes, class_bounds, active_classes)
    effective_frontier_frac, note = _signal_adjusted_frontier_fraction(risk_tolerance, market_signal_level)
    constraints, note = _return_constraints(
        cagrs,
        cov_annual,
        x0,
        bounds,
        classes,
        group_budget,
        required_return_pct,
        effective_frontier_frac,
        note,
        class_constraints,
    )
    # 명시적으로 범위가 지정된 자산군만 실제 SLSQP 부등식 제약으로 추가한다 — 묵시적으로
    # 유도되는 범위는 `_resolve_class_bounds`가 이미 bounds(종목당 상한) 완화에 반영했으므로
    # 여기서 별도 제약으로 다시 추가하면 총합=1 제약과 선형종속돼 야코비안이 특이해질 위험이
    # 있다(no_spread 케이스와 동일한 이유).
    constraints = [*constraints, *class_constraints]

    # 자산군 범위가 걸려 있으면 배당 달성가능성 검증도 동일한 group_budget으로 제한한다(위
    # max_achievable_return 계산과 동일한 이유) — 그렇지 않으면 실제로는 자산군 하한 제약이
    # 저배당 종목에 비중을 강제로 배분시켜 달성 불가능한데도 종목당 상한만 보고 "달성 가능"으로
    # 오판해 SLSQP에 불충족 제약을 넘기고 최적화 전체가 실패한다(단기/IRP 추천에서 실제 재현됨).
    # required_dividend_yield_pct가 없으면(배당 목표 미설정) 헬퍼 내부에서 즉시 no-op.
    dividend_group_budget = group_budget if active_classes else None
    dividend_classes = classes if active_classes else None
    constraints_without_dividend = constraints
    constraints, note = _apply_dividend_floor(
        constraints,
        note,
        bounds,
        dividend_list,
        required_dividend_yield_pct,
        asset_classes=dividend_classes,
        group_budget=dividend_group_budget,
    )

    res, note = _solve_with_dividend_fallback(
        lambda w: float(w @ cov_annual @ w),
        x0,
        bounds,
        constraints,
        constraints_without_dividend,
        required_dividend_yield_pct,
        note,
    )
    if not res.success:
        return [], None, None, "제약 조건을 만족하는 포트폴리오를 찾지 못했습니다"

    weights = res.x
    expected_return = round(float(weights @ cagrs), 2)
    expected_volatility = round(float(np.sqrt(weights @ cov_annual @ weights)) * 100, 2)
    active_bounds = {c: (class_bounds or {}).get(c, (0.0, 1.0)) for c in active_classes}
    items = _weights_to_items(tks, weights, classes, active_bounds, [b[1] for b in bounds])
    if _class_bounds_violated(items, active_bounds):
        return [], None, None, "제약 조건을 만족하는 포트폴리오를 찾지 못했습니다"
    return (
        [{k: v for k, v in item.items() if k != "_class"} for item in items],
        expected_return,
        expected_volatility,
        note,
    )


def _valid_optimizer_inputs(
    symbols: list[str],
    tickers: list[tuple[str, str, str]],
    cagr_pct: list[float],
    returns_map: dict[str, list[float]],
    asset_classes: list[str] | None,
    dividend_yields: list[float] | None,
) -> list[tuple[str, tuple[str, str, str], float, str, float]]:
    """일별수익률이 `_MIN_RETURN_DAYS` 이상 확보된 후보만 (심볼, 티커, CAGR, 자산군, 배당수익률)로 묶는다.

    자산군/배당수익률이 없으면 각각 전부 EQUITY / 0으로 본다."""
    asset_classes_in = asset_classes or ["EQUITY"] * len(symbols)
    dividend_yields_in = dividend_yields or [0.0] * len(symbols)
    return [
        (s, tk, c, ac, dy)
        for s, tk, c, ac, dy in zip(symbols, tickers, cagr_pct, asset_classes_in, dividend_yields_in, strict=False)
        if s in returns_map and len(returns_map[s]) >= _MIN_RETURN_DAYS
    ]


def _max_achievable_return(
    cagrs,
    bounds: list[tuple[float, float]],
    classes: tuple[str, ...],
    group_budget: dict[str, float],
) -> float:
    """종목당 상한·자산군 예산을 지키며 고CAGR 종목부터 그리디하게 채웠을 때의 최대 가중평균 CAGR.

    자산군별 예산(그리디 max_achievable_return·배당 달성가능성 검증 공용) — 명시적 상한이
    없으면(기본 1.0) 무제한. 자산군 범위가 걸려 있으면 해당 그룹의 합산 상한도 함께 지켜야
    한다. 그렇지 않으면 BALANCED/AGGRESSIVE 성향의 프론티어 목표(target)가 그 그룹 제약과
    동시에 만족 불가능한 지점으로 계산돼 옵티마이저가 실패할 수 있다(예: IRP 안전자산 30%
    하한 + LONG_TERM AGGRESSIVE 조합). 상한이 없다면 cagrs.max()겠지만, 캡이 있으면 고CAGR
    종목에만 몰아줄 수 없으므로 그보다 낮을 수 있음.
    """
    import numpy as np

    group_used: dict[str, float] = dict.fromkeys(group_budget, 0.0)
    max_achievable_return = 0.0
    remaining = 1.0
    for idx in np.argsort(-cagrs):
        cls = classes[idx]
        take = max(min(bounds[idx][1], remaining, group_budget[cls] - group_used[cls]), 0.0)
        max_achievable_return += take * float(cagrs[idx])
        remaining -= take
        group_used[cls] += take
        if remaining <= 1e-9:
            break
    return max_achievable_return


def _signal_adjusted_frontier_fraction(
    risk_tolerance: str, market_signal_level: str | None
) -> tuple[float, str | None]:
    """(리스크 성향 보간 비율 × 시장신호 감쇠, 감쇠가 실제로 적용됐으면 그 안내 문구)."""
    frontier_frac = _RISK_TOLERANCE_FRONTIER_FRACTION.get(risk_tolerance, 0.0)
    signal_dampening = _SIGNAL_FRONTIER_DAMPENING.get(market_signal_level or "", 1.0)
    note = None
    if signal_dampening < 1.0 and frontier_frac > 0.0:
        note = f"시장 위험 신호({market_signal_level})를 반영해 추천 비중을 보수적으로 조정했습니다"
    return frontier_frac * signal_dampening, note


def _return_constraints(
    cagrs,
    cov_annual,
    x0,
    bounds: list[tuple[float, float]],
    classes: tuple[str, ...],
    group_budget: dict[str, float],
    required_return_pct: float,
    effective_frontier_frac: float,
    note: str | None,
    class_constraints: list[dict] | None = None,
) -> tuple[list[dict], str | None]:
    """총합=1 + 수익률 제약을 만든다(자산군·배당 제약은 호출측이 뒤에 덧붙인다).

    CONSERVATIVE(보간 비율 0)는 "필요수익률 이상" 부등식, BALANCED/AGGRESSIVE는 제약 없는 최소분산
    포트폴리오의 자연 수익률과 달성 가능 최대 수익률 사이 보간 지점을 등식으로 고정한다.
    자산군 제약이 있으면 목표를 그 제약 안에서 낼 수 있는 최소 수익률 이상으로 올린다 — 시장 신호 감쇠로 목표가 낮아지면
    자산군 하한을 지키면서는 도달할 수 없어 최적화가 실패하고 빈 추천이 나왔다. 정상 범위의 목표는 바꾸지 않는다.
    """
    import numpy as np
    from scipy.optimize import minimize

    sum_to_one = {"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0}
    if effective_frontier_frac <= 0.0:
        # CONSERVATIVE(또는 미인식 값) — 기존과 동일한 코드 경로, 순수 최소분산 + 부등식 제약
        return [sum_to_one, {"type": "ineq", "fun": lambda w: float(w @ cagrs) - required_return_pct}], note

    baseline_res = minimize(
        lambda w: float(w @ cov_annual @ w),
        x0=x0,
        method="SLSQP",
        bounds=bounds,
        constraints=[{"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0}],
        options={"ftol": 1e-9, "maxiter": 500},
    )
    natural_return = float(baseline_res.x @ cagrs) if baseline_res.success else required_return_pct

    frontier_low = max(natural_return, required_return_pct)
    frontier_high = _max_achievable_return(cagrs, bounds, classes, group_budget)
    target = frontier_low + effective_frontier_frac * max(frontier_high - frontier_low, 0.0)
    if class_constraints:
        constrained_res = minimize(
            lambda w: float(w @ cov_annual @ w),
            x0=x0,
            method="SLSQP",
            bounds=bounds,
            constraints=[{"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0}, *class_constraints],
            options={"ftol": 1e-9, "maxiter": 500},
        )
        if constrained_res.success:
            target = max(target, float(constrained_res.x @ cagrs))
    target = min(max(target, required_return_pct), frontier_high)

    no_spread = frontier_high - frontier_low < 1e-6
    if no_spread:
        spread_note = "선택한 리스크 성향을 반영하기에는 후보 종목 간 기대수익률 차이가 크지 않습니다"
        note = f"{note} {spread_note}" if note else spread_note

    # 후보 간 기대수익률 차이가 거의 없으면(no_spread) "가중평균 CAGR = target" 등식 제약의
    # 그래디언트(cagrs 벡터)가 총합=1 제약의 그래디언트(전부 1인 벡터)와 사실상 평행해져
    # SLSQP의 QP 서브문제 야코비안이 특이(singular)해져 최적화 전체가 실패한다 — 실제로
    # 축소추정(James-Stein) 도입 후 유사한 CAGR을 가진 후보가 많은 경우(예: 10종목 큐레이션
    # 유니버스) 흔하게 재현된다. 이 경우 부등식 제약(CONSERVATIVE와 동일)으로 대체해 등식
    # 제약의 중복을 피한다 — 어차피 목표 지점 간 차이가 없어 등식으로 고정할 실익도 없다.
    return_constraint = (
        {"type": "ineq", "fun": lambda w: float(w @ cagrs) - required_return_pct}
        if no_spread
        else {"type": "eq", "fun": lambda w: float(w @ cagrs) - target}
    )
    return [sum_to_one, return_constraint], note
