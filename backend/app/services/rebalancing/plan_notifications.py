"""AUTO 리밸런싱 플랜 관련 이메일/푸시/이력 알림.

`plan_service.py`(구 단일 파일, 1025줄)에서 분리된 서브모듈. 플랜 생성 안내, 게이트 차단
보류 안내(세금영향/시장신호/하루합산한도), leg 실행 완료·실패 결과 안내를 담당한다.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio
from app.models.rebalancing_plan import RebalancingPlan
from app.services.alerts.alert_service import save_alert_history
from app.services.rebalancing.plan_generation import DailyValueCapBlocked, MarketSignalGateBlocked, TaxGateBlocked

logger = structlog.get_logger()

_KST = timezone(timedelta(hours=9))


async def notify_plan_generated(
    plan: RebalancingPlan,
    alert: RebalancingAlert,
    portfolio: Portfolio,
    buy_tokens: list[tuple[str, str]],
    sell_tokens: list[tuple[str, str]],
    email: str | None,
    fcm_token: str | None,
    composite_level: str,
    db: AsyncSession,
    note: str | None = None,
) -> bool:
    """플랜 생성 후 계획 안내 이메일/푸시 발송 + 알림 이력 저장. 반환: 이메일 발송 성공 여부.

    `buy_tokens`/`sell_tokens`는 [(market, raw_token), ...] — KR/US leg가 각각 있으면 최대 2개.
    """
    from app.models.asset import AssetAccount
    from app.services.email_service import send_rebalancing_plan_pending_email
    from app.services.push_service import send_push_to_user

    await db.refresh(plan, attribute_names=["legs"])
    buy_token_map = dict(buy_tokens)
    sell_token_map = dict(sell_tokens)
    buy_legs = [leg for leg in plan.legs if leg.side == "BUY"]
    sell_legs = [leg for leg in plan.legs if leg.side == "SELL"]
    # 이메일 링크용 원문 토큰은 해시만 저장되므로(action_token_hash) leg 객체엔 없다 — 전달받은
    # market→token 맵을 leg의 transient 속성으로 실어 email_service._to_section()이 읽게 한다.
    for leg in buy_legs:
        leg.token = buy_token_map.get(leg.market)
    for leg in sell_legs:
        leg.token = sell_token_map.get(leg.market)

    buy_count = sum(len(leg.items) for leg in buy_legs)
    sell_count = sum(len(leg.items) for leg in sell_legs)

    account_name = None
    if plan.account_id:
        account_name = await db.scalar(select(AssetAccount.name).where(AssetAccount.id == plan.account_id))

    email_sent = False
    if email and (buy_legs or sell_legs):
        try:
            await send_rebalancing_plan_pending_email(
                to_email=email,
                portfolio_name=portfolio.name,
                account_name=account_name,
                buy_legs=buy_legs,
                sell_legs=sell_legs,
            )
            email_sent = True
        except Exception as exc:
            logger.error("rebalancing_plan_pending_email_failed", alert_id=str(alert.id), error=str(exc))

    push_body = f"매수 {buy_count}건"
    if sell_count:
        push_body += f", 매도 승인대기 {sell_count}건"
    try:
        await send_push_to_user(
            user_id=alert.user_id,
            title=f"리밸런싱 자동화 플랜 생성 — {portfolio.name}",
            body=push_body,
            fcm_token=fcm_token,
            data={"type": "REBALANCING_PLAN_PENDING", "portfolio_id": str(portfolio.id)},
        )
    except Exception as exc:
        logger.error("rebalancing_plan_pending_push_failed", alert_id=str(alert.id), error=str(exc))

    history_note = f", {note}" if note else ""
    await save_alert_history(
        db,
        alert.user_id,
        "REBALANCING",
        (
            f"리밸런싱 자동화 플랜 생성: {portfolio.name} — 매수 {buy_count}건"
            + (f", 매도 승인대기 {sell_count}건" if sell_count else "")
            + f" [시장신호: {composite_level}{history_note}]"
        ),
    )
    return email_sent


async def notify_tax_gate_blocked(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    blocked: TaxGateBlocked,
    email: str | None,
    fcm_token: str | None,
    db: AsyncSession,
) -> None:
    """세금영향 게이트로 계획 생성이 보류됐음을 알린다 — 같은 알림에 대해 하루 1회만 발송(dedup).

    dedup 플래그는 재시작에도 유지돼야 하므로(콜드스타트 후 오탐 방지) Postgres 기반
    durable_state를 사용한다.
    """
    from app.services.email_service import send_tax_impact_gate_blocked_email
    from app.services.push_service import send_push_to_user
    from app.utils.cache_keys import TTL_TAX_IMPACT_GATE_ALERT_SENT, tax_impact_gate_alert_sent_key
    from app.utils.durable_state import get_durable, set_durable

    today = datetime.now(tz=UTC).date().isoformat()
    dedup_key = tax_impact_gate_alert_sent_key(alert.id, today)
    if await get_durable(db, dedup_key):
        return

    if email:
        try:
            await send_tax_impact_gate_blocked_email(
                email, portfolio.name, blocked.estimated_tax_krw, blocked.max_tax_impact_krw
            )
        except Exception as exc:
            logger.error("tax_impact_gate_blocked_email_error", alert_id=str(alert.id), error=str(exc))

    push_body = f"세금영향 상한 초과로 이번 계획을 만들지 않았습니다 (추정 양도세 {blocked.estimated_tax_krw:,.0f}원)."
    with contextlib.suppress(Exception):
        await send_push_to_user(
            user_id=alert.user_id,
            title=f"리밸런싱 자동화 보류 — {portfolio.name}",
            body=push_body,
            fcm_token=fcm_token,
            data={"type": "REBALANCING_TAX_GATE_BLOCKED", "portfolio_id": str(portfolio.id)},
        )

    history_message = (
        f"리밸런싱 자동화 보류(세금영향 상한 초과): {portfolio.name} — 추정 양도세 {blocked.estimated_tax_krw:,.0f}원"
    )
    await save_alert_history(db, alert.user_id, "REBALANCING", history_message)
    await db.commit()

    await set_durable(db, dedup_key, "1", ttl=TTL_TAX_IMPACT_GATE_ALERT_SENT)


async def notify_market_signal_gate_blocked(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    blocked: MarketSignalGateBlocked,
    email: str | None,
    fcm_token: str | None,
    db: AsyncSession,
) -> None:
    """시장신호 게이트로 계획 생성이 보류됐음을 알린다 — 같은 알림에 대해 하루 1회만 발송(dedup).

    dedup 플래그는 재시작에도 유지돼야 하므로(콜드스타트 후 오탐 방지) Postgres 기반
    durable_state를 사용한다.
    """
    from app.services.email_service import send_market_signal_gate_blocked_email
    from app.services.push_service import send_push_to_user
    from app.utils.cache_keys import TTL_MARKET_SIGNAL_GATE_ALERT_SENT, market_signal_gate_alert_sent_key
    from app.utils.durable_state import get_durable, set_durable

    today = datetime.now(tz=UTC).date().isoformat()
    dedup_key = market_signal_gate_alert_sent_key(alert.id, today)
    if await get_durable(db, dedup_key):
        return

    if email:
        try:
            await send_market_signal_gate_blocked_email(
                email, portfolio.name, blocked.composite_level, blocked.market_condition_mode
            )
        except Exception as exc:
            logger.error("market_signal_gate_blocked_email_error", alert_id=str(alert.id), error=str(exc))

    push_body = f"시장신호 게이트({blocked.composite_level})로 이번 계획을 만들지 않았습니다."
    with contextlib.suppress(Exception):
        await send_push_to_user(
            user_id=alert.user_id,
            title=f"리밸런싱 자동화 보류 — {portfolio.name}",
            body=push_body,
            fcm_token=fcm_token,
            data={"type": "REBALANCING_MARKET_GATE_BLOCKED", "portfolio_id": str(portfolio.id)},
        )

    history_message = f"리밸런싱 자동화 보류(시장신호 게이트): {portfolio.name} — 현재 신호 {blocked.composite_level}"
    await save_alert_history(db, alert.user_id, "REBALANCING", history_message)
    await db.commit()

    await set_durable(db, dedup_key, "1", ttl=TTL_MARKET_SIGNAL_GATE_ALERT_SENT)


async def notify_daily_value_cap_blocked(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    blocked: DailyValueCapBlocked,
    email: str | None,
    fcm_token: str | None,
    db: AsyncSession,
) -> None:
    """하루 합산 거래한도 게이트로 계획 생성이 보류됐음을 알린다 — 유저당 하루 1회만 발송(dedup).

    이 게이트는 알림(alert) 단위가 아닌 유저 단위로 평가되므로, dedup 키도 alert.id가 아닌
    user_id 기준 — 같은 유저의 여러 PER_ACCOUNT 알림이 같은 날 같은 상한에 걸려도 중복 발송하지 않는다.
    dedup 플래그는 재시작에도 유지돼야 하므로(콜드스타트 후 오탐 방지) Postgres 기반 durable_state를 사용한다.
    """
    from app.services.email_service import send_daily_value_cap_gate_blocked_email
    from app.services.push_service import send_push_to_user
    from app.utils.cache_keys import TTL_DAILY_VALUE_CAP_ALERT_SENT, daily_value_cap_gate_alert_sent_key
    from app.utils.durable_state import get_durable, set_durable

    today = datetime.now(tz=_KST).date().isoformat()
    dedup_key = daily_value_cap_gate_alert_sent_key(alert.user_id, today)
    if await get_durable(db, dedup_key):
        return

    if email:
        try:
            await send_daily_value_cap_gate_blocked_email(
                email, portfolio.name, blocked.today_total_krw, blocked.attempted_value_krw, blocked.cap_krw
            )
        except Exception as exc:
            logger.error("daily_value_cap_gate_blocked_email_error", alert_id=str(alert.id), error=str(exc))

    push_body = (
        f"하루 합산 거래한도({blocked.cap_krw:,.0f}원) 초과로 이번 계획을 만들지 않았습니다 "
        f"(오늘 누적 약 {blocked.today_total_krw:,.0f}원)."
    )
    with contextlib.suppress(Exception):
        await send_push_to_user(
            user_id=alert.user_id,
            title=f"리밸런싱 자동화 보류 — {portfolio.name}",
            body=push_body,
            fcm_token=fcm_token,
            data={"type": "REBALANCING_DAILY_CAP_BLOCKED", "portfolio_id": str(portfolio.id)},
        )

    history_message = (
        f"리밸런싱 자동화 보류(하루 합산 거래한도 초과): {portfolio.name} — "
        f"오늘 누적 약 {blocked.today_total_krw:,.0f}원 + 이번 약 {blocked.attempted_value_krw:,.0f}원 "
        f"> 상한 {blocked.cap_krw:,.0f}원"
    )
    await save_alert_history(db, alert.user_id, "REBALANCING", history_message)
    await db.commit()

    await set_durable(db, dedup_key, "1", ttl=TTL_DAILY_VALUE_CAP_ALERT_SENT)


async def _send_leg_execution_email(plan: RebalancingPlan, execution_id: uuid.UUID, db: AsyncSession) -> None:
    """leg 실행 완료 후 결과 이메일/푸시 발송 (기존 실행완료 템플릿 재사용)."""
    from app.models.asset import RebalancingExecution
    from app.models.user import User, UserSettings
    from app.services.email_service import send_rebalancing_execution_email
    from app.services.push_service import send_push_to_user

    exec_result = await db.scalar(
        select(RebalancingExecution)
        .options(selectinload(RebalancingExecution.result_items))
        .where(RebalancingExecution.id == execution_id)
    )
    if exec_result is None:
        return

    row = await db.execute(
        select(Portfolio.name, User.email, UserSettings.notification_email, UserSettings.fcm_token)
        .select_from(User)
        .outerjoin(Portfolio, Portfolio.id == plan.portfolio_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(User.id == plan.user_id)
    )
    info = row.first()
    if info is None:
        return
    portfolio_name, user_email, notification_email, fcm_token = info
    portfolio_name = portfolio_name or "포트폴리오"
    email = notification_email or user_email

    if email:
        try:
            await send_rebalancing_execution_email(
                to_email=email,
                portfolio_name=portfolio_name,
                executed_at=exec_result.executed_at,
                result_items=exec_result.result_items,
                total_success=exec_result.total_success,
                total_fail=exec_result.total_fail,
                total_skipped=exec_result.total_skipped,
            )
        except Exception as exc:
            logger.error("rebalancing_plan_execution_email_failed", execution_id=str(execution_id), error=str(exc))

    with contextlib.suppress(Exception):
        await send_push_to_user(
            user_id=plan.user_id,
            title=f"리밸런싱 자동 실행 완료 — {portfolio_name}",
            body=(
                f"{exec_result.total_success}건 완료"
                + (f", {exec_result.total_fail}건 실패" if exec_result.total_fail else "")
            ),
            fcm_token=fcm_token,
            data={"type": "REBALANCING_EXECUTED", "portfolio_id": str(plan.portfolio_id or "")},
        )


async def _notify_leg_execution_failed(plan: RebalancingPlan, side: str, error_message: str, db: AsyncSession) -> None:
    """leg 실행 자체가 예외로 실패했을 때(개별 종목 실패가 아닌 전체 실패) 이메일/푸시로 알린다.

    개별 종목 주문 실패는 `_send_leg_execution_email`의 완료 리포트(total_fail)로 이미 안내되지만,
    leg 실행 자체가 예외를 던진 경우(자격증명 오류, 브로커 토큰 발급 실패 등)는 실행 리포트가
    아예 생성되지 않아 사용자가 이력 탭을 직접 열어보지 않으면 알 방법이 없었다 — 그 공백을 메운다.
    """
    from app.models.user import User, UserSettings
    from app.services.email_service import send_rebalancing_plan_execution_failed_email
    from app.services.push_service import send_push_to_user

    row = await db.execute(
        select(Portfolio.name, User.email, UserSettings.notification_email, UserSettings.fcm_token)
        .select_from(User)
        .outerjoin(Portfolio, Portfolio.id == plan.portfolio_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(User.id == plan.user_id)
    )
    info = row.first()
    if info is None:
        return
    portfolio_name, user_email, notification_email, fcm_token = info
    portfolio_name = portfolio_name or "포트폴리오"
    email = notification_email or user_email

    if email:
        try:
            await send_rebalancing_plan_execution_failed_email(email, portfolio_name, side, error_message)
        except Exception as exc:
            logger.error("rebalancing_plan_execution_failed_email_error", plan_id=str(plan.id), error=str(exc))

    with contextlib.suppress(Exception):
        side_label = "매수" if side == "BUY" else "매도"
        await send_push_to_user(
            user_id=plan.user_id,
            title=f"리밸런싱 자동화 {side_label} 실행 실패 — {portfolio_name}",
            body="이번 계획은 체결되지 않았습니다. 앱에서 확인해주세요.",
            fcm_token=fcm_token,
            data={"type": "REBALANCING_PLAN_EXECUTION_FAILED", "portfolio_id": str(plan.portfolio_id or "")},
        )
