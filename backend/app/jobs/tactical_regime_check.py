"""전술 배분 국면 점검 Job — 매일 07:40 KST(미국 장 마감 후) 실행.

전략을 켠 포트폴리오마다 국면 확정 상태를 갱신하고, 확정 국면이 마지막 알림 국면과 다르면 이메일/푸시로
제안 비중을 안내한다. 주문은 내지 않는다. 서버가 잠들어 이 job을 놓친 날은 앱 조회(GET /tactical)가
확정을 대신 진행하고, 다음 job 실행 때 `notified_regime`과 비교해 놓친 알림을 보낸다.

웅덩이(눌림목) 투입 단계가 `notified_dip_level`보다 깊어지면 별도로 알린다(투입을 켠 전략만). 같은 실행에서
국면 알림을 보냈다면 그 제안 비중에 투입분이 이미 들어 있으므로 웅덩이 알림은 생략한다. 단계가 낮아지는
변화(회복·국면 이탈)는 알리지 않고 기록만 맞춘다.
"""

from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select

from app.core.cache_store import get_cache_store
from app.core.database import AsyncSessionLocal
from app.jobs._job_helpers import report_job_failure
from app.models.portfolio import Portfolio
from app.models.tactical import TacticalStrategy
from app.models.user import User, UserSettings
from app.services import tactical_allocation_service as tactical
from app.services.alerts._dispatch import dispatch_dual_channel_alert
from app.services.email_service import send_tactical_dip_email, send_tactical_regime_change_email
from app.services.tactical_dip import DIP_LEVEL_LABELS, dip_reasons
from app.utils.kst import today_kst

logger = structlog.get_logger()


async def run_tactical_regime_check() -> None:
    cache = await get_cache_store()
    try:
        async with AsyncSessionLocal() as db:
            market = await tactical.evaluate_market(cache, db)
            strategy_ids = (await db.execute(select(TacticalStrategy.id))).scalars().all()
    except Exception as e:
        report_job_failure("tactical_regime_check_failed", e)
        return

    logger.info("tactical_regime_check_start", observed=market["observed_regime"], strategies=len(strategy_ids))
    for strategy_id in strategy_ids:
        try:
            async with AsyncSessionLocal() as db:
                await _check_one(db, strategy_id, market)
        except Exception as e:
            report_job_failure("tactical_regime_check_failed", e, strategy_id=str(strategy_id))


async def _check_one(db, strategy_id, market: dict) -> None:
    strategy = await db.get(TacticalStrategy, strategy_id)
    if strategy is None:
        return
    today = today_kst()
    tactical.advance_regime(strategy, market, today)
    tactical.advance_tilt(strategy, market, today)  # 틸트 단독 변경은 알림 없음(월 1회·소폭 조정이라 소음만 늘린다)
    tactical.advance_dip(strategy, market)
    regime_sent = await _notify_regime(db, strategy, market)
    await _notify_dip(db, strategy, market, regime_sent=regime_sent)
    await db.commit()


async def _recipient(db, strategy: TacticalStrategy) -> tuple[Any, str, str | None, Portfolio] | None:
    row = (
        await db.execute(
            select(User, UserSettings, Portfolio)
            .join(Portfolio, Portfolio.user_id == User.id)
            .outerjoin(UserSettings, UserSettings.user_id == User.id)
            .where(Portfolio.id == strategy.portfolio_id, User.is_active == True)
        )
    ).first()
    if row is None:
        return None
    user, settings_row, portfolio = row
    to_email = (settings_row.notification_email if settings_row else None) or user.email
    fcm_token = settings_row.fcm_token if settings_row else None
    return user, to_email, fcm_token, portfolio


async def _notify_regime(db, strategy: TacticalStrategy, market: dict) -> bool:
    """확정 국면이 마지막 알림과 다르면 알린다. 발송했으면 True."""
    regime = strategy.last_regime
    if regime is None or regime == strategy.notified_regime:
        return False
    if not strategy.notify_enabled or regime == strategy.applied_regime:
        strategy.notified_regime = regime  # 알림 꺼짐 / 이미 그 국면 비중을 적용함 — 알릴 필요 없음
        return False
    recipient = await _recipient(db, strategy)
    if recipient is None:
        return False
    user, to_email, fcm_token, portfolio = recipient

    old_label = tactical.REGIME_LABELS.get(strategy.notified_regime or "", "없음")
    new_label = tactical.REGIME_LABELS[regime]
    weights_text = tactical.format_weights(tactical.proposed_weights_for(strategy, regime, market))

    async def _mark_notified() -> None:
        strategy.notified_regime = regime

    # 실패하면 국면 확정 상태만 저장되고 알림은 다음 실행 때 재시도
    return await dispatch_dual_channel_alert(
        db,
        user.id,
        event_prefix="tactical_regime_change",
        alert_type="TACTICAL_REGIME",
        history_message=f"[{portfolio.name}] 전술 배분 국면 {old_label} → {new_label} ({weights_text})",
        send_email=lambda: send_tactical_regime_change_email(
            to_email,
            portfolio.name,
            old_label,
            new_label,
            weights_text,
            tactical.observed_for(market, regime, tactical.uses_macro(strategy))[1],
            portfolio_id=str(portfolio.id),
        ),
        push_title=f"전술 배분: {new_label} 국면",
        push_body=f"{portfolio.name} 제안 비중 {weights_text} — 앱에서 확인 후 적용하세요.",
        push_type="tactical_regime",
        fcm_token=fcm_token,
        after_sent=_mark_notified,
    )


async def _notify_dip(db, strategy: TacticalStrategy, market: dict, *, regime_sent: bool) -> None:
    level = strategy.dip_level or 0
    shift = tactical.dip_shift_of(strategy)
    if level <= (strategy.notified_dip_level or 0) or regime_sent or shift <= 0 or not strategy.notify_enabled:
        strategy.notified_dip_level = level  # 단계 하락·국면 알림에 포함됨·투입 꺼짐·알림 꺼짐 — 따로 알리지 않음
        return
    regime = strategy.last_regime
    if regime is None:
        return
    recipient = await _recipient(db, strategy)
    if recipient is None:
        return
    user, to_email, fcm_token, portfolio = recipient

    stage_label = DIP_LEVEL_LABELS[level]
    deploy = tactical.dip_deployed_for(strategy, regime, market)  # 현금 한도 반영한 실제 투입량
    if deploy <= 0:  # 현금이 없어 옮길 몫이 없으면 알릴 내용도 없다
        strategy.notified_dip_level = level
        return
    weights_text = tactical.format_weights(tactical.proposed_weights_for(strategy, regime, market))
    reasons = dip_reasons(market.get("qqq_pullback_stage", "UNKNOWN"), level, shift, regime, deployed=deploy)

    async def _mark_notified() -> None:
        strategy.notified_dip_level = level

    await dispatch_dual_channel_alert(
        db,
        user.id,
        event_prefix="tactical_dip",
        alert_type="TACTICAL_DIP",
        history_message=f"[{portfolio.name}] 웅덩이 매수 제안 — {stage_label}, 현금 {deploy:g}%p 투입 ({weights_text})",
        send_email=lambda: send_tactical_dip_email(
            to_email, portfolio.name, stage_label, deploy, weights_text, reasons, portfolio_id=str(portfolio.id)
        ),
        push_title=f"웅덩이 매수 제안: {stage_label}",
        push_body=f"{portfolio.name} 현금 {deploy:g}%p를 주식으로 — 제안 비중 {weights_text}",
        push_type="tactical_dip",
        fcm_token=fcm_token,
        after_sent=_mark_notified,
    )
