"""금융결제원 오픈뱅킹 브로커 프로바이더."""
from __future__ import annotations

import secrets
from datetime import date
from typing import Any

import structlog
from sqlalchemy import select

from app.exceptions import ProviderCredentialError
from app.providers.base import BalanceResult, BrokerProvider

logger = structlog.get_logger()


class OpenBankingProvider(BrokerProvider):
    PROVIDER_ID = "OPEN_BANKING"
    PROVIDER_NAME = "금융결제원 오픈뱅킹"

    async def sync(self, account: Any, db: Any, redis: Any) -> BalanceResult:
        from app.models.user import UserSettings
        from app.providers.openbanking import ensure_ob_token_fresh, get_account_balance

        settings_row = await db.scalar(
            select(UserSettings).where(UserSettings.user_id == account.user_id)
        )
        if not settings_row or not settings_row.ob_access_token:
            raise ProviderCredentialError("오픈뱅킹 토큰이 없습니다. 다시 연결해주세요.")
        if not account.ob_fintech_use_no:
            raise ProviderCredentialError("오픈뱅킹 핀테크이용번호가 없습니다")

        access_token = await ensure_ob_token_fresh(settings_row, db)
        bank_tran_id = f"M{date.today().year:04d}00001U{secrets.token_hex(4).upper()}"
        data = await get_account_balance(
            access_token=access_token,
            fintech_use_no=account.ob_fintech_use_no,
            bank_tran_id=bank_tran_id,
        )

        balance_amt = float(data.get("balance_amt", 0))
        logger.info("openbanking_sync_done", account_id=str(account.id), balance=balance_amt)

        return BalanceResult(
            total_value_krw=balance_amt,
            deposit_krw=balance_amt,
            extra={"source": "OPEN_BANKING", "snapshot_date": date.today()},
        )
