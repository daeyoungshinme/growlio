"""추종 지수별 비중 집계 (`GET /portfolio/index-exposure`, 정보 제공 전용).

보유 종목을 `etf_index_classifier.classify_holding`으로 분류해 같은 지수를 추종하는 국내·해외 ETF를
한 그룹으로 합산한다. 포지션은 `build_portfolio_overview`(비-lite) 결과를 그대로 쓴다 — 자산탭
"주식 총평가액"·종목별 비중 차트와 같은 소스·같은 캐시라 금액이 어긋나지 않고, 동기화 시 무효화도
overview 캐시 무효화에 그대로 얹힌다. 이 응답 자체는 캐싱하지 않는다(ETF 프로필은 7일 전역 캐시).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.constants import is_non_tradable
from app.schemas.portfolio import (
    IndexExposureGroup,
    IndexExposureMember,
    IndexExposureResponse,
    IndexGroupSuggestion,
    IndexGroupSuggestionMember,
    IndexGroupSuggestionResponse,
    RegionExposure,
)
from app.services.etf_index_classifier import IndexClass, classify_holding, index_label, is_domestic_listed
from app.services.etf_profile_service import get_etf_profiles_with_status
from app.services.portfolio_service import build_portfolio_overview
from app.services.recommendation_universe import RECOMMENDATION_UNIVERSE

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.cache_keys import CacheStoreType


_STATIC_GROUPS: dict[str, tuple[str, str]] = {
    # kind → (group key, label)
    "OTHER_ETF": ("OTHER_ETF", "기타 ETF"),
    "LEVERAGED": ("LEVERAGED", "레버리지·인버스"),
    "STOCK": ("STOCK", "개별주"),
}
_KIND_ORDER = {"INDEX": 0, "OTHER_ETF": 1, "LEVERAGED": 2, "STOCK": 3}


def _pct(part: float, total: float) -> float:
    return round(part / total * 100, 2) if total > 0 else 0.0


def merge_holdings(positions: list[dict]) -> list[dict]:
    """계좌별 포지션을 ticker+market으로 합산한다. 현금·부동산·평가액 0 이하는 제외."""
    merged: dict[tuple[str, str], dict] = {}
    for p in positions:
        ticker, market = p["ticker"], p["market"]
        if is_non_tradable(ticker, market):
            continue
        entry = merged.setdefault(
            (ticker, market), {"ticker": ticker, "market": market, "name": p.get("name") or ticker, "value_krw": 0.0}
        )
        entry["value_krw"] += float(p.get("value_krw") or 0)
    return [h for h in merged.values() if h["value_krw"] > 0]


def build_index_exposure(
    holdings: list[dict], classes: dict[tuple[str, str], IndexClass], profiles_complete: bool = True
) -> IndexExposureResponse:
    """순수 집계 — `holdings`는 `merge_holdings` 결과, `classes`는 (ticker, market)별 분류 결과."""
    total_stock = sum(h["value_krw"] for h in holdings)
    total_etf = sum(h["value_krw"] for h in holdings if classes[(h["ticker"], h["market"])].kind != "STOCK")

    buckets: dict[str, dict] = {}
    for h in holdings:
        cls = classes[(h["ticker"], h["market"])]
        if cls.kind == "INDEX" and cls.index_key:
            key, label = cls.index_key, cls.label or cls.index_key
        else:
            key, label = _STATIC_GROUPS[cls.kind]
        bucket = buckets.setdefault(key, {"label": label, "kind": cls.kind, "members": []})
        bucket["members"].append((h, cls))

    groups: list[IndexExposureGroup] = []
    for key, bucket in buckets.items():
        members = sorted(bucket["members"], key=lambda m: -m[0]["value_krw"])
        value = sum(h["value_krw"] for h, _ in members)
        domestic = sum(h["value_krw"] for h, _ in members if is_domestic_listed(h["market"]))
        groups.append(
            IndexExposureGroup(
                key=key,
                label=bucket["label"],
                kind=bucket["kind"],
                value_krw=value,
                pct_of_stock=_pct(value, total_stock),
                pct_of_etf=None if bucket["kind"] == "STOCK" else _pct(value, total_etf),
                has_hedged=any(c.hedged for _, c in members),
                domestic_krw=domestic,
                overseas_krw=value - domestic,
                members=[
                    IndexExposureMember(
                        ticker=h["ticker"],
                        name=h["name"],
                        market=h["market"],
                        listing="DOMESTIC" if is_domestic_listed(h["market"]) else "OVERSEAS",
                        value_krw=h["value_krw"],
                        hedged=c.hedged,
                        pct_of_stock=_pct(h["value_krw"], total_stock),
                        region=c.region,
                        underlying_index_key=c.index_key if c.kind == "LEVERAGED" else None,
                        leverage=c.leverage,
                    )
                    for h, c in members
                ],
            )
        )
    groups.sort(key=lambda g: (_KIND_ORDER[g.kind], -g.value_krw))

    region_totals: dict[str | None, float] = {"DOMESTIC": 0.0, "OVERSEAS": 0.0, None: 0.0}
    for h in holdings:
        region_totals[classes[(h["ticker"], h["market"])].region] += h["value_krw"]
    return IndexExposureResponse(
        total_stock_krw=total_stock,
        total_etf_krw=total_etf,
        groups=groups,
        region_exposure=RegionExposure(
            domestic_krw=region_totals["DOMESTIC"],
            overseas_krw=region_totals["OVERSEAS"],
            unknown_krw=region_totals[None],
        ),
        profiles_complete=profiles_complete,
    )


async def get_index_exposure(
    cache: CacheStoreType,
    db: AsyncSession,
    user_id: uuid.UUID,
    account_ids: list[uuid.UUID] | None = None,
) -> IndexExposureResponse:
    overview = await build_portfolio_overview(user_id, db, account_ids=account_ids, cache=cache)
    holdings = merge_holdings(overview.get("all_positions") or [])
    if not holdings:
        return IndexExposureResponse()

    profiles, unresolved = await get_etf_profiles_with_status(
        cache, [(h["ticker"], h["name"], h["market"]) for h in holdings]
    )
    classes = {
        (h["ticker"], h["market"]): classify_holding(
            h["ticker"], h["market"], h["name"], profiles.get((h["ticker"], h["market"]))
        )
        for h in holdings
    }
    # 조회 실패한 종목이라도 이미 지수/레버리지로 판별됐으면 결과에 영향 없음 — 개별주/기타로 떨어진 경우만 불완전.
    incomplete = any(classes[k].kind in ("STOCK", "OTHER_ETF") for k in unresolved if k in classes)
    return build_index_exposure(holdings, classes, profiles_complete=not incomplete)


def _universe_candidates(index_key: str, domestic: bool) -> list[IndexGroupSuggestionMember]:
    return [
        IndexGroupSuggestionMember(ticker=c["ticker"], market=c["market"], name=c["name"])
        for c in RECOMMENDATION_UNIVERSE
        if c.get("tracking_index") == index_key and is_domestic_listed(c["market"]) == domestic
    ]


def _merge_candidates(
    held: list[IndexGroupSuggestionMember], universe: list[IndexGroupSuggestionMember]
) -> list[IndexGroupSuggestionMember]:
    seen = {(m.ticker, m.market) for m in held}
    return held + [c for c in universe if (c.ticker, c.market) not in seen]


def build_index_group_suggestions(
    exposure: IndexExposureResponse,
    in_scope_keys: set[tuple[str, str]] | None = None,
    account_names: dict[tuple[str, str], list[str]] | None = None,
) -> IndexGroupSuggestionResponse:
    """추종 지수별 비중 결과를 리밸런싱 지수 그룹 제안으로 바꾼다(순수 함수, plans/74).

    `exposure`는 전체 계좌 기준이고, `in_scope_keys`(분석 대상 계좌의 보유 키, None이면 전부 범위 안) 밖의
    멤버는 `in_scope=False`로 표시해 함께 넣는다 — 다른 계좌에만 있는 QLD도 묶을 수 있게(그 계좌를 분석
    대상에 추가해야 합산된다). 멤버와 대표·대체 후보는 범위 안 보유가 먼저다.

    INDEX 그룹 멤버에 기초 지수가 같은 정방향 레버리지(QLD → 나스닥100)를 합친다. 레버리지는 노출 기준
    (평가액 × 배수)으로 합산되며 대표·국내 대체 매수 후보에서는 빠진다(1배만 매수). 레버리지만 보유해도
    1배 후보(큐레이션 유니버스)가 있으면 제안한다.
    대표 매수 종목: 보유 중인 해외 상장 1배 멤버 중 평가액 최대 → 없으면 큐레이션 해외 ETF → 그것도 없으면 국내.
    국내 대체 매수 종목(ISA·연금 계좌용)은 대표가 해외 상장일 때만 — 보유 국내 1배 멤버 최대 → 큐레이션 국내 ETF.
    인버스·커버드콜·개별주는 지수 노출이 달라 합치지 않는다(커버드콜은 별도 키라 INDEX여도 자기 그룹).
    """
    buckets: dict[str, dict] = {}
    for g in exposure.groups:
        if g.kind == "INDEX":
            bucket = buckets.setdefault(g.key, {"label": g.label, "members": []})
            bucket["label"] = g.label
            bucket["members"] += g.members
        elif g.kind == "LEVERAGED":
            for m in g.members:
                if m.underlying_index_key:
                    key = m.underlying_index_key
                    buckets.setdefault(key, {"label": index_label(key), "members": []})["members"].append(m)

    groups: list[IndexGroupSuggestion] = []
    for key, bucket in buckets.items():
        held = sorted(
            (
                IndexGroupSuggestionMember(
                    ticker=m.ticker,
                    market=m.market,
                    name=m.name,
                    value_krw=m.value_krw,
                    leverage=m.leverage,
                    in_scope=in_scope_keys is None or (m.ticker, m.market) in in_scope_keys,
                    account_names=(account_names or {}).get((m.ticker, m.market), []),
                )
                for m in bucket["members"]
            ),
            key=lambda m: (not m.in_scope, -m.value_krw),
        )
        unlevered = [m for m in held if m.leverage == 1]
        overseas = _merge_candidates(
            [m for m in unlevered if not is_domestic_listed(m.market)], _universe_candidates(key, domestic=False)
        )
        domestic = _merge_candidates(
            [m for m in unlevered if is_domestic_listed(m.market)], _universe_candidates(key, domestic=True)
        )
        primary_candidates = overseas or domestic
        if not primary_candidates:
            continue  # 1배로 살 종목이 없으면 그룹을 만들 수 없다(레버리지만 있고 큐레이션 후보도 없음)
        primary = primary_candidates[0]
        primary_is_overseas = not is_domestic_listed(primary.market)
        value = sum(m.value_krw for m in held)
        groups.append(
            IndexGroupSuggestion(
                key=key,
                label=bucket["label"],
                value_krw=value,
                exposure_krw=sum(m.value_krw * m.leverage for m in held),
                pct_of_stock=_pct(value, exposure.total_stock_krw),
                primary=primary,
                domestic_alt=domestic[0] if primary_is_overseas and domestic else None,
                members=held,
                primary_candidates=primary_candidates,
                domestic_alt_candidates=domestic if primary_is_overseas else [],
            )
        )
    groups.sort(key=lambda g: -g.value_krw)
    return IndexGroupSuggestionResponse(groups=groups, profiles_complete=exposure.profiles_complete)


async def get_index_group_suggestions(
    cache: CacheStoreType,
    db: AsyncSession,
    user_id: uuid.UUID,
    account_ids: list[uuid.UUID] | None = None,
) -> IndexGroupSuggestionResponse:
    """`GET /portfolios/index-group-suggestions` — 지수별 비중 집계(전체 계좌)를 재사용하고, `account_ids`
    (포트폴리오 분석 대상 계좌) 밖에만 있는 종목은 `in_scope=False`로 표시한다."""
    exposure = await get_index_exposure(cache, db, user_id, None)
    overview = await build_portfolio_overview(user_id, db, account_ids=None, cache=cache)  # 위 호출과 같은 캐시
    names: dict[tuple[str, str], list[str]] = {}
    for p in overview.get("all_positions") or []:
        if float(p.get("value_krw") or 0) <= 0:
            continue
        bucket = names.setdefault((p.get("ticker", ""), p.get("market", "")), [])
        account_name = p.get("account_name") or ""
        if account_name and account_name not in bucket:
            bucket.append(account_name)
    in_scope_keys: set[tuple[str, str]] | None = None
    if account_ids:
        scoped = await build_portfolio_overview(user_id, db, account_ids=account_ids, cache=cache)
        in_scope_keys = {
            (p.get("ticker", ""), p.get("market", ""))
            for p in scoped.get("all_positions") or []
            if float(p.get("value_krw") or 0) > 0
        }
    return build_index_group_suggestions(exposure, in_scope_keys, names)
