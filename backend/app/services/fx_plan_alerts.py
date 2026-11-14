"""환전 계획 구간 목표 환율 알림 맞추기(plans/121·123·126 E1).

계획 범위(포트폴리오 적립 계획 `portfolio_id` 또는 추가 환전 항목 `fx_need_id`)의 FX_PLAN 출처
`ExchangeRateAlert`를 목표 구간에 맞춘다. 계획 계산은 `fx_plan_service`.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, timedelta

import structlog
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import FX_PLAN_ACTION_DAYS, FX_PLAN_ALERT_SOURCE, MAX_EXCHANGE_RATE_ALERTS_PER_USER
from app.core.cache_store import CacheStore
from app.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.alert import ExchangeRateAlert
from app.models.fx_extra_need import FxExtraNeed
from app.models.portfolio import Portfolio
from app.utils.inproc_lock import inproc_lock
from app.utils.kst import kst_day_start, today_kst
from app.utils.quota_lock import lock_user_for_quota

logger = structlog.get_logger()

_SYNC_LOCK_TTL_SECONDS = 30


@dataclass(frozen=True)
class FxPlanAlertSyncResult:
    created: int
    updated: int
    removed: int
    skipped_manual: int
    skipped_shared: int = 0


def _rate_key(rate: float) -> int:
    """Numeric(10,2) 목표 환율을 비교 키로(센트 단위 정수) — float 오차로 같은 목표가 달라 보이지 않게."""
    return round(float(rate) * 100)


async def _check_scope_owned(
    db: AsyncSession,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    fx_need_id: uuid.UUID | None,
    has_targets: bool,
) -> None:
    if (portfolio_id is None) == (fx_need_id is None):
        raise ValueError("portfolio_id와 fx_need_id 중 하나만 지정한다")
    if portfolio_id is not None:
        owned = await db.scalar(select(Portfolio.id).where(Portfolio.id == portfolio_id, Portfolio.user_id == user_id))
        if owned is None:
            raise NotFoundError(detail="포트폴리오를 찾을 수 없습니다")
        return
    due = await db.scalar(
        select(FxExtraNeed.due_date).where(FxExtraNeed.id == fx_need_id, FxExtraNeed.user_id == user_id)
    )
    if due is None:
        raise NotFoundError(detail="추가 환전 항목을 찾을 수 없습니다")
    # 지난 항목의 알림은 발송하지 않는다 — 새로 만들지도 않는다(해제는 허용)
    if has_targets and due < today_kst():
        raise BadRequestError(detail="필요일이 지난 항목에는 알림을 등록할 수 없습니다")


def _in_scope(alert: ExchangeRateAlert, portfolio_id: uuid.UUID | None, fx_need_id: uuid.UUID | None) -> bool:
    """계획 알림이 이번 맞추기 범위인지 — 추가 환전 항목 알림은 portfolio_id가 없다."""
    if fx_need_id is not None:
        return alert.fx_need_id == fx_need_id
    return alert.portfolio_id == portfolio_id and alert.fx_need_id is None


def _is_shareable_portfolio_alert(alert: ExchangeRateAlert) -> bool:
    """다른 포트폴리오 적립 계획의 활성·미발동 알림인지 — 같은 목표면 새로 만들지 않고 함께 쓴다.

    추가 환전 항목 알림은 항목 이름이 실려 따로 둔다. 프론트 `utils/fxPlanAlerts.sharedWith`와 같은 규칙.
    """
    return alert.fx_need_id is None and alert.is_active and alert.direction == "BELOW" and alert.triggered_at is None


def _classify_alerts(
    alerts: Sequence[ExchangeRateAlert], portfolio_id: uuid.UUID | None, fx_need_id: uuid.UUID | None
) -> tuple[dict[int, ExchangeRateAlert], list[ExchangeRateAlert], set[int], set[int]]:
    """맞추기 대상 알림을 나눈다 — (이 범위 미발동 계획 알림[목표 키별 하나], 지울 이 범위 계획 알림,
    직접 등록한 활성 BELOW 목표, 다른 포트폴리오 계획의 활성·미발동 목표[포트폴리오 범위에서만])."""
    triggered_cutoff = kst_day_start(today_kst() - timedelta(days=FX_PLAN_ACTION_DAYS - 1))
    plan_alerts: dict[int, ExchangeRateAlert] = {}
    stale: list[ExchangeRateAlert] = []
    manual_keys: set[int] = set()
    shared_keys: set[int] = set()
    for alert in alerts:
        key = _rate_key(alert.target_rate)
        if alert.source != FX_PLAN_ALERT_SOURCE:
            manual_keys.add(key)
        elif not _in_scope(alert, portfolio_id, fx_need_id):
            # 다른 포트폴리오·추가 환전 항목의 계획 알림은 그 계획이 관리한다
            if fx_need_id is None and _is_shareable_portfolio_alert(alert):
                shared_keys.add(key)
        elif alert.triggered_at is not None:
            fired = alert.triggered_at
            if (fired if fired.tzinfo else fired.replace(tzinfo=UTC)) < triggered_cutoff:
                stale.append(alert)
        # 같은 목표가 둘이면(동시 등록 경합의 흔적) 하나만 남긴다
        elif key in plan_alerts:
            stale.append(alert)
        else:
            plan_alerts[key] = alert
    return plan_alerts, stale, manual_keys, shared_keys


async def sync_fx_plan_alerts(
    db: AsyncSession,
    cache: CacheStore,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    targets: list[tuple[float, float]],
    *,
    fx_need_id: uuid.UUID | None = None,
) -> FxPlanAlertSyncResult:
    """한 계획 범위의 알림(FX_PLAN, 활성·미발동)을 `targets`[(목표 환율, 달러)]에 맞춘다(plans/121).

    범위는 포트폴리오 적립 계획(`portfolio_id`) 또는 추가 환전 항목(`fx_need_id`, plans/123) 중 하나다 —
    한 범위의 맞추기는 다른 범위의 계획 알림을 건드리지 않는다.

    - 같은 목표가 이미 있으면 금액만 갱신, 새 목표면 BELOW 1회 알림 생성, 목표에서 빠진 계획 알림은 삭제.
    - 같은 목표의 **직접 등록한(MANUAL) 활성 BELOW 알림**이 있으면 만들지 않는다(중복 발송 방지).
      MANUAL 알림은 계획이 지우거나 바꾸지 않는다.
    - 포트폴리오 적립 계획끼리는 목표 환율이 같으면 알림을 하나만 둔다 — 다른 포트폴리오 계획의 활성·미발동
      알림이 그 목표에 있으면 만들지 않고, 이 계획에 이미 있던 같은 목표 알림은 지운다(먼저 맞춘 쪽이 남는다).
      같은 환율에 메일·푸시가 두 번 오지 않게 한다. 추가 환전 항목(`fx_need_id`) 알림은 항목 이름이 실려 따로 둔다.
    - 일시정지한 미발동 계획 알림도 계획 알림이다 — 목표에 있으면 다시 켜고, 없으면 지운다(중복 생성 방지).
    - 발동된 계획 알림은 "지금 할 일"이 보이는 동안(`FX_PLAN_ACTION_DAYS`) 두고, 그보다 오래된 것은 지운다 —
      쌓이면 사용자당 알림 상한(50)에 걸려 맞추기·직접 등록이 모두 409가 된다(plans/122 B5).
      발동 기록은 알림 이력에 남는다.
    """
    await _check_scope_owned(db, user_id, portfolio_id, fx_need_id, bool(targets))
    scope_filter = (
        ExchangeRateAlert.fx_need_id == fx_need_id
        if fx_need_id is not None
        else and_(ExchangeRateAlert.portfolio_id == portfolio_id, ExchangeRateAlert.fx_need_id.is_(None))
    )

    async with inproc_lock(cache, f"lock:fx_plan_alerts:{user_id}", ttl=_SYNC_LOCK_TTL_SECONDS) as acquired:
        if not acquired:
            raise ConflictError(detail="환전 계획 알림을 등록하는 중입니다. 잠시 후 다시 시도해 주세요")

        alerts = (
            (
                await db.execute(
                    select(ExchangeRateAlert).where(
                        ExchangeRateAlert.user_id == user_id,
                        or_(
                            and_(ExchangeRateAlert.is_active == True, ExchangeRateAlert.direction == "BELOW"),
                            and_(ExchangeRateAlert.source == FX_PLAN_ALERT_SOURCE, scope_filter),
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        plan_alerts, stale, manual_keys, shared_keys = _classify_alerts(alerts, portfolio_id, fx_need_id)

        wanted = {_rate_key(rate): (rate, usd) for rate, usd in targets}
        # 다른 포트폴리오 계획과 겹친 목표의 이 계획 알림도 지운다 — 같은 환율 알림을 하나로
        stale.extend(alert for key, alert in plan_alerts.items() if key not in wanted or key in shared_keys)

        to_create: list[tuple[float, float]] = []
        updated = skipped = shared = 0
        for key, (rate, usd) in wanted.items():
            if key in shared_keys:
                shared += 1
            elif key in plan_alerts:
                plan_alerts[key].planned_usd = round(usd, 2)
                plan_alerts[key].is_active = True
                updated += 1
            elif key in manual_keys:
                skipped += 1
            else:
                to_create.append((rate, usd))

        await lock_user_for_quota(db, user_id)  # 수동 알림 생성과 동시에 상한을 넘지 않게(plans/129 B3)
        total = await db.scalar(
            select(func.count()).select_from(ExchangeRateAlert).where(ExchangeRateAlert.user_id == user_id)
        )
        if (total or 0) - len(stale) + len(to_create) > MAX_EXCHANGE_RATE_ALERTS_PER_USER:
            await db.rollback()
            raise ConflictError(
                detail=(
                    f"환율 알림은 {MAX_EXCHANGE_RATE_ALERTS_PER_USER}개까지 만들 수 있습니다. 안 쓰는 알림은 지워주세요"
                )
            )

        for alert in stale:
            await db.delete(alert)
        for rate, usd in to_create:
            db.add(
                ExchangeRateAlert(
                    user_id=user_id,
                    target_rate=rate,
                    direction="BELOW",
                    max_trigger_count=1,
                    source=FX_PLAN_ALERT_SOURCE,
                    planned_usd=round(usd, 2),
                    portfolio_id=portfolio_id,
                    fx_need_id=fx_need_id,
                )
            )
        await db.commit()

    logger.info(
        "fx_plan_alerts_synced",
        user_id=str(user_id),
        scope="fx_need" if fx_need_id is not None else "portfolio",
        created=len(to_create),
        updated=updated,
        removed=len(stale),
        skipped_manual=skipped,
        skipped_shared=shared,
    )
    return FxPlanAlertSyncResult(len(to_create), updated, len(stale), skipped, shared)
