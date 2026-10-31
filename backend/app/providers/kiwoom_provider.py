"""키움증권 OpenAPI+ 브로커 프로바이더."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import httpx
import structlog

from app.exceptions import ProviderApiError, ProviderCredentialError, ProviderNetworkError
from app.providers._error_mapping import map_http_status_error, map_network_error
from app.providers._overseas_cache import fetch_overseas_cached
from app.providers._overseas_name_enrichment import enrich_overseas_positions
from app.providers._retry import with_token_refresh
from app.providers.base import SYNC_TIMEOUT_SECONDS, BalanceResult, BrokerProvider, combine_domestic_overseas
from app.providers.http_client import MaxRetriesExceededError
from app.services.accounts.credential_service import decrypt
from app.utils.currency import get_usd_krw_rate
from app.utils.masking import mask_account_no

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.cache_store import CacheStore
    from app.models.asset import AssetAccount

logger = structlog.get_logger()


class KiwoomProvider(BrokerProvider):
    PROVIDER_ID = "KIWOOM_API"
    PROVIDER_NAME = "키움증권 OpenAPI+"

    async def sync(self, account: AssetAccount, db: AsyncSession, cache: CacheStore | None) -> BalanceResult:
        from app.kiwoom.auth import get_access_token as kiwoom_get_access_token
        from app.kiwoom.balance import get_domestic_balance as kiwoom_get_domestic_balance
        from app.kiwoom.balance import get_overseas_balance as kiwoom_get_overseas_balance
        from app.kiwoom.client import KiwoomApiError, KiwoomTokenExpiredError, KiwoomTokenIssueError

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
        logger.info("kiwoom_sync_start", account_no=mask_account_no(account_no), is_mock=is_mock)

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
                on_expired=lambda: logger.warning(
                    "kiwoom_token_expired_refreshing", account_no=mask_account_no(account_no)
                ),
            )

        try:
            domestic, overseas = await asyncio.wait_for(_do(), timeout=SYNC_TIMEOUT_SECONDS)
        except TimeoutError as e:
            logger.error("kiwoom_sync_timeout", account_no=mask_account_no(account.kiwoom_account_no))
            raise ProviderNetworkError(
                f"키움 API 응답 시간 초과 (약 {int(SYNC_TIMEOUT_SECONDS)}초). 잠시 후 다시 시도하세요."
            ) from e
        except KiwoomApiError as e:
            raise ProviderApiError(f"키움 계좌 조회 실패: {e.msg} (코드={e.return_code})") from e
        except httpx.HTTPStatusError as e:
            raise map_http_status_error(e, broker_name="키움", message_key="return_msg") from e
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise map_network_error("키움") from e
        except KiwoomTokenIssueError as e:
            raise ProviderApiError(f"{e} — 앱키/시크릿 및 모의/실계좌 모드를 확인하세요.") from e
        except MaxRetriesExceededError as e:
            # MaxRetriesExceededError도 RuntimeError 하위라 아래 일반 분기보다 먼저 — KIS/토스와 같은 429
            raise ProviderApiError("키움 API 속도 제한 초과. 잠시 후 다시 시도하세요.", http_status=429) from e
        except RuntimeError as e:
            raise ProviderApiError(str(e), http_status=502) from e

        usd_krw_rate = await get_usd_krw_rate(cache)

        overseas_positions = await enrich_overseas_positions(overseas["positions"], cache)
        result = combine_domestic_overseas(
            domestic,
            overseas,
            overseas_positions,
            usd_krw_rate,
            "KIWOOM_API",
            orderable_krw=domestic.get("orderable_krw"),
        )
        logger.info("kiwoom_sync_done", account_id=str(account.id), total_krw=result.total_value_krw)
        return result
