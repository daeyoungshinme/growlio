"""자매 앱(nestlio) 등 외부 서비스가 같은 Supabase 프로젝트의 사용자 JWT로 호출하는
엔드포인트. growlio 자체 프론트엔드는 이 라우터를 사용하지 않는다.

계좌 조회(GET /accounts)는 읽기전용이지만, POST /transactions는 nestlio의 "저축/투자"
가계부 내역을 growlio 입출금 내역(Transaction)에 그대로 반영하고, 수동(MANUAL) 계좌라면
예수금(deposit_krw)까지 합산하는 쓰기 엔드포인트다 — KIS/키움처럼 자동 연동된 계좌는 다음
브로커 동기화가 deposit_krw를 실제 값으로 덮어쓰므로 여기서는 건드리지 않는다(이중 반영 방지).

GET /real-estate는 부동산 계좌의 시세(market_value_krw)와 담보대출 잔액(mortgage_balance_krw)을
분리해서 반환한다 — GET /accounts는 부동산도 담보대출을 뺀 순액 하나만 주므로, nestlio가
"자산 항목"과 "대출 항목"을 각각 등록하려면 이 엔드포인트가 필요하다.

GET /goal은 사용자가 growlio 설정에서 입력한 투자목표(목표금액/목표수익률/연 납입목표 등)를
읽기전용으로 노출한다 — nestlio가 재무목표를 새로 만들 때 이 값으로 폼을 미리 채워준다.
진행률 자체는 nestlio가 이미 가져온 growlio 연동 자산 잔액으로 스스로 계산하므로, 이
엔드포인트는 목표 "설정값"만 내려주고 진행률/달성 시점 같은 계산값은 포함하지 않는다.
"""

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1._account_deps import get_owned_account as _get_owned_account
from app.core.cache_store import get_cache_store
from app.enums import AssetType, DataSource, TransactionType
from app.limiter import limiter
from app.models.asset import Transaction
from app.models.user import User
from app.services._settings_queries import get_settings_row
from app.services.asset_service import list_accounts as _list_accounts
from app.services.snapshot_service import _upsert_snapshot, get_latest_snapshot_with_positions
from app.utils.cache_keys import invalidate_asset_account_caches, invalidate_user_caches, monthly_trend_key
from app.utils.currency import fetch_usd_krw

router = APIRouter(prefix="/external", tags=["external"])


class ExternalAccountBalance(BaseModel):
    id: str
    name: str
    asset_type: AssetType
    current_value_krw: float
    as_of: date | None = None


@router.get("/accounts", response_model=list[ExternalAccountBalance])
@limiter.limit("20/minute")
async def list_account_balances(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 활성 계좌별 최신 평가액(KRW)을 반환한다.

    KIS/키움 실시간 재동기화를 트리거하지 않고, 매일 적재되는 스냅샷(`AssetSnapshot.amount_krw`)
    중 계좌별 최신 값을 그대로 돌려준다 — growlio 자체 조회 API와 달리 이 엔드포인트는
    외부 서비스가 자유 빈도로 호출할 수 있어야 하므로 평가 비용이 드는 실시간 재계산을 피한다.
    """
    accounts = await _list_accounts(current_user.id, db, skip=0, limit=200)
    result: list[ExternalAccountBalance] = []
    for account in accounts:
        latest_snap, _positions = await get_latest_snapshot_with_positions(db, account.id)
        if latest_snap is not None:
            value = latest_snap.amount_krw
            as_of = latest_snap.snapshot_date
        else:
            value = account.manual_amount or 0
            as_of = None
        result.append(
            ExternalAccountBalance(
                id=str(account.id),
                name=account.name,
                asset_type=account.asset_type,
                current_value_krw=value,
                as_of=as_of,
            )
        )
    return result


class ExternalRealEstateItem(BaseModel):
    id: str
    name: str
    address: str | None = None
    property_type: str | None = None
    market_value_krw: float
    mortgage_balance_krw: float
    net_equity_krw: float
    purchase_price_krw: float | None = None
    purchase_date: str | None = None
    as_of: date | None = None


@router.get("/real-estate", response_model=list[ExternalRealEstateItem])
@limiter.limit("20/minute")
async def list_real_estate_items(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재 사용자의 활성 부동산 계좌를 시세/담보대출 분리 형태로 반환한다.

    GET /accounts는 부동산도 담보대출을 뺀 순액(net) 하나만 주지만, nestlio가 "자산 항목"과
    "대출 항목"을 각각 등록하려면 원본 시세와 대출잔액이 따로 필요하다.
    """
    accounts = await _list_accounts(current_user.id, db, skip=0, limit=200)
    result: list[ExternalRealEstateItem] = []
    for account in accounts:
        if account.asset_type != AssetType.REAL_ESTATE:
            continue
        details = account.real_estate_details or {}
        market_value = float(account.manual_amount or 0)
        mortgage = float(details.get("mortgage_balance_krw", 0) or 0)
        result.append(
            ExternalRealEstateItem(
                id=str(account.id),
                name=account.name,
                address=details.get("address"),
                property_type=details.get("property_type"),
                market_value_krw=market_value,
                mortgage_balance_krw=mortgage,
                net_equity_krw=market_value - mortgage,
                purchase_price_krw=details.get("purchase_price_krw"),
                purchase_date=details.get("purchase_date"),
                as_of=account.manual_updated_at.date() if account.manual_updated_at else None,
            )
        )
    return result


class ExternalGoalSettings(BaseModel):
    is_configured: bool
    goal_amount: float | None = None
    goal_annual_return_pct: float | None = None
    goal_start_date: datetime | None = None
    goal_initial_amount: float | None = None
    annual_deposit_goal: float | None = None
    annual_dividend_goal: float | None = None


@router.get("/goal", response_model=ExternalGoalSettings)
@limiter.limit("20/minute")
async def get_investment_goal(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """nestlio가 재무목표를 미리 채우기 위해 조회하는, 사용자가 growlio에 설정한 투자목표.

    포트폴리오 구성용 필드(candidate_tickers, risk_tolerance 등)는 목표 진행상황
    모니터링과 무관해 내려주지 않는다.
    """
    row = await get_settings_row(db, current_user.id)
    if row is None or row.goal_amount is None:
        return ExternalGoalSettings(is_configured=False)
    return ExternalGoalSettings(
        is_configured=True,
        goal_amount=float(row.goal_amount),
        goal_annual_return_pct=float(row.goal_annual_return_pct) if row.goal_annual_return_pct is not None else None,
        goal_start_date=row.goal_start_date,
        goal_initial_amount=float(row.goal_initial_amount) if row.goal_initial_amount is not None else None,
        annual_deposit_goal=float(row.annual_deposit_goal) if row.annual_deposit_goal is not None else None,
        annual_dividend_goal=float(row.annual_dividend_goal) if row.annual_dividend_goal is not None else None,
    )


class ExternalTransactionCreate(BaseModel):
    account_id: UUID
    transaction_type: TransactionType
    amount: float
    transaction_date: date
    notes: str | None = None


class ExternalTransactionResult(BaseModel):
    transaction_id: str
    deposit_krw_adjusted: bool
    deposit_krw: float | None = None


@router.post("/transactions", response_model=ExternalTransactionResult, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_external_transaction(
    request: Request,
    req: ExternalTransactionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """nestlio 가계부의 "저축/투자" 내역을 growlio 입출금 내역에 반영한다.

    DEPOSIT/WITHDRAWAL만 허용한다(DIVIDEND는 growlio 자체 배당 기능의 영역이라 이 경로로 들어오지 않는다).
    수동(MANUAL) 계좌는 예수금(deposit_krw)까지 함께 갱신하고 오늘자 스냅샷을 재계산한다 —
    `PUT /assets/{account_id}`가 예수금 직접 수정 시 하는 일과 동일한 계산이다. KIS/키움 자동
    연동 계좌는 내역만 기록하고 예수금은 다음 브로커 동기화가 채우도록 그대로 둔다.
    """
    if req.transaction_type not in (TransactionType.DEPOSIT, TransactionType.WITHDRAWAL):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "transaction_type은 DEPOSIT 또는 WITHDRAWAL만 허용합니다.")

    account = await _get_owned_account(req.account_id, current_user.id, db)

    tx = Transaction(
        user_id=current_user.id,
        account_id=account.id,
        transaction_type=req.transaction_type,
        amount=req.amount,
        transaction_date=req.transaction_date,
        notes=req.notes or "nestlio 가계부 저축/투자 내역에서 자동 기록",
    )
    db.add(tx)

    deposit_krw_adjusted = False
    if account.data_source == DataSource.MANUAL:
        deposit_krw_adjusted = True
        delta = req.amount if req.transaction_type == TransactionType.DEPOSIT else -req.amount
        account.deposit_krw = float(account.deposit_krw or 0) + delta
        account.manual_updated_at = datetime.now(UTC)

        cache = await get_cache_store()
        usd_rate = await fetch_usd_krw(cache)
        latest_snap, pos_list = await get_latest_snapshot_with_positions(db, account.id)
        pos_value = sum(
            (float(p.current_price) if p.current_price else float(p.avg_price or 0)) * float(p.qty or 0)
            for p in pos_list
        )
        usd_as_krw = float(account.deposit_usd or 0) * usd_rate
        total = pos_value + float(account.deposit_krw or 0) + usd_as_krw
        await _upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=date.today(),
            amount_krw=total,
            invested_amount=latest_snap.invested_amount if latest_snap else None,
            unrealized_pnl=latest_snap.unrealized_pnl if latest_snap else None,
            source="MANUAL",
        )

    await db.commit()
    await db.refresh(tx)

    cache = await get_cache_store()
    await invalidate_asset_account_caches(cache, current_user.id, account_id=account.id)
    await invalidate_user_caches(cache, monthly_trend_key(current_user.id))

    return ExternalTransactionResult(
        transaction_id=str(tx.id),
        deposit_krw_adjusted=deposit_krw_adjusted,
        deposit_krw=account.deposit_krw if deposit_krw_adjusted else None,
    )
