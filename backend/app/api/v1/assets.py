from datetime import UTC, datetime
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, get_owned_or_404
from app.api.v1 import positions as _positions_module
from app.api.v1._account_deps import get_owned_account as _get_owned_account
from app.core.cache_store import get_cache_store
from app.exceptions import BadRequestError
from app.kis.auth import promote_user_token_to_account
from app.kiwoom.client import KiwoomTokenIssueError
from app.limiter import account_rate_limit_key, limiter
from app.models.alert import RebalancingAlert
from app.models.asset import AssetAccount, Transaction
from app.models.fx_extra_need import FxExtraNeed
from app.models.portfolio import Portfolio
from app.models.user import User
from app.schemas.asset import (
    AssetAccountCreate,
    AssetAccountResponse,
    AssetAccountUpdate,
    BatchSetTargetPortfolioRequest,
    IsaPnlOverrideUpdate,
    KisCredentialVerifyRequest,
    KiwoomCredentialVerifyRequest,
    TossCredentialVerifyRequest,
)
from app.services.accounts._account_queries import portfolio_accounts_stmt
from app.services.accounts.asset_credential_service import (
    BROKER_CREDENTIAL_SPECS,
    CREDENTIAL_FIELDS,
    BrokerCredentialSpec,
    clear_issued_token_cache,
    delete_credentials,
    delete_issued_tokens,
)
from app.services.accounts.asset_credential_service import (
    verify_kis_credentials as _verify_kis_credentials_service,
)
from app.services.accounts.asset_credential_service import (
    verify_kiwoom_credentials as _verify_kiwoom_credentials_service,
)
from app.services.accounts.asset_credential_service import (
    verify_toss_credentials as _verify_toss_credentials_service,
)
from app.services.accounts.asset_service import (
    list_accounts as _list_accounts,
)
from app.services.accounts.asset_service import (
    list_accounts_by_ids as _list_accounts_by_ids,
)
from app.services.accounts.asset_service import (
    sync_account_now as _sync_account_now,
)
from app.services.accounts.credential_service import encrypt, encrypt_if_present
from app.services.accounts.snapshot_service import (
    get_latest_snapshot_with_positions,
    upsert_snapshot,
    write_manual_deposit_snapshot,
)
from app.services.accounts.sync_all_service import get_sync_all_status, is_sync_all_running, run_sync_all
from app.services.tax.isa_service import calc_account_auto_pnl
from app.utils.cache_invalidation import invalidate_asset_account_caches
from app.utils.cache_keys import sync_lock_key
from app.utils.currency import require_live_usd_krw
from app.utils.inproc_lock import inproc_lock
from app.utils.kst import today_kst
from app.utils.pnl import calc_net_asset_amount

# 시장가 변동이 없는 순수 현금성 계좌 — 잔액 변경은 전액 입출금으로 간주
_CASH_ASSET_TYPES: set[str] = {"BANK_ACCOUNT", "DEPOSIT", "CASH_OTHER"}


def _account_response(account: AssetAccount) -> AssetAccountResponse:
    """AssetAccount ORM 모델을 Response 스키마로 변환."""
    data = AssetAccountResponse.model_validate(account)
    for spec in BROKER_CREDENTIAL_SPECS.values():
        setattr(data, spec.has_own_attr, bool(getattr(account, spec.key_attr)))
    return data


router = APIRouter(prefix="/assets", tags=["assets"])
router.include_router(_positions_module.router)


def _calc_manual_snap_amount(account: AssetAccount) -> float:
    """manual_amount에서 부동산 모기지를 차감한 스냅샷 저장용 금액을 반환한다."""
    return calc_net_asset_amount(account.manual_amount, account.asset_type, account.real_estate_details)


@router.get("", response_model=list[AssetAccountResponse])
async def list_accounts(
    # 음수 skip은 Postgres OFFSET 오류로 500이 났고 limit은 상한이 없었다(plans/118 B4)
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    accounts = await _list_accounts(current_user.id, db, skip=skip, limit=limit)
    return [_account_response(a) for a in accounts]


_KIS_INVALID_CREDENTIALS = "KIS 자격증명이 잘못되었습니다. App Key/Secret 및 모드를 확인하세요."
_KIWOOM_INVALID_CREDENTIALS = "키움 자격증명이 잘못되었습니다. App Key/Secret 및 모의/실계좌 모드를 확인하세요."
_TOSS_INVALID_CREDENTIALS = "토스 자격증명이 잘못되었습니다. Client ID/Secret을 확인하세요."


def _verify_http_error(e: httpx.HTTPError, label: str, invalid_detail: str) -> HTTPException:
    """자격증명 검증 라우트 공통 HTTP 오류 매핑: 400/401/403 → 400(잘못된 키), 그 외 상태 → 502,
    연결 실패/타임아웃 → 504."""
    if isinstance(e, httpx.HTTPStatusError):
        if e.response.status_code in (400, 401, 403):
            return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=invalid_detail)
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=f"{label} 서버 오류. 잠시 후 다시 시도하세요."
        )
    return HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail=f"{label} 서버에 연결하지 못했습니다. 잠시 후 다시 시도하세요.",
    )


@router.post("/verify-kis-credentials")
@limiter.limit("10/minute")
async def verify_kis_credentials(
    request: Request,
    req: KisCredentialVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    """KIS 자격증명 유효성 확인 (계좌 생성 없이)."""
    cache = await get_cache_store()
    try:
        await _verify_kis_credentials_service(
            req.kis_app_key,
            req.kis_app_secret,
            req.is_mock,
            current_user.id,
            cache,
        )
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
        raise _verify_http_error(e, "KIS", _KIS_INVALID_CREDENTIALS) from e
    return {"valid": True, "message": "KIS 자격증명이 확인되었습니다."}


@router.post("/verify-kiwoom-credentials")
@limiter.limit("10/minute")
async def verify_kiwoom_credentials(
    request: Request,
    req: KiwoomCredentialVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    """키움 자격증명 유효성 확인 (계좌 생성 없이)."""
    try:
        await _verify_kiwoom_credentials_service(req.kiwoom_app_key, req.kiwoom_app_secret, req.is_mock)
    except KiwoomTokenIssueError as e:
        # 키움은 잘못된 키에 HTTP 200 + return_code != 0으로 응답한다 (kiwoom/auth.py _request_token)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_KIWOOM_INVALID_CREDENTIALS,
        ) from e
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
        raise _verify_http_error(e, "키움", _KIWOOM_INVALID_CREDENTIALS) from e
    return {"valid": True, "message": "키움 자격증명이 확인되었습니다."}


@router.post("/verify-toss-credentials")
@limiter.limit("10/minute")
async def verify_toss_credentials(
    request: Request,
    req: TossCredentialVerifyRequest,
    current_user: User = Depends(get_current_user),
):
    """토스 자격증명 유효성 확인 (계좌 생성 없이)."""
    from app.toss.client import TossApiError

    try:
        await _verify_toss_credentials_service(req.toss_client_id, req.toss_client_secret)
    except TossApiError as e:
        if e.status_code == 403 or e.code in ("edge-blocked", "forbidden"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="토스 API 접근이 거부되었습니다. 토스 'Open API → IP 관리'에 서버 IP를 등록했는지 확인하세요.",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"토스 자격증명이 잘못되었습니다: {e.message}",
        ) from e
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
        raise _verify_http_error(e, "토스", _TOSS_INVALID_CREDENTIALS) from e
    return {"valid": True, "message": "토스 자격증명이 확인되었습니다."}


@router.post("", response_model=AssetAccountResponse, status_code=status.HTTP_201_CREATED)
async def create_account(
    req: AssetAccountCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    req_data = req.model_dump(exclude=CREDENTIAL_FIELDS)
    spec = BROKER_CREDENTIAL_SPECS.get(req.data_source)
    if spec is not None:
        key, secret = getattr(req, spec.key_attr), getattr(req, spec.secret_attr)
        account_no_missing = spec.required_account_no_attr is not None and not getattr(
            req, spec.required_account_no_attr
        )
        if account_no_missing or not key or not secret:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=spec.missing_detail)
        req_data[spec.key_attr] = encrypt(key)
        req_data[spec.secret_attr] = encrypt(secret)
        if spec.forced_asset_type is not None:
            req_data["asset_type"] = spec.forced_asset_type
    account = AssetAccount(user_id=current_user.id, **req_data)
    db.add(account)
    await db.commit()
    await db.refresh(account)
    if req.data_source == "KIS_API":
        # 직전 "자격증명 확인" 단계에서 발급된 유저 레벨 토큰을 이 계좌로 승격 —
        # 등록 직후 프론트가 자동으로 호출하는 첫 동기화가 새 토큰을 또 발급받으려다
        # KIS 토큰 발급 속도 제한에 걸려 실패하는 것을 방지한다.
        cache = await get_cache_store()
        await promote_user_token_to_account(str(current_user.id), str(account.id), account.is_mock_mode, cache, db)
    if account.manual_amount:
        await upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=today_kst(),
            amount_krw=_calc_manual_snap_amount(account),
            source="MANUAL",
        )
        await db.commit()
    # 새 계좌(특히 수동 금액 스냅샷)가 대시보드·월별 추이·추천 집계에 바로 반영되도록
    await invalidate_asset_account_caches(await get_cache_store(), current_user.id)
    return _account_response(account)


@router.put("/{account_id}", response_model=AssetAccountResponse)
async def update_account(
    account_id: UUID,
    req: AssetAccountUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_owned_account(account_id, current_user.id, db)

    # 비활성화는 DELETE만 — 수정 경로로 꺼면 자동화 중단·자격증명 삭제 정리를 건너뛴다(plans/110 D10)
    if req.is_active is False:
        raise BadRequestError("계좌를 비활성화하려면 삭제 기능을 사용해주세요")

    update_fields = req.model_dump(exclude_none=True, exclude=CREDENTIAL_FIELDS | {"is_active"})
    for field, value in update_fields.items():
        setattr(account, field, value)
    # 지울 수 있는 항목만 null을 반영한다 — 금액·이름 등은 null이어도 기존 값 유지
    for field in _CLEARABLE_ACCOUNT_FIELDS & req.model_fields_set:
        if getattr(req, field) is None:
            setattr(account, field, None)

    # 키가 전송된 브로커만 키·시크릿 쌍을 함께 교체 (시크릿만 단독 전송은 무시 — 기존 동작 유지).
    # 옛 키로 발급된 토큰도 지운다 — 남기면 만료 전까지 옛 키 토큰으로 동기화한다(plans/116 B1).
    stale_token_specs: list[BrokerCredentialSpec] = []
    for spec in BROKER_CREDENTIAL_SPECS.values():
        if getattr(req, spec.key_attr) is not None:
            setattr(account, spec.key_attr, encrypt_if_present(getattr(req, spec.key_attr)))
            setattr(account, spec.secret_attr, encrypt_if_present(getattr(req, spec.secret_attr)))
            await delete_issued_tokens(db, account.id, spec)
            stale_token_specs.append(spec)

    if (
        req.manual_amount is not None
        or req.deposit_krw is not None
        or req.deposit_usd is not None
        or req.real_estate_details is not None
    ):
        account.manual_updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(account)
    if stale_token_specs:
        token_cache = await get_cache_store()
        for spec in stale_token_specs:
            await clear_issued_token_cache(token_cache, account.id, spec)

    # 두 블록이 참조할 "요청 시작 시점의" 최신 스냅샷/포지션을 한 번만 조회해 재사용.
    # 블록 1이 오늘자 스냅샷을 먼저 써버리면 아래 조회가 포지션 0개인 방금 쓴 스냅샷을
    # latest로 잘못 인식해 주식 평가액이 누락되는 버그(STOCK_OTHER 계좌)를 방지한다.
    latest_snap, pos_list = await get_latest_snapshot_with_positions(db, account.id)

    needs_snapshot = req.manual_amount is not None or (
        account.asset_type == "REAL_ESTATE" and req.real_estate_details is not None
    )
    deposit_trigger = req.deposit_krw is not None or req.deposit_usd is not None
    if needs_snapshot and account.manual_amount and not deposit_trigger:
        await upsert_snapshot(
            db,
            account_id=account.id,
            user_id=account.user_id,
            snapshot_date=today_kst(),
            amount_krw=_calc_manual_snap_amount(account),
            source="MANUAL",
        )
        await db.commit()
    if deposit_trigger:
        cache = await get_cache_store()
        # 현금 계좌는 아래에서 차액이 영구 입출금 행이 된다 — 달러 잔액을 fallback 환율로 환산해 기록하면 되돌릴 수 없다
        usd_rate = await require_live_usd_krw(cache) if account.deposit_usd else 1.0
        _, total = await write_manual_deposit_snapshot(
            db, account, latest_snap=latest_snap, positions=pos_list, usd_rate=usd_rate
        )
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
                        transaction_date=today_kst(),
                    )
                )
        await db.commit()

    _cache = await get_cache_store()
    await invalidate_asset_account_caches(_cache, account.user_id)
    return _account_response(account)


async def _delete_own_credentials(account_id: UUID, user: User, db: AsyncSession, data_source: str) -> None:
    account = await _get_owned_account(account_id, user.id, db)
    await delete_credentials(account, db, await get_cache_store(), BROKER_CREDENTIAL_SPECS[data_source])


def _credential_delete_route(data_source: str):
    async def delete_account_credentials(
        account_id: UUID,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        await _delete_own_credentials(account_id, current_user, db, data_source)

    return delete_account_credentials


for _slug, _data_source, _label in (
    ("kis", "KIS_API", "KIS API"),
    ("kiwoom", "KIWOOM_API", "키움 API"),
    ("toss", "TOSS_API", "토스 Open API"),
):
    router.add_api_route(
        f"/{{account_id}}/{_slug}-credentials",
        _credential_delete_route(_data_source),
        methods=["DELETE"],
        status_code=status.HTTP_204_NO_CONTENT,
        summary=f"계좌별 {_label} 자격증명 삭제",
    )


_CLEARABLE_ACCOUNT_FIELDS = {"notes", "institution", "investment_horizon"}


async def _stop_automation_for_account(account_id: UUID, db: AsyncSession) -> None:
    """이 계좌로 주문하는 알림을 끄고 대기 매수를 취소한다. commit은 호출자가 한다."""
    from app.services.rebalancing.plan_execution import cancel_pending_buy_legs

    alerts = await db.scalars(
        select(RebalancingAlert).where(
            RebalancingAlert.account_id == account_id,
            or_(RebalancingAlert.mode == "AUTO", RebalancingAlert.alert_scope == "PER_ACCOUNT"),
        )
    )
    for alert in alerts.all():
        alert.is_active = False
        await cancel_pending_buy_legs(db, alert_id=alert.id)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_owned_account(account_id, current_user.id, db)
    account.is_active = False
    await _stop_automation_for_account(account.id, db)
    # 소프트 삭제라 FK SET NULL이 안 걸린다 — 추가 환전 보관 계좌 지정을 직접 푼다(plans/126 A4)
    await db.execute(
        update(FxExtraNeed).where(FxExtraNeed.reserved_account_id == account.id).values(reserved_account_id=None)
    )
    cache = await get_cache_store()
    # 삭제 계좌는 복구 경로가 없다 — 쓸 일 없는 App Key·토큰을 남겨두지 않는다(commit 포함)
    spec = BROKER_CREDENTIAL_SPECS.get(account.data_source)
    if spec is not None:
        await delete_credentials(account, db, cache, spec)
    else:
        await db.commit()
    await invalidate_asset_account_caches(cache, current_user.id)


@router.post("/{account_id}/sync")
@limiter.limit("5/minute", key_func=account_rate_limit_key)
@limiter.limit("30/minute")
async def sync_account(
    request: Request,
    account_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_owned_account(account_id, current_user.id, db)
    await db.commit()  # 브로커 동기화(느린 외부 HTTP 호출) 전 요청 DB 커넥션 풀 슬롯을 미리 반환
    cache = await get_cache_store()

    lock_key = sync_lock_key(account_id)
    async with inproc_lock(cache, lock_key, ttl=120) as acquired:
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 동기화가 진행 중입니다. 잠시 후 다시 시도하세요.",
            )
        return await _sync_account_now(account, cache)


@router.post("/sync-all")
@limiter.limit("3/minute")
async def sync_all_accounts(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """전체 계좌("투자현황" 대상)를 백그라운드로 동기화한다.

    요청은 즉시 반환하고, 실제 동기화는 세마포어 기반 배치 로직으로 처리된다
    (요청 DB 커넥션을 오래 붙잡지 않아 다른 화면 조회를 막지 않음).
    """
    if await is_sync_all_running(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 전체 동기화가 진행 중입니다. 잠시 후 다시 시도하세요.",
        )

    result = await db.execute(portfolio_accounts_stmt(current_user.id))
    accounts = result.scalars().all()

    background_tasks.add_task(run_sync_all, current_user.id, list(accounts))

    return {"total": len(accounts), "status": "started"}


@router.get("/sync-all/status")
async def get_sync_all_status_endpoint(
    current_user: User = Depends(get_current_user),
):
    """ "전체 갱신" 진행 상태를 조회한다 (프론트 폴링용)."""
    return await get_sync_all_status(current_user.id)


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
    if body.portfolio_id is not None:
        await get_owned_or_404(db, Portfolio, body.portfolio_id, current_user.id, "포트폴리오를 찾을 수 없습니다")
    # 중복 ID가 있으면 조회 결과 수와 어긋나 정상 요청도 403이 났다(plans/119 B5)
    account_ids = list(dict.fromkeys(body.account_ids))
    accounts = await _list_accounts_by_ids(account_ids, current_user.id, db)
    if len(accounts) != len(account_ids):
        raise HTTPException(status_code=403, detail="접근 권한이 없는 계좌가 포함되어 있습니다")
    for account in accounts:
        account.target_portfolio_id = body.portfolio_id
    await db.commit()
    for account in accounts:
        await db.refresh(account)
    return [_account_response(a) for a in accounts]


@router.patch("/{account_id}/isa-pnl-override", response_model=AssetAccountResponse)
@limiter.limit("30/minute")
async def update_isa_pnl_override(
    request: Request,
    account_id: UUID,
    body: IsaPnlOverrideUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """ISA 계좌의 누적 손익 기준선을 설정하거나(값 전송) 해제한다(null 전송, 자동 추정치로 복귀).

    값 설정 시 그 순간의 시스템 자동 추정치(auto_pnl)를 함께 캡처해두고, 이후 조회 시점의
    auto_pnl과의 차이(가격변동·신규배당)를 기준값에 더해 계속 자동으로 갱신한다.
    """
    account = await _get_owned_account(account_id, current_user.id, db)
    if account.tax_type != "ISA":
        raise HTTPException(status_code=400, detail="ISA 계좌에만 손익 수동 입력을 설정할 수 있습니다.")
    account.isa_manual_cumulative_pnl_krw = body.cumulative_pnl_krw
    if body.cumulative_pnl_krw is not None:
        account.isa_baseline_auto_pnl_krw = await calc_account_auto_pnl(current_user.id, account.id, db)
        account.isa_baseline_captured_at = today_kst()
    else:
        account.isa_baseline_auto_pnl_krw = None
        account.isa_baseline_captured_at = None
    await db.commit()
    await db.refresh(account)
    # 이 값은 ISA 현황·절세 액션(둘 다 캐시 없이 매번 계산)만 읽는다 — 계좌 캐시 전체 무효화는 목표 추천
    # 세대 교체(콜드 MVO 재계산)까지 일으켜 불필요하다
    return _account_response(account)
