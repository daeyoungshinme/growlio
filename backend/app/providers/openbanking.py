"""금융결제원 오픈뱅킹 API 제공자.

OAuth2 Authorization Code flow:
  1. GET  /oauth/2.0/authorize  → 사용자 인증 페이지로 리다이렉트
  2. 콜백 → POST /oauth/2.0/token → access_token 획득
  3. GET  /v2.0/user/me         → 연결된 계좌 목록 (fintech_use_no)
  4. GET  /v2.0/account/balance/fin_num → 잔액 조회

API 문서: https://developers.openbanking.or.kr
테스트베드: https://testapi.openbanking.or.kr
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.user import UserSettings

logger = structlog.get_logger()


def get_authorize_url(state: str) -> str:
    """오픈뱅킹 OAuth2 인증 URL 생성."""
    params = {
        "response_type": "code",
        "client_id": settings.open_banking_client_id,
        "redirect_uri": settings.open_banking_redirect_uri,
        "scope": "login inquiry",
        "state": state,
        "auth_type": "0",
    }
    return f"{settings.open_banking_base_url}/oauth/2.0/authorize?" + urllib.parse.urlencode(params)


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    """인증 코드 → 액세스 토큰 교환."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.open_banking_base_url}/oauth/2.0/token",
            data={
                "code": code,
                "client_id": settings.open_banking_client_id,
                "client_secret": settings.open_banking_client_secret,
                "redirect_uri": settings.open_banking_redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


async def refresh_access_token(refresh_token: str) -> dict[str, Any]:
    """리프레시 토큰으로 액세스 토큰 갱신."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{settings.open_banking_base_url}/oauth/2.0/token",
            data={
                "refresh_token": refresh_token,
                "client_id": settings.open_banking_client_id,
                "client_secret": settings.open_banking_client_secret,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        return resp.json()


async def get_user_accounts(access_token: str, user_seq_no: str) -> list[dict]:
    """연결된 은행 계좌 목록 조회 (핀테크이용번호 포함)."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{settings.open_banking_base_url}/v2.0/user/me",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"user_seq_no": user_seq_no},
        )
        resp.raise_for_status()
        data = resp.json()

    return data.get("res_list", [])


async def ensure_ob_token_fresh(settings_row: "UserSettings", db: "AsyncSession") -> str:
    """오픈뱅킹 토큰 만료 1시간 전에 자동 갱신 후 유효한 액세스 토큰 반환.

    갱신 실패 시 로그 경고만 남기고 기존 토큰으로 재시도.
    """
    if not settings_row.ob_access_token or not settings_row.ob_refresh_token:
        raise ValueError("오픈뱅킹 토큰이 없습니다. 다시 연결해주세요.")

    expires_at = settings_row.ob_token_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    needs_refresh = not expires_at or expires_at < datetime.now(timezone.utc) + timedelta(hours=1)
    if needs_refresh:
        try:
            token_data = await refresh_access_token(settings_row.ob_refresh_token)
            settings_row.ob_access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                settings_row.ob_refresh_token = token_data["refresh_token"]
            if "expires_in" in token_data:
                settings_row.ob_token_expires_at = datetime.now(timezone.utc) + timedelta(
                    seconds=int(token_data["expires_in"])
                )
            await db.commit()
            logger.info("ob_token_refreshed", user_id=str(settings_row.user_id))
        except Exception as e:
            logger.error("ob_token_refresh_failed", user_id=str(settings_row.user_id), error=str(e))
            raise RuntimeError("오픈뱅킹 토큰 갱신에 실패했습니다. 다시 연결해주세요.") from e

    return settings_row.ob_access_token


async def get_account_balance(
    access_token: str,
    fintech_use_no: str,
    bank_tran_id: str,
) -> dict[str, Any]:
    """오픈뱅킹 잔액 조회.

    bank_tran_id: 이용기관코드(8자리) + 거래고유번호(9자리)
    """
    tran_dtime = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{settings.open_banking_base_url}/v2.0/account/balance/fin_num",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "bank_tran_id": bank_tran_id,
                "fintech_use_no": fintech_use_no,
                "tran_dtime": tran_dtime,
            },
        )
        resp.raise_for_status()
        return resp.json()
