"""해외주식 올해 실현손익 자동 집계(E6) — 250만원 양도세 공제 잔여를 증권사 체결 기준으로 계산한다.

지원 범위: KIS 실전 계좌(해외주식 기간손익 TTTS3039R). 키움·토스 Open API에는 기간 실현손익 조회가 없고,
KIS 모의투자 서버도 이 TR을 지원하지 않는다 — 이런 계좌가 **현재 해외 종목을 보유 중이면** `uncovered_accounts`로
돌려주고, 프론트는 해당 금액을 사용자가 수기로 보탤 수 있게 안내한다. (올해 해외 종목을 전량 매도해 지금은
보유가 없는 미지원 계좌는 감지할 수 없다 — 문구에 "현재 보유 기준"을 명시.)

ISA/연금저축/IRP(과세이연) 계좌는 양도세 대상이 아니라 제외한다. 조회 실패는 예외를 올리지 않고 해당 계좌를
uncovered(사유 "조회 실패")로 표시한다 — 세금 요약·액션 플랜 전체가 브로커 장애로 깨지지 않게.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from typing import Literal, TypedDict

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import POSITION_STOCK_ASSET_TYPES
from app.core.cache_store import CacheStore, get_cache_store
from app.kis.auth import get_access_token
from app.kis.client import KisTokenExpiredError
from app.kis.realized import get_overseas_realized_pnl
from app.models.asset import AssetAccount
from app.providers._retry import with_token_refresh
from app.services.credential_service import decrypt_kis_credentials
from app.services.tax_service import _TAX_DEFERRED_TYPES, get_overseas_positions_detail
from app.utils.cache_keys import (
    TTL_TAX_OVERSEAS_REALIZED,
    get_cached_json,
    set_cached_json,
    tax_overseas_realized_key,
)
from app.utils.kst import today_kst

logger = structlog.get_logger()

_FETCH_TIMEOUT_SECONDS = 20.0

RealizedSource = Literal["BROKER", "PARTIAL", "NONE"]


class RealizedAccount(TypedDict):
    account_id: str
    account_name: str
    realized_krw: float


class UncoveredAccount(TypedDict):
    account_id: str
    account_name: str
    reason: str


class OverseasRealizedSummary(TypedDict):
    year: int
    realized_gain_krw: float | None
    source: RealizedSource
    covered_accounts: list[RealizedAccount]
    uncovered_accounts: list[UncoveredAccount]
    as_of: str


def _is_kis_auto(acc: AssetAccount) -> bool:
    return bool(
        acc.asset_type == "STOCK_KIS"
        and not acc.is_mock_mode
        and acc.kis_app_key
        and acc.kis_app_secret
        and acc.kis_account_no
    )


def _unsupported_reason(acc: AssetAccount) -> str:
    if acc.asset_type == "STOCK_KIS" and acc.is_mock_mode:
        return "모의투자 계좌는 실현손익 조회를 지원하지 않아요"
    if acc.asset_type == "STOCK_KIS":
        return "KIS API 자격증명이 없어요"
    if acc.asset_type == "STOCK_KIWOOM":
        return "키움 API는 기간 실현손익 조회를 제공하지 않아요"
    if acc.asset_type == "STOCK_TOSS":
        return "토스 API는 기간 실현손익 조회를 제공하지 않아요"
    return "수기 계좌라 자동 집계할 수 없어요"


async def _fetch_kis_realized(acc: AssetAccount, start: date, end: date, db: AsyncSession, cache: CacheStore) -> float:
    creds = decrypt_kis_credentials(acc)
    if creds is None or not acc.kis_account_no:
        raise ValueError("KIS 자격증명 없음")
    app_key, app_secret = creds
    account_no: str = acc.kis_account_no

    async def _get_token(force_refresh: bool) -> str:
        return await get_access_token(
            app_key,
            app_secret,
            is_mock=False,
            cache=cache,
            db=db,
            user_id=str(acc.user_id),
            account_id=str(acc.id),
            force_refresh=force_refresh,
        )

    async def _fetch(token: str) -> float:
        result = await get_overseas_realized_pnl(app_key, app_secret, token, account_no, start, end)
        return result["total_krw"]

    return await asyncio.wait_for(
        with_token_refresh(_fetch, _get_token, KisTokenExpiredError), timeout=_FETCH_TIMEOUT_SECONDS
    )


def resolve_source(covered: list[RealizedAccount], uncovered: list[UncoveredAccount]) -> RealizedSource:
    if not covered:
        return "NONE"
    return "PARTIAL" if uncovered else "BROKER"


async def get_overseas_realized_summary(
    user_id: uuid.UUID,
    year: int,
    db: AsyncSession,
    account_id: uuid.UUID | None = None,
    cache: CacheStore | None = None,
) -> OverseasRealizedSummary:
    """올해(또는 지정 연도) 해외주식 실현손익 합계. 계좌 조회는 순차(같은 AsyncSession 동시 사용 금지)."""
    cache = cache if cache is not None else await get_cache_store()
    cache_key = tax_overseas_realized_key(user_id, year, str(account_id) if account_id else "all")
    cached = await get_cached_json(cache, cache_key)
    if cached is not None:
        return cached

    conditions = [
        AssetAccount.user_id == user_id,
        AssetAccount.is_active == True,
        AssetAccount.asset_type.in_(POSITION_STOCK_ASSET_TYPES),
    ]
    if account_id is not None:
        conditions.append(AssetAccount.id == account_id)
    accounts = [
        acc
        for acc in (await db.execute(select(AssetAccount).where(*conditions))).scalars().all()
        if acc.tax_type not in _TAX_DEFERRED_TYPES
    ]
    positions = await get_overseas_positions_detail(user_id, db, account_id)
    holding_account_ids = {p["account_id"] for p in positions}

    today = today_kst()
    start = date(year, 1, 1)
    end = min(date(year, 12, 31), today)

    covered: list[RealizedAccount] = []
    uncovered: list[UncoveredAccount] = []
    had_failure = False
    for acc in sorted(accounts, key=lambda a: a.name):
        if _is_kis_auto(acc):
            try:
                realized = await _fetch_kis_realized(acc, start, end, db, cache)
            except Exception as e:  # 브로커 장애가 세금 화면 전체를 깨지 않게 — 계좌 단위로 격리
                logger.warning("overseas_realized_fetch_failed", account_id=str(acc.id), error=str(e))
                had_failure = True
                uncovered.append({"account_id": str(acc.id), "account_name": acc.name, "reason": "조회 실패"})
                continue
            covered.append({"account_id": str(acc.id), "account_name": acc.name, "realized_krw": round(realized, 0)})
        elif str(acc.id) in holding_account_ids:
            uncovered.append({"account_id": str(acc.id), "account_name": acc.name, "reason": _unsupported_reason(acc)})

    summary: OverseasRealizedSummary = {
        "year": year,
        "realized_gain_krw": round(sum(a["realized_krw"] for a in covered), 0) if covered else None,
        "source": resolve_source(covered, uncovered),
        "covered_accounts": covered,
        "uncovered_accounts": uncovered,
        "as_of": today.isoformat(),
    }
    if not had_failure:  # 일시 실패 결과를 1시간 고정하지 않도록 성공 시에만 캐시
        await set_cached_json(cache, cache_key, summary, TTL_TAX_OVERSEAS_REALIZED)
    return summary
