from datetime import UTC, date, datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.v1 import positions as _positions_module
from app.api.v1._account_deps import get_owned_account as _get_owned_account
from app.limiter import limiter
from app.models.asset import AssetAccount, Transaction
from app.models.user import User
from app.redis_client import get_redis
from app.schemas.asset import (
    AssetAccountCreate,
    AssetAccountResponse,
    AssetAccountUpdate,
    AssetSnapshotResponse,
    BatchSetTargetPortfolioRequest,
    KisCredentialVerifyRequest,
    SetTargetPortfolioRequest,
)
from app.services.asset_service import (
    list_accounts as _list_accounts,
)
from app.services.asset_service import (
    list_accounts_by_ids as _list_accounts_by_ids,
)
from app.services.asset_service import (
    list_snapshots_in_range as _list_snapshots_in_range,
)
from app.services.asset_service import (
    sync_account as _sync_account_service,
)
from app.services.credential_service import encrypt, encrypt_if_present
from app.services.snapshot_service import _upsert_snapshot, get_latest_snapshot_with_positions, sync_snapshot_positions
from app.utils.cache_keys import (
    TTL_ACCOUNT_DETAIL,
    account_detail_key,
    get_cached_json,
    invalidate_asset_account_caches,
    invalidate_user_caches,
    set_cached_json,
)
from app.utils.currency import fetch_usd_krw
from app.utils.pnl import calc_net_asset_amount
from app.utils.redis_lock import redis_lock

_CREDENTIAL_FIELDS: set[str] = {"kis_app_key", "kis_app_secret", "kiwoom_app_key", "kiwoom_app_secret"}
# 시장가 변동이 없는 순수 현금성 계좌 — 잔액 변경은 전액 입출금으로 간주
_CASH_ASSET_TYPES: set[str] = {"BANK_ACCOUNT", "DEPOSIT", "CASH_OTHER"}


def _account_response(account: AssetAccount) -> AssetAccountResponse:
    """AssetAccount ORM 모델을 Response 스키마로 변환."""
    data = AssetAccountResponse.model_validate(account)
    data.has_own_kis_credentials = bool(account.kis_app_key)
    data.has_own_kiwoom_credentials = bool(account.kiwoom_app_key)
    return data


router = APIRouter(prefix="/assets", tags=["assets"])
router.include_router(_positions_module.router)


def _calc_manual_snap_amount(account: AssetAccount) -> float:
    """manual_amount에서 부동산 모기지를 차감한 스냅샷 저장용 금액을 반환한다."""
    return calc_net_asset_amount(account.manual_amount, account.asset_type, account.real_estate_details)


@router.get("", response_model=list[AssetAccountResponse])
async def list_accounts(
    skip: int = 0,
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    accounts = await _list_accounts(current_user.id, db, skip=skip, limit=limit)
    return [_account_response(a) for a in accounts]


@router.post("/verify-kis-credentials")
@limiter.limit("10/minute")
async def verify_kis_credentials(
    request: Request,
    req: KisCredentialVerifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """KIS 자격증명 유효성 확인 (계좌 생성 없이)."""
    from app.kis.auth import _fetch_and_store_token

    redis = await get_redis()
    try:
        await _fetch_and_store_token(
            req.kis_app_key,
            req.kis_app_secret,
            is_mock=req.is_mock,
            redis=redis,
            db=db,
            user_id=str(current_user.id),
            account_id=None,
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 401, 403):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="KIS 자격증명이 잘못되었습니다. App Key/Secret 및 모드를 확인하세요.",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="KIS 서버 오류. 잠시 후 다시 시도하세요.",
        ) from e
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="KIS 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요.",
        ) from e
    return {"valid": True, "message": "KIS 자격증명이 확인되었습니다."}


@router.post("", response_model=AssetAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    req: AssetAccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.data_source == "KIS_API":
        if not req.kis_app_key or not req.kis_app_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="KIS API 자격증명(App Key, App Secret)을 모두 입력하세요.",
            )
        req_data = req.model_dump(exclude=_CREDENTIAL_FIELDS)
        req_data["kis_app_key"] = encrypt(req.kis_app_key)
        req_data["kis_app_secret"] = encrypt(req.kis_app_secret)
        account = AssetAccount(user_id=current_user.id, **req_data)
    elif req.data_source == "KIWOOM_API":
        if not req.kiwoom_account_no or not req.kiwoom_app_key or not req.kiwoom_app_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="키움 계좌번호와 API 자격증명(App Key, App Secret)을 모두 입력하세요.",
            )
        req_data = req.model_dump(exclude=_CREDENTIAL_FIELDS)
        req_data["kiwoom_app_key"] = encrypt(req.kiwoom_app_key)
        req_data["kiwoom_app_secret"] = encrypt(req.kiwoom_app_secret)
        req_data["asset_type"] = "STOCK_KIWOOM"
        account = AssetAccount(user_id=current_user.id, **req_data)
    else:
        account = AssetAccount(user_id=current_user.id, **req.model_dump(exclude=_CREDENTIAL_FIELDS))
    db.add(account)
    await db.commit()
    await db.refresh(account)
    if account.manual_amount:
        await _upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=date.today(),
            amount_krw=_calc_manual_snap_amount(account),
            source="MANUAL",
        )
        await db.commit()
    return _account_response(account)


_MAX_SNAPSHOTS_LIMIT = 365


@router.get("/snapshots/range", response_model=list[AssetSnapshotResponse])
async def get_snapshots(
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=_MAX_SNAPSHOTS_LIMIT, ge=1, le=_MAX_SNAPSHOTS_LIMIT),
    skip: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date는 end_date보다 이전이어야 합니다",
        )
    limit = min(limit, _MAX_SNAPSHOTS_LIMIT)
    return await _list_snapshots_in_range(
        current_user.id,
        db,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )


@router.get("/{account_id}", response_model=AssetAccountResponse)
async def get_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    redis = await get_redis()
    cache_key = account_detail_key(current_user.id, account_id)
    cached = await get_cached_json(redis, cache_key)
    if cached is not None:
        return cached

    account = await _get_owned_account(account_id, current_user.id, db)
    response = _account_response(account)
    await set_cached_json(redis, cache_key, response.model_dump(mode="json"), TTL_ACCOUNT_DETAIL)
    return response


@router.put("/{account_id}", response_model=AssetAccountResponse)
async def update_account(
    account_id: UUID,
    req: AssetAccountUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_owned_account(account_id, current_user.id, db)

    update_fields = req.model_dump(exclude_none=True, exclude=_CREDENTIAL_FIELDS)
    for field, value in update_fields.items():
        setattr(account, field, value)

    if req.kis_app_key is not None:
        account.kis_app_key = encrypt_if_present(req.kis_app_key)
        account.kis_app_secret = encrypt_if_present(req.kis_app_secret)

    if req.kiwoom_app_key is not None:
        account.kiwoom_app_key = encrypt_if_present(req.kiwoom_app_key)
        account.kiwoom_app_secret = encrypt_if_present(req.kiwoom_app_secret)

    if (
        req.manual_amount is not None
        or req.deposit_krw is not None
        or req.deposit_usd is not None
        or req.real_estate_details is not None
    ):  # noqa: E501
        account.manual_updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(account)
    needs_snapshot = req.manual_amount is not None or (
        account.asset_type == "REAL_ESTATE" and req.real_estate_details is not None
    )
    if needs_snapshot and account.manual_amount:
        await _upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=date.today(),
            amount_krw=_calc_manual_snap_amount(account),
            source="MANUAL",
        )
        await db.commit()
    if req.deposit_krw is not None or req.deposit_usd is not None:
        redis = await get_redis()
        usd_rate = await fetch_usd_krw(redis)
        latest_snap, pos_list = await get_latest_snapshot_with_positions(db, account.id)

        pos_value = sum(
            (float(p.current_price) if p.current_price else float(p.avg_price or 0)) * float(p.qty or 0)
            for p in pos_list
        )
        usd_as_krw = float(account.deposit_usd or 0) * usd_rate
        total = pos_value + float(account.deposit_krw or 0) + usd_as_krw
        new_snap = await _upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=date.today(),
            amount_krw=total,
            invested_amount=latest_snap.invested_amount if latest_snap else None,
            unrealized_pnl=latest_snap.unrealized_pnl if latest_snap else None,
            source="MANUAL",
        )
        # 스냅샷 포지션 복사 (기존 포지션 → 새 스냅샷)
        if pos_list:
            await sync_snapshot_positions(db, snapshot_id=new_snap.id, account_id=account.id, positions=pos_list)
        if latest_snap is not None and account.asset_type in _CASH_ASSET_TYPES:
            # 현금성 계좌는 시장가 변동이 없으므로 잔액 변화 = 순수 입출금.
            # 거래내역으로 기록하지 않으면 이 변화분이 통째로 "투자 수익"으로 오인되어
            # 홈탭 누적 수익률(Modified Dietz)이 왜곡된다. 최초 스냅샷(latest_snap is None)은
            # 기준값(base) 자체이므로 거래로 잡지 않는다 — 이중계산 방지.
            delta = total - float(latest_snap.amount_krw)
            if delta != 0:
                db.add(
                    Transaction(
                        user_id=account.user_id,
                        account_id=account.id,
                        transaction_type="DEPOSIT" if delta > 0 else "WITHDRAWAL",
                        amount=abs(delta),
                        transaction_date=date.today(),
                    )
                )
        await db.commit()

    _redis = await get_redis()
    await invalidate_asset_account_caches(_redis, account.user_id, account.id)
    return _account_response(account)


@router.delete("/{account_id}/kis-credentials", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account_kis_credentials(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """계좌별 KIS API 자격증명을 삭제한다. 이후 전역 자격증명으로 폴백된다."""
    from app.models.token import KisToken

    await _delete_account_credentials(
        account_id,
        current_user.id,
        db,
        app_key_attr="kis_app_key",
        app_secret_attr="kis_app_secret",  # nosec B106 — 속성명 문자열, 비밀번호 아님
        token_model=KisToken,
        redis_key=f"kis_token:account:{account_id}",
    )


@router.delete("/{account_id}/kiwoom-credentials", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account_kiwoom_credentials(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """계좌별 키움 API 자격증명을 삭제한다."""
    from app.models.token import KiwoomToken

    await _delete_account_credentials(
        account_id,
        current_user.id,
        db,
        app_key_attr="kiwoom_app_key",
        app_secret_attr="kiwoom_app_secret",  # nosec B106 — 속성명 문자열, 비밀번호 아님
        token_model=KiwoomToken,
        redis_key=f"kiwoom_token:account:{account_id}",
    )


async def _delete_account_credentials(
    account_id: UUID,
    user_id,
    db: AsyncSession,
    *,
    app_key_attr: str,
    app_secret_attr: str,
    token_model,
    redis_key: str,
) -> None:
    account = await _get_owned_account(account_id, user_id, db)
    setattr(account, app_key_attr, None)
    setattr(account, app_secret_attr, None)
    await db.execute(sql_delete(token_model).where(token_model.account_id == account_id))
    await db.commit()

    redis = await get_redis()
    await redis.delete(redis_key)
    await invalidate_user_caches(redis, account_detail_key(user_id, account_id))


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_owned_account(account_id, current_user.id, db)
    account.is_active = False
    await db.commit()
    await invalidate_asset_account_caches(await get_redis(), current_user.id, account_id)


@router.post("/{account_id}/sync")
@limiter.limit("5/minute")
async def sync_account(
    request: Request,
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_owned_account(account_id, current_user.id, db)
    redis = await get_redis()

    lock_key = f"sync_lock:{account_id}"
    async with redis_lock(redis, lock_key, ttl=120) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 동기화가 진행 중입니다. 잠시 후 다시 시도하세요.",
            )
        return await _do_sync(account, current_user, db, redis)


async def _do_sync(account: AssetAccount, current_user, db: AsyncSession, redis):
    """sync_account의 실제 동기화 로직 — redis_lock 내부에서 호출.

    SyncError/CircuitOpenError는 main.py 전역 핸들러가 처리한다.
    """
    snapshot = await _sync_account_service(account, db, redis)

    await invalidate_asset_account_caches(redis, current_user.id, account.id)
    return {
        "detail": "동기화 완료",
        "snapshot_date": str(snapshot.snapshot_date),
        "amount_krw": float(snapshot.amount_krw),
    }


@router.patch("/batch-target-portfolio", response_model=list[AssetAccountResponse])
@limiter.limit("30/minute")
async def batch_set_target_portfolio(
    request: Request,
    body: BatchSetTargetPortfolioRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """여러 계좌의 목표 포트폴리오를 일괄 지정하거나 해제한다.

    target_portfolio_id는 계좌 1개당 1개만 가리키는 단순 UI 라벨이다 — 실제 리밸런싱 분석
    대상 계좌 집합은 PortfolioAccount(M:N, Portfolio.account_ids)가 결정하며, 계좌 하나가
    여러 포트폴리오의 account_ids에 동시에 포함될 수 있으므로 두 값은 서로 독립적이다.
    """
    if not body.account_ids:
        return []
    accounts = await _list_accounts_by_ids(body.account_ids, current_user.id, db)
    if len(accounts) != len(body.account_ids):
        raise HTTPException(status_code=403, detail="접근 권한이 없는 계좌가 포함되어 있습니다")
    for account in accounts:
        account.target_portfolio_id = body.portfolio_id
    await db.commit()
    for account in accounts:
        await db.refresh(account)
    return [_account_response(a) for a in accounts]


@router.patch("/{account_id}/target-portfolio", response_model=AssetAccountResponse)
@limiter.limit("30/minute")
async def set_target_portfolio(
    request: Request,
    account_id: UUID,
    body: SetTargetPortfolioRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """계좌의 목표 포트폴리오를 지정하거나 해제한다."""
    account = await _get_owned_account(account_id, current_user.id, db)
    account.target_portfolio_id = body.target_portfolio_id
    await db.commit()
    await db.refresh(account)
    return _account_response(account)
