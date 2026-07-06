"""투자 목표(목표금액/월적립액/목표연도)로부터 필요 연평균 수익률을 역산하는 순수 계산 함수.

`dca_service.py`의 미래가치(FV) 수식(`initial*(1+r)^n + pmt*((1+r)^n-1)/r`)과 동일한 공식을
사용하되, r 대신 n(개월수)과 목표금액을 고정하고 r을 미지수로 풀이한다.
"""

from __future__ import annotations

_LO_ANNUAL_RETURN = -0.9
_HI_ANNUAL_RETURN = 5.0  # 연 500% — 이 이상 필요하면 사실상 달성 불가능한 목표로 간주


def _future_value(pv: float, pmt: float, annual_r: float, n_months: int) -> float:
    r_m = annual_r / 12
    if abs(r_m) < 1e-12:
        return pv + pmt * n_months
    try:
        growth = (1 + r_m) ** n_months
    except OverflowError:
        # 매우 긴 기간(수백년) × 높은 수익률 조합 — FV가 목표를 훨씬 초과한다는 뜻이므로 +inf로 취급
        return float("inf")
    return pv * growth + pmt * ((growth - 1) / r_m)


def solve_required_annual_return_pct(
    pv: float,
    pmt: float,
    n_months: int,
    goal_amount: float,
) -> float | None:
    """목표 달성에 필요한 연평균 수익률(%)을 역산한다.

    호출 전 `pv < goal_amount`이고 `n_months > 0`임을 보장해야 한다(이미 달성했거나
    목표연도가 지난 경우는 호출측에서 별도 분기 처리).
    반환값이 None이면 탐색 범위(연 -90%~500%) 내에서 해가 없는 것 — 사실상 달성 불가능한 목표.
    """
    from scipy.optimize import brentq

    def f(annual_r: float) -> float:
        return _future_value(pv, pmt, annual_r, n_months) - goal_amount

    f_lo, f_hi = f(_LO_ANNUAL_RETURN), f(_HI_ANNUAL_RETURN)
    if f_lo > 0:
        return round(_LO_ANNUAL_RETURN * 100, 2)
    if f_hi < 0:
        return None

    return round(brentq(f, _LO_ANNUAL_RETURN, _HI_ANNUAL_RETURN) * 100, 2)
