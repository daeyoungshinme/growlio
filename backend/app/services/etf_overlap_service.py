"""추천 후보 ETF ↔ 보유 종목·다른 후보 간 중복(같은 지수/사실상 같은 움직임) 분석 + 총보수 비교.

"후보 ETF 관리"에 새 ETF를 넣거나 추천 결과를 볼 때, 이미 보유 중이거나 함께 등록된 다른 ETF와
실질적으로 같은 상품인지(운용사만 다른 S&P500 ETF 등)와 어느 쪽 보수가 더 싼지를 보여주기 위한
정보 제공 기능이다. 후보 목록·추천 비중을 바꾸지 않는다(사용자 동의 없이 후보를 바꾸지 않는다는
`goal_candidate_service`의 원칙과 동일).

판정 사유 두 가지:
- `SAME_INDEX`: 추종 지수 키가 같다. 키 우선순위 — 명시 태그/큐레이션 유니버스 > Naver 기초지수명
  (`guess_tracking_index`로 정규화, 안 되면 원문 정규화) > 종목명 휴리스틱 > 해외 ETF 정식명칭 휴리스틱.
- `HIGH_CORR`: 최근 1년 **주간** 수익률 상관계수 ≥ `_HIGH_CORR_THRESHOLD`이면서 변동성 비율이
  `_MAX_VOL_RATIO` 이내. 일별 수익률 목록(`fetch_yf_daily_returns`)은 날짜가 없어 정렬할 수 없으므로
  날짜가 붙은 종가(`fetch_yf_close_series`)를 주간으로 리샘플링해 쓴다. 변동성 비율 조건은 레버리지 ETF
  (KODEX 레버리지 vs KODEX 200 — 상관은 0.99지만 위험은 2배)를 "중복"으로 오판하지 않기 위함이다.

비교 쌍 규칙:
- 최소 한쪽은 등록 후보여야 한다(보유 종목끼리는 이 기능의 관심사가 아님).
- 양쪽 다 보유 종목이 아니고 상장 시장 그룹(국내/해외)이 다르면 비교하지 않는다 — SPY와 TIGER
  미국S&P500처럼 계좌 유형(해외전용 vs ISA/연금)별로 의도적으로 함께 등록하는 조합이 흔하다
  (`detect_duplicate_tracking_index_note` 독스트링과 같은 이유).
- 상장 시장 그룹이 다르면 `HIGH_CORR`은 계산하지 않는다 — 거래 시간대·환율 차이로 주간 상관이
  낮게 나와 판정이 불안정하다. `SAME_INDEX`만 본다.
- 현금성(CASH) 후보는 분석에서 제외, 레버리지·인버스·배당주기 명시(`distribution_frequency`) 종목은
  `SAME_INDEX` 판정에서 제외(같은 기초지수라도 다른 상품).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING

import structlog

from app.constants import CASH_EQUIVALENT_MARKET, DOMESTIC_MARKETS
from app.schemas.rebalancing.goal import (
    CandidateOverlapResponse,
    EtfProfileOut,
    OverlapGroup,
    OverlapMember,
)
from app.services._settings_queries import get_settings_row
from app.services.etf_profile_service import EtfProfile, get_etf_profiles
from app.services.goal_candidate_service import LEVERAGED_INVERSE_RE, existing_items_from_positions
from app.services.market_data_fetcher import fetch_yf_close_series
from app.services.position_aggregator import query_latest_position_map
from app.services.recommendation_universe import (
    guess_tracking_index,
    index_key_from_base_index,
    resolve_distribution_frequency,
    resolve_tracking_index,
)
from app.services.yahoo_price import run_yf_bounded, to_yf_symbol
from app.utils.cache_keys import (
    TTL_CANDIDATE_OVERLAP,
    CacheStoreType,
    candidate_overlap_key,
    get_cached_json,
    set_cached_json,
)
from app.utils.kst import today_kst

if TYPE_CHECKING:
    import pandas as pd
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

_HIGH_CORR_THRESHOLD = 0.97
"""주간 수익률 상관 기준. 운용사만 다른 동일지수 ETF는 0.99+, S&P500 vs 나스닥100(SPY/QQQ)은 ~0.93으로
이 선 아래라 "다른 상품"으로 남는다 — 0.95로 두면 대형 성장/블렌드 지수 쌍이 경계에서 오탐된다."""
_MIN_OVERLAP_WEEKS = 26
_MAX_VOL_RATIO = 1.5
_LOOKBACK_DAYS = 365

_CACHE_SCHEMA_VERSION = "v1"


@dataclass
class _Item:
    ticker: str
    name: str
    market: str
    asset_class: str = "EQUITY"
    held: bool = False
    candidate: bool = False
    tracking_index: str | None = None
    distribution_frequency: str | None = None
    profile: EtfProfile | None = field(default=None, compare=False)

    @property
    def key(self) -> tuple[str, str]:
        return (self.ticker, self.market)

    @property
    def is_domestic_listed(self) -> bool:
        return self.market.upper() in DOMESTIC_MARKETS


def resolve_index_key(item: _Item) -> str | None:
    """추종 지수 비교 키. 판별 불가면 None(`SAME_INDEX` 판정 안 함)."""
    known = resolve_tracking_index(item.ticker, item.market, "", item.tracking_index)
    if known:
        return known
    base_index = item.profile.get("base_index") if item.profile else None
    if base_index:
        return index_key_from_base_index(base_index)
    guessed = guess_tracking_index(item.name)
    if guessed:
        return guessed
    long_name = item.profile.get("long_name") if item.profile else None
    return guess_tracking_index(long_name) if long_name else None


def _same_index_eligible(item: _Item) -> bool:
    return not item.distribution_frequency and not LEVERAGED_INVERSE_RE.search(item.name.upper())


def _pair_comparable(a: _Item, b: _Item) -> bool:
    if not (a.candidate or b.candidate):
        return False
    return a.held or b.held or a.is_domestic_listed == b.is_domestic_listed


def weekly_returns_frame(close_series: dict[str, pd.Series]) -> pd.DataFrame:
    """종목별 종가 → 주간(금요일 마감) 수익률 DataFrame. 열 이름은 입력 키 그대로."""
    import pandas as pd

    if not close_series:
        return pd.DataFrame()
    frame = pd.DataFrame(
        {sym: s.set_axis(pd.to_datetime(s.index).tz_localize(None)) for sym, s in close_series.items()}
    )
    return frame.sort_index().resample("W-FRI").last().pct_change(fill_method=None)


def _pair_correlation(weekly: pd.DataFrame, sym_a: str, sym_b: str) -> float | None:
    """상관계수(변동성 비율 조건 불충족·표본 부족이면 None)."""
    if sym_a not in weekly.columns or sym_b not in weekly.columns:
        return None
    pair = weekly[[sym_a, sym_b]].dropna()
    if len(pair) < _MIN_OVERLAP_WEEKS:
        return None
    std_a, std_b = float(pair[sym_a].std()), float(pair[sym_b].std())
    if std_a <= 0 or std_b <= 0 or max(std_a, std_b) / min(std_a, std_b) > _MAX_VOL_RATIO:
        return None
    return float(pair[sym_a].corr(pair[sym_b]))


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, a: int, b: int) -> None:
        self.parent[self.find(a)] = self.find(b)


def find_overlap_groups(items: list[_Item], weekly: pd.DataFrame | None) -> list[OverlapGroup]:
    """순수 판정 로직 — 프로필은 `items[i].profile`에 미리 채워져 있어야 한다."""
    index_keys = [resolve_index_key(i) if _same_index_eligible(i) else None for i in items]
    symbols = [to_yf_symbol(i.ticker, i.market) for i in items]
    uf = _UnionFind(len(items))
    reasons: dict[int, set[str]] = {}
    max_corr: dict[int, float] = {}
    edges: list[tuple[int, int, str, float | None]] = []

    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            ia, ib = items[a], items[b]
            if not _pair_comparable(ia, ib):
                continue
            if index_keys[a] is not None and index_keys[a] == index_keys[b]:
                edges.append((a, b, "SAME_INDEX", None))
            if weekly is not None and ia.is_domestic_listed == ib.is_domestic_listed:
                corr = _pair_correlation(weekly, symbols[a], symbols[b])
                if corr is not None and corr >= _HIGH_CORR_THRESHOLD:
                    edges.append((a, b, "HIGH_CORR", corr))

    for a, b, _reason, _corr in edges:
        uf.union(a, b)
    for a, _b, reason, corr in edges:
        root = uf.find(a)
        reasons.setdefault(root, set()).add(reason)
        if corr is not None:
            max_corr[root] = max(max_corr.get(root, -1.0), corr)

    members_by_root: dict[int, list[int]] = {}
    for idx in range(len(items)):
        root = uf.find(idx)
        if root in reasons:
            members_by_root.setdefault(root, []).append(idx)

    groups = [
        _build_group([items[i] for i in idxs], reasons[root], max_corr.get(root))
        for root, idxs in members_by_root.items()
    ]
    # 보유 종목이 걸린 그룹(실제 중복 매수 위험)을 먼저, 그다음 보수 차이 큰 순
    groups.sort(key=lambda g: (not any(m.held for m in g.members), -(g.ter_gap_pct or 0.0)))
    return groups


def _build_group(members: list[_Item], reasons: set[str], max_corr: float | None) -> OverlapGroup:
    out_members = [
        OverlapMember(
            ticker=m.ticker,
            name=m.name,
            market=m.market,
            held=m.held,
            candidate=m.candidate,
            ter_pct=m.profile.get("ter_pct") if m.profile else None,
            base_index=m.profile.get("base_index") if m.profile else None,
        )
        for m in members
    ]
    with_ter = [m for m in out_members if m.ter_pct is not None]
    cheapest: OverlapMember | None = None
    ter_gap: float | None = None
    if len(with_ter) >= 2:
        cheapest = min(with_ter, key=lambda m: m.ter_pct or 0.0)
        ter_gap = round(max(m.ter_pct or 0.0 for m in with_ter) - (cheapest.ter_pct or 0.0), 4)
        if ter_gap <= 0:
            cheapest, ter_gap = None, None
    return OverlapGroup(
        reasons=sorted(reasons, key=lambda r: 0 if r == "SAME_INDEX" else 1),
        max_correlation=round(max_corr, 3) if max_corr is not None else None,
        members=out_members,
        cheapest_ticker=cheapest.ticker if cheapest else None,
        cheapest_market=cheapest.market if cheapest else None,
        ter_gap_pct=ter_gap,
    )


def build_items(candidates: list[dict], existing_items: list[tuple[str, str, str]]) -> list[_Item]:
    """등록 후보 + 보유 종목을 (ticker, market) 기준으로 합친다. 현금성은 제외."""
    by_key: dict[tuple[str, str], _Item] = {}
    for c in candidates:
        if c.get("asset_class") == "CASH" or str(c["market"]).upper() == CASH_EQUIVALENT_MARKET:
            continue
        by_key[(c["ticker"], c["market"])] = _Item(
            ticker=c["ticker"],
            name=c.get("name") or c["ticker"],
            market=c["market"],
            asset_class=c.get("asset_class") or "EQUITY",
            candidate=True,
            tracking_index=c.get("tracking_index"),
            distribution_frequency=resolve_distribution_frequency(
                c["ticker"], c["market"], c.get("distribution_frequency")
            ),
        )
    for ticker, name, market in existing_items:
        item = by_key.get((ticker, market))
        if item is not None:
            item.held = True
        else:
            by_key[(ticker, market)] = _Item(
                ticker=ticker,
                name=name,
                market=market,
                held=True,
                distribution_frequency=resolve_distribution_frequency(ticker, market),
            )
    return list(by_key.values())


def _digest(items: list[_Item]) -> str:
    payload = sorted(
        (i.ticker, i.market, i.name, i.asset_class, i.held, i.candidate, i.tracking_index, i.distribution_frequency)
        for i in items
    )
    raw = json.dumps([_CACHE_SCHEMA_VERSION, payload], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _is_relevant_held(item: _Item) -> bool:
    """보유 전용(후보 아님) 종목 중 비교 가치가 있는 것 — ETF 프로필이 있거나 지수 판별이 되는 종목.
    개별주 수십 개의 시세까지 받아 상관을 계산하지 않기 위함(개별주가 ETF와 0.97 상관일 일은 드물다)."""
    return item.candidate or item.profile is not None or resolve_index_key(item) is not None


async def analyze_candidate_overlap_for_user(
    cache: CacheStoreType,
    db: AsyncSession,
    user_id: uuid.UUID,
    draft_candidates: list[dict] | None,
) -> CandidateOverlapResponse:
    """사용자 단위 진입점 — 편집 중 목록(`draft_candidates`)이 없으면 저장된 후보 목록을, 보유 종목은
    전체 계좌 최신 포지션을 쓴다. 후보를 한 번도 등록하지 않았으면(시딩 전) 빈 결과."""
    if draft_candidates is not None:
        candidates = draft_candidates
    else:
        settings_row = await get_settings_row(db, user_id)
        candidates = list(getattr(settings_row, "goal_candidate_tickers", None) or [])
    pos_map = await query_latest_position_map(user_id, db, include_name=True)
    return await analyze_candidate_overlap(cache, candidates, existing_items_from_positions(pos_map))


async def analyze_candidate_overlap(
    cache: CacheStoreType,
    candidates: list[dict],
    existing_items: list[tuple[str, str, str]],
) -> CandidateOverlapResponse:
    """후보·보유 종목의 중복 그룹과 후보 ETF 프로필(보수 등)을 반환한다. 입력 해시 단위로 1일 캐싱."""
    items = build_items(candidates, existing_items)
    if not any(i.candidate for i in items):
        return CandidateOverlapResponse()

    cache_key = candidate_overlap_key(_digest(items))
    cached = await get_cached_json(cache, cache_key)
    if cached is not None:
        return CandidateOverlapResponse(**cached)

    profiles = await get_etf_profiles(cache, [(i.ticker, i.name, i.market) for i in items])
    for i in items:
        i.profile = profiles.get(i.key)
    items = [i for i in items if _is_relevant_held(i)]

    weekly, prices_complete = await _fetch_weekly_returns(items)
    groups = find_overlap_groups(items, weekly)
    result = CandidateOverlapResponse(
        groups=groups,
        profiles=[
            EtfProfileOut(
                ticker=i.ticker,
                market=i.market,
                ter_pct=i.profile.get("ter_pct"),
                base_index=i.profile.get("base_index"),
                issuer=i.profile.get("issuer"),
                tracking_error_pct=i.profile.get("tracking_error_pct"),
            )
            for i in items
            if i.profile is not None
        ],
        price_data_available=weekly is not None,
    )
    # 시세 조회가 전부/일부 실패한 결과(상관 판정 누락)는 캐싱하지 않는다 — 일시 장애를 하루 동안 고정하지 않기 위함.
    # Yahoo 서킷이 열리면 국내 심볼만 pykrx로 채워진 부분 결과가 오므로 "비어 있지 않음"만으로는 부족하다.
    if weekly is not None and prices_complete:
        await set_cached_json(cache, cache_key, result.model_dump(mode="json"), TTL_CANDIDATE_OVERLAP)
    return result


async def _fetch_weekly_returns(items: list[_Item]) -> tuple[pd.DataFrame | None, bool]:
    """(주간 수익률 프레임, 요청 심볼 전부의 시세를 받았는지)를 반환한다."""
    symbols = sorted({to_yf_symbol(i.ticker, i.market) for i in items})
    if len(symbols) < 2:
        return None, True
    end = today_kst()
    start = end - timedelta(days=_LOOKBACK_DAYS)
    try:
        close_series = await run_yf_bounded(fetch_yf_close_series, symbols, start, end)
    except Exception as e:
        logger.warning("candidate_overlap_price_fetch_failed", error=str(e))
        return None, False
    if not close_series:
        return None, False
    return weekly_returns_frame(close_series), set(symbols) <= set(close_series)
