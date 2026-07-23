"""목표 역산 추천 전용 MVO(Mean-Variance Optimization) 최적화 엔진.

`portfolio_optimizer.py`의 SLSQP 골격을 재사용하되, 기대수익률로 CAGR을 쓰고 목표수익률
이상을 제약으로 둔다는 점이 다르다 — 일반 효율적 프론티어 최적화는 `portfolio_optimizer.py`
참고. DB 의존 없는 순수 계산이라 `goal_recommendation_service.py`에서 분리했다.
"""

from __future__ import annotations

_MAX_WEIGHT = 0.4  # 종목당 최대 비중 상한 (과도한 집중 방지) — 기본값, UserSettings.goal_max_weight_pct로 조정 가능
_MIN_RETURN_DAYS = 30
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
) -> tuple[dict | None, str | None]:
    """종목당 비중 상한(bounds) 하에서 목표 배당수익률 달성 가능 여부를 그리디하게 판정한다.

    달성 가능하면 (SLSQP 부등식 제약 dict, None)을, 불가능하면 (None, 안내 note)를 반환한다
    — `_optimize_goal_portfolio`의 순환 복잡도를 낮추기 위해 분리한 헬퍼(로직 자체는 동일).
    """
    import numpy as np

    divs = np.array(dividend_list, dtype=float)
    achievable = 0.0
    remaining = 1.0
    for idx in np.argsort(-divs):
        take = max(min(bounds[idx][1], remaining), 0.0)
        achievable += take * float(divs[idx])
        remaining -= take
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
) -> tuple[list[dict], str | None]:
    """`_dividend_floor_constraint()` 결과를 constraints/note에 병합한다 — 호출부(`_optimize_goal_portfolio`)의
    순환 복잡도를 낮추기 위해 분기 처리를 이 헬퍼로 옮겼다. required_dividend_yield_pct가 없거나
    0 이하면(배당 목표 미설정) 아무것도 하지 않고 그대로 반환한다."""
    if required_dividend_yield_pct is None or required_dividend_yield_pct <= 0:
        return constraints, note

    constraint, dividend_note = _dividend_floor_constraint(bounds, dividend_list, required_dividend_yield_pct)
    if constraint is not None:
        constraints = [*constraints, constraint]
    if dividend_note:
        note = f"{note} {dividend_note}" if note else dividend_note
    return constraints, note


def _optimize_goal_portfolio(
    symbols: list[str],
    tickers: list[tuple[str, str, str]],  # (ticker, name, market)
    cagr_pct: list[float],
    returns_map: dict[str, list[float]],
    required_return_pct: float,
    max_weight: float = _MAX_WEIGHT,
    risk_tolerance: str = "CONSERVATIVE",
    is_equity: list[bool] | None = None,
    equity_floor: float | None = None,
    equity_ceiling: float | None = None,
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

    `is_equity`+`equity_floor`가 함께 주어지면(단기 추천 전용) "주식 비중 합 ≥ equity_floor"
    부등식 제약을 추가한다 — 총합=1 제약과 결합되면 "안전자산 비중 ≤ 1-equity_floor"도 자동
    성립한다. 후보가 전부 주식이거나 전부 비주식이면(비교 대상이 없어 제약이 무의미) 무시한다.

    `is_equity`+`equity_ceiling`이 함께 주어지면(IRP 추천 전용) `equity_floor`와 대칭으로
    "주식 비중 합 ≤ equity_ceiling" 부등식 제약을 추가한다 — 총합=1 제약과 결합되면 "안전자산
    비중 ≥ 1-equity_ceiling"도 자동 성립한다. 호출측은 `equity_floor`와 `equity_ceiling`을
    동시에 넘기지 않는다(IRP는 단기 주식 하한 규칙보다 우선하므로 상호 배타적으로 세팅됨).

    `market_signal_level`(GREEN/YELLOW/RED)이 주어지면 `_SIGNAL_FRONTIER_DAMPENING`에 따라
    `frontier_frac`을 감쇠시켜 최소분산 쪽으로 결과를 당긴다 — `equity_floor`/`equity_ceiling`
    같은 규제·정책성 하드 제약과는 별개 축이라 함께 조정하지 않는다.

    `dividend_yields`+`required_dividend_yield_pct`가 함께 주어지면 "가중평균 배당수익률 ≥
    required_dividend_yield_pct" 부등식 제약을 추가한다 — 배당 목표(`UserSettings.annual_dividend_goal`)를
    실제 비중 계산에 반영하기 위함(과거에는 표시용으로만 사후 계산되고 최적화 입력으로 쓰이지
    않았음). 종목당 비중 상한(bounds) 하에서 그리디하게 계산한 달성 가능 최대 배당수익률이
    목표에 못 미치면 제약을 적용하지 않고(자산 목표 기준으로만 계산) note에 안내를 남긴다 —
    배당 목표를 못 채운다고 전체 추천 자체를 실패시키지 않는다(fail-soft).
    """
    import numpy as np
    from scipy.optimize import minimize

    equity_flags_in = is_equity or [False] * len(symbols)
    dividend_yields_in = dividend_yields or [0.0] * len(symbols)
    valid = [
        (s, tk, c, eq, dy)
        for s, tk, c, eq, dy in zip(symbols, tickers, cagr_pct, equity_flags_in, dividend_yields_in, strict=False)
        if s in returns_map and len(returns_map[s]) >= _MIN_RETURN_DAYS
    ]
    if len(valid) < _MIN_CANDIDATES:
        return [], None, None, f"추천에 충분한 시세 데이터가 있는 종목이 {_MIN_CANDIDATES}개 미만입니다"

    syms, tks, cagrs_list, equity_flags, dividend_list = zip(*valid, strict=False)
    cagrs = np.array(cagrs_list, dtype=float)
    n = len(syms)

    if float(cagrs.max()) < required_return_pct:
        return [], None, None, f"큐레이션 종목만으로는 목표 수익률(연 {required_return_pct:.1f}%)을 달성하기 어렵습니다"

    min_len = min(len(returns_map[s]) for s in syms)
    rets = np.array([returns_map[s][:min_len] for s in syms])
    cov_annual = np.cov(rets) * 252 if n > 1 else np.array([[float(np.var(rets[0])) * 252]])

    max_weight_used = max(max_weight, 1.0 / n)  # n이 작아 상한 합이 100%를 못 채우면 완화

    n_equity = sum(equity_flags)
    apply_equity_floor = equity_floor is not None and equity_floor > 0 and 0 < n_equity < n
    apply_equity_ceiling = equity_ceiling is not None and equity_ceiling < 1.0 and 0 < n_equity < n
    if apply_equity_floor:
        assert equity_floor is not None  # nosec B101 — apply_equity_floor 가드로 이미 None 아님 보장, mypy 타입 내로잉용
        # 주식 후보가 적어도(예: 1개) 하한을 채울 수 있도록 주식 종목당 상한을 별도로 완화
        equity_cap = max(max_weight_used, equity_floor / n_equity)
        bounds = [(0.0, equity_cap if eq else max_weight_used) for eq in equity_flags]
    elif apply_equity_ceiling:
        assert equity_ceiling is not None  # nosec B101 — apply_equity_ceiling 가드로 이미 None 아님 보장, mypy 타입 내로잉용
        # 비주식(안전자산) 후보가 적어도(예: 1개) 하한(1-equity_ceiling)을 채울 수 있도록 비주식
        # 종목당 상한을 별도로 완화 — apply_equity_floor의 equity_cap과 대칭.
        n_non_equity = n - n_equity
        non_equity_cap = max(max_weight_used, (1.0 - equity_ceiling) / n_non_equity)
        bounds = [(0.0, max_weight_used if eq else non_equity_cap) for eq in equity_flags]
    else:
        bounds = [(0.0, max_weight_used)] * n
    x0 = np.full(n, 1.0 / n)

    # 종목당 비중 상한(bounds) 하에서 달성 가능한 최대 가중평균 CAGR — equity_floor/equity_ceiling이
    # 걸려 있으면 해당 그룹(주식/비주식)의 합산 상한도 함께 지켜야 한다. 그렇지 않으면 BALANCED/
    # AGGRESSIVE 성향의 프론티어 목표(target)가 그 그룹 제약과 동시에 만족 불가능한 지점으로
    # 계산돼 옵티마이저가 실패할 수 있다(예: IRP 안전자산 30% 하한 + LONG_TERM AGGRESSIVE 조합).
    # 상한이 없다면 cagrs.max()겠지만, 캡이 있으면 고CAGR 종목에만 몰아줄 수 없으므로 그보다 낮을 수 있음.
    equity_budget: float = equity_ceiling if apply_equity_ceiling and equity_ceiling is not None else 1.0
    non_equity_budget: float = 1.0 - equity_floor if apply_equity_floor and equity_floor is not None else 1.0
    group_budget = {True: equity_budget, False: non_equity_budget}
    group_used = {True: 0.0, False: 0.0}
    max_achievable_return = 0.0
    remaining = 1.0
    for idx in np.argsort(-cagrs):
        is_eq = bool(equity_flags[idx])
        take = max(min(bounds[idx][1], remaining, group_budget[is_eq] - group_used[is_eq]), 0.0)
        max_achievable_return += take * float(cagrs[idx])
        remaining -= take
        group_used[is_eq] += take
        if remaining <= 1e-9:
            break

    note: str | None = None
    frontier_frac = _RISK_TOLERANCE_FRONTIER_FRACTION.get(risk_tolerance, 0.0)
    signal_dampening = _SIGNAL_FRONTIER_DAMPENING.get(market_signal_level or "", 1.0)
    effective_frontier_frac = frontier_frac * signal_dampening
    if signal_dampening < 1.0 and frontier_frac > 0.0:
        note = f"시장 위험 신호({market_signal_level})를 반영해 추천 비중을 보수적으로 조정했습니다"

    if effective_frontier_frac <= 0.0:
        # CONSERVATIVE(또는 미인식 값) — 기존과 동일한 코드 경로, 순수 최소분산 + 부등식 제약
        constraints = [
            {"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0},
            {"type": "ineq", "fun": lambda w: float(w @ cagrs) - required_return_pct},
        ]
    else:
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
        frontier_high = max_achievable_return
        target = frontier_low + effective_frontier_frac * max(frontier_high - frontier_low, 0.0)
        target = min(max(target, required_return_pct), frontier_high)

        if frontier_high - frontier_low < 1e-6:
            note = "선택한 리스크 성향을 반영하기에는 후보 종목 간 기대수익률 차이가 크지 않습니다"

        constraints = [
            {"type": "eq", "fun": lambda w: float(np.sum(w)) - 1.0},
            {"type": "eq", "fun": lambda w: float(w @ cagrs) - target},
        ]
    if apply_equity_floor or apply_equity_ceiling:
        equity_mask = np.array(equity_flags, dtype=bool)
        if apply_equity_floor:
            assert equity_floor is not None  # nosec B101 — apply_equity_floor 가드로 이미 None 아님 보장, mypy 타입 내로잉용
            constraints = [
                *constraints,
                {"type": "ineq", "fun": lambda w: float(w[equity_mask].sum()) - equity_floor},
            ]
        if apply_equity_ceiling:
            assert equity_ceiling is not None  # nosec B101 — apply_equity_ceiling 가드로 이미 None 아님 보장, mypy 타입 내로잉용
            constraints = [
                *constraints,
                {"type": "ineq", "fun": lambda w: equity_ceiling - float(w[equity_mask].sum())},
            ]

    # equity_floor/ceiling 그룹 예산은 반영하지 않음 — 배당 목표는 전체 자산 기준 추천에서만 쓰이고
    # 그 호출 경로는 equity_floor/ceiling을 넘기지 않으므로 무해한 단순화. required_dividend_yield_pct가
    # 없으면(배당 목표 미설정) 헬퍼 내부에서 즉시 no-op.
    constraints, note = _apply_dividend_floor(constraints, note, bounds, dividend_list, required_dividend_yield_pct)

    res = minimize(
        lambda w: float(w @ cov_annual @ w),
        x0=x0,
        method="SLSQP",
        bounds=bounds,
        constraints=constraints,
        options={"ftol": 1e-9, "maxiter": 500},
    )
    if not res.success:
        return [], None, None, "제약 조건을 만족하는 포트폴리오를 찾지 못했습니다"

    weights = res.x
    expected_return = round(float(weights @ cagrs), 2)
    expected_volatility = round(float(np.sqrt(weights @ cov_annual @ weights)) * 100, 2)

    items = [
        {"ticker": tk[0], "name": tk[1], "market": tk[2], "weight": round(float(w) * 100, 1)}
        for tk, w in zip(tks, weights, strict=False)
        if w >= 0.005
    ]
    total = sum(i["weight"] for i in items)
    if items and abs(total - 100) > 0.01:
        items[0]["weight"] = round(items[0]["weight"] + (100 - total), 1)

    return items, expected_return, expected_volatility, note


def compute_weighted_expected_metrics(
    symbols: list[str],
    weights_pct: list[float],  # 0~100, symbols와 동일 순서로 대응
    cagr_by_symbol: dict[str, float],
    dividend_by_symbol: dict[str, float],
    returns_map: dict[str, list[float]],
) -> tuple[float | None, float | None, float | None]:
    """임의의 "이미 정해진" 비중(최적화 대상이 아님)에 대해 가중평균 기대수익률·배당수익률·변동성을
    계산한다 — `_optimize_goal_portfolio`가 SLSQP 최적화 이후 계산하는 것과 동일한 수식을 최적화
    과정 없이 바로 적용한 버전. "적용 전 비교 미리보기"에서 포트폴리오의 현재 목표 비중에 대해
    추천 비중과 같은 지표를 나란히 보여주기 위해 쓰인다.

    시세 데이터가 없는 종목(`returns_map`에 없거나 데이터 부족)은 계산에서 제외하고 나머지
    비중으로 재정규화한다. 유효 종목이 하나도 없으면 (None, None, None)을 반환한다.
    """
    import numpy as np

    valid = [
        (sym, w)
        for sym, w in zip(symbols, weights_pct, strict=False)
        if sym in returns_map and len(returns_map[sym]) >= _MIN_RETURN_DAYS and w > 0
    ]
    if not valid:
        return None, None, None

    syms, ws = zip(*valid, strict=False)
    raw_weights = np.array(ws, dtype=float)
    weight_sum = float(raw_weights.sum())
    if weight_sum <= 0:
        return None, None, None
    weights = raw_weights / weight_sum

    cagrs = np.array([cagr_by_symbol.get(s, 0.0) for s in syms], dtype=float)
    dividends = np.array([dividend_by_symbol.get(s, 0.0) for s in syms], dtype=float)

    expected_return = round(float(weights @ cagrs), 2)
    expected_dividend = round(float(weights @ dividends), 2)

    min_len = min(len(returns_map[s]) for s in syms)
    rets = np.array([returns_map[s][:min_len] for s in syms])
    cov_annual = np.cov(rets) * 252 if len(syms) > 1 else np.array([[float(np.var(rets[0])) * 252]])
    expected_volatility = round(float(np.sqrt(weights @ cov_annual @ weights)) * 100, 2)

    return expected_return, expected_dividend, expected_volatility
