"""KIS(한국투자증권) 브로커 프로바이더."""
from __future__ import annotations

from datetime import date
from typing import Any

import httpx
import structlog

from app.exceptions import ProviderApiError, ProviderCredentialError, ProviderNetworkError
from app.kis.auth import get_access_token
from app.kis.balance import get_domestic_balance, get_overseas_balance
from app.kis.client import KisApiError, KisTokenExpiredError
from app.kis.overseas_quote import get_overseas_price
from app.providers.base import BalanceResult, BrokerProvider, Position
from app.services.credential_service import decrypt
from app.utils.currency import cache_usd_krw_rate, get_usd_krw_rate

logger = structlog.get_logger()


class KISProvider(BrokerProvider):
    PROVIDER_ID = "KIS_API"
    PROVIDER_NAME = "한국투자증권 KIS API"

    async def sync(self, account: Any, db: Any, redis: Any) -> BalanceResult:
        if not account.kis_app_key or not account.kis_app_secret:
            raise ProviderCredentialError(
                "KIS 자격증명이 설정되지 않았습니다. 계좌 설정에서 App Key와 App Secret을 입력해주세요."
            )
        app_key = decrypt(account.kis_app_key)
        app_secret = decrypt(account.kis_app_secret)
        is_mock = account.is_mock_mode
        account_id_str = str(account.id)
        user_id_str = str(account.user_id)

        logger.info("kis_sync_start", account_no=account.kis_account_no, is_mock=is_mock)

        try:
            access_token = await get_access_token(
                app_key, app_secret, is_mock=is_mock, redis=redis, db=db,
                user_id=user_id_str, account_id=account_id_str,
            )
            try:
                domestic = await get_domestic_balance(
                    app_key, app_secret, access_token, account.kis_account_no, is_mock=is_mock
                )
                overseas = await get_overseas_balance(
                    app_key, app_secret, access_token, account.kis_account_no, is_mock=is_mock
                )
            except KisTokenExpiredError:
                logger.warning("kis_token_expired_refreshing", account_no=account.kis_account_no)
                access_token = await get_access_token(
                    app_key, app_secret, is_mock=is_mock, redis=redis, db=db,
                    user_id=user_id_str, account_id=account_id_str, force_refresh=True,
                )
                domestic = await get_domestic_balance(
                    app_key, app_secret, access_token, account.kis_account_no, is_mock=is_mock
                )
                overseas = await get_overseas_balance(
                    app_key, app_secret, access_token, account.kis_account_no, is_mock=is_mock
                )
        except KisApiError as e:
            raise ProviderApiError(
                f"KIS 계좌 조회 실패: {e.msg} (rt_cd={e.rt_cd}). 계좌 유형이 지원되지 않거나 API 권한이 없을 수 있습니다."
            ) from e
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

        usd_krw_rate = await get_usd_krw_rate(redis)
        if overseas["positions"]:
            sample = overseas["positions"][0]
            try:
                quote = await get_overseas_price(
                    app_key, app_secret, access_token,
                    sample["ticker"], sample["market"], is_mock=is_mock,
                )
                usd_krw_rate = quote["usd_krw_rate"]
                await cache_usd_krw_rate(redis, usd_krw_rate)
            except Exception as e:
                logger.warning("usd_krw_rate_fetch_failed", ticker=sample["ticker"], error=str(e))

        overseas_value_krw = overseas["total_value_usd"] * usd_krw_rate
        overseas_deposit_krw = overseas["deposit_usd"] * usd_krw_rate
        overseas_invested_krw = sum(
            float(p.get("avg_price", 0)) * int(p.get("qty", 0)) * usd_krw_rate
            for p in overseas["positions"]
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


def _raw_to_position(p: dict, usd_krw_rate: float) -> Position:
    if p.get("currency") == "USD":
        avg_usd = float(p.get("avg_price", 0))
        cur_usd = float(p.get("current_price", 0))
        qty = int(p.get("qty", 0))
        return Position(
            ticker=p["ticker"], name=p["name"], market=p["market"],
            qty=qty,
            avg_price=avg_usd * usd_krw_rate,
            current_price=cur_usd * usd_krw_rate,
            currency="USD",
            value_krw=float(p.get("value_krw", cur_usd * usd_krw_rate * qty)),
            avg_price_usd=avg_usd,
            usd_rate=usd_krw_rate,
        )
    qty = int(p.get("qty", 0))
    cur_price = float(p["current_price"]) if p.get("current_price") else 0.0
    return Position(
        ticker=p["ticker"], name=p["name"], market=p["market"],
        qty=qty,
        avg_price=float(p.get("avg_price", 0)),
        current_price=cur_price,
        currency="KRW",
        value_krw=float(p.get("value_krw", 0)) or cur_price * qty,
    )
