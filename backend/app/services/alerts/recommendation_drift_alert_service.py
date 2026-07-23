"""추천 비중 변화 자동 알림 — 매주 월요일 09:15 KST, 옵트인(기본 OFF) 유저에게

목표 역산 추천 비중(전체 자산 기준 + 투자기간별)이 타겟 포트폴리오의 현재 목표 비중과 유의미하게
(3%p 이상 또는 신규 후보 존재) 달라진 경우 이메일/푸시로 안내한다. 화면을 열어야만 보이는
`RecommendationCard.tsx`의 "추천이 달라졌어요" 배지(Phase A)를 주기적으로 알려주는 Phase B —
`docs/plans/03-recommendation-diagnosis-linkage.md` 참고.

`goal_recommendation_service.compute_recommendation_drift()`가 프론트
`frontend/src/utils/recommendationDrift.ts`의 `computeRecommendationDrift()`와 동일한 로직이다.

타겟 포트폴리오 판별은 프론트 `utils/portfolio.ts`의 `getPortfolioTargetState`/`getPortfolioHorizonTaxType`을
단순화한 backend 버전 — 계좌 태그 추론 폴백은 생략(opt-in 주간 요약이라 엣지케이스 허용 가능).

`tax_reminder_service.py`(연말 절세 리마인더)와 동일한 유저별 AsyncSessionLocal + DB(AlertHistory)
기반 dedup(당일 발송 여부 — 주 1회 실행이라 이게 곧 주간 dedup) + 세마포어 패턴을 따른다.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, date, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.alert import AlertHistory
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.services._account_queries import active_accounts_stmt
from app.services._portfolio_queries import get_linked_portfolios
from app.services.alerts.alert_service import save_alert_history
from app.services.goal_candidate_service import existing_items_from_positions
from app.services.goal_recommendation_service import (
    _RECOMMENDATION_DRIFT_THRESHOLD_PCT,
    compute_recommendation_drift,
    get_goal_recommendation,
    get_horizon_recommendations,
)
from app.services.portfolio_service import build_portfolio_overview
from app.services.position_aggregator import query_latest_position_map
from app.utils.cache_keys import CacheStoreType

logger = structlog.get_logger()

_ALERT_CONCURRENCY = 5
_STOCK_ASSET_TYPES = ("STOCK_KIS", "STOCK_KIWOOM", "STOCK_OTHER")


async def _get_subscribers(db: AsyncSession) -> list[tuple[User, UserSettings]]:
    """recommendation_drift_alert_enabled가 True인 활성 유저 목록. 기본값이 OFF이므로 inner join으로 충분."""
    result = await db.execute(
        select(User, UserSettings)
        .join(UserSettings, UserSettings.user_id == User.id)
        .where(
            User.is_active == True,  # noqa: E712
            UserSettings.recommendation_drift_alert_enabled == True,  # noqa: E712
        )
    )
    return [(user, user_settings) for user, user_settings in result.all()]


async def _already_sent_this_week(db: AsyncSession, user_id: uuid.UUID) -> bool:
    """오늘(=이번 주, 주 1회 실행) 이미 발송했으면 True — 스케줄러 재시작/misfire로 인한 중복 발송 방지."""
    today = date.today()
    day_start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    result = await db.execute(
        select(AlertHistory.id)
        .where(
            AlertHistory.user_id == user_id,
            AlertHistory.alert_type == "RECOMMENDATION_DRIFT",
            AlertHistory.created_at >= day_start,
        )
        .limit(1)
    )
    return result.scalar() is not None


def _is_full_target(portfolio: Portfolio, stock_accounts: list[AssetAccount]) -> bool:
    """포트폴리오에 연결된(또는 미연결 시 전체) 주식 계좌 전부가 이 포트폴리오를 목표로 지정했는지."""
    linked_ids = set(portfolio.account_ids) if portfolio.account_ids else {str(a.id) for a in stock_accounts}
    relevant = [a for a in stock_accounts if str(a.id) in linked_ids]
    if not relevant:
        return False
    return all(a.target_portfolio_id == portfolio.id for a in relevant)


async def _find_drifted_portfolios(
    user_id: uuid.UUID, db: AsyncSession, cache: CacheStoreType, settings_row: UserSettings
) -> list[str]:
    """추천이 유의미하게 달라진 타겟 포트폴리오의 이름 목록을 반환한다."""
    portfolios = await get_linked_portfolios(db, user_id)
    if not portfolios:
        return []

    stock_accounts_result = await db.execute(
        active_accounts_stmt(user_id).where(AssetAccount.asset_type.in_(_STOCK_ASSET_TYPES))
    )
    stock_accounts = list(stock_accounts_result.scalars().all())

    drifted_names: list[str] = []

    def _is_significant(max_delta_pct: float, new_candidate_count: int) -> bool:
        return max_delta_pct >= _RECOMMENDATION_DRIFT_THRESHOLD_PCT or new_candidate_count > 0

    # 전체(overall) 경로 — /rebalancing?rtab=포트폴리오의 "전체" 탭과 동일한 입력 구성
    overview = await build_portfolio_overview(user_id, db, cache=cache)
    real_estate_krw = next(
        (item["amount_krw"] for item in overview.get("asset_type_allocation", []) if item.get("type") == "REAL_ESTATE"),
        0.0,
    )
    base_krw = float(overview.get("total_assets_krw", 0)) - real_estate_krw
    pos_map = await query_latest_position_map(user_id, db, include_name=True)
    existing_items = existing_items_from_positions(pos_map)
    overall_rec = await get_goal_recommendation(cache, base_krw, existing_items, settings_row, db)
    if overall_rec.recommended_items:
        overall_target = next((p for p in portfolios if _is_full_target(p, stock_accounts)), None)
        if overall_target is not None:
            current_items = [(i.ticker, i.market, float(i.weight)) for i in overall_target.items]
            recommended_items = [(i.ticker, i.market, i.weight) for i in overall_rec.recommended_items]
            max_delta_pct, new_candidate_count = compute_recommendation_drift(recommended_items, current_items)
            if _is_significant(max_delta_pct, new_candidate_count):
                drifted_names.append(overall_target.name)

    # 기간별 경로 — 명시적으로 investment_horizon+tax_type이 지정된 포트폴리오만 대상(계좌 태그
    # 추론 폴백은 생략). 현금성 자산(CMA·파킹통장) 합성 후보만 있는 추천은 실제 매수 대상이 아니라
    # 화면에서도 "적용" 버튼이 숨겨지므로 여기서도 건너뛴다.
    horizon_resp = await get_horizon_recommendations(cache, db, user_id, settings_row)
    for rec in horizon_resp.recommendations:
        if not rec.recommended_items or rec.includes_cash_equivalent:
            continue
        target = next(
            (p for p in portfolios if p.investment_horizon == rec.investment_horizon and p.tax_type == rec.tax_type),
            None,
        )
        if target is None:
            continue
        current_items = [(i.ticker, i.market, float(i.weight)) for i in target.items]
        recommended_items = [(i.ticker, i.market, i.weight) for i in rec.recommended_items]
        max_delta_pct, new_candidate_count = compute_recommendation_drift(recommended_items, current_items)
        if _is_significant(max_delta_pct, new_candidate_count) and target.name not in drifted_names:
            drifted_names.append(target.name)

    return drifted_names


async def _send_alert_to_user(user: User, user_settings: UserSettings, sem: asyncio.Semaphore) -> None:
    from app.core.cache_store import get_cache_store
    from app.services.email_service import send_recommendation_drift_alert_email
    from app.services.push_service import send_push_to_user

    async with sem:
        try:
            async with AsyncSessionLocal() as db:
                if await _already_sent_this_week(db, user.id):
                    return

                cache = await get_cache_store()
                drifted_names = await _find_drifted_portfolios(user.id, db, cache, user_settings)
                if not drifted_names:
                    return

                to_email = user_settings.notification_email or user.email

                email_sent = False
                try:
                    email_sent = await send_recommendation_drift_alert_email(to_email, drifted_names)
                except Exception as exc:
                    logger.error("recommendation_drift_alert_email_failed", user_id=str(user.id), error=str(exc))

                push_sent = False
                try:
                    push_sent = await send_push_to_user(
                        user_id=user.id,
                        title="추천 비중이 달라졌어요",
                        body=f"{', '.join(drifted_names)} 포트폴리오의 추천 비중을 확인해보세요.",
                        fcm_token=user_settings.fcm_token,
                        data={"type": "RECOMMENDATION_DRIFT"},
                    )
                except Exception as exc:
                    logger.error("recommendation_drift_alert_push_failed", user_id=str(user.id), error=str(exc))

                if email_sent or push_sent:
                    await save_alert_history(
                        db, user.id, "RECOMMENDATION_DRIFT", f"추천 비중 변화 알림 발송 ({', '.join(drifted_names)})"
                    )
                    await db.commit()
        except Exception as exc:
            logger.error("recommendation_drift_alert_user_failed", user_id=str(user.id), error=str(exc))


async def send_recommendation_drift_alerts(db: AsyncSession) -> None:
    """매주 월요일 09:15 KST — 옵트인 유저 중 추천 비중이 유의미하게 달라진 유저에게 안내 발송."""
    subscribers = await _get_subscribers(db)
    sem = asyncio.Semaphore(_ALERT_CONCURRENCY)
    await asyncio.gather(*(_send_alert_to_user(user, user_settings, sem) for user, user_settings in subscribers))
    logger.info("recommendation_drift_alert_completed", subscriber_count=len(subscribers))
