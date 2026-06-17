"""키움증권 OpenAPI+ 브로커 프로바이더."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import TYPE_CHECKING

import httpx
import structlog

from app.exceptions import ProviderApiError, ProviderCredentialError, ProviderNetworkError
from app.providers.base import BalanceResult, BrokerProvider, Position
from app.services.credential_service import decrypt
from app.utils.currency import get_usd_krw_rate

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.asset import AssetAccount

logger = structlog.get_logger()

_SYNC_TIMEOUT = 50.0


class KiwoomProvider(BrokerProvider):
    PROVIDER_ID = "KIWOOM_API"
    PROVIDER_NAME = "키움증권 OpenAPI+"

    async def sync(self, account: AssetAccount, db: AsyncSession, redis: aioredis.Redis | None) -> BalanceResult:
        from app.kiwoom.auth import get_access_token as kiwoom_get_access_token
        from app.kiwoom.balance import get_domestic_balance as kiwoom_get_balance
        from app.kiwoom.client import KiwoomApiError, KiwoomTokenExpiredError

        if not account.kiwoom_app_key or not account.kiwoom_app_secret:
            raise ProviderCredentialError("키움 API 자격증명이 설정되지 않았습니다")
        if not account.kiwoom_account_no:
            raise ProviderCredentialError("키움 계좌번호가 설정되지 않았습니다")

        account_no: str = account.kiwoom_account_no
        app_key = decrypt(account.kiwoom_app_key)
        app_secret = decrypt(account.kiwoom_app_secret)
        is_mock = account.is_mock_mode
        logger.info("kiwoom_sync_start", account_no=account_no, is_mock=is_mock)

        async def _do() -> dict:
            token = await kiwoom_get_access_token(
                app_key,
                app_secret,
                is_mock=is_mock,
                redis=redis,
                db=db,
                user_id=str(account.user_id),
                account_id=str(account.id),
            )
            try:
                return await kiwoom_get_balance(token, account_no, is_mock=is_mock)
            except KiwoomTokenExpiredError:
                logger.warning("kiwoom_token_expired_refreshing", account_no=account_no)
                refreshed = await kiwoom_get_access_token(
                    app_key,
                    app_secret,
                    is_mock=is_mock,
                    redis=redis,
                    db=db,
                    user_id=str(account.user_id),
                    account_id=str(account.id),
                    force_refresh=True,
                )
                return await kiwoom_get_balance(refreshed, account_no, is_mock=is_mock)

        try:
            domestic = await asyncio.wait_for(_do(), timeout=_SYNC_TIMEOUT)
        except TimeoutError as e:
            logger.error("kiwoom_sync_timeout", account_no=account.kiwoom_account_no)
            raise ProviderNetworkError("키움 API 응답 시간 초과 (50초). 잠시 후 다시 시도하세요.") from e
        except KiwoomApiError as e:
            raise ProviderApiError(f"키움 계좌 조회 실패: {e.msg} (코드={e.return_code})") from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                raise ProviderApiError("키움 API 오류: 모의투자/실계좌 설정을 확인하세요.", http_status=502) from e
            try:
                msg = e.response.json().get("return_msg") or str(e)
            except Exception:
                msg = str(e)
            raise ProviderApiError(f"키움 API 오류: {msg}") from e
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise ProviderNetworkError("키움 서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.") from e
        except RuntimeError as e:
            msg = str(e)
            if "토큰 발급 실패" in msg:
                raise ProviderApiError(f"{msg} — 앱키/시크릿 및 모의/실계좌 모드를 확인하세요.") from e
            raise ProviderApiError(msg, http_status=502) from e

        usd_krw_rate = await get_usd_krw_rate(redis)
        positions = [_raw_to_position(p, usd_krw_rate) for p in domestic["positions"]]
        stock_value_krw = domestic["total_value_krw"]
        total_value_krw = stock_value_krw + domestic["deposit_krw"]
        total_invested = domestic["invested_krw"]

        logger.info("kiwoom_sync_done", account_id=str(account.id), total_krw=total_value_krw)

        return BalanceResult(
            positions=positions,
            total_value_krw=total_value_krw,
            deposit_krw=domestic["deposit_krw"],
            invested_krw=total_invested,
            pnl_krw=stock_value_krw - total_invested,
            usd_krw_rate=usd_krw_rate,
            extra={"source": "KIWOOM_API", "snapshot_date": date.today()},
        )


def _raw_to_position(p: dict, usd_krw_rate: float) -> Position:
    return Position(
        ticker=p["ticker"],
        name=p["name"],
        market=p["market"],
        qty=int(p.get("qty", 0)),
        avg_price=float(p.get("avg_price", 0)),
        current_price=float(p.get("current_price", 0)),
        currency="KRW",
        value_krw=float(p.get("value_krw", 0)) or float(p.get("current_price", 0)) * int(p.get("qty", 0)),
    )
