"""국내(KRX·NXT) 지정가 호가단위 보정 (plans/61 C2).

broker는 호가 격자에서 벗어난 지정가 주문을 거부한다. 실시간 현재가는 체결가라 원래 격자 위에 있지만,
수동 실행 화면에서 사용자가 입력한 지정가는 그렇지 않을 수 있다. 주문 직전 공용 경로
(`_kis_order_executor`·`_kiwoom_order_executor`)에서 이 함수로 맞춘다.

호가표(2023-01-25 개편, 코스피·코스닥 공통): 2천 미만 1원, 5천 미만 5원, 2만 미만 10원, 5만 미만 50원,
20만 미만 100원, 50만 미만 500원, 그 이상 1,000원. ETF·ETN은 가격과 무관하게 5원.

방향: 매수는 내림, 매도는 올림 — 사용자가 지정한 가격보다 불리하게 체결되지 않게 한다.
ETF 판별은 종목명 기반(`has_korean_etf_name`)이다. 일반주를 ETF로 잘못 보면 5원 격자가 일반주에서
무효(5천원 이상)라 거부되므로 확실한 경우만 ETF로 본다. 반대로 ETF를 일반주로 보면 5천원 이상에서는
주식 호가(10원 이상, 모두 5의 배수)가 ETF 격자에서도 유효하다.
"""

from __future__ import annotations

import math
from typing import Literal

# (상한 미만, 호가단위)
_STOCK_TICKS: tuple[tuple[int, int], ...] = (
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
)
_STOCK_TOP_TICK = 1_000
ETF_ETN_TICK = 5


def stock_tick_size(price: float) -> int:
    for upper, tick in _STOCK_TICKS:
        if price < upper:
            return tick
    return _STOCK_TOP_TICK


def is_etf_or_etn_name(name: str | None) -> bool:
    from app.services.goal.goal_candidate_service import has_korean_etf_name

    return has_korean_etf_name(name) or "ETN" in (name or "").upper()


def round_to_tick(price: float, side: Literal["BUY", "SELL"], *, is_etf: bool) -> int:
    """지정가를 호가 격자에 맞춘다(매수 내림·매도 올림). 결과가 0 이하가 되지 않게 최소 1틱."""
    # 올림이 구간 상한(2천·5천·2만·5만·20만·50만)에 닿아도 상한값은 모두 다음 구간 단위의 배수라 유효하다
    tick = ETF_ETN_TICK if is_etf else stock_tick_size(price)
    units = math.floor(price / tick) if side == "BUY" else math.ceil(price / tick)
    return int(max(units, 1) * tick)


def domestic_limit_price(price: float | None, side: Literal["BUY", "SELL"], name: str | None) -> float | None:
    """국내 지정가 주문용 가격 — None(시장가)은 그대로 둔다."""
    if price is None:
        return None
    return float(round_to_tick(price, side, is_etf=is_etf_or_etn_name(name)))
