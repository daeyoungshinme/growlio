"""토스증권 Open API 브로커 프로바이더.

키움 provider와 구조가 같으나 더 단순하다: 토스는 국내+미국 보유종목이 단일
`holdings` 호출로 통합되어 오므로 해외 분리 조회(`_overseas_cache`)가 불필요하다.
토스에는 모의투자(샌드박스)가 없어 `is_mock_mode`를 사용하지 않는다.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import date
from typing import TYPE_CHECKING

import httpx
import structlog

from app.exceptions import ProviderApiError, ProviderCredentialError, ProviderNetworkError
from app.providers._error_mapping import map_http_status_error, map_network_error
from app.providers._overseas_name_enrichment import enrich_overseas_names
from app.providers._retry import with_token_refresh
from app.providers.base import BalanceResult, BrokerProvider, raw_to_position
from app.providers.http_client import MaxRetriesExceededError
from app.services.credential_service import decrypt
from app.utils.currency import get_usd_krw_rate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.cache_store import CacheStore
    from app.models.asset import AssetAccount

logger = structlog.get_logger()

_SYNC_TIMEOUT = 50.0


_IP_BLOCK_MSG = "토스 API 접근이 거부되었습니다. 토스 `Open API → IP 관리`에 서버 IP가 등록되어 있는지 확인하세요."


def _is_edge_blocked(response: httpx.Response) -> bool:
    try:
        return (response.json().get("error") or {}).get("code") == "edge-blocked"
    except Exception:
        return False


async def _run_fetch(do: Callable[[], Awaitable[dict]], *, account_id: str) -> dict:
    """토스 조회를 실행하고 브로커 예외를 SyncError 계층으로 변환한다."""
    from app.toss.client import TossApiError

    try:
        return await asyncio.wait_for(do(), timeout=_SYNC_TIMEOUT)
    except TimeoutError as e:
        logger.error("toss_sync_timeout", account_id=account_id)
        raise ProviderNetworkError("토스 API 응답 시간 초과 (50초). 잠시 후 다시 시도하세요.") from e
    except TossApiError as e:
        if e.status_code == 403 or e.code in ("edge-blocked", "forbidden"):
            raise ProviderApiError(_IP_BLOCK_MSG, http_status=403) from e
        raise ProviderApiError(f"토스 계좌 조회 실패: {e.message} (코드={e.code})") from e
    except MaxRetriesExceededError as e:
        raise ProviderApiError("토스 API 속도 제한 초과. 잠시 후 다시 시도하세요.", http_status=429) from e
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 403 and _is_edge_blocked(e.response):
            raise ProviderApiError(_IP_BLOCK_MSG, http_status=403) from e
        raise map_http_status_error(e, broker_name="토스", message_key="message") from e
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        raise map_network_error("토스") from e


class TossProvider(BrokerProvider):
    PROVIDER_ID = "TOSS_API"
    PROVIDER_NAME = "토스증권 Open API"

    async def sync(self, account: AssetAccount, db: AsyncSession, cache: CacheStore | None) -> BalanceResult:
        from app.toss.auth import get_access_token as toss_get_access_token
        from app.toss.balance import get_balance as toss_get_balance
        from app.toss.client import TossTokenExpiredError

        if not account.toss_client_id or not account.toss_client_secret:
            raise ProviderCredentialError("토스 API 자격증명(Client ID/Secret)이 설정되지 않았습니다")
        if not account.toss_account_no:
            raise ProviderCredentialError("토스 계좌번호가 설정되지 않았습니다")
        if cache is None:
            raise ProviderApiError("캐시 연결이 필요합니다.")

        account_no: str = account.toss_account_no
        client_id = decrypt(account.toss_client_id)
        client_secret = decrypt(account.toss_client_secret)
        logger.info("toss_sync_start", account_id=str(account.id))

        async def _get_token(force_refresh: bool) -> str:
            return await toss_get_access_token(
                client_id,
                client_secret,
                cache=cache,
                db=db,
                user_id=str(account.user_id),
                account_id=str(account.id),
                force_refresh=force_refresh,
            )

        async def _fetch(token: str) -> dict:
            return await toss_get_balance(token, account_id=str(account.id), account_no=account_no, cache=cache)

        async def _do() -> dict:
            return await with_token_refresh(
                _fetch,
                _get_token,
                TossTokenExpiredError,
                on_expired=lambda: logger.warning("toss_token_expired_refreshing", account_id=str(account.id)),
            )

        bal = await _run_fetch(_do, account_id=str(account.id))

        usd_krw_rate = await get_usd_krw_rate(cache)

        raw_positions = bal["positions"]
        usd_positions = [p for p in raw_positions if p.get("currency") == "USD"]
        if usd_positions:
            enriched = {p["ticker"]: p["name"] for p in await enrich_overseas_names(usd_positions, cache)}
            raw_positions = [
                {**p, "name": enriched.get(p["ticker"], p["name"])} if p.get("currency") == "USD" else p
                for p in raw_positions
            ]
        positions = [raw_to_position(p, usd_krw_rate) for p in raw_positions]

        def _krw(components: dict) -> float:
            return float(components.get("krw", 0)) + float(components.get("usd", 0)) * usd_krw_rate

        invested_krw = _krw(bal["invested"])
        stock_value_krw = _krw(bal["market_value"])
        if stock_value_krw <= 0 and positions:
            stock_value_krw = sum(p.value_krw for p in positions)

        deposit_krw = float(bal["deposit_krw"])
        deposit_usd = float(bal["deposit_usd"])
        total_value_krw = stock_value_krw + deposit_krw + deposit_usd * usd_krw_rate

        logger.info("toss_sync_done", account_id=str(account.id), total_krw=total_value_krw)

        return BalanceResult(
            positions=positions,
            total_value_krw=total_value_krw,
            deposit_krw=deposit_krw,
            deposit_foreign=deposit_usd,
            invested_krw=invested_krw,
            pnl_krw=stock_value_krw - invested_krw,
            usd_krw_rate=usd_krw_rate,
            extra={"source": "TOSS_API", "snapshot_date": date.today()},
        )
