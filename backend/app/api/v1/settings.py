"""사용자 설정 및 증권사 자격증명 관리 API."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.constants import (
    DEFAULT_GOAL_CAGR_LOOKBACK_YEARS,
    DEFAULT_GOAL_MAX_WEIGHT_PCT,
    DEFAULT_GOAL_SHORT_TERM_EQUITY_FLOOR_PCT,
)
from app.core.cache_store import get_cache_store
from app.core.config import settings
from app.enums import AgeGroup, GoalRiskTolerance, IncomeBracket
from app.limiter import limiter
from app.models.user import User, UserSettings
from app.schemas.rebalancing.goal import GoalCandidateTicker
from app.schemas.settings import (
    AutoRebalancingDailyCapUpdate,
    DartApiKeyUpdate,
    GoalCandidateTickersUpdate,
    GoalRecommendationOptionsUpdate,
    GoalUpdate,
    IncomeBracketUpdate,
    NotificationEmailUpdate,
    PushTokenUpdate,
    SettingsResponse,
    ToggleUpdate,
)
from app.services._settings_queries import get_or_create_settings, get_settings_row, has_active_kis_credentials
from app.services.accounts.credential_service import encrypt
from app.services.goal.goal_age_recommendation_service import age_group_from_birth_year
from app.utils.cache_keys import (
    challenge_progress_key,
    dashboard_summary_key,
    dca_analysis_key,
    invalidate_goal_recommendation_caches,
    invalidate_rebalancing_analysis_cache_all,
    invalidate_user_caches,
)
from app.utils.numbers import opt_float

router = APIRouter(prefix="/settings", tags=["settings"])


_GOAL_PLAIN_FIELDS = (
    "goal_amount",
    "goal_annual_return_pct",
    "annual_deposit_goal",
    "monthly_deposit_amount",
    "retirement_target_year",
    "goal_initial_amount",
    "annual_dividend_goal",
)


@router.get("", response_model=SettingsResponse)
@limiter.limit("30/minute")
async def get_settings(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 설정 조회 (자격증명 원문은 반환하지 않음)."""
    row = await get_settings_row(db, current_user.id)
    has_kis = await has_active_kis_credentials(db, current_user.id)

    if not row:
        return SettingsResponse(
            has_kis=has_kis,
            has_dart=False,
            goal_amount=None,
            goal_annual_return_pct=None,
            annual_deposit_goal=None,
            user_email=current_user.email,
            notification_email=None,
            auto_rebalancing_max_order_value_krw=settings.auto_rebalancing_max_order_value_krw,
        )
    return SettingsResponse(
        has_kis=has_kis,
        has_dart=bool(row.dart_api_key),
        goal_amount=opt_float(row.goal_amount),
        goal_annual_return_pct=opt_float(row.goal_annual_return_pct),
        annual_deposit_goal=opt_float(row.annual_deposit_goal),
        monthly_deposit_amount=opt_float(row.monthly_deposit_amount),
        retirement_target_year=row.retirement_target_year,
        user_email=current_user.email,
        notification_email=row.notification_email,
        annual_dividend_goal=opt_float(row.annual_dividend_goal),
        fcm_token_stored=bool(row.fcm_token),
        composite_signal_alerts_enabled=row.composite_signal_alerts_enabled,
        market_signal_daily_digest_enabled=row.market_signal_daily_digest_enabled,
        year_end_tax_reminder_enabled=row.year_end_tax_reminder_enabled,
        goal_achievement_alerts_enabled=row.goal_achievement_alerts_enabled,
        monthly_report_enabled=row.monthly_report_enabled,
        recommendation_drift_alert_enabled=row.recommendation_drift_alert_enabled,
        challenge_reminders_enabled=row.challenge_reminders_enabled,
        goal_candidate_tickers=[GoalCandidateTicker(**t) for t in (row.goal_candidate_tickers or [])],
        goal_risk_tolerance=(
            GoalRiskTolerance(row.goal_risk_tolerance) if row.goal_risk_tolerance else GoalRiskTolerance.CONSERVATIVE
        ),
        goal_max_weight_pct=float(row.goal_max_weight_pct or DEFAULT_GOAL_MAX_WEIGHT_PCT),
        goal_cagr_lookback_years=row.goal_cagr_lookback_years or DEFAULT_GOAL_CAGR_LOOKBACK_YEARS,
        goal_short_term_equity_floor_pct=float(
            row.goal_short_term_equity_floor_pct or DEFAULT_GOAL_SHORT_TERM_EQUITY_FLOOR_PCT
        ),
        goal_bond_ceiling_pct=opt_float(row.goal_bond_ceiling_pct),
        goal_cash_ceiling_pct=opt_float(row.goal_cash_ceiling_pct),
        age_group=AgeGroup(row.age_group) if row.age_group else None,
        birth_year=row.birth_year,
        income_bracket=IncomeBracket(row.income_bracket) if row.income_bracket else None,
        auto_rebalancing_max_order_value_krw=settings.auto_rebalancing_max_order_value_krw,
        auto_rebalancing_daily_value_cap_krw=opt_float(row.auto_rebalancing_daily_value_cap_krw),
    )


@router.put("/dart")
@limiter.limit("10/minute")
async def update_dart_api_key(
    request: Request,
    req: DartApiKeyUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """DART OpenAPI 키 저장."""
    row = await get_or_create_settings(db, current_user.id)
    row.dart_api_key = encrypt(req.api_key)
    await db.commit()
    return {"detail": "DART API 키가 저장되었습니다"}


@router.delete("/dart")
@limiter.limit("10/minute")
async def delete_dart_api_key(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await get_settings_row(db, current_user.id)
    if row:
        row.dart_api_key = None
        await db.commit()
    return {"detail": "DART API 키가 삭제되었습니다"}


@router.put("/goal")
@limiter.limit("20/minute")
async def update_goal(
    request: Request,
    req: GoalUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """투자 목표 설정."""
    row = await get_or_create_settings(db, current_user.id)
    # 보낸 필드만 바꾼다 — 생략한 필드는 유지하고, 명시적으로 null을 보낸 필드는 비운다
    # (`is not None`으로만 거르면 사용자가 입력을 지워도 이전 목표가 남는다).
    sent = req.model_fields_set
    for field in _GOAL_PLAIN_FIELDS:
        if field in sent:
            setattr(row, field, getattr(req, field))
    if "goal_start_date" in sent:
        row.goal_start_date = (
            datetime.combine(req.goal_start_date, datetime.min.time()).replace(tzinfo=UTC)
            if req.goal_start_date is not None
            else None
        )
    if "birth_year" in sent:
        row.birth_year = req.birth_year
        # age_group은 추천 옵션에서 직접 고를 수도 있으므로, 출생연도를 지울 때는 건드리지 않는다
        if req.birth_year is not None:
            row.age_group = age_group_from_birth_year(req.birth_year).value
    await db.commit()
    cache = await get_cache_store()
    await invalidate_user_caches(
        cache,
        dashboard_summary_key(current_user.id),
        dca_analysis_key(current_user.id),
        challenge_progress_key(current_user.id),
    )
    await invalidate_goal_recommendation_caches(cache, current_user.id)
    return {"detail": "목표가 저장되었습니다"}


@router.put("/goal-candidate-tickers")
@limiter.limit("20/minute")
async def update_goal_candidate_tickers(
    request: Request,
    req: GoalCandidateTickersUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """목표 역산 추천에 사용할 사용자 등록 후보 ETF 목록 저장(전체 교체)."""
    row = await get_or_create_settings(db, current_user.id)
    row.goal_candidate_tickers = [t.model_dump() for t in req.tickers]
    await db.commit()
    cache = await get_cache_store()
    await invalidate_goal_recommendation_caches(cache, current_user.id)
    return {"detail": "후보 ETF 목록이 저장되었습니다"}


@router.put("/goal-recommendation-options")
@limiter.limit("20/minute")
async def update_goal_recommendation_options(
    request: Request,
    req: GoalRecommendationOptionsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """목표 역산 추천 엔진의 리스크 성향/종목당 최대비중/CAGR 산출기간 설정(전체 교체)."""
    row = await get_or_create_settings(db, current_user.id)
    row.goal_risk_tolerance = req.risk_tolerance.value
    row.goal_max_weight_pct = req.max_weight_pct
    row.goal_cagr_lookback_years = req.cagr_lookback_years
    row.goal_short_term_equity_floor_pct = req.short_term_equity_floor_pct
    row.goal_bond_ceiling_pct = req.bond_ceiling_pct
    row.goal_cash_ceiling_pct = req.cash_ceiling_pct
    row.age_group = req.age_group.value if req.age_group else None
    await db.commit()
    cache = await get_cache_store()
    await invalidate_goal_recommendation_caches(cache, current_user.id)
    return {"detail": "목표 역산 추천 설정이 저장되었습니다"}


@router.put("/notification-email")
@limiter.limit("10/minute")
async def update_notification_email(
    request: Request,
    req: NotificationEmailUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """알림 수신 이메일 설정. 비워두면 로그인 이메일로 발송됩니다."""
    row = await get_or_create_settings(db, current_user.id)
    row.notification_email = req.notification_email or None
    await db.commit()
    return {"detail": "알림 이메일이 저장되었습니다"}


@router.put("/income-bracket")
@limiter.limit("10/minute")
async def update_income_bracket(
    request: Request,
    req: IncomeBracketUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """연금 세액공제율(16.5%/13.2%) 분기용 소득 구간 저장 — 총급여 금액 자체는 받지 않는다."""
    row = await get_or_create_settings(db, current_user.id)
    row.income_bracket = req.income_bracket.value if req.income_bracket else None
    await db.commit()
    return {"detail": "소득 구간이 저장되었습니다"}


@router.put("/auto-rebalancing-daily-cap")
@limiter.limit("10/minute")
async def update_auto_rebalancing_daily_cap(
    request: Request,
    req: AutoRebalancingDailyCapUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AUTO 리밸런싱 유저 단위 하루 합산 거래대금 상한 설정. None(미지정)이면 무제한(기본값)."""
    row = await get_or_create_settings(db, current_user.id)
    row.auto_rebalancing_daily_value_cap_krw = req.daily_value_cap_krw
    await db.commit()
    return {"detail": "하루 합산 거래한도 설정이 저장되었습니다"}


# 계정 단위 on/off 알림 설정 — 경로마다 컬럼 하나를 그대로 저장한다. URL·응답은 기존과 같다(설치된 APK가 호출).
# (경로, UserSettings 컬럼, 응답 문구, 설명, 저장 후 리밸런싱 분석 캐시 무효화 여부)
_TOGGLE_SETTINGS: tuple[tuple[str, str, str, str, bool], ...] = (
    (
        "composite-signal-alerts",
        "composite_signal_alerts_enabled",
        "복합신호 알림 설정이 저장되었습니다",
        "시장/리스크 복합신호 알림(이메일·푸시) 수신 여부 — 신호가 유저 단위이므로 계정 단일 설정.",
        # 진단 결과(diagnosis_context)가 이 설정으로 계산돼 캐시되므로 함께 비운다
        True,
    ),
    (
        "market-signal-digest",
        "market_signal_daily_digest_enabled",
        "시장신호 매일 요약 설정이 저장되었습니다",
        "시장신호 매일 요약(08:30 KST) 수신 여부 — 등급 전환 시 즉시 알림과 별개의 옵트인 설정.",
        False,
    ),
    (
        "year-end-tax-reminder",
        "year_end_tax_reminder_enabled",
        "연말 절세 리마인더 설정이 저장되었습니다",
        "11~12월 매주 월요일 발송되는 연말 절세 리마인더 수신 여부.",
        False,
    ),
    (
        "goal-achievement-alerts",
        "goal_achievement_alerts_enabled",
        "목표 달성 알림 설정이 저장되었습니다",
        "자산/입금/배당 목표 달성 알림(이메일·푸시) 수신 여부.",
        False,
    ),
    (
        "monthly-report-alerts",
        "monthly_report_enabled",
        "월간 리포트 설정이 저장되었습니다",
        "매월 1일 발송되는 월간 포트폴리오 리포트 수신 여부.",
        False,
    ),
    (
        "recommendation-drift-alert",
        "recommendation_drift_alert_enabled",
        "추천 비중 변화 알림 설정이 저장되었습니다",
        "매주 월요일 09:15 KST — 목표 역산 추천 비중이 타겟 포트폴리오의 현재 목표 비중과 유의미하게 달라지면 "
        "이메일/푸시로 알리는 기능의 수신 여부.",
        False,
    ),
    (
        "challenge-reminders",
        "challenge_reminders_enabled",
        "적립 챌린지 알림 설정이 저장되었습니다",
        "적립 챌린지 독려(매월 25일)·월간 결산(매월 1일) 알림 수신 여부 — 옵트인(기본 OFF).",
        False,
    ),
)


def _register_toggle(path: str, column: str, detail: str, description: str, invalidate_analysis: bool) -> None:
    async def update_toggle(
        request: Request,
        req: ToggleUpdate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        row = await get_or_create_settings(db, current_user.id)
        setattr(row, column, req.enabled)
        await db.commit()
        if invalidate_analysis:
            await invalidate_rebalancing_analysis_cache_all(await get_cache_store(), current_user.id)
        return {"detail": detail}

    name = f"update_{column}"
    update_toggle.__name__ = name
    router.put(f"/{path}", name=name, description=description)(limiter.limit("10/minute")(update_toggle))


for _toggle in _TOGGLE_SETTINGS:
    _register_toggle(*_toggle)


@router.put("/push-token")
@limiter.limit("10/minute")
async def update_push_token(
    request: Request,
    req: PushTokenUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """FCM 푸시 알림 토큰 등록/삭제. fcm_token=null 전달 시 토큰 삭제."""
    if req.fcm_token:
        # FCM 토큰은 기기 단위다. 공유 기기에서 A가 로그아웃(토큰 미삭제)하고 B가 로그인하면 두 사용자가
        # 같은 토큰을 갖게 되어 A의 포트폴리오·목표 알림이 B 기기로 간다 — 다른 사용자 row에서 먼저 뗀다(plans/61 A4).
        await db.execute(
            update(UserSettings)
            .where(UserSettings.fcm_token == req.fcm_token, UserSettings.user_id != current_user.id)
            .values(fcm_token=None)
        )
    row = await get_or_create_settings(db, current_user.id)
    row.fcm_token = req.fcm_token or None
    await db.commit()
    msg = "푸시 알림 토큰이 저장되었습니다" if req.fcm_token else "푸시 알림 토큰이 삭제되었습니다"
    return {"detail": msg}


@router.post("/test-email")
@limiter.limit("3/minute")
async def send_test_email_endpoint(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """알림 이메일 설정 확인용 테스트 이메일 발송."""
    from app.services.notifications.email_service import send_test_email

    row = await get_settings_row(db, current_user.id)
    to_email = (row.notification_email if row else None) or current_user.email

    try:
        sent = await send_test_email(to_email)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="SMTP가 설정되지 않았습니다. 서버 관리자에게 문의하세요",
        ) from e

    if not sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="이메일 발송에 실패했습니다",
        )

    return {"detail": f"{to_email}으로 테스트 이메일을 발송했습니다."}
