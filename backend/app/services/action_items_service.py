"""홈 "지금 할 일" — 흩어진 행동 신호를 우선순위 리스트 1장으로 모은다 (docs/plans/50 M5).

소스(이 결과는 캐시하지 않는다 — 사용자가 행동한 직후 바로 사라져야 한다. 리밸런싱·챌린지는 자체 캐시를 쓰지만
세금 요약은 캐시가 없어 홈 로드마다 다시 계산한다):
- REBALANCE: 비중 이탈이 임계값을 넘은 포트폴리오 (`get_drift_summaries` — `/rebalancing/drift-summary`와 같은 판정)
- DCA_SHORTFALL: 정기 적립식 자동매수 다음 실행일 기준 예수금 부족 (`find_dca_cash_shortfalls` — 18:30 잡과 같은 판정)
- TAX_WARNING: 건보 피부양자·금융소득 종합과세·국내 대주주 경고 (세금 추정 요약)
- TAX_ACTION: 절세 액션 플랜 1순위 (손실수확도 이 플랜의 한 카테고리라 별도 항목을 만들지 않는다)
- CHALLENGE: 이번 달 아직 입금하지 않은 적립 챌린지 (`get_challenge_summary` — 20일 이후만, BottomNav 배지와 같은 판정)

추천 비중 변화는 MVO 계산 비용이 커서 제외한다(주간 이메일 알림이 담당).
한 소스가 실패해도 나머지 항목은 반환한다. 같은 AsyncSession을 쓰므로 소스는 순차 호출한다.
"""

from __future__ import annotations

import calendar
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.dca_cash_shortfall import NOTICE_WINDOW_DAYS, find_dca_cash_shortfalls
from app.schemas.action_items import ActionItem
from app.services.challenge_service import get_challenge_summary
from app.services.rebalancing.drift_summary_service import get_drift_summaries
from app.services.tax_action_service import get_tax_action_plan_with_summary
from app.utils.cache_keys import CacheStoreType
from app.utils.kst import today_kst

logger = structlog.get_logger()

MAX_ACTION_ITEMS = 5
_PRIORITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_LINK_TAX_ESTIMATE = "/invest-plan?tab=절세&taxTab=세금 추정"
_LINK_CHALLENGE = "/invest-plan?tab=챌린지"


def _portfolio_link(portfolio_id: uuid.UUID | str, *, open_alert: bool = False) -> str:
    link = f"/rebalancing?rtab=포트폴리오&portfolioId={portfolio_id}"
    return f"{link}&openAlert=1" if open_alert else link


async def _rebalance_items(user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType) -> list[ActionItem]:
    items: list[ActionItem] = []
    for s in await get_drift_summaries(user_id, db, cache):
        if not s.needs_rebalancing:
            continue
        items.append(
            ActionItem(
                id=f"rebalance:{s.portfolio_id}",
                kind="REBALANCE",
                priority="HIGH",
                title=f"{s.portfolio_name} 리밸런싱 필요",
                detail=(
                    f"최대 {s.max_drift_pct:.1f}%p 이탈 · {s.drifted_items_count}종목이 기준 {s.threshold_pct:g}%p 초과"
                ),
                cta_label="점검하기",
                link=_portfolio_link(s.portfolio_id),
            )
        )
    return items


async def _dca_items(user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType) -> list[ActionItem]:
    items: list[ActionItem] = []
    for sf in await find_dca_cash_shortfalls(db, cache, user_id=user_id):
        if sf.expected_krw:
            detail = f"예수금 {sf.cash_krw:,.0f}원 — 월 적립액보다 {sf.expected_krw - sf.cash_krw:,.0f}원 부족"
        else:
            detail = f"예수금 {sf.cash_krw:,.0f}원 — 매수할 예수금이 거의 없어요"
        items.append(
            ActionItem(
                id=f"dca:{sf.alert.id}",
                kind="DCA_SHORTFALL",
                # 잡 알림 창(1~3일 전)에 들어오면 급함 — 그 전에는 미리 알려두기만 한다
                priority="HIGH" if sf.days_until <= NOTICE_WINDOW_DAYS[1] else "MEDIUM",
                title=f"{sf.run_date.month}월 {sf.run_date.day}일 자동매수 전 예수금 채우기",
                detail=f"{sf.portfolio.name} · {sf.account.name} {detail}",
                cta_label="설정 보기",
                link=_portfolio_link(sf.portfolio.id, open_alert=True),
                deadline=sf.run_date.isoformat(),
            )
        )
    return items


def _tax_warning_text(summary: dict[str, Any]) -> str | None:
    """프론트 예전 홈 "주의" 배지(`useTaxLimitsSummary.warningText`)와 같은 우선순위."""
    if (summary.get("health_insurance_estimate") or {}).get("dependent_risk_warning"):
        return "건강보험 피부양자 자격 상실 위험"
    if summary.get("comprehensive_tax_warning"):
        return "금융소득 종합과세 대상 가능"
    if summary.get("domestic_large_holder_warning"):
        excess = float(summary.get("domestic_large_holder_excess_krw") or 0)
        return f"국내주식 대주주요건 주의 ({excess:,.0f}원 초과)" if excess > 0 else "국내주식 대주주요건 주의"
    return None


async def _tax_items(user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType) -> list[ActionItem]:
    plan, summary = await get_tax_action_plan_with_summary(user_id, today_kst().year, db)
    items: list[ActionItem] = []
    warning = _tax_warning_text(summary)
    if warning:
        items.append(
            ActionItem(
                id="tax-warning",
                kind="TAX_WARNING",
                priority="HIGH",
                title=warning,
                detail="올해 세금 추정 기준 — 연말 전에 확인해 두세요",
                cta_label="세금 추정 보기",
                link=_LINK_TAX_ESTIMATE,
            )
        )
    if plan["actions"]:
        top = plan["actions"][0]
        items.append(
            ActionItem(
                id=f"tax-action:{top['id']}",
                kind="TAX_ACTION",
                priority=top["priority"],
                title=top["title"],
                detail=top["detail"],
                cta_label=top["cta"]["label"],
                link=top["cta"]["link"],
                deadline=top["deadline"],
            )
        )
    return items


async def _challenge_items(user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType) -> list[ActionItem]:
    summary = await get_challenge_summary(user_id, db, cache)
    if not summary.needs_attention:
        return []
    today = today_kst()
    month_end = today.replace(day=calendar.monthrange(today.year, today.month)[1])
    return [
        ActionItem(
            id="challenge:this-month",
            kind="CHALLENGE",
            priority="MEDIUM",
            title="이번 달 적립 챌린지 입금 전",
            detail=f"아직 입금하지 않은 챌린지 {summary.count}개 — 월말 전에 입금하면 연속 기록이 이어져요",
            cta_label="챌린지 보기",
            link=_LINK_CHALLENGE,
            deadline=month_end.isoformat(),
        )
    ]


_SOURCES: list[tuple[str, Callable[[uuid.UUID, AsyncSession, CacheStoreType], Awaitable[list[ActionItem]]]]] = [
    ("rebalance", _rebalance_items),
    ("dca", _dca_items),
    ("tax", _tax_items),
    ("challenge", _challenge_items),
]


async def get_action_items(user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType = None) -> list[ActionItem]:
    collected: list[ActionItem] = []
    for name, source in _SOURCES:
        try:
            collected.extend(await source(user_id, db, cache))
        except Exception as e:
            logger.warning("action_items_source_failed", source=name, error=str(e), exc_type=type(e).__name__)
            # DB 오류로 트랜잭션이 aborted 상태면 뒤 소스 쿼리까지 전부 실패하므로 되돌려 둔다
            # (읽기 전용 요청이라 잃을 쓰기가 없고, 뒤 소스는 ORM 객체를 새로 읽는다)
            try:
                await db.rollback()
            except Exception:
                logger.warning("action_items_rollback_failed", source=name)
    # 안정 정렬 — 같은 우선순위·마감이면 소스 순서(리밸런싱 → 적립 → 세금 → 챌린지)를 유지한다
    collected.sort(key=lambda it: (_PRIORITY_ORDER[it.priority], it.deadline or "9999-12-31"))
    return collected[:MAX_ACTION_ITEMS]
