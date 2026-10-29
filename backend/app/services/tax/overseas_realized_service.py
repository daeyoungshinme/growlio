"""해외주식 올해 실현손익 자동 집계(E6) — 250만원 양도세 공제 잔여를 증권사 체결 기준으로 계산한다.

지원 범위: KIS 실전 계좌(해외주식 기간손익 TTTS3039R). 키움·토스 Open API에는 기간 실현손익 조회가 없고,
KIS 모의투자 서버도 이 TR을 지원하지 않는다 — 이런 계좌는 사용자가 남긴 해외 SELL 수기 매매 기록(`TradeRecord`)이
있으면 그 기록으로 계산한다(`method="TRADE_RECORD"`, 올해 전량 매도해 지금은 보유가 없는 계좌도 포함). 기록도 없고
**현재 해외 종목을 보유 중이면** `uncovered_accounts`로 돌려주고, 프론트는 매도 기록을 남기거나
금액을 직접 보태도록 안내한다.

기록 기반 취득가(KRW): 매도일 이전 BUY 기록이 매도 수량을 덮으면 그 이동평균 원가(매수일 환율 환산값) — 아니면 매도일
직전 스냅샷의 평균단가, 그것도 없으면 현재 포지션 평균단가로 추정한다(`estimated=True` — 스냅샷 원화 평단은 당일 환율로
재환산된 값이라 세법상 취득일 환율 기준과 다를 수 있다). 취득가를 전혀 알 수 없는 기록은 집계에서 뺀다.

ISA/연금저축/IRP(과세이연) 계좌는 양도세 대상이 아니라 제외한다. 조회 실패는 예외를 올리지 않고 해당 계좌를
uncovered(사유 "조회 실패")로 표시한다 — 세금 요약·액션 플랜 전체가 브로커 장애로 깨지지 않게.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal, TypedDict

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DOMESTIC_MARKETS, POSITION_STOCK_ASSET_TYPES, TAX_DEFERRED_TAX_TYPES
from app.core.cache_store import CacheStore, get_cache_store
from app.enums import TradeSide
from app.kis.auth import get_access_token
from app.kis.client import KisTokenExpiredError
from app.kis.realized import get_overseas_realized_pnl
from app.models.asset import AssetAccount, AssetSnapshot, Position
from app.models.trade import TradeRecord
from app.providers._retry import with_token_refresh
from app.services.accounts.credential_service import decrypt_kis_credentials
from app.services.portfolio.period_purchase_service import Lot
from app.services.tax.tax_service import get_overseas_positions_detail
from app.utils.cache_keys import (
    TTL_TAX_OVERSEAS_REALIZED,
    get_cached_json,
    set_cached_json,
    tax_overseas_realized_key,
)
from app.utils.kst import today_kst

logger = structlog.get_logger()

_FETCH_TIMEOUT_SECONDS = 20.0
_QTY_EPS = 1e-6
# 매도일 직전 스냅샷을 찾는 하한 — 1월 초 매도도 작년 말 스냅샷 평단을 쓸 수 있게 1년 앞까지 본다
_BASIS_SNAPSHOT_LOOKBACK_DAYS = 366

RealizedSource = Literal["BROKER", "PARTIAL", "NONE"]
RealizedMethod = Literal["BROKER", "TRADE_RECORD"]


class RealizedAccount(TypedDict):
    account_id: str
    account_name: str
    realized_krw: float
    method: RealizedMethod
    estimated: bool  # TRADE_RECORD 취득가 일부를 평균단가로 추정했는지(또는 취득가를 몰라 뺀 기록이 있는지)


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
        # 타임아웃은 순수 HTTP 조회에만 건다 — 토큰 발급(`store_token`)은 공유 세션에서 commit하므로
        # wait_for 취소가 commit 도중에 떨어지면 세션이 깨진 채 다음 계좌 루프로 넘어간다.
        # 토큰 발급 HTTP는 공용 httpx 클라이언트 타임아웃(30초)으로 이미 상한이 있다.
        result = await asyncio.wait_for(
            get_overseas_realized_pnl(app_key, app_secret, token, account_no, start, end),
            timeout=_FETCH_TIMEOUT_SECONDS,
        )
        return result["total_krw"]

    return await with_token_refresh(_fetch, _get_token, KisTokenExpiredError)


def _is_overseas(market: str) -> bool:
    return market.upper() not in DOMESTIC_MARKETS


@dataclass
class TradeRealized:
    realized_krw: float = 0.0
    sell_count: int = 0  # 집계에 쓴 기간 내 SELL 기록 수
    missing_basis_count: int = 0  # 취득가를 몰라 뺀 기간 내 SELL 기록 수
    estimated: bool = False


def compute_trade_realized(
    trades: list[TradeRecord],
    start: date,
    end: date,
    snapshot_avg_price: Callable[[TradeRecord], float | None],
) -> TradeRealized:
    """한 계좌의 해외 수기 매매 기록 → 기간 [start, end] SELL 실현손익(순수 함수).

    BUY 기록(기간 앞 포함)으로 종목별 이동평균 lot을 쌓고, SELL이 lot 수량 안이면 그 원가를 쓴다. lot이 모자라면
    `snapshot_avg_price(trade)`(매도일 직전 평균단가)로 추정하고, 그것도 없으면 그 기록은 뺀다.
    같은 날은 BUY를 먼저 반영한다.
    """
    result = TradeRealized()
    lots: dict[str, Lot] = {}
    for t in sorted(trades, key=lambda t: (t.trade_date, 0 if t.side == TradeSide.BUY else 1)):
        if t.trade_date > end:
            continue
        qty = float(t.qty)
        price = float(t.price_krw)
        fee = float(t.fee or 0)
        lot = lots.setdefault(t.ticker, Lot())
        if t.side == TradeSide.BUY:
            lot.buy(qty, price, t.trade_date, fee)
            continue
        in_period = t.trade_date >= start
        if lot.qty + _QTY_EPS >= qty:
            before = lot.realized_pnl
            lot.sell(qty, price, fee)
            if in_period:
                result.realized_krw += lot.realized_pnl - before
                result.sell_count += 1
            continue
        # BUY 기록이 매도 수량을 다 덮지 못함 — 기록 lot은 남은 만큼 소진하고 손익은 평균단가로 추정
        lot.sell(min(qty, lot.qty), price)
        if not in_period:
            continue
        avg = snapshot_avg_price(t)
        if avg is None or avg <= 0:
            result.missing_basis_count += 1
            continue
        result.realized_krw += qty * price - fee - qty * avg
        result.sell_count += 1
        result.estimated = True
    return result


def _ticker_avg_prices(positions: list[Position]) -> dict[str, float]:
    """해외 포지션 ticker별 수량 가중 평균단가(KRW)."""
    qty: dict[str, float] = defaultdict(float)
    cost: dict[str, float] = defaultdict(float)
    for p in positions:
        if not _is_overseas(p.market or ""):
            continue
        q = float(p.qty or 0)
        qty[p.ticker] += q
        cost[p.ticker] += q * float(p.avg_price or 0)
    return {ticker: cost[ticker] / q for ticker, q in qty.items() if q > 0}


async def load_trade_record_realized(
    user_id: uuid.UUID, accounts: list[AssetAccount], start: date, end: date, db: AsyncSession
) -> dict[str, TradeRealized]:
    """계좌별(account_id 문자열) 해외 SELL 기록 실현손익 — 기간 안 SELL 기록이 있는 계좌만 담는다."""
    if not accounts:
        return {}
    rows = await db.execute(
        select(TradeRecord).where(
            TradeRecord.user_id == user_id,
            TradeRecord.account_id.in_([a.id for a in accounts]),
            TradeRecord.trade_date <= end,
        )
    )
    trades_by_account: dict[uuid.UUID, list[TradeRecord]] = defaultdict(list)
    for t in rows.scalars().all():
        if t.account_id is not None and _is_overseas(t.market):
            trades_by_account[t.account_id].append(t)
    selling_ids = [
        acc_id
        for acc_id, trades in trades_by_account.items()
        if any(t.side == TradeSide.SELL and start <= t.trade_date <= end for t in trades)
    ]
    if not selling_ids:
        return {}

    # 매도일 직전 스냅샷 평단 조회용 — 스냅샷 날짜 목록만 먼저 읽고, 실제로 쓸 스냅샷의 포지션만 읽는다
    snap_rows = await db.execute(
        select(AssetSnapshot.id, AssetSnapshot.account_id, AssetSnapshot.snapshot_date).where(
            AssetSnapshot.account_id.in_(selling_ids),
            AssetSnapshot.snapshot_date >= start - timedelta(days=_BASIS_SNAPSHOT_LOOKBACK_DAYS),
            AssetSnapshot.snapshot_date <= end,
        )
    )
    # 키가 UUID | None인 건 컬럼이 nullable이라서일 뿐 — account_id.in_() 필터로 None은 오지 않는다
    snaps_by_account: dict[uuid.UUID | None, list[tuple[date, uuid.UUID]]] = defaultdict(list)
    for snap_id, acc_id, snap_date in snap_rows.all():
        snaps_by_account[acc_id].append((snap_date, snap_id))
    for snaps in snaps_by_account.values():
        snaps.sort()

    # 매도 당일 스냅샷은 이미 줄어든 수량이라 "직전"(당일 제외) 스냅샷을 쓴다
    snapshot_before: dict[uuid.UUID, uuid.UUID] = {}
    for acc_id in selling_ids:
        for t in trades_by_account[acc_id]:
            prior = [sid for d, sid in snaps_by_account.get(acc_id, []) if d < t.trade_date]
            if t.side == TradeSide.SELL and prior:
                snapshot_before[t.id] = prior[-1]

    needed = set(snapshot_before.values())
    current_cond = Position.account_id.in_(selling_ids) & Position.snapshot_id.is_(None)
    pos_rows = await db.execute(
        select(Position).where((Position.snapshot_id.in_(needed) | current_cond) if needed else current_cond)
    )
    positions_by_snap: dict[uuid.UUID, list[Position]] = defaultdict(list)
    current_by_account: dict[uuid.UUID, list[Position]] = defaultdict(list)
    for p in pos_rows.scalars().all():
        if p.snapshot_id is not None:
            positions_by_snap[p.snapshot_id].append(p)
        elif p.account_id is not None:
            current_by_account[p.account_id].append(p)
    snap_avgs = {sid: _ticker_avg_prices(ps) for sid, ps in positions_by_snap.items()}
    current_avgs = {acc_id: _ticker_avg_prices(ps) for acc_id, ps in current_by_account.items()}

    def _avg_for(t: TradeRecord) -> float | None:
        sid = snapshot_before.get(t.id)
        if sid is not None and (avg := snap_avgs.get(sid, {}).get(t.ticker)):
            return avg
        return current_avgs.get(t.account_id, {}).get(t.ticker) if t.account_id else None

    return {
        str(acc_id): compute_trade_realized(trades_by_account[acc_id], start, end, _avg_for) for acc_id in selling_ids
    }


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
    overseas_positions: list[dict] | None = None,
) -> OverseasRealizedSummary:
    """올해(또는 지정 연도) 해외주식 실현손익 합계. 계좌 조회는 순차(같은 AsyncSession 동시 사용 금지).

    `overseas_positions`: 호출부가 이미 조회한 `get_overseas_positions_detail` 결과(같은 account_id 기준).
    None이면 직접 조회한다.
    """
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
        if acc.tax_type not in TAX_DEFERRED_TAX_TYPES
    ]
    positions = (
        overseas_positions
        if overseas_positions is not None
        else await get_overseas_positions_detail(user_id, db, account_id)
    )
    holding_account_ids = {p["account_id"] for p in positions}

    today = today_kst()
    start = date(year, 1, 1)
    end = min(date(year, 12, 31), today)

    # KIS 자동 집계 계좌의 수기 기록은 쓰지 않는다 — 브로커 체결 기준이 정답이고 합치면 이중 집계된다
    by_records = await load_trade_record_realized(
        user_id, [acc for acc in accounts if not _is_kis_auto(acc)], start, end, db
    )

    covered: list[RealizedAccount] = []
    uncovered: list[UncoveredAccount] = []
    had_failure = False
    for acc in sorted(accounts, key=lambda a: a.name):
        acc_id = str(acc.id)
        record = by_records.get(acc_id)
        if _is_kis_auto(acc):
            try:
                realized = await _fetch_kis_realized(acc, start, end, db, cache)
            except Exception as e:  # 브로커 장애가 세금 화면 전체를 깨지 않게 — 계좌 단위로 격리
                logger.warning("overseas_realized_fetch_failed", account_id=acc_id, error=str(e))
                had_failure = True
                uncovered.append({"account_id": acc_id, "account_name": acc.name, "reason": "조회 실패"})
                continue
            covered.append(
                {
                    "account_id": acc_id,
                    "account_name": acc.name,
                    "realized_krw": round(realized, 0),
                    "method": "BROKER",
                    "estimated": False,
                }
            )
        elif record is not None and record.sell_count > 0:
            covered.append(
                {
                    "account_id": acc_id,
                    "account_name": acc.name,
                    "realized_krw": round(record.realized_krw, 0),
                    "method": "TRADE_RECORD",
                    "estimated": record.estimated or record.missing_basis_count > 0,
                }
            )
        elif record is not None:
            uncovered.append(
                {"account_id": acc_id, "account_name": acc.name, "reason": "매도 기록의 취득가를 알 수 없어요"}
            )
        elif acc_id in holding_account_ids:
            uncovered.append({"account_id": acc_id, "account_name": acc.name, "reason": _unsupported_reason(acc)})

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
