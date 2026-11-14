"""목표 역산 추천 MVO 결과 후처리 — 공분산, 비중 반올림(종목 상한·자산군 범위 유지), 기대 지표.

최적화 자체는 `goal_portfolio_optimizer.py`. DB 의존 없는 순수 계산이다.
"""

from __future__ import annotations

_MIN_RETURN_DAYS = 30


def _annualized_covariance(syms: tuple[str, ...], returns_map: dict[str, list[float]]):
    """가장 짧은 시계열 길이에 맞춘 일별수익률의 연환산 공분산(Ledoit-Wolf 축소 적용).

    시계열은 오래된 날짜부터 정렬돼 있으므로 **최근 구간**(`[-min_len:]`)으로 맞춘다. 앞에서 자르면 오래된 ETF의 옛
    구간과 신규 ETF의 최근 구간을 짝지어 상관이 사라지고, 가짜 분산 효과로 신규 ETF에 비중이 쏠린다(plans/110 C1).
    시계열에 날짜가 없어 시장 간 거래일 차이는 남는다.
    """
    import numpy as np

    from app.services.estimation import shrink_covariance

    min_len = min(len(returns_map[s]) for s in syms)
    rets = np.array([returns_map[s][-min_len:] for s in syms])
    cov_annual = np.cov(rets) * 252 if len(syms) > 1 else np.array([[float(np.var(rets[0])) * 252]])
    return shrink_covariance(rets, cov_annual)


class _RoundedWeights:
    """반올림한 비중(0.1%p 단위)을 종목당 상한·자산군 범위 안에서 옮기는 도구."""

    def __init__(self, items: list[dict], caps: list[float], bounds: dict[str, tuple[float, float]]) -> None:
        self.items = items
        self.caps = caps
        self.bounds = bounds
        # 큰 항목부터 — 작은 항목에 오차를 몰면 상대 왜곡이 커진다
        self.by_weight = sorted(range(len(items)), key=lambda k: -items[k]["weight"])

    def class_sum(self, cls: str) -> float:
        return sum(i["weight"] for i in self.items if i["_class"] == cls)

    def _fits(self, idx: int, delta: float, check_class: bool) -> bool:
        item = self.items[idx]
        if item["weight"] + delta > self.caps[idx] + 1e-9 or item["weight"] + delta < 0:
            return False
        if not check_class:
            return True
        lower, upper = self.bounds.get(item["_class"], (0.0, 1.0))
        return lower * 100 - 1e-9 <= self.class_sum(item["_class"]) + delta <= upper * 100 + 1e-9

    def shift(self, amount: float, candidates: list[int], *, check_class: bool = True) -> float:
        """amount를 후보들에 0.1 단위로 나눠 싣고 못 실은 나머지를 돌려준다."""
        step = 0.1 if amount > 0 else -0.1
        remaining = round(amount, 1)
        for idx in candidates:
            while abs(remaining) >= 0.05 and self._fits(idx, step, check_class):
                self.items[idx]["weight"] = round(self.items[idx]["weight"] + step, 1)
                remaining = round(remaining - step, 1)
        return remaining

    def repair_class_bounds(self) -> None:
        """자산군 범위를 벗어난 만큼 다른 자산군과 주고받는다."""
        for cls, (lower, upper) in self.bounds.items():
            members = [k for k in self.by_weight if self.items[k]["_class"] == cls]
            others = [k for k in self.by_weight if self.items[k]["_class"] != cls]
            if not others:
                continue
            over = round(self.class_sum(cls) - upper * 100, 1)
            under = round(lower * 100 - self.class_sum(cls), 1)
            if over > 0:
                moved = round(over + self.shift(-over, members, check_class=False), 1)
                self.shift(moved, others, check_class=False)
            elif under > 0:
                moved = round(under + self.shift(-under, others, check_class=False), 1)
                self.shift(moved, members, check_class=False)

    def complete_to_100(self) -> None:
        """합계 100을 맞춘다. 범위 안에서 못 맞추면 합계를 우선한다 — 자산군 범위는 호출부가 최종 검증한다."""
        diff = round(100 - sum(i["weight"] for i in self.items), 1)
        if abs(diff) >= 0.05:
            diff = self.shift(diff, self.by_weight)
        if abs(diff) >= 0.05:
            first = self.items[self.by_weight[0]]
            first["weight"] = round(first["weight"] + diff, 1)


def _weights_to_items(
    tks: tuple[tuple[str, str, str], ...],
    weights,
    classes: tuple[str, ...] | None = None,
    class_bounds: dict[str, tuple[float, float]] | None = None,
    upper_bounds: list[float] | None = None,
) -> list[dict]:
    """0.5% 미만 비중은 버리고 % 단위(소수 1자리)로 반올림한 뒤 합계 100과 자산군 범위를 맞춘다.

    반올림·버린 비중은 최적화 뒤에 생기는 오차라 그대로 두면 자산군 상한(IRP 주식 70% 등)을 넘는다. 오차는 종목당 상한과
    자산군 범위에 여유가 있는 항목으로 보낸다. 항목에는 자산군(`_class`)을 남겨 호출부가 최종 검증한 뒤 지운다.
    """
    items: list[dict] = []
    caps: list[float] = []
    for idx, (tk, w) in enumerate(zip(tks, weights, strict=False)):
        if w < 0.005:
            continue
        items.append(
            {
                "ticker": tk[0],
                "name": tk[1],
                "market": tk[2],
                "weight": round(float(w) * 100, 1),
                "_class": classes[idx] if classes else None,
            }
        )
        caps.append(upper_bounds[idx] * 100 if upper_bounds else 100.0)
    if items:
        rounded = _RoundedWeights(items, caps, class_bounds or {})
        rounded.repair_class_bounds()
        rounded.complete_to_100()
    return items


def _class_bounds_violated(items: list[dict], class_bounds: dict[str, tuple[float, float]]) -> bool:
    """반올림 보정 뒤에도 자산군 범위를 벗어났는지. 0.05%p 미만은 반올림 단위 안이라 허용한다."""
    for cls, (lower, upper) in class_bounds.items():
        total = sum(i["weight"] for i in items if i.get("_class") == cls)
        if total > upper * 100 + 0.05 or total < lower * 100 - 0.05:
            return True
    return False


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

    시세·CAGR 데이터가 없는 종목은 수익률 0으로 치지 않고 계산에서 제외한 뒤 나머지
    비중으로 재정규화한다. 유효 종목이 하나도 없으면 (None, None, None)을 반환한다.
    """
    import numpy as np

    valid = [
        (sym, w)
        for sym, w in zip(symbols, weights_pct, strict=False)
        if sym in returns_map and len(returns_map[sym]) >= _MIN_RETURN_DAYS and sym in cagr_by_symbol and w > 0
    ]
    if not valid:
        return None, None, None

    syms, ws = zip(*valid, strict=False)
    raw_weights = np.array(ws, dtype=float)
    weight_sum = float(raw_weights.sum())
    if weight_sum <= 0:
        return None, None, None
    weights = raw_weights / weight_sum

    # 기대수익률은 "이미 정해진" 비중에 대한 실제 가중평균이므로(최적화 대상이 아님) 축소추정을
    # 적용하지 않는다 — 축소추정(CAGR)은 `_optimize_goal_portfolio`가 최적화 입력을 만들 때만
    # 쓰인다. 변동성(공분산)은 최적화 쪽 결과와 같은 척도로 비교되도록 동일하게 축소추정을 적용.
    cagrs = np.array([cagr_by_symbol[s] for s in syms], dtype=float)
    dividends = np.array([dividend_by_symbol.get(s, 0.0) for s in syms], dtype=float)

    expected_return = round(float(weights @ cagrs), 2)
    expected_dividend = round(float(weights @ dividends), 2)

    cov_annual = _annualized_covariance(tuple(syms), returns_map)
    expected_volatility = round(float(np.sqrt(weights @ cov_annual @ weights)) * 100, 2)

    return expected_return, expected_dividend, expected_volatility
