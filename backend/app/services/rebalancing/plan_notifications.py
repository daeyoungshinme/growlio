"""AUTO 리밸런싱 플랜 관련 이메일/푸시/이력 알림.

플랜 생성 안내, 게이트 차단 보류 안내(세금영향/시장신호/하루합산한도), leg 실행 완료·실패 결과 안내를 담당한다.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from types import SimpleNamespace

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants import uses_krw_overseas_order
from app.core.job_runner import report_handled_failure
from app.models.alert import RebalancingAlert
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.rebalancing_plan import RebalancingPlan
from app.models.user import User, UserSettings
from app.services.alerts._dispatch import send_push_safely
from app.services.alerts.alert_service import save_alert_history
from app.services.rebalancing.plan_gates import (
    DailyValueCapBlocked,
    MarketSignalGateBlocked,
    SnapshotTooStale,
    TaxGateBlocked,
)
from app.utils.kst import today_kst

logger = structlog.get_logger()


async def _plan_recipient(plan: RebalancingPlan, db: AsyncSession) -> tuple[str, str | None, str | None] | None:
    """(포트폴리오 이름(없으면 "포트폴리오"), 수신 이메일, fcm_token). 유저가 없으면 None.

    수신 이메일은 알림 전용 이메일이 있으면 그것, 없으면 가입 이메일.
    """
    row = await db.execute(
        select(Portfolio.name, User.email, UserSettings.notification_email, UserSettings.fcm_token)
        .select_from(User)
        .outerjoin(Portfolio, Portfolio.id == plan.portfolio_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .where(User.id == plan.user_id)
    )
    info = row.first()
    if info is None:
        return None
    portfolio_name, user_email, notification_email, fcm_token = info
    return portfolio_name or "포트폴리오", notification_email or user_email, fcm_token


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
    from app.services.notifications.email_service import send_rebalancing_plan_pending_email

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
            report_handled_failure("rebalancing_plan_pending_email_failed", exc, alert_id=str(alert.id))

    push_body = f"매수 {buy_count}건"
    if sell_count:
        push_body += f", 매도 승인대기 {sell_count}건"
    await send_push_safely(
        alert.user_id,
        title=f"리밸런싱 자동화 플랜 생성 — {portfolio.name}",
        body=push_body,
        fcm_token=fcm_token,
        data={"type": "REBALANCING_PLAN_PENDING", "portfolio_id": str(portfolio.id)},
        failure_event="rebalancing_plan_pending_push_failed",
        alert_id=str(alert.id),
    )

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


async def _notify_gate_blocked(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    db: AsyncSession,
    *,
    dedup_key: str,
    ttl: int,
    event_prefix: str,
    send_email: Callable[[], Awaitable[bool]],
    push_body: str,
    push_type: str,
    history_message: str,
    fcm_token: str | None,
) -> None:
    """게이트 차단 보류 안내 공통 흐름 — 하루 1회(dedup) 이메일+푸시, 하나라도 성공하면 이력·dedup 저장.

    dedup 플래그는 재시작에도 유지돼야 하므로(콜드스타트 후 오탐 방지) Postgres 기반 durable_state를 쓴다.
    두 채널이 모두 실패하면 이력도 dedup도 남기지 않아 다음 평가 때 다시 시도한다(다른 알림과 같은 규칙, plans/79 B).
    """
    from app.services.alerts._dispatch import dispatch_dual_channel_alert
    from app.utils.durable_state import get_durable, set_durable

    if await get_durable(db, dedup_key):
        return

    async def _mark_sent() -> None:
        await set_durable(db, dedup_key, "1", ttl=ttl, commit=False)

    await dispatch_dual_channel_alert(
        db,
        alert.user_id,
        event_prefix=event_prefix,
        alert_type="REBALANCING",
        history_message=history_message,
        send_email=send_email,
        push_title=f"리밸런싱 자동화 보류 — {portfolio.name}",
        push_body=push_body,
        push_type=push_type,
        push_data={"portfolio_id": str(portfolio.id)},
        fcm_token=fcm_token,
        after_sent=_mark_sent,
    )


async def _no_email() -> bool:
    return False


async def notify_tax_gate_blocked(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    blocked: TaxGateBlocked,
    email: str | None,
    fcm_token: str | None,
    db: AsyncSession,
) -> None:
    """세금영향 게이트로 계획 생성이 보류됐음을 알린다 — 같은 알림에 대해 하루 1회만 발송(dedup)."""
    from app.services.notifications.email_service import send_tax_impact_gate_blocked_email
    from app.utils.cache_keys import TTL_TAX_IMPACT_GATE_ALERT_SENT, tax_impact_gate_alert_sent_key

    await _notify_gate_blocked(
        alert,
        portfolio,
        db,
        dedup_key=tax_impact_gate_alert_sent_key(alert.id, today_kst().isoformat()),
        ttl=TTL_TAX_IMPACT_GATE_ALERT_SENT,
        event_prefix="tax_impact_gate_blocked",
        send_email=(
            (
                lambda: send_tax_impact_gate_blocked_email(
                    email, portfolio.name, blocked.estimated_tax_krw, blocked.max_tax_impact_krw
                )
            )
            if email
            else _no_email
        ),
        push_body=(
            f"세금영향 상한 초과로 이번 계획을 만들지 않았습니다 (추정 양도세 {blocked.estimated_tax_krw:,.0f}원)."
        ),
        push_type="REBALANCING_TAX_GATE_BLOCKED",
        history_message=(
            f"리밸런싱 자동화 보류(세금영향 상한 초과): {portfolio.name}"
            f" — 추정 양도세 {blocked.estimated_tax_krw:,.0f}원"
        ),
        fcm_token=fcm_token,
    )


async def notify_market_signal_gate_blocked(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    blocked: MarketSignalGateBlocked,
    email: str | None,
    fcm_token: str | None,
    db: AsyncSession,
) -> None:
    """시장신호 게이트(전술 방어 국면 포함)로 계획 생성이 보류됐음을 알린다 — 같은 알림에 대해 하루 1회만 발송."""
    from app.services.notifications.email_service import send_market_signal_gate_blocked_email
    from app.utils.cache_keys import TTL_MARKET_SIGNAL_GATE_ALERT_SENT, market_signal_gate_alert_sent_key

    tactical = blocked.market_condition_mode == "TACTICAL"
    await _notify_gate_blocked(
        alert,
        portfolio,
        db,
        dedup_key=market_signal_gate_alert_sent_key(alert.id, today_kst().isoformat()),
        ttl=TTL_MARKET_SIGNAL_GATE_ALERT_SENT,
        event_prefix="market_signal_gate_blocked",
        send_email=(
            (
                lambda: send_market_signal_gate_blocked_email(
                    email, portfolio.name, blocked.composite_level, blocked.market_condition_mode
                )
            )
            if email
            else _no_email
        ),
        push_body=(
            "전술 배분이 방어 국면이라 이번 적립 매수를 보류했어요. 다음 매수일에 함께 매수해요."
            if tactical
            else f"시장신호 게이트({blocked.composite_level})로 이번 계획을 만들지 않았습니다."
        ),
        push_type="REBALANCING_MARKET_GATE_BLOCKED",
        history_message=(
            f"적립 매수 보류(전술 방어 국면): {portfolio.name}"
            if tactical
            else f"리밸런싱 자동화 보류(시장신호 게이트): {portfolio.name} — 현재 신호 {blocked.composite_level}"
        ),
        fcm_token=fcm_token,
    )


async def notify_stale_snapshot_blocked(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    blocked: SnapshotTooStale,
    email: str | None,
    fcm_token: str | None,
    db: AsyncSession,
) -> None:
    """동기화가 오래 끊겨 AUTO 계획을 만들지 않았음을 알린다 — 같은 알림에 대해 하루 1회만 발송."""
    from app.services.notifications.email_service import send_stale_snapshot_blocked_email
    from app.utils.cache_keys import TTL_STALE_SNAPSHOT_ALERT_SENT, stale_snapshot_alert_sent_key

    await _notify_gate_blocked(
        alert,
        portfolio,
        db,
        dedup_key=stale_snapshot_alert_sent_key(alert.id, today_kst().isoformat()),
        ttl=TTL_STALE_SNAPSHOT_ALERT_SENT,
        event_prefix="stale_snapshot_blocked",
        send_email=(
            (
                lambda: send_stale_snapshot_blocked_email(
                    email, portfolio.name, blocked.account_name, blocked.days_since_sync
                )
            )
            if email
            else _no_email
        ),
        push_body=(
            f"{blocked.account_name} 계좌가 {blocked.days_since_sync}일째 동기화되지 않아 이번 계획을 만들지 않았어요."
        ),
        push_type="REBALANCING_STALE_SNAPSHOT_BLOCKED",
        history_message=(
            f"리밸런싱 자동화 보류(동기화 끊김): {portfolio.name} — "
            f"{blocked.account_name} 계좌 {blocked.days_since_sync}일째 미동기화"
        ),
        fcm_token=fcm_token,
    )


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
    """
    from app.services.notifications.email_service import send_daily_value_cap_gate_blocked_email
    from app.utils.cache_keys import TTL_DAILY_VALUE_CAP_ALERT_SENT, daily_value_cap_gate_alert_sent_key

    await _notify_gate_blocked(
        alert,
        portfolio,
        db,
        dedup_key=daily_value_cap_gate_alert_sent_key(alert.user_id, today_kst().isoformat()),
        ttl=TTL_DAILY_VALUE_CAP_ALERT_SENT,
        event_prefix="daily_value_cap_gate_blocked",
        send_email=(
            (
                lambda: send_daily_value_cap_gate_blocked_email(
                    email, portfolio.name, blocked.today_total_krw, blocked.attempted_value_krw, blocked.cap_krw
                )
            )
            if email
            else _no_email
        ),
        push_body=(
            f"하루 합산 거래한도({blocked.cap_krw:,.0f}원) 초과로 이번 계획을 만들지 않았습니다 "
            f"(오늘 누적 약 {blocked.today_total_krw:,.0f}원)."
        ),
        push_type="REBALANCING_DAILY_CAP_BLOCKED",
        history_message=(
            f"리밸런싱 자동화 보류(하루 합산 거래한도 초과): {portfolio.name} — "
            f"오늘 누적 약 {blocked.today_total_krw:,.0f}원 + 이번 약 {blocked.attempted_value_krw:,.0f}원 "
            f"> 상한 {blocked.cap_krw:,.0f}원"
        ),
        fcm_token=fcm_token,
    )


async def _send_leg_execution_email(plan: RebalancingPlan, execution_id: uuid.UUID, db: AsyncSession) -> None:
    """leg 실행 완료 후 결과 이메일/푸시 발송 (기존 실행완료 템플릿 재사용)."""
    from app.models.asset import RebalancingExecution
    from app.services.notifications.email_service import send_rebalancing_execution_email

    exec_result = await db.scalar(
        select(RebalancingExecution)
        .options(selectinload(RebalancingExecution.result_items))
        .where(RebalancingExecution.id == execution_id)
    )
    if exec_result is None:
        return

    recipient = await _plan_recipient(plan, db)
    if recipient is None:
        return
    portfolio_name, email, fcm_token = recipient

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
            report_handled_failure("rebalancing_plan_execution_email_failed", exc, execution_id=str(execution_id))

    await send_push_safely(
        plan.user_id,
        title=f"리밸런싱 자동 실행 완료 — {portfolio_name}",
        body=(
            f"{exec_result.total_success}건 완료"
            + (f", {exec_result.total_fail}건 실패" if exec_result.total_fail else "")
        ),
        fcm_token=fcm_token,
        data={"type": "REBALANCING_EXECUTED", "portfolio_id": str(plan.portfolio_id or "")},
        failure_event="rebalancing_plan_execution_push_failed",
        execution_id=str(execution_id),
    )


async def _notify_leg_execution_failed(plan: RebalancingPlan, side: str, error_message: str, db: AsyncSession) -> None:
    """leg 실행 자체가 예외로 실패했을 때(개별 종목 실패가 아닌 전체 실패) 이메일/푸시로 알린다.

    개별 종목 주문 실패는 `_send_leg_execution_email`의 완료 리포트(total_fail)로 이미 안내되지만,
    leg 실행 자체가 예외를 던진 경우(자격증명 오류, 브로커 토큰 발급 실패 등)는 실행 리포트가
    아예 생성되지 않아 사용자가 이력 탭을 직접 열어보지 않으면 알 방법이 없었다 — 그 공백을 메운다.
    """
    from app.services.notifications.email_service import send_rebalancing_plan_execution_failed_email

    recipient = await _plan_recipient(plan, db)
    if recipient is None:
        return
    portfolio_name, email, fcm_token = recipient

    if email:
        try:
            await send_rebalancing_plan_execution_failed_email(email, portfolio_name, side, error_message)
        except Exception as exc:
            report_handled_failure("rebalancing_plan_execution_failed_email_error", exc, plan_id=str(plan.id))

    side_label = "매수" if side == "BUY" else "매도"
    await send_push_safely(
        plan.user_id,
        title=f"리밸런싱 자동화 {side_label} 실행 실패 — {portfolio_name}",
        body="이번 계획은 체결되지 않았습니다. 앱에서 확인해주세요.",
        fcm_token=fcm_token,
        data={"type": "REBALANCING_PLAN_EXECUTION_FAILED", "portfolio_id": str(plan.portfolio_id or "")},
        failure_event="rebalancing_plan_execution_failed_push_failed",
        plan_id=str(plan.id),
    )


async def _notify_buy_leg_expired(plan: RebalancingPlan, market: str | None, db: AsyncSession) -> None:
    """실행 시점에 장이 닫혀 매수 leg가 만료됐음을 푸시로 알린다."""
    recipient = await _plan_recipient(plan, db)
    if recipient is None:
        return
    portfolio_name, _email, fcm_token = recipient
    market_label = "국내" if market == "KR" else "해외"
    await send_push_safely(
        plan.user_id,
        title=f"리밸런싱 자동화 매수 미실행 — {portfolio_name}",
        body=f"실행 시점에 {market_label} 장이 닫혀 있어 이번 매수는 진행되지 않았습니다.",
        fcm_token=fcm_token,
        data={"type": "REBALANCING_PLAN_EXPIRED", "portfolio_id": str(plan.portfolio_id or "")},
        failure_event="rebalancing_plan_buy_expired_push_failed",
        plan_id=str(plan.id),
    )


def _kst_date_label(at) -> str:
    from app.utils.kst import KST

    return at.astimezone(KST).strftime("%m/%d") if at is not None else "기한"


async def plan_account_is_krw_order(plan: RebalancingPlan, db: AsyncSession) -> bool:
    """플랜 실행 계좌가 키움 원화주문 계좌인지 — 그 계좌의 환전 대기는 달러가 아니라 원화가 모자란 것이다."""
    account_id = getattr(plan, "account_id", None)
    if account_id is None:
        return False
    row = (
        await db.execute(
            select(AssetAccount.asset_type, AssetAccount.krw_overseas_order).where(AssetAccount.id == account_id)
        )
    ).first()
    if row is None:
        return False
    return uses_krw_overseas_order(SimpleNamespace(asset_type=row[0], krw_overseas_order=row[1]))


async def notify_dca_fx_required(
    plan: RebalancingPlan, required_usd: float, available_usd: float, retry_until, db: AsyncSession
) -> None:
    """정액 적립 해외 매수 leg가 달러 부족으로 환전 대기(WAITING_FX)에 들어갔음을 메일·푸시로 알린다(plans/120).

    메일에는 로그인 없이 누르는 매수 버튼을 넣지 않는다 — 재매수는 실주문이라 앱(인증)에서만 받는다.
    키움 원화주문 계좌는 `available_usd`가 원화 매수여력 환산분을 포함하고 할 일이 원화 입금이라
    문구를 바꾼다(plans/129 A3).
    """
    from app.services.notifications.email_service import send_dca_fx_required_email

    recipient = await _plan_recipient(plan, db)
    if recipient is None:
        return
    portfolio_name, email, fcm_token = recipient
    until_label = _kst_date_label(retry_until)
    krw_order = await plan_account_is_krw_order(plan, db)

    if email:
        try:
            await send_dca_fx_required_email(
                email, portfolio_name, required_usd, available_usd, until_label, krw_order=krw_order
            )
        except Exception as exc:
            report_handled_failure("dca_fx_required_email_failed", exc, plan_id=str(plan.id))

    if krw_order:
        title = f"원화 예수금 부족 — {portfolio_name} 적립"
        body = (
            f"해외 적립 매수에 ${required_usd:,.2f}가 필요한데 매수여력(원화 환산 포함)은 ${available_usd:,.2f}입니다. "
            f"원화를 입금한 뒤 '다시 매수'를 눌러주세요 ({until_label}까지 자동 재확인)."
        )
    else:
        title = f"달러 환전 필요 — {portfolio_name} 적립"
        body = (
            f"해외 적립 매수에 ${required_usd:,.2f}가 필요한데 보유 달러는 ${available_usd:,.2f}입니다. "
            f"환전 후 '다시 매수'를 눌러주세요 ({until_label}까지 자동 재확인)."
        )
    await send_push_safely(
        plan.user_id,
        title=title,
        body=body,
        fcm_token=fcm_token,
        data={"type": "DCA_FX_REQUIRED", "portfolio_id": str(plan.portfolio_id or "")},
        failure_event="dca_fx_required_push_failed",
        plan_id=str(plan.id),
    )


async def notify_dca_fx_wait_expired(plan: RebalancingPlan, db: AsyncSession) -> None:
    """환전 대기 기한이 지나 이번 회차 해외 적립 매수를 마감했음을 푸시로 알린다."""
    recipient = await _plan_recipient(plan, db)
    if recipient is None:
        return
    portfolio_name, _email, fcm_token = recipient
    await send_push_safely(
        plan.user_id,
        title=f"해외 적립 매수 미실행 — {portfolio_name}",
        body="환전 대기 기한이 지나 이번 회차 해외 매수는 진행되지 않았습니다. 다음 적립일에 다시 매수합니다.",
        fcm_token=fcm_token,
        data={"type": "REBALANCING_PLAN_EXPIRED", "portfolio_id": str(plan.portfolio_id or "")},
        failure_event="dca_fx_wait_expired_push_failed",
        plan_id=str(plan.id),
    )
