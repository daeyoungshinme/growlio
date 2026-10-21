"""전술 배분 국면 점검 Job — 매일 07:40 KST(미국 장 마감 후) 실행.

전략을 켠 포트폴리오마다 국면 확정 상태를 갱신하고, 확정 국면이 마지막 알림 국면과 다르면 이메일/푸시로
제안 비중을 안내한다. 주문은 내지 않는다. 서버가 잠들어 이 job을 놓친 날은 앱 조회(GET /tactical)가
확정을 대신 진행하고, 다음 job 실행 때 `notified_regime`과 비교해 놓친 알림을 보낸다.
"""

from __future__ import annotations

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
from app.services.email_service import send_tactical_regime_change_email
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
    regime = strategy.last_regime
    if regime is None or regime == strategy.notified_regime:
        await db.commit()
        return
    if not strategy.notify_enabled or regime == strategy.applied_regime:
        strategy.notified_regime = regime  # 알림 꺼짐 / 이미 그 국면 비중을 적용함 — 알릴 필요 없음
        await db.commit()
        return

    row = (
        await db.execute(
            select(User, UserSettings, Portfolio)
            .join(Portfolio, Portfolio.user_id == User.id)
            .outerjoin(UserSettings, UserSettings.user_id == User.id)
            .where(Portfolio.id == strategy.portfolio_id, User.is_active == True)
        )
    ).first()
    if row is None:
        await db.commit()
        return
    user, settings_row, portfolio = row
    to_email = (settings_row.notification_email if settings_row else None) or user.email
    fcm_token = settings_row.fcm_token if settings_row else None

    old_label = tactical.REGIME_LABELS.get(strategy.notified_regime or "", "없음")
    new_label = tactical.REGIME_LABELS[regime]
    weights_text = tactical.format_weights(tactical.proposed_weights_for(strategy, regime, market))

    async def _mark_notified() -> None:
        strategy.notified_regime = regime

    sent = await dispatch_dual_channel_alert(
        db,
        user.id,
        event_prefix="tactical_regime_change",
        alert_type="TACTICAL_REGIME",
        history_message=f"[{portfolio.name}] 전술 배분 국면 {old_label} → {new_label} ({weights_text})",
        send_email=lambda: send_tactical_regime_change_email(
            to_email, portfolio.name, old_label, new_label, weights_text, tactical.observed_for(market, regime)[1]
        ),
        push_title=f"전술 배분: {new_label} 국면",
        push_body=f"{portfolio.name} 제안 비중 {weights_text} — 앱에서 확인 후 적용하세요.",
        push_type="tactical_regime",
        fcm_token=fcm_token,
        after_sent=_mark_notified,
    )
    if not sent:
        await db.commit()  # 국면 확정 상태는 저장하고, 알림은 다음 실행 때 재시도
