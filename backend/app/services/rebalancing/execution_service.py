"""리밸런싱 실행 서비스 — KIS/키움 API를 통해 매수/매도 주문을 일괄 실행한다."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import ORDER_EXECUTABLE_ASSET_TYPES, OVERSEAS_MARKETS, TAX_DEFERRED_TAX_TYPES
from app.core.job_runner import report_handled_failure
from app.core.logging import public_error_message, redact_secrets
from app.exceptions import AppError, BadRequestError, NotFoundError, SyncError
from app.kis.auth import get_access_token
from app.kis.exchange_master import resolve_kis_overseas_market
from app.kiwoom.auth import get_access_token as kiwoom_get_access_token
from app.models.asset import AssetAccount, RebalancingExecution, RebalancingExecutionResult
from app.schemas.rebalancing import ExecutionOrderItem, ExecutionResult, OrderResult
from app.services.accounts._account_queries import active_accounts_stmt
from app.services.accounts.credential_service import decrypt_kis_credentials, decrypt_kiwoom_credentials
from app.services.rebalancing._kis_order_executor import (
    _execute_buys_with_cash_check,
    _execute_sells_with_clamp,
    _execute_two_phase_orders,
)
from app.services.rebalancing._kiwoom_order_executor import (
    _execute_kiwoom_buys_with_cash_check,
    _execute_kiwoom_sells_with_clamp,
)
from app.services.rebalancing.order_cancel_rules import active_account_asset_types, cancel_block_reason
from app.utils.cache_keys import invalidate_rebalancing_analysis_cache
from app.utils.metrics import rebalancing_execution_count

logger = structlog.get_logger()


async def load_executable_account(
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession,
) -> AssetAccount:
    account = await db.scalar(active_accounts_stmt(user_id).where(AssetAccount.id == account_id))
    if not account:
        raise NotFoundError(detail=f"계좌를 찾을 수 없습니다. (id={account_id})")
    if account.asset_type not in ORDER_EXECUTABLE_ASSET_TYPES:
        raise BadRequestError(detail="KIS 또는 키움 계좌만 실행 주문이 가능합니다.")
    if account.asset_type == "STOCK_KIS" and not account.kis_account_no:
        raise BadRequestError(detail="KIS 계좌번호가 설정되지 않았습니다.")
    if account.asset_type == "STOCK_KIWOOM" and not account.kiwoom_account_no:
        raise BadRequestError(detail="키움 계좌번호가 설정되지 않았습니다.")
    return account


def load_kis_credentials(account: AssetAccount) -> tuple[str, str]:
    """KIS 계좌 자격증명 로드. 미설정 시 400 에러."""
    creds = decrypt_kis_credentials(account)
    if creds is None:
        raise BadRequestError(
            detail="KIS 자격증명이 설정되지 않았습니다. 계좌 설정에서 App Key와 App Secret을 입력해주세요.",
        )
    return creds


def load_kiwoom_credentials(account: AssetAccount) -> tuple[str, str]:
    """키움 계좌 자격증명 로드 (전역 폴백 없음)."""
    creds = decrypt_kiwoom_credentials(account)
    if creds is None:
        raise BadRequestError(detail="키움 자격증명이 설정되지 않았습니다.")
    return creds


def _group_orders_by_account(
    orders: list[ExecutionOrderItem], account_id: uuid.UUID | None
) -> dict[str, list[ExecutionOrderItem]]:
    """주문을 account_id별로 그룹화한다. account_id 없는 주문은 인자로 받은 기본 계좌를 사용한다."""
    groups: dict[str, list[ExecutionOrderItem]] = defaultdict(list)
    for order in orders:
        target_acc_id = order.account_id or (str(account_id) if account_id else None)
        if not target_acc_id:
            raise BadRequestError(
                detail=f"주문 계좌가 지정되지 않았습니다. (ticker={order.ticker})",
            )
        groups[target_acc_id].append(order)
    return groups


def _build_failed_group_result(
    user_id: uuid.UUID, acc_id_str: str, group_orders: list[ExecutionOrderItem], error: Exception
) -> ExecutionResult:
    """계좌 그룹 실행 중 예외 발생 시 해당 그룹의 전체 주문을 FAILED로 표시한 ExecutionResult를 만든다."""
    # 응답·실행 이력에 남는 문구 — 예상 밖 예외 원문(SQL·URL)은 로그에만(계획 57 D1)
    detail = public_error_message(error)
    # 예상 밖 예외는 원인 추적용으로 예외 타입을 남기고 error로 올린다. exc_info/Sentry 전송은 하지 않는다 —
    # 이 경로의 프레임 지역변수에 복호화된 증권사 자격증명이 있다(_job_helpers.report_job_failure 참고).
    expected = isinstance(error, AppError | SyncError)
    log = logger.warning if expected else logger.error
    log(
        "rebalancing_group_failed",
        user_id=str(user_id),
        account_id=acc_id_str,
        error=redact_secrets(str(error)),
        error_type=type(error).__name__,
    )
    fail_orders = [
        OrderResult.for_order(
            o,
            "FAILED",
            error_msg=detail,
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

    저장 실패는 오류 로그·Sentry만 남기고 삼킨다(세션은 rollback) — 이미 완료된 주문 실행 결과
    자체는 영향받지 않아야 한다.
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

        saved: list[tuple[OrderResult, RebalancingExecutionResult]] = []
        for exec_result in results:
            for placed in exec_result.orders:
                # id를 미리 정해 두어 커밋 뒤 응답 주문에 result_id를 붙인다(미체결 취소 대상 지정용)
                result_row = RebalancingExecutionResult(
                    id=uuid.uuid4(),
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
                    order_org_no=placed.order_org_no,
                    error_message=placed.error_msg,
                    order_type=placed.order_type,
                    price=placed.price,
                )
                saved.append((placed, result_row))
                db.add(result_row)

        await db.commit()
    except Exception as e:
        # 실주문은 이미 나갔는데 기록이 없는 상태 — 경고가 아니라 오류로 알린다. flush 이후 실패면 세션이
        # 실패 상태라 호출부의 후속 commit(leg 상태 기록 등)이 PendingRollbackError로 깨지므로 되돌린다.
        report_handled_failure("rebalancing_history_save_failed", e, user_id=str(user_id))
        await db.rollback()
        return None

    await _mark_cancelable(db, user_id, saved)
    return execution.id


async def _mark_cancelable(
    db: AsyncSession, user_id: uuid.UUID, saved: list[tuple[OrderResult, RebalancingExecutionResult]]
) -> None:
    """응답 주문에 result_id·취소 가능 여부를 붙인다 — 이력 상세와 같은 규칙(`cancel_block_reason`, plans/90 A4).

    계좌 유형 조회가 실패해도 이미 저장된 이력에는 영향이 없으므로 취소 버튼만 숨긴다(이력 탭에서 다시 판정).
    """
    try:
        asset_types = await active_account_asset_types(db, user_id, (row.account_id for _, row in saved))
    except Exception as e:
        logger.warning("rebalancing_cancelable_lookup_failed", user_id=str(user_id), error_type=type(e).__name__)
        asset_types = {}
    now = datetime.now(UTC)
    for placed, row in saved:
        placed.result_id = row.id
        placed.cancelable = cancel_block_reason(row, now, asset_types.get(row.account_id or ""), now=now) is None


async def execute_rebalancing(
    user_id: uuid.UUID,
    account_id: uuid.UUID | None,
    orders: list[ExecutionOrderItem],
    db: AsyncSession,
    cache,
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
        raise BadRequestError(detail="실행할 주문이 없습니다.")

    results: list[ExecutionResult] = []
    for acc_id_str, group_orders in groups.items():
        try:
            results.append(await _execute_account_group(acc_id_str, group_orders, user_id, db, cache, strategy))
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
    if portfolio_id and cache:
        await invalidate_rebalancing_analysis_cache(cache, user_id, portfolio_id)

    rebalancing_execution_count.labels(status="success" if total_fail == 0 else "partial").inc()
    return results, execution_id


TAX_DEFERRED_OVERSEAS_MSG = (
    "ISA·연금 계좌는 해외 상장 종목을 살 수 없습니다. 국내 상장 대체 종목이나 일반 계좌로 매수하세요."
)


def _split_tax_deferred_overseas_buys(
    account: AssetAccount, group_orders: list[ExecutionOrderItem]
) -> tuple[list[ExecutionOrderItem], list[OrderResult]]:
    """(낼 주문, SKIPPED 결과) — 절세 계좌의 해외 매수는 증권사가 거부하므로 보내지 않는다.

    자동 실행은 주문 생성 단계(order_builder)에서 같은 주문을 빼지만, 수동 실행은 화면이 만든 주문을
    그대로 받으므로 여기서 한 번 더 막는다(plans/80 A4).
    """
    if account.tax_type not in TAX_DEFERRED_TAX_TYPES:
        return group_orders, []
    executable: list[ExecutionOrderItem] = []
    skipped: list[OrderResult] = []
    for o in group_orders:
        if o.side == "BUY" and o.market in OVERSEAS_MARKETS:
            skipped.append(
                OrderResult.for_order(
                    o,
                    "SKIPPED",
                    error_msg=TAX_DEFERRED_OVERSEAS_MSG,
                )
            )
        else:
            executable.append(o)
    return executable, skipped


async def _execute_kiwoom_account_orders(
    account: AssetAccount,
    group_orders: list[ExecutionOrderItem],
    user_id: uuid.UUID,
    acc_uuid: uuid.UUID,
    db: AsyncSession,
    cache,
    is_mock: bool,
) -> list[OrderResult]:
    """키움 계좌: 매도(보유수량 clamp) → 매수 순으로 주문을 실행한다."""
    app_key, app_secret = load_kiwoom_credentials(account)
    account_no = account.kiwoom_account_no
    if account_no is None:
        # load_executable_account가 사전 검증하므로 실행 경로상 도달 불가 — mypy 타입 좁히기 목적
        raise BadRequestError(detail="키움 계좌번호가 설정되지 않았습니다.")
    access_token = await kiwoom_get_access_token(
        app_key,
        app_secret,
        is_mock=is_mock,
        cache=cache,
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
    account_results.extend(
        await _execute_kiwoom_buys_with_cash_check(
            buys,
            access_token,
            account_no,
            is_mock,
        )
    )
    return account_results


async def _normalize_kis_overseas_markets(orders: list[ExecutionOrderItem], cache) -> list[ExecutionOrderItem]:
    """NYSE Arca ETF처럼 "NYSE"로 저장됐지만 KIS가 아멕스로 분류하는 종목의 market을 "AMEX"로 보정한다.

    보정하지 않으면 매수는 거래소 불일치로 거부되고, 매도는 KIS 잔고(AMEX)와 ticker+market 키가
    어긋나 clamp에서 SKIPPED가 된다. 키움은 같은 종목을 NYSE로 분류하므로 KIS 경로에만 적용한다.
    """
    if not any(o.market.upper() == "NYSE" for o in orders):
        return orders
    normalized: list[ExecutionOrderItem] = []
    for order in orders:
        market = await resolve_kis_overseas_market(order.ticker, order.market, cache)
        normalized.append(order if market == order.market else order.model_copy(update={"market": market}))
    return normalized


async def _execute_kis_account_orders(
    account: AssetAccount,
    group_orders: list[ExecutionOrderItem],
    user_id: uuid.UUID,
    acc_uuid: uuid.UUID,
    db: AsyncSession,
    cache,
    is_mock: bool,
    strategy: str,
) -> list[OrderResult]:
    """KIS 계좌: strategy가 TWO_PHASE면 예수금→매도→잔여매수 3단계, 아니면 매도(clamp)→매수 순으로 실행한다."""
    app_key, app_secret = load_kis_credentials(account)
    account_no = account.kis_account_no
    if account_no is None:
        # load_executable_account가 사전 검증하므로 실행 경로상 도달 불가 — mypy 타입 좁히기 목적
        raise BadRequestError(detail="KIS 계좌번호가 설정되지 않았습니다.")

    access_token = await get_access_token(
        app_key,
        app_secret,
        is_mock=is_mock,
        cache=cache,
        db=db,
        user_id=str(user_id),
        account_id=str(acc_uuid),
    )

    group_orders = await _normalize_kis_overseas_markets(group_orders, cache)

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
    account_results.extend(
        await _execute_buys_with_cash_check(
            buys,
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
    cache,
    strategy: str,
) -> ExecutionResult:
    """단일 계좌 그룹의 주문을 실행하고 ExecutionResult를 반환한다."""
    acc_uuid = uuid.UUID(acc_id_str)
    account = await load_executable_account(acc_uuid, user_id, db)
    is_mock = account.is_mock_mode
    group_orders, blocked = _split_tax_deferred_overseas_buys(account, group_orders)

    if not group_orders:
        account_results: list[OrderResult] = []
    elif account.asset_type == "STOCK_KIWOOM":
        # 키움은 주문가능금액 조회 API가 없어 TWO_PHASE(예수금 매수→매도→잔여 매수)를 지원하지 않는다 —
        # 매도→매수(예수금 근사 예산 clamp)로 실행한다. 결과(매도 후 가능한 만큼 매수)는 같은 방향이다.
        if strategy == "TWO_PHASE":
            logger.info("kiwoom_two_phase_runs_as_sell_then_buy", account_id=acc_id_str)
        account_results = await _execute_kiwoom_account_orders(
            account, group_orders, user_id, acc_uuid, db, cache, is_mock
        )
    else:
        account_results = await _execute_kis_account_orders(
            account, group_orders, user_id, acc_uuid, db, cache, is_mock, strategy
        )
    account_results = [*account_results, *blocked]

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
