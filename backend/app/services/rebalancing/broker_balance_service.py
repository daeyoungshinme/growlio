"""KIS/키움 계좌 실시간 잔고 조회 — api/v1/rebalancing.py의 broker-balance 엔드포인트 전용 헬퍼."""

from __future__ import annotations

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.kis.auth import get_access_token
from app.kis.balance import get_orderable_cash
from app.models.asset import AssetAccount
from app.providers.base import BrokerProvider
from app.providers.kis_provider import KISProvider
from app.providers.kiwoom_provider import KiwoomProvider
from app.schemas.rebalancing import KisBalancePosition, KisBalanceResponse
from app.services.credential_service import decrypt_kis_credentials

logger = structlog.get_logger()


async def fetch_broker_balance(
    account: AssetAccount,
    db: AsyncSession,
    cache,
) -> KisBalanceResponse:
    """KIS 또는 키움 계좌 실시간 잔고를 조회해 KisBalanceResponse로 반환한다.

    실제 조회는 BrokerProvider(KISProvider/KiwoomProvider)에 위임한다 — 자격증명 검증,
    토큰 갱신-재시도, 원화 포지션 변환은 sync_account()가 쓰는 것과 동일한 provider
    경로를 공유한다. 실패 시 SyncError 계층 예외(ProviderCredentialError 등)가 그대로
    전파되며 main.py 전역 핸들러가 HTTP 응답으로 변환한다.
    """
    if account.asset_type == "STOCK_KIS":
        provider: BrokerProvider = KISProvider()
    elif account.asset_type == "STOCK_KIWOOM":
        provider = KiwoomProvider()
    else:
        raise ValueError(f"지원하지 않는 계좌 유형: {account.asset_type}")

    result = await provider.sync(account, db, cache)

    orderable_krw: float | None = None
    if account.asset_type == "STOCK_KIS" and account.kis_app_key and account.kis_app_secret and account.kis_account_no:
        try:
            creds = decrypt_kis_credentials(account)
            if creds is None:
                raise ValueError("KIS credentials are not configured for this account")
            app_key, app_secret = creds
            access_token = await get_access_token(
                app_key,
                app_secret,
                is_mock=account.is_mock_mode,
                cache=cache,
                db=db,
                user_id=str(account.user_id),
                account_id=str(account.id),
            )
            orderable_krw = await get_orderable_cash(
                app_key, app_secret, access_token, account.kis_account_no, is_mock=account.is_mock_mode
            )
        except Exception as e:
            logger.warning("orderable_cash_fetch_failed", account_id=str(account.id), error=str(e))

    positions = [
        KisBalancePosition(
            ticker=p.ticker,
            name=p.name,
            market=p.market,
            quantity=p.qty,
            avg_price=p.avg_price,
            current_price=p.current_price,
            value_krw=p.value_krw,
        )
        for p in result.positions
    ]
    return KisBalanceResponse(
        account_id=str(account.id),
        account_name=account.name,
        is_mock=account.is_mock_mode,
        positions=positions,
        deposit_krw=result.deposit_krw,
        orderable_krw=orderable_krw,
    )
