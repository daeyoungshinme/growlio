"""KIS(한국투자증권) 브로커 프로바이더."""

from __future__ import annotations

import asyncio
from datetime import date
from typing import TYPE_CHECKING

import httpx
import structlog

from app.exceptions import ProviderApiError, ProviderCredentialError
from app.kis.auth import get_access_token
from app.kis.balance import get_domestic_balance, get_overseas_balance
from app.kis.client import KisApiError, KisTokenExpiredError
from app.kis.overseas_quote import get_overseas_price
from app.providers._error_mapping import map_http_status_error, map_network_error
from app.providers._overseas_cache import fetch_overseas_cached
from app.providers._overseas_name_enrichment import enrich_overseas_names
from app.providers._retry import with_token_refresh
from app.providers.base import BalanceResult, BrokerProvider, raw_to_position
from app.providers.http_client import MaxRetriesExceededError
from app.services.credential_service import decrypt
from app.utils.currency import cache_usd_krw_rate, get_usd_krw_rate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.cache_store import CacheStore
    from app.models.asset import AssetAccount

logger = structlog.get_logger()


class KISProvider(BrokerProvider):
    PROVIDER_ID = "KIS_API"
    PROVIDER_NAME = "한국투자증권 KIS API"

    async def sync(self, account: AssetAccount, db: AsyncSession, cache: CacheStore | None) -> BalanceResult:
        if not account.kis_app_key or not account.kis_app_secret:
            raise ProviderCredentialError(
                "KIS 자격증명이 설정되지 않았습니다. 계좌 설정에서 App Key와 App Secret을 입력해주세요."
            )
        if not account.kis_account_no:
            raise ProviderCredentialError("KIS 계좌번호가 설정되지 않았습니다.")
        if cache is None:
            raise ProviderApiError("캐시 연결이 필요합니다.")
        account_no: str = account.kis_account_no
        app_key = decrypt(account.kis_app_key)
        app_secret = decrypt(account.kis_app_secret)
        is_mock = account.is_mock_mode
        account_id_str = str(account.id)
        user_id_str = str(account.user_id)

        logger.info("kis_sync_start", account_no=account_no, is_mock=is_mock)

        last_token: str | None = None

        async def _get_token(force_refresh: bool) -> str:
            nonlocal last_token
            last_token = await get_access_token(
                app_key,
                app_secret,
                is_mock=is_mock,
                cache=cache,
                db=db,
                user_id=user_id_str,
                account_id=account_id_str,
                force_refresh=force_refresh,
            )
            return last_token

        async def _fetch(access_token: str) -> tuple[dict, dict]:
            return await asyncio.gather(
                get_domestic_balance(
                    app_key,
                    app_secret,
                    access_token,
                    account_no,
                    is_mock=is_mock,
                ),
                fetch_overseas_cached(
                    lambda: get_overseas_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock),
                    account.id,
                    cache,
                    token_expired_exc=KisTokenExpiredError,
                    broker_name="KIS",
                ),
            )

        try:
            domestic, overseas = await with_token_refresh(
                _fetch,
                _get_token,
                KisTokenExpiredError,
                on_expired=lambda: logger.warning("kis_token_expired_refreshing", account_no=account_no),
            )
        except KisApiError as e:
            raise ProviderApiError(
                f"KIS 계좌 조회 실패: {e.msg} (rt_cd={e.rt_cd}). 계좌 유형 또는 API 권한 오류."
            ) from e
        except MaxRetriesExceededError as e:
            raise ProviderApiError("KIS API 속도 제한 초과. 잠시 후 다시 시도하세요.", http_status=429) from e
        except httpx.HTTPStatusError as e:
            raise map_http_status_error(e, broker_name="KIS", message_key="msg1") from e
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise map_network_error("KIS") from e

        if last_token is None:
            raise RuntimeError("last_token이 설정되지 않음: _get_token이 호출되지 않았습니다.")
        usd_krw_rate = await get_usd_krw_rate(cache)
        if overseas["positions"]:
            sample = overseas["positions"][0]
            try:
                quote = await get_overseas_price(
                    app_key,
                    app_secret,
                    last_token,
                    sample["ticker"],
                    sample["market"],
                    is_mock=is_mock,
                )
                usd_krw_rate = quote["usd_krw_rate"]
                await cache_usd_krw_rate(cache, usd_krw_rate)
            except Exception as e:
                logger.warning("usd_krw_rate_fetch_failed", ticker=sample["ticker"], error=str(e))

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

        logger.info("kis_sync_done", account_id=str(account.id), total_krw=total_value_krw)

        return BalanceResult(
            positions=positions,
            total_value_krw=total_value_krw,
            deposit_krw=domestic["deposit_krw"],
            deposit_foreign=overseas["deposit_usd"],
            invested_krw=total_invested,
            pnl_krw=stock_value_krw - total_invested,
            usd_krw_rate=usd_krw_rate,
            extra={"source": "KIS_API", "snapshot_date": date.today()},
        )
