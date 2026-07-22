"""리밸런싱 알림 체크(10분 간격 job) 메인 루프.

alert_scope 전환 → rebalancing/alert_scope.py
테스트 즉시 발송 → rebalancing/alert_test.py
환율 알림 → alerts/exchange_rate_service.py
주가 알림 → alerts/stock_price_service.py
공통 알림 저장/조회 → alerts/alert_service.py
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, Literal, cast

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.alert import RebalancingAlert
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.services.alerts.alert_service import save_alert_history
from app.services.alerts.calculator import (
    already_fired_today,
    should_fire_today,
)
from app.services.rebalancing.alert_scope import resolve_effective_account_ids
from app.services.rebalancing.diagnosis_service import check_composite_signal, fetch_market_and_risk_signal
from app.services.rebalancing.order_builder import (
    build_rebalancing_orders,
    filter_drifting_items,
    is_market_signal_blocking_auto_mode,
    refresh_live_prices,
)
from app.utils.cache_keys import TTL_COMPOSITE_ALERT_SENT, composite_alert_sent_key
from app.utils.durable_state import get_durable, set_durable
from app.utils.market_hours import is_alert_execution_time
from app.utils.metrics import alert_trigger_count

__all__ = [
    "build_rebalancing_orders",
    "check_rebalancing_alerts",
    "refresh_live_prices",
]

logger = structlog.get_logger()

_KST = timezone(timedelta(hours=9))


async def _composite_alert_sent_today(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """오늘(KST) 이 유저에게 복합신호만으로 리밸런싱 알림이 이미 발송되었는지 확인한다.

    dedup 플래그는 재시작에도 유지돼야 하므로(콜드스타트 후 오탐 방지) Postgres 기반
    durable_state를 사용한다.
    """
    today = datetime.now(tz=_KST).date().isoformat()
    return bool(await get_durable(db, composite_alert_sent_key(user_id, today)))


async def _mark_composite_alert_sent_today(db: AsyncSession, user_id: uuid.UUID) -> None:
    """복합신호만으로 발송한 뒤, 오늘 이 유저에게는 더 이상 중복 발송하지 않도록 표시한다."""
    today = datetime.now(tz=_KST).date().isoformat()
    await set_durable(db, composite_alert_sent_key(user_id, today), "1", ttl=TTL_COMPOSITE_ALERT_SENT)


def _select_items_to_show(
    trigger_condition: str,
    is_schedule_day: bool,
    drifting: list,
    all_items: list,
    extra_trigger: bool = False,
) -> tuple[list, bool, bool] | None:
    """trigger_condition + extra_trigger(복합 리스크/시장 신호)에 따라
    (items_to_show, is_scheduled_report, is_composite_triggered)를 반환.

    발송하지 않아야 하는 경우 None 반환. extra_trigger는 drift/스케줄로 이미 발송이
    확정되지 않은 경우에만 "추가로" 발송시킨다 — 기존 발송 조건을 억제하지 않는다.
    """
    if trigger_condition == "SCHEDULE_ONLY":
        if not is_schedule_day:
            return None
        return all_items, True, False
    if trigger_condition == "DRIFT_ONLY":
        if drifting:
            return drifting, False, False
        if extra_trigger:
            return all_items, False, True
        return None
    # BOTH
    if is_schedule_day:
        return all_items, True, False
    if drifting:
        return drifting, False, False
    if extra_trigger:
        return all_items, False, True
    return None


async def _process_rebalancing_alert(
    alert,
    portfolio: Portfolio,
    drifting: list,
    items_to_show: list,
    is_scheduled_report: bool,
    threshold: float,
    email: str,
    composite_level: str,
    db: AsyncSession,
    data_freshness: str = "LIVE",
    fcm_token: str | None = None,
    is_composite_triggered: bool = False,
    composite_reason: str | None = None,
    cache: Any = None,
    ticker_account_map: dict[str, list] | None = None,
    automation_note: str | None = None,
) -> bool:
    """단일 리밸런싱 알림을 처리 (AUTO 실행 또는 이메일/FCM 발송).

    이메일·FCM 중 하나라도 성공하면 True 반환. 둘 다 실패하면 False 반환.
    `automation_note`는 AUTO 모드가 시장신호 게이트로 이번만 NOTIFY로 강등됐을 때 그 사유를
    담아 이메일 본문에 노출하기 위한 것 — 호출부(`check_rebalancing_alerts`)가 계산해 전달한다.
    """
    from app.services.email_service import send_rebalancing_alert
    from app.services.push_service import send_push_to_user

    # 실제 매수/매도 수량 미리보기 — drift가 있을 때만 계산(실행/저장은 하지 않음, 표시 전용).
    order_preview_items: list = []
    if drifting:
        strategy = getattr(alert, "strategy", "BUY_ONLY")
        order_type = cast(Literal["MARKET", "LIMIT"], getattr(alert, "order_type", "MARKET"))
        buy_account_id = str(alert.account_id) if alert.account_id else ""
        order_preview_items = build_rebalancing_orders(
            drifting, ticker_account_map or {}, strategy, order_type, buy_account_id, alert_id=str(alert.id)
        )

    mode = getattr(alert, "mode", "NOTIFY")

    # 시장 신호 기반 자동 실행 게이트
    if mode == "AUTO":
        market_mode = getattr(alert, "market_condition_mode", "DISABLED")
        if is_market_signal_blocking_auto_mode(market_mode, composite_level, data_freshness):
            logger.info(
                "rebalancing_auto_skipped_market_signal",
                alert_id=str(alert.id),
                composite_level=composite_level,
                data_freshness=data_freshness,
                market_condition_mode=market_mode,
            )
            mode = "NOTIFY"

    # AUTO 모드 실행은 rebalancing_auto_execution 인트라데이 잡이 전담한다.
    # 10분 간격 job(check_rebalancing_alerts)은 각 알림의 notify_time 창에서만 이메일/FCM 리포트를 발송한다.

    drift_count = len(drifting)
    if drift_count:
        push_title = f"리밸런싱 알림 — {portfolio.name}"
        push_body = f"{drift_count}개 종목이 ±{threshold:.1f}% 이상 이탈했습니다."
    elif is_composite_triggered:
        # 복합신호는 특정 포트폴리오가 아닌 계정 전체 기준 신호이므로 포트폴리오명을 노출하지 않는다.
        push_title = "시장/리스크 신호 감지"
        push_body = f"보유 포트폴리오 점검을 권장합니다: {composite_reason}"
    else:
        push_title = f"리밸런싱 알림 — {portfolio.name}"
        push_body = f"{portfolio.name} 정기 리밸런싱 리포트"

    # 이메일 독립 처리
    email_sent = False
    try:
        email_sent = await send_rebalancing_alert(
            to_email=email,
            portfolio_name=portfolio.name,
            threshold_pct=threshold,
            items_to_show=items_to_show,
            drifting_count=drift_count,
            is_scheduled_report=is_scheduled_report,
            schedule_type=getattr(alert, "schedule_type", "DAILY"),
            is_composite_triggered=is_composite_triggered,
            composite_reason=composite_reason,
            order_preview_items=order_preview_items,
            automation_note=automation_note,
        )
    except Exception as exc:
        logger.error("rebalancing_alert_email_failed", alert_id=str(alert.id), error=str(exc))

    # FCM 독립 처리 — 이메일 실패와 무관하게 항상 시도
    push_sent = False
    with contextlib.suppress(Exception):
        push_sent = await send_push_to_user(
            user_id=alert.user_id,
            title=push_title,
            body=push_body,
            fcm_token=fcm_token,
            data={"type": "REBALANCING", "portfolio_id": str(portfolio.id)},
        )

    any_sent = email_sent or push_sent
    if not any_sent:
        logger.warning(
            "rebalancing_alert_no_channel_sent",
            alert_id=str(alert.id),
            email_sent=email_sent,
            push_sent=push_sent,
        )
    elif is_composite_triggered and cache is not None:
        # 복합신호는 유저 단위로 동일하게 평가되므로, 여러 포트폴리오에 걸친 중복 발송을 막기 위해 표시한다.
        await _mark_composite_alert_sent_today(db, alert.user_id)
    return any_sent


async def _get_composite_level(cache) -> tuple[str, str]:
    """전체 알림 루프에서 공용으로 쓸 시장 신호 등급을 1회 조회한다.

    조회 자체가 실패하면 (composite_level="GREEN", data_freshness="STALE")로 폴백한다 —
    composite_level만 보면 "안전"으로 오인되므로, data_freshness="STALE"을 함께 반환해
    `is_market_signal_blocking_auto_mode`가 AUTO를 보수적으로 차단할 수 있게 한다.
    """
    from app.services.market_signal_service import get_market_signal

    try:
        market_signal = await get_market_signal(cache)
        return market_signal.get("composite_level", "GREEN"), market_signal.get("data_freshness", "LIVE")
    except Exception as exc:
        logger.warning("market_signal_fetch_failed_in_alert_check", error=str(exc))
        return "GREEN", "STALE"


def _should_skip_by_schedule(alert: RebalancingAlert, trigger_condition: str, is_schedule_day: bool) -> bool:
    """notify_time 실행창(±4분)·스케줄 요일·당일 중복발송 여부에 따라 이번 체크를 건너뛸지 판정한다."""
    notify_time = getattr(alert, "notify_time", "08:30")
    if not is_alert_execution_time(notify_time):
        return True

    # BOTH: 매일 체크; DRIFT_ONLY/SCHEDULE_ONLY: 스케줄 날만 체크
    if not is_schedule_day and trigger_condition != "BOTH":
        logger.debug(
            "rebalancing_alert_not_schedule_day",
            alert_id=str(alert.id),
            schedule=alert.schedule_type,
            trigger_condition=trigger_condition,
        )
        return True
    if already_fired_today(alert):
        logger.debug("rebalancing_alert_already_fired_today", alert_id=str(alert.id))
        return True
    return False


async def _analyze_alert_drift(alert: RebalancingAlert, portfolio: Portfolio, db: AsyncSession, cache: Any = None):
    """알림 대상 포트폴리오의 현재 배분을 조회·분석한다. 실패 시 None(호출부에서 skip)."""
    from app.services.portfolio_service import build_portfolio_overview
    from app.services.rebalancing.service import analyze_rebalancing

    effective_account_ids = resolve_effective_account_ids(alert, portfolio)

    try:
        overview = await build_portfolio_overview(alert.user_id, db, account_ids=effective_account_ids, cache=cache)
    except Exception as exc:
        logger.error("rebalancing_alert_overview_failed", alert_id=str(alert.id), error=str(exc))
        return None

    try:
        return analyze_rebalancing(portfolio, overview, include_implicit_cash=True)
    except Exception as exc:
        logger.error("rebalancing_alert_analysis_failed", alert_id=str(alert.id), error=str(exc))
        return None


async def _evaluate_composite_trigger(
    alert: RebalancingAlert,
    trigger_condition: str,
    is_schedule_day: bool,
    drifting: list,
    composite_signal_alerts_enabled: bool,
    db: AsyncSession,
    cache,
) -> tuple[bool, str | None]:
    """drift/스케줄만으로 발송이 확정되지 않을 때만 복합 시장신호를 조회해 추가 트리거 여부를 판정한다.

    drift/스케줄만으로 이미 발송이 확정되는 경우 복합신호 조회를 스킵해 불필요한 리스크 API 호출을 절약한다.
    복합신호는 포트폴리오와 무관하게 유저 단위로 동일하게 평가되므로, 게이팅도 포트폴리오별이 아닌
    UserSettings.composite_signal_alerts_enabled(유저 단위 단일 설정)로 판단한다. 같은 유저가 여러
    포트폴리오 알림을 갖고 있어도 이 값은 동일하므로, dedup(_composite_alert_sent_today)이
    실제 중복 발송을 막는다.
    """
    will_send_without_composite = bool(drifting) or (trigger_condition in ("SCHEDULE_ONLY", "BOTH") and is_schedule_day)
    if will_send_without_composite or not composite_signal_alerts_enabled:
        return False, None

    extra_trigger = False
    composite_reason: str | None = None
    try:
        market_level, risk = await fetch_market_and_risk_signal(alert.user_id, db, cache)
        extra_trigger, composite_reason = check_composite_signal(
            market_level,
            bool(risk.get("data_available")),
            risk.get("diversification_score"),
            risk.get("top_holding_weight_pct"),
            risk.get("annualized_volatility_pct"),
        )
    except Exception as exc:
        logger.warning("rebalancing_alert_composite_signal_failed", alert_id=str(alert.id), error=str(exc))

    if extra_trigger and await _composite_alert_sent_today(db, alert.user_id):
        extra_trigger = False
        composite_reason = None

    return extra_trigger, composite_reason


async def check_rebalancing_alerts(db: AsyncSession) -> None:
    """활성 리밸런싱 알림을 조회하고 스케줄·조건에 따라 이메일 발송."""
    from app.core.cache_store import get_cache_store

    _cache = await get_cache_store()
    # 시장 신호를 루프 전 한 번만 조회 (전체 알림 공용)
    composite_level, market_data_freshness = await _get_composite_level(_cache)

    result = await db.execute(
        select(
            RebalancingAlert,
            Portfolio,
            User.email,
            UserSettings.notification_email,
            UserSettings.fcm_token,
            UserSettings.composite_signal_alerts_enabled,
        )
        .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
        .join(User, User.id == RebalancingAlert.user_id)
        .outerjoin(UserSettings, UserSettings.user_id == User.id)
        .options(selectinload(Portfolio.linked_accounts), selectinload(Portfolio.items))
        .where(RebalancingAlert.is_active == True)  # noqa: E712
    )
    rows = result.all()

    triggered_count = 0
    for alert, portfolio, user_email, notification_email, fcm_token, composite_signal_alerts_enabled in rows:
        trigger_condition = getattr(alert, "trigger_condition", "DRIFT_ONLY")
        is_schedule_day = should_fire_today(alert)

        if _should_skip_by_schedule(alert, trigger_condition, is_schedule_day):
            continue

        analysis = await _analyze_alert_drift(alert, portfolio, db, _cache)
        if analysis is None:
            continue

        threshold = float(alert.threshold_pct)
        drifting = filter_drifting_items(analysis.items, threshold)

        # UserSettings 행이 없으면(outerjoin NULL) 기본값 True로 폴백 — 신규 유저 기본 동작 유지
        effective_composite_enabled = (
            composite_signal_alerts_enabled if composite_signal_alerts_enabled is not None else True
        )
        extra_trigger, composite_reason = await _evaluate_composite_trigger(
            alert, trigger_condition, is_schedule_day, drifting, effective_composite_enabled, db, _cache
        )

        selected = _select_items_to_show(trigger_condition, is_schedule_day, drifting, analysis.items, extra_trigger)
        if selected is None:
            logger.debug(
                "rebalancing_alert_no_items_selected",
                alert_id=str(alert.id),
                trigger_condition=trigger_condition,
                drifting_count=len(drifting),
                extra_trigger=extra_trigger,
            )
            continue
        items_to_show, is_scheduled_report, is_composite_triggered = selected

        automation_note = None
        if getattr(alert, "mode", "NOTIFY") == "AUTO":
            market_mode = getattr(alert, "market_condition_mode", "DISABLED")
            if is_market_signal_blocking_auto_mode(market_mode, composite_level, market_data_freshness):
                automation_note = f"시장 위험 신호({composite_level})로 이번엔 자동 실행 대신 알림만 발송됐습니다."

        email = notification_email or user_email
        triggered = await _process_rebalancing_alert(
            alert=alert,
            portfolio=portfolio,
            drifting=drifting,
            items_to_show=items_to_show,
            is_scheduled_report=is_scheduled_report,
            threshold=threshold,
            email=email,
            composite_level=composite_level,
            data_freshness=market_data_freshness,
            db=db,
            fcm_token=fcm_token,
            is_composite_triggered=is_composite_triggered,
            composite_reason=composite_reason,
            cache=_cache,
            ticker_account_map=analysis.ticker_account_map,
            automation_note=automation_note,
        )
        if not triggered:
            continue

        drift_desc = (
            f"{len(drifting)}개 종목 드리프트"
            if drifting
            else ("복합 리스크 신호" if is_composite_triggered else "정기 보고")
        )
        history_automation_suffix = f", 자동실행→알림 전환({composite_level})" if automation_note else ""
        await save_alert_history(
            db,
            alert.user_id,
            "REBALANCING",
            (
                f"리밸런싱 알림: {portfolio.name} — {drift_desc} ({alert.schedule_type}) "
                f"[시장신호: {composite_level}]{history_automation_suffix}"
            ),
        )
        # AUTO 모드는 last_triggered_at을 갱신하지 않는다.
        # 인트라데이 잡(rebalancing_auto_execution)에서 실제 실행 후 갱신하므로,
        # 여기서 갱신하면 already_fired_today()가 True → 당일 자동 실행 차단됨.
        if getattr(alert, "mode", "NOTIFY") != "AUTO":
            alert.last_triggered_at = datetime.now(tz=UTC)
        triggered_count += 1

    if triggered_count:
        await db.commit()
        alert_trigger_count.labels(alert_type="rebalancing").inc(triggered_count)
        logger.info("rebalancing_alerts_triggered", count=triggered_count)
