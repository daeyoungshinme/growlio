"""KIS(한국투자증권) 브로커 프로바이더."""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from typing import TYPE_CHECKING

import httpx
import structlog

from app.exceptions import ProviderApiError, ProviderCredentialError, ProviderNetworkError
from app.kis.auth import get_access_token
from app.kis.balance import get_domestic_balance, get_overseas_balance
from app.kis.client import KisApiError, KisTokenExpiredError
from app.kis.overseas_quote import get_overseas_price
from app.providers._retry import with_token_refresh
from app.providers.base import BalanceResult, BrokerProvider, Position, raw_krw_to_position
from app.providers.http_client import MaxRetriesExceededError
from app.services.credential_service import decrypt
from app.utils.cache_keys import TTL_HAS_OVERSEAS_FALSE, TTL_HAS_OVERSEAS_TRUE, has_overseas_key
from app.utils.currency import cache_usd_krw_rate, get_usd_krw_rate

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.asset import AssetAccount

logger = structlog.get_logger()


class KISProvider(BrokerProvider):
    PROVIDER_ID = "KIS_API"
    PROVIDER_NAME = "한국투자증권 KIS API"

    async def sync(self, account: AssetAccount, db: AsyncSession, redis: aioredis.Redis | None) -> BalanceResult:
        if not account.kis_app_key or not account.kis_app_secret:
            raise ProviderCredentialError(
                "KIS 자격증명이 설정되지 않았습니다. 계좌 설정에서 App Key와 App Secret을 입력해주세요."
            )
        if not account.kis_account_no:
            raise ProviderCredentialError("KIS 계좌번호가 설정되지 않았습니다.")
        if redis is None:
            raise ProviderApiError("Redis 연결이 필요합니다.")
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
                redis=redis,
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
                _fetch_overseas_cached(
                    app_key,
                    app_secret,
                    access_token,
                    account_no,
                    is_mock,
                    account.id,
                    redis,
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
            if e.response.status_code >= 500:
                raise ProviderApiError("KIS API 오류: 모의투자/실계좌 설정을 확인하세요.", http_status=502) from e
            try:
                msg = e.response.json().get("msg1") or str(e)
            except Exception:
                msg = str(e)
            raise ProviderApiError(f"KIS API 오류: {msg}") from e
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise ProviderNetworkError("KIS 서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.") from e

        assert last_token is not None  # _get_token은 성공적으로 완료된 fetch 이전에 항상 최소 1회 호출됨
        usd_krw_rate = await get_usd_krw_rate(redis)
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
                await cache_usd_krw_rate(redis, usd_krw_rate)
            except Exception as e:
                logger.warning("usd_krw_rate_fetch_failed", ticker=sample["ticker"], error=str(e))

        overseas_value_krw = overseas["total_value_usd"] * usd_krw_rate
        overseas_deposit_krw = overseas["deposit_usd"] * usd_krw_rate
        overseas_invested_krw = sum(
            float(p.get("avg_price", 0)) * int(p.get("qty", 0)) * usd_krw_rate for p in overseas["positions"]
        )

        all_raw = domestic["positions"] + [
            {**p, "value_krw": p["value_usd"] * usd_krw_rate} for p in overseas["positions"]
        ]

        positions = [_raw_to_position(p, usd_krw_rate) for p in all_raw]

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


_EMPTY_OVERSEAS: dict = {"positions": [], "total_value_usd": 0.0, "deposit_usd": 0.0}


async def _fetch_overseas_cached(
    app_key: str,
    app_secret: str,
    access_token: str,
    account_no: str,
    is_mock: bool,
    account_id: uuid.UUID,
    redis: aioredis.Redis,
) -> dict:
    """해외 잔고 조회 — Redis 캐시로 국내 전용 계좌의 해외 API 호출을 건너뛴다."""
    cached = await redis.get(has_overseas_key(account_id))
    if cached == b"0":
        return dict(_EMPTY_OVERSEAS)
    result = await _safe_overseas(app_key, app_secret, access_token, account_no, is_mock)
    has_ov = bool(result["positions"])
    await redis.setex(
        has_overseas_key(account_id),
        TTL_HAS_OVERSEAS_TRUE if has_ov else TTL_HAS_OVERSEAS_FALSE,
        "1" if has_ov else "0",
    )
    return result


async def _safe_overseas(app_key: str, app_secret: str, access_token: str, account_no: str, is_mock: bool) -> dict:
    """해외 잔고 조회. KisTokenExpiredError는 re-raise, 나머지 오류는 warn 후 빈 결과 반환."""
    try:
        return await get_overseas_balance(app_key, app_secret, access_token, account_no, is_mock=is_mock)
    except KisTokenExpiredError:
        raise
    except Exception as e:
        logger.warning("kis_overseas_fetch_failed", account_no=account_no, error=str(e))
        return dict(_EMPTY_OVERSEAS)


def _raw_to_position(p: dict, usd_krw_rate: float) -> Position:
    if p.get("currency") == "USD":
        avg_usd = float(p.get("avg_price", 0))
        cur_usd = float(p.get("current_price", 0))
        qty = int(p.get("qty", 0))
        return Position(
            ticker=p["ticker"],
            name=p["name"],
            market=p["market"],
            qty=qty,
            avg_price=avg_usd * usd_krw_rate,
            current_price=cur_usd * usd_krw_rate,
            currency="USD",
            value_krw=float(p.get("value_krw", cur_usd * usd_krw_rate * qty)),
            avg_price_usd=avg_usd,
            usd_rate=usd_krw_rate,
        )
    return raw_krw_to_position(p)
