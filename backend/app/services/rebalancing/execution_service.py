"""리밸런싱 실행 서비스 — KIS/키움 API를 통해 매수/매도 주문을 일괄 실행한다."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.kis.auth import get_access_token
from app.kiwoom.auth import get_access_token as kiwoom_get_access_token
from app.models.asset import AssetAccount, RebalancingExecution, RebalancingExecutionResult
from app.schemas.rebalancing import ExecutionOrderItem, ExecutionResult, OrderResult
from app.services._account_queries import active_accounts_stmt
from app.services.credential_service import decrypt_kis_credentials, decrypt_kiwoom_credentials
from app.services.rebalancing._kis_order_executor import (
    _execute_sells_with_clamp,
    _execute_single_order,
    _execute_two_phase_orders,
)
from app.services.rebalancing._kiwoom_order_executor import (
    _execute_kiwoom_sells_with_clamp,
    _execute_kiwoom_single_order,
)
from app.utils.cache_keys import invalidate_rebalancing_analysis_cache, invalidate_rebalancing_strategy_cache
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
    creds = decrypt_kis_credentials(account)
    if creds is None:
        raise HTTPException(
            status_code=400,
            detail="KIS 자격증명이 설정되지 않았습니다. 계좌 설정에서 App Key와 App Secret을 입력해주세요.",
        )
    return creds


async def _load_kiwoom_credentials(account: AssetAccount) -> tuple[str, str]:
    """키움 계좌 자격증명 로드 (전역 폴백 없음)."""
    creds = decrypt_kiwoom_credentials(account)
    if creds is None:
        raise HTTPException(status_code=400, detail="키움 자격증명이 설정되지 않았습니다.")
    return creds


def _group_orders_by_account(
    orders: list[ExecutionOrderItem], account_id: uuid.UUID | None
) -> dict[str, list[ExecutionOrderItem]]:
    """주문을 account_id별로 그룹화한다. account_id 없는 주문은 인자로 받은 기본 계좌를 사용한다."""
    groups: dict[str, list[ExecutionOrderItem]] = defaultdict(list)
    for order in orders:
        target_acc_id = order.account_id or (str(account_id) if account_id else None)
        if not target_acc_id:
            raise HTTPException(
                status_code=400,
                detail=f"주문 계좌가 지정되지 않았습니다. (ticker={order.ticker})",
            )
        groups[target_acc_id].append(order)
    return groups


def _build_failed_group_result(
    user_id: uuid.UUID, acc_id_str: str, group_orders: list[ExecutionOrderItem], error: Exception
) -> ExecutionResult:
    """계좌 그룹 실행 중 예외 발생 시 해당 그룹의 전체 주문을 FAILED로 표시한 ExecutionResult를 만든다."""
    detail = error.detail if isinstance(error, HTTPException) else str(error)
    logger.warning("rebalancing_group_failed", user_id=str(user_id), account_id=acc_id_str, error=detail)
    fail_orders = [
        OrderResult(
            ticker=o.ticker,
            name=o.name,
            market=o.market,
            side=o.side,
            quantity=o.quantity,
            status="FAILED",
            error_msg=str(detail),
            order_type=o.order_type,
            price=o.limit_price or o.reference_price,
        )
        for o in group_orders
    ]
    return ExecutionResult(
        account_id=acc_id_str,
        account_name=acc_id_str,
        is_mock=False,
        orders=fail_orders,
        success_count=0,
        fail_count=len(fail_orders),
        executed_at=datetime.now(UTC).isoformat(),
    )


async def _save_execution_history(
    db: AsyncSession,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    triggered_by: str,
    strategy: str,
    results: list[ExecutionResult],
    total_success: int,
    total_fail: int,
    total_skipped: int,
) -> uuid.UUID | None:
    """실행 결과를 RebalancingExecution/RebalancingExecutionResult로 저장한다.

    저장 실패는 경고 로그만 남기고 삼킨다 — 이미 완료된 주문 실행 결과 자체는 영향받지 않아야 한다.
    반환값(생성된 execution.id, 저장 실패 시 None)은 AUTO 실행 후 "방금 이 실행이 만든" 기록을
    정확히 재조회하는 데 쓰인다 — "가장 최근 것"으로 재조회하면 같은 포트폴리오의 다른 실행(다른
    계좌 등) 결과를 잘못 집어올 수 있다.
    """
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
        return execution.id
    except Exception as e:
        logger.warning("rebalancing_history_save_failed", user_id=str(user_id), error=str(e))
        return None


async def execute_rebalancing(
    user_id: uuid.UUID,
    account_id: uuid.UUID | None,
    orders: list[ExecutionOrderItem],
    db: AsyncSession,
    redis,
    portfolio_id: uuid.UUID | None = None,
    triggered_by: str = "MANUAL",
    strategy: str = "FULL",
) -> tuple[list[ExecutionResult], uuid.UUID | None]:
    """선택된 리밸런싱 주문 항목을 KIS API를 통해 순차 실행한다.

    주문별 account_id로 계좌를 그룹화해 각 계좌별 독립 실행한다.
    account_id가 없는 주문은 인자로 전달된 account_id(기본 계좌)를 사용한다.
    매도 주문을 먼저 처리해 현금을 확보한 뒤 매수 주문을 실행한다.
    개별 주문 실패 시 나머지 주문은 계속 진행된다.
    (계좌별 ExecutionResult 목록, 저장된 실행 이력의 id)를 반환한다 — 실행 이력은 DB에 저장된다.
    """
    groups = _group_orders_by_account(orders, account_id)
    if not groups:
        raise HTTPException(status_code=400, detail="실행할 주문이 없습니다.")

    results: list[ExecutionResult] = []
    for acc_id_str, group_orders in groups.items():
        try:
            results.append(await _execute_account_group(acc_id_str, group_orders, user_id, db, redis, strategy))
        except Exception as e:
            results.append(_build_failed_group_result(user_id, acc_id_str, group_orders, e))

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

    execution_id = await _save_execution_history(
        db, user_id, portfolio_id, triggered_by, strategy, results, total_success, total_fail, total_skipped
    )

    # 실행 후 전략·진단 캐시 무효화 (포트폴리오 구성이 변경되었으므로)
    if portfolio_id and redis:
        await invalidate_rebalancing_strategy_cache(redis, user_id, portfolio_id)
        await invalidate_rebalancing_analysis_cache(redis, user_id, portfolio_id)

    rebalancing_execution_count.labels(status="success" if total_fail == 0 else "partial").inc()
    return results, execution_id


async def _execute_kiwoom_account_orders(
    account: AssetAccount,
    group_orders: list[ExecutionOrderItem],
    user_id: uuid.UUID,
    acc_uuid: uuid.UUID,
    db: AsyncSession,
    redis,
    is_mock: bool,
) -> list[OrderResult]:
    """키움 계좌: 매도(보유수량 clamp) → 매수 순으로 주문을 실행한다."""
    app_key, app_secret = await _load_kiwoom_credentials(account)
    account_no = account.kiwoom_account_no
    if account_no is None:
        # _load_account가 사전 검증하므로 실행 경로상 도달 불가 — mypy 타입 좁히기 목적
        raise HTTPException(status_code=400, detail="키움 계좌번호가 설정되지 않았습니다.")
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

    account_results: list[OrderResult] = await _execute_kiwoom_sells_with_clamp(
        sells,
        access_token,
        account_no,
        is_mock,
    )
    for order in buys:
        account_results.append(
            await _execute_kiwoom_single_order(
                order,
                access_token,
                account_no,
                is_mock,
            )
        )
    return account_results


async def _execute_kis_account_orders(
    account: AssetAccount,
    group_orders: list[ExecutionOrderItem],
    user_id: uuid.UUID,
    acc_uuid: uuid.UUID,
    db: AsyncSession,
    redis,
    is_mock: bool,
    strategy: str,
) -> list[OrderResult]:
    """KIS 계좌: strategy가 TWO_PHASE면 예수금→매도→잔여매수 3단계, 아니면 매도(clamp)→매수 순으로 실행한다."""
    app_key, app_secret = await _load_credentials(account)
    account_no = account.kis_account_no
    if account_no is None:
        # _load_account가 사전 검증하므로 실행 경로상 도달 불가 — mypy 타입 좁히기 목적
        raise HTTPException(status_code=400, detail="KIS 계좌번호가 설정되지 않았습니다.")

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
        return await _execute_two_phase_orders(
            group_orders,
            app_key,
            app_secret,
            access_token,
            account_no,
            is_mock,
        )

    sells = [o for o in group_orders if o.side == "SELL"]
    buys = [o for o in group_orders if o.side == "BUY"]

    account_results = await _execute_sells_with_clamp(
        sells,
        app_key,
        app_secret,
        access_token,
        account_no,
        is_mock,
    )
    for order in buys:
        account_results.append(
            await _execute_single_order(
                order,
                app_key,
                app_secret,
                access_token,
                account_no,
                is_mock,
            )
        )
    return account_results


async def _execute_account_group(
    acc_id_str: str,
    group_orders: list[ExecutionOrderItem],
    user_id: uuid.UUID,
    db: AsyncSession,
    redis,
    strategy: str,
) -> ExecutionResult:
    """단일 계좌 그룹의 주문을 실행하고 ExecutionResult를 반환한다."""
    acc_uuid = uuid.UUID(acc_id_str)
    account = await _load_account(acc_uuid, user_id, db)
    is_mock = account.is_mock_mode

    if account.asset_type == "STOCK_KIWOOM":
        account_results = await _execute_kiwoom_account_orders(
            account, group_orders, user_id, acc_uuid, db, redis, is_mock
        )
    else:
        account_results = await _execute_kis_account_orders(
            account, group_orders, user_id, acc_uuid, db, redis, is_mock, strategy
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

    return ExecutionResult(
        account_id=str(account.id),
        account_name=account.name,
        is_mock=is_mock,
        orders=account_results,
        success_count=success_count,
        fail_count=fail_count,
        executed_at=datetime.now(UTC).isoformat(),
    )
