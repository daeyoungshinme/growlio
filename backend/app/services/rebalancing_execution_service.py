"""리밸런싱 실행 서비스 — KIS/키움 API를 통해 매수/매도 주문을 일괄 실행한다."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.kis.auth import get_access_token
from app.kis.balance import get_orderable_cash
from app.kis.order import is_overseas_market, place_domestic_order, place_overseas_order
from app.models.asset import AssetAccount, RebalancingExecution, RebalancingExecutionResult
from app.schemas.rebalancing import ExecutionOrderItem, ExecutionResult, OrderResult
from app.services._account_queries import active_accounts_stmt
from app.services.credential_service import decrypt
from app.utils.metrics import rebalancing_execution_count

logger = structlog.get_logger()

_BROKER_ASSET_TYPES = {"STOCK_KIS", "STOCK_KIWOOM"}


async def _load_account(
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> AssetAccount:
    account = await db.scalar(active_accounts_stmt(user_id).where(AssetAccount.id == account_id))
    if not account:
        raise HTTPException(status_code=404, detail=f"계좌를 찾을 수 없습니다. (id={account_id})")
    if account.asset_type not in _BROKER_ASSET_TYPES:
        raise HTTPException(status_code=400, detail="KIS 또는 키움 계좌만 실행 주문이 가능합니다.")
    if account.asset_type == "STOCK_KIS" and not account.kis_account_no:
        raise HTTPException(status_code=400, detail="KIS 계좌번호가 설정되지 않았습니다.")
    if account.asset_type == "STOCK_KIWOOM" and not account.kiwoom_account_no:
        raise HTTPException(status_code=400, detail="키움 계좌번호가 설정되지 않았습니다.")
    return account


async def _load_credentials(account: AssetAccount) -> tuple[str, str]:
    """KIS 계좌 자격증명 로드. 미설정 시 400 에러."""
    if account.kis_app_key and account.kis_app_secret:
        return decrypt(account.kis_app_key), decrypt(account.kis_app_secret)
    raise HTTPException(
        status_code=400,
        detail="KIS 자격증명이 설정되지 않았습니다. 계좌 설정에서 App Key와 App Secret을 입력해주세요.",
    )


async def _load_kiwoom_credentials(account: AssetAccount) -> tuple[str, str]:
    """키움 계좌 자격증명 로드 (전역 폴백 없음)."""
    if account.kiwoom_app_key and account.kiwoom_app_secret:
        return decrypt(account.kiwoom_app_key), decrypt(account.kiwoom_app_secret)
    raise HTTPException(status_code=400, detail="키움 자격증명이 설정되지 않았습니다.")


async def execute_rebalancing(
    user_id: uuid.UUID,
    account_id: uuid.UUID | None,
    orders: list[ExecutionOrderItem],
    db: AsyncSession,
    redis,
    portfolio_id: uuid.UUID | None = None,
    triggered_by: str = "MANUAL",
    strategy: str = "FULL",
) -> list[ExecutionResult]:
    """선택된 리밸런싱 주문 항목을 KIS API를 통해 순차 실행한다.

    주문별 account_id로 계좌를 그룹화해 각 계좌별 독립 실행한다.
    account_id가 없는 주문은 인자로 전달된 account_id(기본 계좌)를 사용한다.
    매도 주문을 먼저 처리해 현금을 확보한 뒤 매수 주문을 실행한다.
    개별 주문 실패 시 나머지 주문은 계속 진행된다.
    계좌별 ExecutionResult 목록을 반환하고 실행 이력을 DB에 저장한다.
    """
    # 주문을 account_id별로 그룹화
    groups: dict[str, list[ExecutionOrderItem]] = defaultdict(list)
    for order in orders:
        target_acc_id = order.account_id or (str(account_id) if account_id else None)
        if not target_acc_id:
            raise HTTPException(
                status_code=400,
                detail=f"주문 계좌가 지정되지 않았습니다. (ticker={order.ticker})",
            )
        groups[target_acc_id].append(order)

    if not groups:
        raise HTTPException(status_code=400, detail="실행할 주문이 없습니다.")

    results: list[ExecutionResult] = []

    for acc_id_str, group_orders in groups.items():
        acc_uuid = uuid.UUID(acc_id_str)
        account = await _load_account(acc_uuid, user_id, db)
        is_mock = account.is_mock_mode

        if account.asset_type == "STOCK_KIWOOM":
            from app.kiwoom.auth import get_access_token as kiwoom_get_access_token
            from app.kiwoom.order import place_domestic_order as kiwoom_place_order

            app_key, app_secret = await _load_kiwoom_credentials(account)
            account_no = account.kiwoom_account_no
            access_token = await kiwoom_get_access_token(
                app_key,
                app_secret,
                is_mock=is_mock,
                redis=redis,
                db=db,
                user_id=str(user_id),
                account_id=str(acc_uuid),
            )

            sells = [o for o in group_orders if o.side == "SELL"]
            buys = [o for o in group_orders if o.side == "BUY"]

            account_results: list[OrderResult] = []
            for order in sells + buys:
                account_results.append(
                    await _execute_kiwoom_single_order(
                        order,
                        access_token,
                        account_no,  # type: ignore[arg-type]
                        is_mock,
                        kiwoom_place_order,
                    )
                )
        else:
            # KIS 계좌
            app_key, app_secret = await _load_credentials(account)
            account_no = account.kis_account_no

            access_token = await get_access_token(
                app_key,
                app_secret,
                is_mock=is_mock,
                redis=redis,
                db=db,
                user_id=str(user_id),
                account_id=str(acc_uuid),
            )

            if strategy == "TWO_PHASE":
                account_results = await _execute_two_phase_orders(
                    group_orders,
                    app_key,
                    app_secret,
                    access_token,
                    account_no,  # type: ignore[arg-type]
                    is_mock,
                )
            else:
                sells = [o for o in group_orders if o.side == "SELL"]
                buys = [o for o in group_orders if o.side == "BUY"]

                account_results = []
                for order in sells + buys:
                    account_results.append(
                        await _execute_single_order(
                            order,
                            app_key,
                            app_secret,
                            access_token,
                            account_no,  # type: ignore[arg-type]
                            is_mock,
                        )
                    )

        success_count = sum(1 for r in account_results if r.status == "SUCCESS")
        fail_count = sum(1 for r in account_results if r.status == "FAILED")

        logger.info(
            "rebalancing_group_executed",
            user_id=str(user_id),
            account_id=acc_id_str,
            is_mock=is_mock,
            orders=len(group_orders),
            success=success_count,
            failed=fail_count,
        )

        results.append(
            ExecutionResult(
                account_id=str(account.id),
                account_name=account.name,
                is_mock=is_mock,
                orders=account_results,
                success_count=success_count,
                fail_count=fail_count,
                executed_at=datetime.now(UTC).isoformat(),
            )
        )

    total_success = sum(r.success_count for r in results)
    total_fail = sum(r.fail_count for r in results)
    total_skipped = sum(sum(1 for o in r.orders if o.status == "SKIPPED") for r in results)
    logger.info(
        "rebalancing_executed",
        user_id=str(user_id),
        account_groups=len(groups),
        success=total_success,
        failed=total_fail,
        skipped=total_skipped,
    )

    # 실행 이력 저장
    try:
        execution = RebalancingExecution(
            user_id=user_id,
            portfolio_id=portfolio_id,
            triggered_by=triggered_by,
            strategy=strategy,
            total_success=total_success,
            total_fail=total_fail,
            total_skipped=total_skipped,
        )
        db.add(execution)
        await db.flush()  # execution.id 생성

        for exec_result in results:
            for placed in exec_result.orders:
                db.add(
                    RebalancingExecutionResult(
                        execution_id=execution.id,
                        account_id=exec_result.account_id,
                        account_name=exec_result.account_name,
                        is_mock=exec_result.is_mock,
                        action=placed.side,
                        ticker=placed.ticker,
                        name=placed.name,
                        market=placed.market,
                        quantity=placed.quantity,
                        status=placed.status,
                        order_no=placed.order_no,
                        error_message=placed.error_msg,
                        order_type=placed.order_type,
                    )
                )

        await db.commit()
    except Exception as e:
        logger.warning("rebalancing_history_save_failed", user_id=str(user_id), error=str(e))

    # 실행 후 전략 캐시 무효화 (포트폴리오 구성이 변경되었으므로)
    if portfolio_id and redis:
        import contextlib

        with contextlib.suppress(Exception):
            await redis.delete(f"rebalancing_strategy:{user_id}:{portfolio_id}")

    rebalancing_execution_count.labels(status="success" if total_fail == 0 else "partial").inc()
    return results


async def _execute_kiwoom_single_order(
    order: ExecutionOrderItem,
    access_token: str,
    account_no: str,
    is_mock: bool,
    place_order_fn,
) -> OrderResult:
    """키움 단건 주문 실행 — 국내주식만 지원 (해외주식 미지원)."""
    if order.quantity <= 0:
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="SKIPPED",
            error_msg="주문 수량이 0 이하입니다.",
        )
    if is_overseas_market(order.market):
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="SKIPPED",
            error_msg="키움 연동은 국내주식만 지원합니다.",
        )

    try:
        result = await place_order_fn(
            access_token,
            account_no,
            side=order.side,
            ticker=order.ticker,
            quantity=order.quantity,
            is_mock=is_mock,
            order_type=order.order_type,
            limit_price=order.limit_price,
        )
        logger.info(
            "kiwoom_order_placed",
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            order_no=result.get("order_no"),
            is_mock=is_mock,
            order_type=order.order_type,
        )
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="SUCCESS",
            order_no=result.get("order_no"),
            order_type=order.order_type,
        )
    except Exception as e:
        logger.warning("kiwoom_order_failed", ticker=order.ticker, side=order.side, error=str(e))
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="FAILED",
            error_msg=str(e),
            order_type=order.order_type,
        )


async def _execute_single_order(
    order: ExecutionOrderItem,
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> OrderResult:
    if order.quantity <= 0:
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="SKIPPED",
            error_msg="주문 수량이 0 이하입니다.",
        )

    try:
        if is_overseas_market(order.market):
            result = await place_overseas_order(
                app_key,
                app_secret,
                access_token,
                account_no,
                side=order.side,
                ticker=order.ticker,
                market=order.market,
                quantity=order.quantity,
                is_mock=is_mock,
                order_type=order.order_type,
                limit_price=order.limit_price,
            )
        else:
            result = await place_domestic_order(
                app_key,
                app_secret,
                access_token,
                account_no,
                side=order.side,
                ticker=order.ticker,
                quantity=order.quantity,
                is_mock=is_mock,
                order_type=order.order_type,
                limit_price=order.limit_price,
            )

        logger.info(
            "order_placed",
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            order_no=result.get("order_no"),
            is_mock=is_mock,
            order_type=order.order_type,
        )
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="SUCCESS",
            order_no=result.get("order_no"),
            order_type=order.order_type,
        )

    except Exception as e:
        logger.warning(
            "order_failed",
            ticker=order.ticker,
            side=order.side,
            quantity=order.quantity,
            error=str(e),
        )
        return OrderResult(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=order.quantity,
            status="FAILED",
            error_msg=str(e),
            order_type=order.order_type,
        )


async def _execute_two_phase_orders(
    group_orders: list[ExecutionOrderItem],
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> list[OrderResult]:
    """TWO_PHASE 전략 실행: 예수금 매수 → 매도 → 매도금 추가 매수.

    Phase 1: KIS 주문가능금액 조회 → 예수금 범위 내 BUY 실행
    Phase 2: SELL 전체 실행
    Phase 3: 주문가능금액 재조회(매도예정금 포함) → 나머지 BUY 실행
    """
    sells = [o for o in group_orders if o.side == "SELL"]
    buys = [o for o in group_orders if o.side == "BUY"]

    if not buys and not sells:
        return []

    # 해외 주식 포함 시 get_orderable_cash()가 국내 전용이므로 FULL 방식으로 폴백
    has_overseas = any(is_overseas_market(o.market) for o in buys)
    if has_overseas:
        logger.info("two_phase_fallback_overseas_detected", account_no=account_no)
        results: list[OrderResult] = []
        for order in sells + buys:
            results.append(await _execute_single_order(order, app_key, app_secret, access_token, account_no, is_mock))
        return results

    # Phase 1: 예수금으로 매수 가능한 만큼 실행
    try:
        orderable_cash = await get_orderable_cash(app_key, app_secret, access_token, account_no, is_mock=is_mock)
    except Exception as exc:
        logger.warning("two_phase_orderable_cash_failed_p1", error=str(exc))
        orderable_cash = 0.0

    logger.info("two_phase_phase1_start", orderable_cash=orderable_cash, buy_count=len(buys))

    phase1_results, remaining_buys, _ = await _execute_buys_within_budget(
        buys, orderable_cash, app_key, app_secret, access_token, account_no, is_mock
    )

    # Phase 2: 매도 전체 실행
    logger.info("two_phase_phase2_sells", sell_count=len(sells))
    sell_results: list[OrderResult] = []
    for order in sells:
        sell_results.append(await _execute_single_order(order, app_key, app_secret, access_token, account_no, is_mock))

    # Phase 3: 매도 후 주문가능금액 재조회 → 나머지 BUY 실행
    phase3_results: list[OrderResult] = []
    if remaining_buys:
        try:
            new_orderable_cash = await get_orderable_cash(
                app_key, app_secret, access_token, account_no, is_mock=is_mock
            )
        except Exception as exc:
            logger.warning("two_phase_orderable_cash_failed_p3", error=str(exc))
            new_orderable_cash = 0.0

        logger.info(
            "two_phase_phase3_start",
            new_orderable_cash=new_orderable_cash,
            remaining_buy_count=len(remaining_buys),
        )
        phase3_results, _, _ = await _execute_buys_within_budget(
            remaining_buys, new_orderable_cash, app_key, app_secret, access_token, account_no, is_mock
        )

    return phase1_results + sell_results + phase3_results


async def _execute_buys_within_budget(
    buy_orders: list[ExecutionOrderItem],
    budget: float,
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
) -> tuple[list[OrderResult], list[ExecutionOrderItem], float]:
    """예산(budget) 범위 내에서 매수 주문을 실행한다.

    지정가(limit_price)가 있는 경우 예산 초과분은 수량 조정하고 나머지를 remaining에 추가한다.
    시장가 주문은 가격 추정이 불가하므로 전량 시도 후 remaining 없음.
    Returns: (실행 결과 목록, 예산 부족으로 남은 주문 목록, 사용된 예산)
    """
    results: list[OrderResult] = []
    remaining: list[ExecutionOrderItem] = []
    remaining_budget = budget

    for order in buy_orders:
        price = order.limit_price
        if price and price > 0:
            if remaining_budget <= 0:
                remaining.append(order)
                continue
            affordable_qty = int(remaining_budget // price)
            if affordable_qty <= 0:
                remaining.append(order)
                continue
            execute_qty = min(order.quantity, affordable_qty)
            leftover_qty = order.quantity - execute_qty
        else:
            # 시장가: 가격 모름, 전량 시도
            execute_qty = order.quantity
            leftover_qty = 0

        if execute_qty <= 0:
            remaining.append(order)
            continue

        if leftover_qty > 0:
            remaining.append(
                ExecutionOrderItem(
                    ticker=order.ticker,
                    name=order.name,
                    market=order.market,
                    side=order.side,
                    quantity=leftover_qty,
                    account_id=order.account_id,
                    order_type=order.order_type,
                    limit_price=order.limit_price,
                )
            )

        exec_order = ExecutionOrderItem(
            ticker=order.ticker,
            name=order.name,
            market=order.market,
            side=order.side,
            quantity=execute_qty,
            account_id=order.account_id,
            order_type=order.order_type,
            limit_price=order.limit_price,
        )
        result = await _execute_single_order(exec_order, app_key, app_secret, access_token, account_no, is_mock)
        results.append(result)

        if result.status == "SUCCESS" and price and price > 0:
            remaining_budget -= execute_qty * price

    return results, remaining, budget - remaining_budget
