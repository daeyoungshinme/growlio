"""AUTO 리밸런싱 플랜 생성 게이트 — 생성하지 않을 때 돌려주는 sentinel과 세금영향·스냅샷 신선도 판정.

하루 합산 거래한도 게이트는 오늘 누적액 조회와 함께 `plan_generation`에 있다. `plan_generation`이 이 모듈의
심볼을 import해 쓰므로 테스트 patch는 `plan_generation.X` 경로로 한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import BROKER_API_DATA_SOURCES
from app.models.alert import RebalancingAlert
from app.models.asset import AssetAccount, RebalancingExecution, RebalancingExecutionResult
from app.models.portfolio import Portfolio, PortfolioAccount
from app.services.rebalancing.order_builder import is_tax_impact_blocking_auto_mode

logger = structlog.get_logger()


@dataclass(frozen=True)
class TaxGateBlocked:
    """`build_pending_plan_for_alert`가 세금영향 게이트로 차단됐을 때 반환하는 sentinel.

    알림 발송에 필요한 추정치를 함께 실어 나른다."""

    estimated_tax_krw: float
    max_tax_impact_krw: float


@dataclass(frozen=True)
class MarketSignalGateBlocked:
    """AUTO 계획 생성이 시장신호 게이트로 차단됐을 때 알림에 필요한 컨텍스트를 실어 나르는 sentinel."""

    composite_level: str
    market_condition_mode: str
    data_freshness: str
    tactical_regime: str | None = None


@dataclass(frozen=True)
class DailyValueCapBlocked:
    """AUTO 계획 생성이 유저 단위 하루 합산 거래대금 상한으로 차단됐을 때 반환하는 sentinel."""

    today_total_krw: float
    attempted_value_krw: float
    cap_krw: float


@dataclass(frozen=True)
class UsdRateUnavailable:
    """해외 종목이 있는데 실환율이 없어 주문 수량을 계산하지 않았다 — 드리프트 없음이 아니라 다음에 다시 평가할 대상."""


@dataclass(frozen=True)
class SyncRequiredAfterExecution:
    """접수된 주문이 아직 스냅샷에 반영되지 않았다 — 지금 만들면 체결 전 수량으로 같은 주문이 다시 나간다.

    다음 동기화로 풀리므로 알림 없이 다음 평가로 넘긴다.
    """

    account_name: str


@dataclass(frozen=True)
class SnapshotTooStale:
    """동기화가 오래 끊겨 보유 수량을 믿을 수 없다 — 무인 AUTO는 생성하지 않고 사용자에게 알린다."""

    account_name: str
    days_since_sync: int


@dataclass(frozen=True)
class PlanGenerationInProgress:
    """동시에 들어온 다른 계획 생성 요청이 이미 처리 중이라 유저 단위 락을 획득하지 못했을 때 반환하는 sentinel.

    AUTO 스케줄러 job과 수동 "지금 실행"이 같은 유저에 대해 거의 동시에 호출되는 경우에만 발생한다
    (하루 합산 거래한도의 check-then-act 레이스를 막기 위한 `inproc_lock` 직렬화, `build_pending_plan_for_alert`
    참고). 흔치 않은 경합이므로 재시도 안내만 하면 충분 — 별도 알림 발송은 하지 않는다.
    """


def _check_tax_gate(alert: RebalancingAlert, analysis: Any, overview: Any) -> TaxGateBlocked | None:
    """세금영향 게이트 — 켜져 있고 추정 양도세가 상한을 넘으면 TaxGateBlocked."""
    tax_gate_mode = alert.tax_impact_gate_mode
    max_tax_impact_krw = alert.max_tax_impact_krw
    if tax_gate_mode != "ENABLED" or max_tax_impact_krw is None:
        return None
    from app.services.rebalancing.diagnosis_service import _build_tax_preview

    _total_gain, estimated_tax_krw, _fee, _notes, _items = _build_tax_preview(analysis, overview)
    if not is_tax_impact_blocking_auto_mode(tax_gate_mode, estimated_tax_krw, max_tax_impact_krw):
        return None
    logger.info(
        "rebalancing_plan_blocked_tax_impact",
        alert_id=str(alert.id),
        estimated_tax_krw=estimated_tax_krw,
        max_tax_impact_krw=max_tax_impact_krw,
    )
    return TaxGateBlocked(estimated_tax_krw=estimated_tax_krw, max_tax_impact_krw=float(max_tax_impact_krw))


# 연휴에도 일일 동기화는 돈다. 이만큼 끊겼다면 장애로 보고 무인 실행을 멈춘다
_AUTO_SNAPSHOT_MAX_AGE = timedelta(days=5)


async def _check_snapshot_freshness(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    buy_account_id: uuid.UUID | None,
    db: AsyncSession,
    *,
    enforce_max_age: bool,
) -> SyncRequiredAfterExecution | SnapshotTooStale | None:
    """플랜의 수량 근거인 스냅샷이 믿을 만한지 — 대상은 실행 계좌와 포트폴리오 연결 계좌 중 브로커 계좌.

    플랜은 스냅샷 보유 수량으로 계산되는데 체결 뒤 자동 동기화는 없다. 그래서 마지막 접수 주문이 마지막 동기화보다
    뒤면 같은 주문이 다시 만들어진다(plans/110 A2).
    """
    accounts = (
        await db.execute(
            select(AssetAccount.id, AssetAccount.name, AssetAccount.last_synced_at).where(
                AssetAccount.user_id == alert.user_id,
                AssetAccount.is_active == True,
                AssetAccount.data_source.in_(BROKER_API_DATA_SOURCES),
                or_(
                    AssetAccount.id == buy_account_id,
                    AssetAccount.id.in_(
                        select(PortfolioAccount.account_id).where(PortfolioAccount.portfolio_id == portfolio.id)
                    ),
                ),
            )
        )
    ).all()
    if not accounts:
        return None

    if enforce_max_age:
        now = datetime.now(UTC)
        for _account_id, name, last_synced_at in accounts:
            if last_synced_at is not None and now - last_synced_at > _AUTO_SNAPSHOT_MAX_AGE:
                return SnapshotTooStale(account_name=name, days_since_sync=(now - last_synced_at).days)

    last_executed_at = dict(
        (
            await db.execute(
                select(RebalancingExecutionResult.account_id, func.max(RebalancingExecution.executed_at))
                .join(RebalancingExecution, RebalancingExecution.id == RebalancingExecutionResult.execution_id)
                .where(
                    RebalancingExecution.user_id == alert.user_id,
                    RebalancingExecutionResult.account_id.in_([str(row[0]) for row in accounts]),
                    RebalancingExecutionResult.status == "SUCCESS",
                    or_(
                        RebalancingExecutionResult.cancel_status.is_(None),
                        RebalancingExecutionResult.cancel_status != "CANCELED",
                    ),
                )
                .group_by(RebalancingExecutionResult.account_id)
            )
        )
        .tuples()
        .all()
    )
    for account_id, name, last_synced_at in accounts:
        executed_at = last_executed_at.get(str(account_id))
        if executed_at is not None and (last_synced_at is None or executed_at > last_synced_at):
            return SyncRequiredAfterExecution(account_name=name)
    return None
