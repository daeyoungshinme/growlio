"""정액 적립 해외 매수 전 달러 예수금 확인(plans/120).

해외 매수 leg를 실행하기 직전에 실행 계좌의 **실시간** 외화(USD) 예수금을 조회해 필요한 달러와 비교한다.
동기화 값(`AssetAccount.deposit_usd`)은 하루 1회라 환전 직후 상태를 모른다 — 그래서 증권사를 직접 조회한다.

- KIS: 해외잔고 `output2.frcr_dncl_amt_2`(외화예수금), 키움: 예수금 `fc_entra`(USD) — 둘 다 각 클라이언트가
  `deposit_usd`로 정규화한다.
- 조회 실패·미지원 계좌는 None(미확인) — 호출부는 확인 없이 기존처럼 주문을 시도한다(증권사가 최종 판정).

**함정**: 토큰 발급은 DB commit을 한다 — leg를 `FOR UPDATE`로 잠그기 *전에* 호출해야 락이 중간에 풀리지 않는다.
"""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.job_runner import report_handled_failure
from app.models.rebalancing_plan import RebalancingPlanItem
from app.services.rebalancing.order_builder import market_group

logger = structlog.get_logger()

FX_FEE_BUFFER = 1.003
"""필요 달러에 더하는 수수료·호가 여유(0.3%) — 지정가 갱신분과 해외 매매수수료를 덮는다."""


@dataclass(frozen=True)
class UsdShortfall:
    required_usd: float
    available_usd: float


async def fetch_usd_buying_power(account_id: uuid.UUID, user_id: uuid.UUID, db: AsyncSession, cache) -> float | None:
    """실행 계좌의 실시간 달러 예수금. 조회 실패·미지원 계좌·필드 없음이면 None."""
    from app.kis.auth import get_access_token
    from app.kis.balance import get_overseas_balance as kis_overseas_balance
    from app.kiwoom.auth import get_access_token as kiwoom_get_access_token
    from app.kiwoom.balance import get_overseas_balance as kiwoom_overseas_balance
    from app.services.rebalancing.execution_service import (
        load_executable_account,
        load_kis_credentials,
        load_kiwoom_credentials,
    )

    token_args = {"cache": cache, "db": db, "user_id": str(user_id), "account_id": str(account_id)}
    try:
        account = await load_executable_account(account_id, user_id, db)
        is_mock = account.is_mock_mode
        if account.asset_type == "STOCK_KIWOOM":
            app_key, app_secret = load_kiwoom_credentials(account)
            token = await kiwoom_get_access_token(app_key, app_secret, is_mock=is_mock, **token_args)
            balance = await kiwoom_overseas_balance(token, account.kiwoom_account_no or "", is_mock=is_mock)
        else:
            app_key, app_secret = load_kis_credentials(account)
            token = await get_access_token(app_key, app_secret, is_mock=is_mock, **token_args)
            balance = await kis_overseas_balance(
                app_key, app_secret, token, account.kis_account_no or "", is_mock=is_mock
            )
    except Exception as exc:
        report_handled_failure("dca_usd_buying_power_fetch_failed", exc, account_id=str(account_id))
        return None

    raw = balance.get("deposit_usd")
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


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
) -> UsdShortfall | None:
    """이 leg를 사려면 달러가 부족한지. 부족할 때만 UsdShortfall, 충분하거나 판정 불가(미확인)면 None."""
    from app.services.rebalancing.plan_execution import _rebuild_orders_from_items

    try:
        orders = await _rebuild_orders_from_items(items, "BUY", user_id, db, cache)
    except ValueError:
        # 해외 현재가를 못 받아 지정가를 정할 수 없다 — 실행 경로가 같은 이유로 FAILED 처리·알림한다
        return None
    required = required_usd_for_orders(orders)
    if required is None or required <= 0:
        return None
    available = await fetch_usd_buying_power(account_id, user_id, db, cache)
    if available is None:
        logger.info("dca_usd_buying_power_unknown", account_id=str(account_id))
        return None
    if available + 1e-6 >= required:
        return None
    logger.info(
        "dca_usd_shortfall",
        account_id=str(account_id),
        required_usd=required,
        available_usd=available,
    )
    return UsdShortfall(required_usd=required, available_usd=round(available, 2))
