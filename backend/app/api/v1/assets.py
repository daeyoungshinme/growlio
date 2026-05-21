import asyncio
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.kis.client import KisApiError
from app.models.asset import AssetAccount, AssetSnapshot
from app.models.user import User, UserSettings
from app.redis_client import get_redis
from app.schemas.asset import (
    AssetAccountCreate,
    AssetAccountResponse,
    AssetAccountUpdate,
    AssetSnapshotResponse,
)
from app.services.asset_service import (
    _upsert_snapshot,
    sync_kis_account,
    sync_manual_account,
    sync_openbanking_account,
)
from app.limiter import limiter
from app.services.credential_service import encrypt
from app.services.price_service import fetch_prices_batch

OVERSEAS_MARKETS = {"NYSE", "NASDAQ", "AMEX"}


def _account_response(account: AssetAccount) -> AssetAccountResponse:
    """AssetAccount ORM 모델을 Response 스키마로 변환 (has_own_kis_credentials 계산 포함)."""
    data = AssetAccountResponse.model_validate(account)
    data.has_own_kis_credentials = bool(account.kis_app_key)
    return data


_VALID_MARKETS = {"KOSPI", "KOSDAQ", "NYSE", "NASDAQ", "AMEX", "OTHER"}


class ManualPosition(BaseModel):
    ticker: str
    name: str
    market: str = "KOSPI"
    qty: float
    avg_price: float          # 항상 KRW — 해외종목은 프론트에서 환율 적용 후 전송
    avg_price_usd: float | None = None   # 원본 달러 입력값 (표시용)
    usd_rate: float | None = None        # 평단가 환산에 사용한 환율
    current_price: float | None = None   # 항상 KRW

    @field_validator("ticker")
    @classmethod
    def ticker_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("티커는 빈 값일 수 없습니다")
        return v.strip().upper()

    @field_validator("qty")
    @classmethod
    def qty_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("수량은 0보다 커야 합니다")
        return v

    @field_validator("avg_price")
    @classmethod
    def avg_price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("평균단가는 0보다 커야 합니다")
        return v

    @field_validator("market")
    @classmethod
    def market_valid(cls, v: str) -> str:
        if v not in _VALID_MARKETS:
            raise ValueError(f"유효하지 않은 시장: {v}. 허용값: {sorted(_VALID_MARKETS)}")
        return v

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetAccountResponse])
async def list_accounts(
    skip: int = 0,
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AssetAccount)
        .where(AssetAccount.user_id == current_user.id, AssetAccount.is_active == True)  # noqa: E712
        .order_by(AssetAccount.sort_order, AssetAccount.created_at)
        .offset(skip)
        .limit(limit)
    )
    return [_account_response(a) for a in result.scalars().all()]


@router.post("", response_model=AssetAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    req: AssetAccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.data_source == "KIS_API":
        if not req.kis_account_no:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="KIS 계좌번호를 입력하세요.")

        req_data = req.model_dump(exclude={"kis_app_key", "kis_app_secret"})

        if req.kis_app_key and req.kis_app_secret:
            # 계좌별 자격증명 사용
            req_data["kis_app_key"] = encrypt(req.kis_app_key)
            req_data["kis_app_secret"] = encrypt(req.kis_app_secret)
        else:
            # 전역 자격증명 확인 (폴백용)
            settings = await db.get(UserSettings, current_user.id)
            if not settings or not settings.kis_app_key:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="KIS API 자격증명이 없습니다. 계좌별 API 키를 입력하거나, 설정 > KIS 연동에서 먼저 등록하세요.",
                )
            req_data["is_mock_mode"] = settings.kis_is_mock
            req_data["kis_app_key"] = None
            req_data["kis_app_secret"] = None

        account = AssetAccount(user_id=current_user.id, **req_data)
    else:
        exclude_creds = {"kis_app_key", "kis_app_secret"}
        account = AssetAccount(user_id=current_user.id, **req.model_dump(exclude=exclude_creds))
    db.add(account)
    await db.commit()
    await db.refresh(account)
    if account.manual_amount:
        snap_amount = float(account.manual_amount)
        if account.asset_type == "REAL_ESTATE":
            mortgage = float((account.real_estate_details or {}).get("mortgage_balance_krw", 0) or 0)
            snap_amount = snap_amount - mortgage
        await _upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=date.today(),
            amount_krw=snap_amount,
            source="MANUAL",
        )
        await db.commit()
    return _account_response(account)


@router.get("/snapshots/range", response_model=list[AssetSnapshotResponse])
async def get_snapshots(
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 365,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(AssetSnapshot).where(AssetSnapshot.user_id == current_user.id)
    if start_date:
        query = query.where(AssetSnapshot.snapshot_date >= start_date)
    if end_date:
        query = query.where(AssetSnapshot.snapshot_date <= end_date)
    query = query.order_by(AssetSnapshot.snapshot_date.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{account_id}", response_model=AssetAccountResponse)
async def get_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_owned_account(account_id, current_user.id, db)
    return _account_response(account)


@router.put("/{account_id}", response_model=AssetAccountResponse)
async def update_account(
    account_id: UUID,
    req: AssetAccountUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_owned_account(account_id, current_user.id, db)

    # 계좌별 KIS 자격증명 업데이트 처리 (암호화 필요, 별도 처리)
    update_fields = req.model_dump(exclude_none=True, exclude={"kis_app_key", "kis_app_secret"})
    for field, value in update_fields.items():
        setattr(account, field, value)

    if req.kis_app_key is not None:
        account.kis_app_key = encrypt(req.kis_app_key) if req.kis_app_key else None
        account.kis_app_secret = encrypt(req.kis_app_secret) if req.kis_app_secret else None

    if req.manual_amount is not None or req.deposit_krw is not None or req.real_estate_details is not None:  # noqa: E501
        account.manual_updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(account)
    needs_snapshot = req.manual_amount is not None or (
        account.asset_type == "REAL_ESTATE" and req.real_estate_details is not None
    )
    if needs_snapshot and account.manual_amount:
        snap_amount = float(account.manual_amount)
        if account.asset_type == "REAL_ESTATE":
            mortgage = float((account.real_estate_details or {}).get("mortgage_balance_krw", 0) or 0)
            snap_amount = snap_amount - mortgage
        await _upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=date.today(),
            amount_krw=snap_amount,
            source="MANUAL",
        )
        await db.commit()
    if req.deposit_krw is not None:
        latest_snap = await db.scalar(
            select(AssetSnapshot)
            .where(AssetSnapshot.account_id == account.id)
            .order_by(AssetSnapshot.snapshot_date.desc())
            .limit(1)
        )
        pos_list = (latest_snap.positions if latest_snap else None) or account.manual_positions or []
        pos_value = sum(
            (p.get("current_price") or p.get("avg_price", 0)) * p.get("qty", 0)
            for p in pos_list
        )
        total = pos_value + float(account.deposit_krw or 0)
        await _upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=date.today(),
            amount_krw=total,
            invested_amount=latest_snap.invested_amount if latest_snap else None,
            unrealized_pnl=latest_snap.unrealized_pnl if latest_snap else None,
            positions=latest_snap.positions if latest_snap else None,
            source="MANUAL",
        )
        await db.commit()
    return _account_response(account)


@router.delete("/{account_id}/kis-credentials", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account_kis_credentials(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """계좌별 KIS API 자격증명을 삭제한다. 이후 전역 자격증명으로 폴백된다."""
    from sqlalchemy import delete as sql_delete

    from app.models.token import KisToken
    from app.redis_client import get_redis

    account = await _get_owned_account(account_id, current_user.id, db)
    account.kis_app_key = None
    account.kis_app_secret = None
    await db.execute(sql_delete(KisToken).where(KisToken.account_id == account_id))
    await db.commit()

    redis = await get_redis()
    await redis.delete(f"kis_token:account:{account_id}")


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_owned_account(account_id, current_user.id, db)
    account.is_active = False
    await db.commit()


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

    if account.data_source == "KIS_API":
        try:
            snapshot = await sync_kis_account(account, db, redis)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="KIS API 오류: 모의투자/실계좌 설정을 확인하세요. (계정번호, 앱키, 모드가 일치해야 합니다)",
                )
            try:
                kis_body = e.response.json()
                msg = kis_body.get("msg1") or str(e)
            except Exception:
                msg = str(e)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"KIS API 오류: {msg}")
        except KisApiError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"KIS 계좌 조회 실패: {e.msg} (rt_cd={e.rt_cd}). 계좌 유형이 지원되지 않거나 API 권한이 없을 수 있습니다.",
            )
        except (httpx.ConnectError, httpx.TimeoutException):
            raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="KIS 서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.")
        except RuntimeError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    elif account.data_source == "OPEN_BANKING":
        snapshot = await sync_openbanking_account(account, db)
    elif account.data_source == "MANUAL":
        snapshot = await sync_manual_account(account, db, redis)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"지원하지 않는 데이터 소스: {account.data_source}")

    await redis.delete(f"dividend:by-ticker:{current_user.id}:{date.today().year}")
    return {"detail": "동기화 완료", "snapshot_date": str(snapshot.snapshot_date), "amount_krw": float(snapshot.amount_krw)}


@router.get("/{account_id}/positions")
async def get_positions(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """수동 종목 목록 조회 (매입합계·평가합계·수익률 포함)."""
    account = await _get_owned_account(account_id, current_user.id, db)
    positions = account.manual_positions or []
    return _enrich_positions(positions)


@router.put("/{account_id}/positions")
async def save_positions(
    account_id: UUID,
    positions: list[ManualPosition],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """수동 종목 저장 — 매입금액 합계를 manual_amount로 업데이트."""
    account = await _get_owned_account(account_id, current_user.id, db)
    raw = [p.model_dump() for p in positions]
    account.manual_positions = raw
    total_invested = sum(p.qty * p.avg_price for p in positions)
    total_value = sum((p.current_price or p.avg_price) * p.qty for p in positions)
    account.manual_amount = total_value  # 평가금액 기준 (current_price 없으면 avg_price 대체)
    account.manual_updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(account)
    await _upsert_snapshot(
        db,
        account_id=account.id,
        user_id=account.user_id,
        snapshot_date=date.today(),
        amount_krw=total_value + float(account.deposit_krw or 0),
        invested_amount=total_invested,
        unrealized_pnl=total_value - total_invested,
        positions=raw,
        source="MANUAL",
    )
    await db.commit()
    return _enrich_positions(raw)


@router.post("/{account_id}/positions/sync-prices")
async def sync_position_prices(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """현재가를 조회해 manual_positions를 갱신하고 스냅샷을 저장한다."""
    account = await _get_owned_account(account_id, current_user.id, db)
    positions = account.manual_positions or []
    if not positions:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="저장된 종목이 없습니다")

    redis = await get_redis()
    tickers = [(p["ticker"], p.get("market", "KOSPI")) for p in positions]
    price_map = await fetch_prices_batch(current_user.id, tickers, db, redis)

    # 해외 종목이 있으면 환율 조회 (USD → KRW 변환)
    has_overseas = any(p.get("market", "KOSPI") in OVERSEAS_MARKETS for p in positions)
    usd_rate: float | None = None
    if has_overseas:
        from app.api.v1.stocks import _sync_usdkrw
        loop = asyncio.get_event_loop()
        usd_rate = await loop.run_in_executor(None, _sync_usdkrw)

    updated = []
    for p in positions:
        raw_price = price_map.get(p["ticker"])
        if raw_price and p.get("market", "KOSPI") in OVERSEAS_MARKETS and usd_rate:
            # yfinance에서 가져온 USD 가격 → KRW 변환
            price_krw = raw_price * usd_rate
        elif raw_price:
            price_krw = raw_price
        else:
            price_krw = p.get("current_price") or p["avg_price"]
        updated.append({**p, "current_price": price_krw})

    account.manual_positions = updated
    account.manual_updated_at = datetime.now(UTC)

    # 평가금액 합계 → manual_amount 갱신 & 스냅샷 저장
    total_value = sum(p["current_price"] * p["qty"] for p in updated)
    total_invested = sum(p["avg_price"] * p["qty"] for p in updated)
    account.manual_amount = total_value

    await _upsert_snapshot(
        db,
        account_id=account.id,
        user_id=account.user_id,
        snapshot_date=date.today(),
        amount_krw=total_value + float(account.deposit_krw or 0),
        invested_amount=total_invested,
        unrealized_pnl=total_value - total_invested,
        positions=updated,
        source="MANUAL",
    )
    await db.commit()

    return _enrich_positions(updated)


def _enrich_positions(positions: list[dict[str, Any]]) -> dict[str, Any]:
    """합계·수익률을 계산해 응답 형태로 변환."""
    items = []
    total_invested = 0.0
    total_value = 0.0

    for p in positions:
        qty = p.get("qty", 0)
        avg = p.get("avg_price", 0.0)
        cur = p.get("current_price") or avg
        invested = qty * avg
        value = qty * cur
        pnl = value - invested
        pnl_pct = (pnl / invested * 100) if invested else 0.0
        total_invested += invested
        total_value += value
        items.append({
            **p,
            "current_price": cur,
            "invested_amount": invested,
            "value_amount": value,
            "pnl": pnl,
            "pnl_pct": round(pnl_pct, 2),
        })

    total_pnl = total_value - total_invested
    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested else 0.0
    return {
        "positions": items,
        "summary": {
            "total_invested": total_invested,
            "total_value": total_value,
            "total_pnl": total_pnl,
            "total_pnl_pct": round(total_pnl_pct, 2),
        },
    }


async def _get_owned_account(account_id: UUID, user_id, db: AsyncSession) -> AssetAccount:
    account = await db.scalar(
        select(AssetAccount).where(
            AssetAccount.id == account_id,
            AssetAccount.user_id == user_id,
            AssetAccount.is_active == True,  # noqa: E712
        )
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계좌를 찾을 수 없습니다")
    return account
