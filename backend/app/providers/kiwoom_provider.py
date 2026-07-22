"""키움증권 OpenAPI+ 브로커 프로바이더."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import TYPE_CHECKING

import httpx
import structlog

from app.exceptions import ProviderApiError, ProviderCredentialError, ProviderNetworkError
from app.providers._error_mapping import map_http_status_error, map_network_error
from app.providers._overseas_cache import fetch_overseas_cached
from app.providers._overseas_name_enrichment import enrich_overseas_names
from app.providers._retry import with_token_refresh
from app.providers.base import BalanceResult, BrokerProvider, raw_to_position
from app.services.credential_service import decrypt
from app.utils.currency import get_usd_krw_rate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.cache_store import CacheStore
    from app.models.asset import AssetAccount

logger = structlog.get_logger()

_SYNC_TIMEOUT = 50.0


class KiwoomProvider(BrokerProvider):
    PROVIDER_ID = "KIWOOM_API"
    PROVIDER_NAME = "키움증권 OpenAPI+"

    async def sync(self, account: AssetAccount, db: AsyncSession, cache: CacheStore | None) -> BalanceResult:
        from app.kiwoom.auth import get_access_token as kiwoom_get_access_token
        from app.kiwoom.balance import get_domestic_balance as kiwoom_get_domestic_balance
        from app.kiwoom.balance import get_overseas_balance as kiwoom_get_overseas_balance
        from app.kiwoom.client import KiwoomApiError, KiwoomTokenExpiredError

        if not account.kiwoom_app_key or not account.kiwoom_app_secret:
            raise ProviderCredentialError("키움 API 자격증명이 설정되지 않았습니다")
        if not account.kiwoom_account_no:
            raise ProviderCredentialError("키움 계좌번호가 설정되지 않았습니다")
        if cache is None:
            raise ProviderApiError("캐시 연결이 필요합니다.")

        account_no: str = account.kiwoom_account_no
        app_key = decrypt(account.kiwoom_app_key)
        app_secret = decrypt(account.kiwoom_app_secret)
        is_mock = account.is_mock_mode
        logger.info("kiwoom_sync_start", account_no=account_no, is_mock=is_mock)

        async def _get_token(force_refresh: bool) -> str:
            return await kiwoom_get_access_token(
                app_key,
                app_secret,
                is_mock=is_mock,
                cache=cache,
                db=db,
                user_id=str(account.user_id),
                account_id=str(account.id),
                force_refresh=force_refresh,
            )

        async def _fetch(token: str) -> tuple[dict, dict]:
            return await asyncio.gather(
                kiwoom_get_domestic_balance(token, account_no, is_mock=is_mock),
                fetch_overseas_cached(
                    lambda: kiwoom_get_overseas_balance(token, account_no, is_mock=is_mock),
                    account.id,
                    cache,
                    token_expired_exc=KiwoomTokenExpiredError,
                    broker_name="키움",
                ),
            )

        async def _do() -> tuple[dict, dict]:
            return await with_token_refresh(
                _fetch,
                _get_token,
                KiwoomTokenExpiredError,
                on_expired=lambda: logger.warning("kiwoom_token_expired_refreshing", account_no=account_no),
            )

        try:
            domestic, overseas = await asyncio.wait_for(_do(), timeout=_SYNC_TIMEOUT)
        except TimeoutError as e:
            logger.error("kiwoom_sync_timeout", account_no=account.kiwoom_account_no)
            raise ProviderNetworkError("키움 API 응답 시간 초과 (50초). 잠시 후 다시 시도하세요.") from e
        except KiwoomApiError as e:
            raise ProviderApiError(f"키움 계좌 조회 실패: {e.msg} (코드={e.return_code})") from e
        except httpx.HTTPStatusError as e:
            raise map_http_status_error(e, broker_name="키움", message_key="return_msg") from e
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise map_network_error("키움") from e
        except RuntimeError as e:
            msg = str(e)
            if "토큰 발급 실패" in msg:
                raise ProviderApiError(f"{msg} — 앱키/시크릿 및 모의/실계좌 모드를 확인하세요.") from e
            raise ProviderApiError(msg, http_status=502) from e

        usd_krw_rate = await get_usd_krw_rate(cache)

        overseas_value_krw = overseas["total_value_usd"] * usd_krw_rate
        overseas_deposit_krw = overseas["deposit_usd"] * usd_krw_rate
        overseas_invested_krw = sum(
            float(p.get("avg_price", 0)) * int(p.get("qty", 0)) * usd_krw_rate for p in overseas["positions"]
        )

        overseas_positions = await enrich_overseas_names(overseas["positions"], cache)
        all_raw = domestic["positions"] + [
            {**p, "value_krw": p["value_usd"] * usd_krw_rate} for p in overseas_positions
        ]
        positions = [raw_to_position(p, usd_krw_rate) for p in all_raw]

        stock_value_krw = domestic["total_value_krw"] + overseas_value_krw
        total_value_krw = stock_value_krw + domestic["deposit_krw"] + overseas_deposit_krw
        total_invested = domestic["invested_krw"] + overseas_invested_krw

        logger.info("kiwoom_sync_done", account_id=str(account.id), total_krw=total_value_krw)

        return BalanceResult(
            positions=positions,
            total_value_krw=total_value_krw,
            deposit_krw=domestic["deposit_krw"],
            deposit_foreign=overseas["deposit_usd"],
            invested_krw=total_invested,
            pnl_krw=stock_value_krw - total_invested,
            usd_krw_rate=usd_krw_rate,
            extra={"source": "KIWOOM_API", "snapshot_date": date.today()},
        )
