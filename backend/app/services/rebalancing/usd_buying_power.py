"""정액 적립 해외 매수 전 달러 예수금 확인(plans/120).

해외 매수 leg를 실행하기 직전에 실행 계좌의 **실시간** 외화(USD) 예수금을 조회해 필요한 달러와 비교한다.
동기화 값(`AssetAccount.deposit_usd`)은 하루 1회라 환전 직후 상태를 모른다 — 그래서 증권사를 직접 조회한다.

- KIS: 해외잔고 `output2.frcr_dncl_amt_2`(외화예수금), 키움: 예수금 `fc_entra`(USD) — 둘 다 각 클라이언트가
  `deposit_usd`로 정규화한다.
- 키움 원화주문 계좌(`AssetAccount.krw_overseas_order`)는 원화 매수여력(kt00001)을 실환율로 달러 환산해 더한다 —
  증권사가 부족분을 원화로 결제하므로 달러만 보면 "환전 대기"로 잘못 막는다. 실환율이 없으면 미확인.
- 조회 실패·미지원 계좌·시세 실패는 `USD_UNKNOWN`(미확인). 실행 경로는 확인 없이 기존처럼 주문을 시도하지만
  (증권사가 최종 판정), 자동 재확인은 미확인을 "충분"으로 보지 않고 대기를 유지한다(plans/122 A2).

**함정**: 토큰 발급은 DB commit을 한다 — leg를 `FOR UPDATE`로 잠그기 *전에* 호출해야 락이 중간에 풀리지 않는다.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import uses_krw_overseas_order
from app.core.job_runner import report_handled_failure
from app.models.rebalancing_plan import RebalancingPlanItem
from app.services.rebalancing.order_builder import market_group

logger = structlog.get_logger()

FX_FEE_BUFFER = 1.003
"""필요 달러에 더하는 수수료·호가 여유(0.3%) — 지정가 갱신분과 해외 매매수수료를 덮는다."""

KRW_ORDER_FX_MARGIN = 1.03
"""원화주문 계좌의 원화 매수여력을 달러로 바꿀 때 환율에 얹는 여유(3%) — 증권사 가환율·결제일 환율 변동 대비."""


@dataclass(frozen=True)
class UsdShortfall:
    required_usd: float
    available_usd: float


@dataclass(frozen=True)
class UsdUnknown:
    """달러가 충분한지 판정하지 못했다(잔고·시세 조회 실패, 실행 계좌 없음)."""


USD_UNKNOWN = UsdUnknown()

UsdCheck = UsdShortfall | UsdUnknown | None
"""`check_usd_shortfall` 결과 — 부족(UsdShortfall)·미확인(USD_UNKNOWN)·충분(None)."""


async def fetch_usd_buying_power(account_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession, cache) -> float | None:
    """실행 계좌의 실시간 달러 예수금. 조회 실패·미지원 계좌·필드 없음이면 None."""
    from app.kis.auth import get_access_token
    from app.kis.balance import get_overseas_deposit_usd as kis_overseas_deposit_usd
    from app.kiwoom.auth import get_access_token as kiwoom_get_access_token
    from app.kiwoom.balance import get_overseas_deposit_usd as kiwoom_overseas_deposit_usd
    from app.services.rebalancing.execution_service import (
        load_executable_account,
        load_kis_credentials,
        load_kiwoom_credentials,
    )

    token_args = {"cache": cache, "db": db, "user_id": str(user_id), "account_id": str(account_id)}
    raw: float | None
    try:
        account = await load_executable_account(account_id, user_id, db)
        is_mock = account.is_mock_mode
        # 예수금만 필요하다 — 보유종목 전체 잔고(거래소 3곳 × 연속조회)는 받지 않는다(plans/124 A)
        if account.asset_type == "STOCK_KIWOOM":
            app_key, app_secret = load_kiwoom_credentials(account)
            token = await kiwoom_get_access_token(app_key, app_secret, is_mock=is_mock, **token_args)
            raw = await kiwoom_overseas_deposit_usd(token, is_mock=is_mock)
            if uses_krw_overseas_order(account) and raw is not None:
                krw_usd = await _krw_order_usd(token, is_mock, cache)
                if krw_usd is None:
                    return None
                raw = float(raw) + krw_usd
        else:
            app_key, app_secret = load_kis_credentials(account)
            token = await get_access_token(app_key, app_secret, is_mock=is_mock, **token_args)
            raw = await kis_overseas_deposit_usd(
                app_key, app_secret, token, account.kis_account_no or "", is_mock=is_mock
            )
    except Exception as exc:
        report_handled_failure("dca_usd_buying_power_fetch_failed", exc, account_id=str(account_id))
        return None

    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


async def _krw_order_usd(token: str, is_mock: bool, cache) -> float | None:
    """키움 원화주문 계좌의 원화 매수여력을 달러로 — 실환율이 없으면 None(판정 불가).

    증권사가 원화주문 증거금에 쓰는 환율·여유율은 공개 API로 알 수 없어 `KRW_ORDER_FX_MARGIN`만큼 보수적으로 깎는다.
    """
    from app.kiwoom.balance import get_orderable_krw
    from app.utils.currency import get_live_or_cached_usd_krw

    rate, is_live = await get_live_or_cached_usd_krw(cache)
    if not is_live or rate <= 0:
        return None
    orderable_krw = await get_orderable_krw(token, is_mock=is_mock)
    return max(0.0, float(orderable_krw)) / (rate * KRW_ORDER_FX_MARGIN)


def required_usd_for_orders(orders: list) -> float | None:
    """해외 주문들의 필요 달러(수량 × 현지통화 지정가 × 여유). 지정가가 없는 주문이 있으면 None(계산 불가)."""
    total = 0.0
    for order in orders:
        if market_group(order.market or "") != "US":
            continue
        if not order.limit_price or order.limit_price <= 0:
            return None
        total += order.quantity * float(order.limit_price)
    return round(total * FX_FEE_BUFFER, 2)


async def check_usd_shortfall(
    items: list[RebalancingPlanItem],
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
    cache,
) -> UsdCheck:
    """이 leg를 사려면 달러가 부족한지. 부족하면 UsdShortfall, 판정 불가면 USD_UNKNOWN, 충분하면 None."""
    from app.services.rebalancing.plan_execution import _rebuild_orders_from_items

    try:
        orders = await _rebuild_orders_from_items(items, "BUY", user_id, db, cache)
    except ValueError:
        # 해외 현재가를 못 받아 지정가를 정할 수 없다 — 실행 경로가 같은 이유로 FAILED 처리·알림한다
        return USD_UNKNOWN
    required = required_usd_for_orders(orders)
    if required is None:
        return USD_UNKNOWN
    if required <= 0:
        return None
    available = await fetch_usd_buying_power(account_id, user_id, db, cache)
    if available is None:
        logger.info("dca_usd_buying_power_unknown", account_id=str(account_id))
        return USD_UNKNOWN
    if available + 1e-6 >= required:
        return None
    logger.info(
        "dca_usd_shortfall",
        account_id=str(account_id),
        required_usd=required,
        available_usd=available,
    )
    return UsdShortfall(required_usd=required, available_usd=round(available, 2))
