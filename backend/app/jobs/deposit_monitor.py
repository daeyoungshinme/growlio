"""예수금 입금 감지 Job — 매일 15:35, 18:05 KST 실행 (asset_sync 완료 후).

감지 로직: RebalancingAlert.deposit_trigger_enabled=TRUE 인 알림에 대해
  감시 계좌별 (current deposit_krw - last_known_deposit_krw) 양수 합산이
  deposit_trigger_min_amount_krw 이상이면
  포트폴리오 비중대로 입금 증분을 즉시 배분 매수(AUTO) 또는 알림(NOTIFY) 발송.
"""

from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.kis.auth import get_access_token
from app.kis.order import is_overseas_market, place_domestic_order, place_overseas_order
from app.models.alert import RebalancingAlert, RebalancingAlertDepositAccount
from app.models.asset import AssetAccount
from app.models.portfolio import Portfolio
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.services.alert_repository import save_alert_history
from app.services.credential_service import decrypt
from app.services.price_service import fetch_prices_batch
from app.utils.cache_keys import TTL_JOB_LOCK_DEPOSIT
from app.utils.redis_lock import redis_lock

logger = structlog.get_logger()


async def run_deposit_monitor() -> None:
    """15:35·18:05 KST — 예수금 증가 감지 후 비중 배분 매수/알림."""
    redis = await get_redis()
    async with redis_lock(redis, "deposit_monitor_lock", ttl=TTL_JOB_LOCK_DEPOSIT) as acquired:
        if not acquired:
            logger.info("deposit_monitor_skipped_lock_held")
            return
        await _run_deposit_monitor(redis)


async def _run_deposit_monitor(redis) -> None:
    from app.services.market_signal_service import get_market_signal

    try:
        market_signal = await get_market_signal(redis)
        composite_level: str = market_signal.get("composite_level", "GREEN")
    except Exception as exc:
        logger.warning("deposit_monitor_market_signal_failed", error=str(exc))
        composite_level = "GREEN"

    async with AsyncSessionLocal() as db:
        # deposit_accounts 관계가 있는 알림만 조회 (association table에 row 있는 것)
        result = await db.execute(
            select(
                RebalancingAlert,
                Portfolio,
                User.email,
                UserSettings.notification_email,
                UserSettings.fcm_token,
            )
            .join(Portfolio, Portfolio.id == RebalancingAlert.portfolio_id)
            .join(User, User.id == RebalancingAlert.user_id)
            .outerjoin(UserSettings, UserSettings.user_id == RebalancingAlert.user_id)
            .where(
                RebalancingAlert.is_active == True,  # noqa: E712
                RebalancingAlert.deposit_trigger_enabled == True,  # noqa: E712
                RebalancingAlert.id.in_(select(RebalancingAlertDepositAccount.alert_id).distinct()),
            )
        )
        rows = result.all()

    if not rows:
        return

    triggered_count = 0
    for alert, portfolio, user_email, notification_email, fcm_token in rows:
        try:
            fired = await _process_deposit_alert(
                alert,
                portfolio,
                user_email,
                notification_email,
                fcm_token,
                composite_level,
                redis,
            )
            if fired:
                triggered_count += 1
        except Exception as exc:
            logger.error(
                "deposit_monitor_alert_failed",
                alert_id=str(alert.id),
                error=str(exc),
            )

    logger.info("deposit_monitor_complete", triggered=triggered_count, checked=len(rows))


async def _process_deposit_alert(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    user_email: str,
    notification_email: str | None,
    fcm_token: str | None,
    composite_level: str,
    redis,
) -> bool:
    """단일 알림에 대한 예수금 변화 감지 및 처리. True=발동, False=스킵."""
    async with AsyncSessionLocal() as db:
        # 감시 계좌 목록 + 현재 예수금 조회
        deposit_rows_result = await db.execute(
            select(RebalancingAlertDepositAccount, AssetAccount)
            .join(AssetAccount, AssetAccount.id == RebalancingAlertDepositAccount.account_id)
            .where(
                RebalancingAlertDepositAccount.alert_id == alert.id,
                AssetAccount.is_active == True,  # noqa: E712
            )
        )
        deposit_rows = deposit_rows_result.all()

        if not deposit_rows:
            logger.warning("deposit_monitor_no_accounts", alert_id=str(alert.id))
            return False

        min_amount = int(alert.deposit_trigger_min_amount_krw or 0)
        total_increment = 0.0
        updates: list[tuple[RebalancingAlertDepositAccount, float]] = []

        for da, account in deposit_rows:
            current = float(account.deposit_krw or 0)
            last = float(da.last_known_deposit_krw or 0)
            inc = current - last
            if inc > 0:
                total_increment += inc
            updates.append((da, current))

        if total_increment < min_amount:
            for da, baseline in updates:
                fresh_da = await db.scalar(
                    select(RebalancingAlertDepositAccount).where(RebalancingAlertDepositAccount.id == da.id)
                )
                if fresh_da:
                    fresh_da.last_known_deposit_krw = baseline
            fresh_alert = await db.scalar(select(RebalancingAlert).where(RebalancingAlert.id == alert.id))
            if fresh_alert:
                fresh_alert.last_deposit_checked_at = datetime.now(UTC)
            await db.commit()
            logger.debug(
                "deposit_monitor_no_trigger",
                alert_id=str(alert.id),
                total_increment=total_increment,
                min_required=min_amount,
            )
            return False

        # 시장 신호 게이트 (AUTO 모드)
        effective_mode = alert.mode
        if effective_mode == "AUTO":
            market_mode = getattr(alert, "market_condition_mode", "DISABLED")
            blocked = (market_mode == "CAUTIOUS" and composite_level == "RED") or (
                market_mode == "STRICT" and composite_level in ("YELLOW", "RED")
            )
            if blocked:
                logger.info(
                    "deposit_monitor_auto_blocked_market_signal",
                    alert_id=str(alert.id),
                    composite_level=composite_level,
                )
                effective_mode = "NOTIFY"

        email = notification_email or user_email

        if effective_mode == "AUTO":
            await _execute_dca_by_deposit_increment(alert, portfolio, total_increment, db, redis)
        else:
            await _notify_deposit_rebalancing(alert, portfolio, total_increment, email, fcm_token, db)

        await _update_deposit_baselines(db, alert.id, updates)
        await save_alert_history(
            db,
            alert.user_id,
            "REBALANCING",
            (
                f"예수금 입금 감지: +{total_increment:,.0f}원 → "
                f"{portfolio.name} {'자동매수' if effective_mode == 'AUTO' else '알림'} "
                f"[시장신호: {composite_level}]"
            ),
        )
        await db.commit()
        logger.info(
            "deposit_monitor_triggered",
            alert_id=str(alert.id),
            total_increment=total_increment,
            mode=effective_mode,
        )
        return True


async def _update_deposit_baselines(
    db: AsyncSession,
    alert_id: uuid.UUID,
    updates: list[tuple[RebalancingAlertDepositAccount, float]],
) -> None:
    for da, baseline in updates:
        fresh_da = await db.scalar(
            select(RebalancingAlertDepositAccount).where(RebalancingAlertDepositAccount.id == da.id)
        )
        if fresh_da:
            fresh_da.last_known_deposit_krw = baseline

    fresh_alert = await db.scalar(select(RebalancingAlert).where(RebalancingAlert.id == alert_id))
    if fresh_alert:
        fresh_alert.last_deposit_checked_at = datetime.now(UTC)


async def _execute_dca_by_deposit_increment(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    deposit_increment: float,
    db: AsyncSession,
    redis,
) -> None:
    """AUTO 모드: 입금 증분을 포트폴리오 비중대로 분배하여 즉시 매수 (DCA 방식).

    실행 계좌는 alert.account_id (AUTO 모드 지정 KIS 계좌) 사용.
    """
    items = portfolio.items
    if not items:
        logger.warning("deposit_monitor_no_portfolio_items", portfolio_id=str(portfolio.id))
        return

    if not alert.account_id:
        logger.warning("deposit_monitor_no_execution_account", alert_id=str(alert.id))
        return

    account = await db.scalar(
        select(AssetAccount).where(
            AssetAccount.id == alert.account_id,
            AssetAccount.is_active == True,  # noqa: E712
        )
    )
    if not account or account.asset_type != "STOCK_KIS":
        logger.warning(
            "deposit_monitor_invalid_account",
            alert_id=str(alert.id),
            account_id=str(alert.account_id),
        )
        return
    if not account.kis_app_key or not account.kis_app_secret:
        logger.warning("deposit_monitor_missing_credentials", alert_id=str(alert.id))
        return

    app_key = decrypt(account.kis_app_key)
    app_secret = decrypt(account.kis_app_secret)
    access_token = await get_access_token(
        app_key,
        app_secret,
        is_mock=account.is_mock_mode,
        redis=redis,
        db=db,
        user_id=str(alert.user_id),
        account_id=str(account.id),
    )

    tickers = [(item.ticker, item.market) for item in items]
    price_map = await fetch_prices_batch(alert.user_id, tickers, db, redis)

    total_weight = sum(float(item.weight) for item in items)
    if total_weight <= 0:
        return

    order_type = getattr(alert, "order_type", "MARKET")

    for item in items:
        ticker = item.ticker
        market = item.market
        weight = float(item.weight) / total_weight
        alloc_amount = deposit_increment * weight

        price = price_map.get(ticker)
        if not price or price <= 0:
            logger.warning("deposit_monitor_no_price", ticker=ticker)
            continue

        qty = math.floor(alloc_amount / price)
        if qty <= 0:
            continue

        try:
            if is_overseas_market(market):
                await place_overseas_order(
                    app_key,
                    app_secret,
                    access_token,
                    account.kis_account_no,  # type: ignore[arg-type]
                    side="BUY",
                    ticker=ticker,
                    market=market,
                    quantity=qty,
                    is_mock=account.is_mock_mode,
                    order_type=order_type,
                )
            else:
                await place_domestic_order(
                    app_key,
                    app_secret,
                    access_token,
                    account.kis_account_no,  # type: ignore[arg-type]
                    side="BUY",
                    ticker=ticker,
                    quantity=qty,
                    is_mock=account.is_mock_mode,
                    order_type=order_type,
                )
            logger.info(
                "deposit_monitor_order_placed",
                ticker=ticker,
                qty=qty,
                price=price,
                alloc=alloc_amount,
                is_mock=account.is_mock_mode,
            )
        except Exception as exc:
            logger.error("deposit_monitor_order_failed", ticker=ticker, error=str(exc))


async def _notify_deposit_rebalancing(
    alert: RebalancingAlert,
    portfolio: Portfolio,
    deposit_increment: float,
    email: str,
    fcm_token: str | None,
    db: AsyncSession,
) -> None:
    """NOTIFY 모드: 드리프트 분석 기반 매수 추천 이메일 + FCM 푸시 발송.

    단순 비중 배분 대신 현재 포트폴리오 상태를 분석하여
    부족한(underweight) 종목부터 예수금 입금액을 배분한다.
    """
    from app.services.email_service import send_deposit_trigger_alert
    from app.services.portfolio_service import build_portfolio_overview
    from app.services.push_service import send_push_to_user
    from app.services.rebalancing_service import analyze_rebalancing

    notify_items: list[dict] = []

    try:
        saved_ids = getattr(portfolio, "account_ids", None)
        account_ids = [uuid.UUID(aid) for aid in saved_ids] if saved_ids else None
        overview = await build_portfolio_overview(alert.user_id, db, account_ids=account_ids)
        analysis = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)

        # 부족한(underweight) 종목만 추출: diff_krw < 0이면 현재 < 목표 (매수 필요)
        # CASH는 매수 대상에서 제외
        underweight = [
            i for i in analysis.items if i.diff_krw < 0 and i.ticker != "CASH" and i.shares_to_trade is not None
        ]

        if underweight:
            total_deficit = sum(abs(i.diff_krw) for i in underweight)
            for item in underweight:
                alloc_ratio = abs(item.diff_krw) / total_deficit if total_deficit > 0 else 0
                alloc_amount = deposit_increment * alloc_ratio
                notify_items.append(
                    {
                        "ticker": item.ticker,
                        "name": item.name,
                        "weight_pct": float(item.target_weight_pct),
                        "alloc_amount": alloc_amount,
                        "weight_diff_pct": float(item.weight_diff_pct),
                    }
                )
    except Exception as exc:
        logger.warning(
            "deposit_notify_analysis_failed_fallback_to_proportional",
            alert_id=str(alert.id),
            error=str(exc),
        )

    # 분석 실패 또는 underweight 종목 없을 경우 기존 비중 비례 배분으로 폴백
    if not notify_items:
        p_items = portfolio.items
        total_weight = sum(float(pi.weight) for pi in p_items) if p_items else 0
        for pi in p_items:
            w = float(pi.weight) / total_weight if total_weight > 0 else 0
            notify_items.append(
                {
                    "ticker": pi.ticker,
                    "name": pi.name,
                    "weight_pct": float(pi.weight),
                    "alloc_amount": deposit_increment * w,
                }
            )

    await send_deposit_trigger_alert(
        to_email=email,
        portfolio_name=portfolio.name,
        deposit_increment=deposit_increment,
        items=notify_items,
    )

    push_body = f"+{deposit_increment:,.0f}원 입금 감지 → {portfolio.name} 비중 매수 추천"
    await send_push_to_user(
        user_id=alert.user_id,
        title="예수금 입금 감지",
        body=push_body,
        fcm_token=fcm_token,
    )
