"""추종 지수별 비중 집계 (`GET /portfolio/index-exposure`, 정보 제공 전용).

보유 종목을 `etf_index_classifier.classify_holding`으로 분류해 같은 지수를 추종하는 국내·해외 ETF를
한 그룹으로 합산한다. 포지션은 `build_portfolio_overview`(비-lite) 결과를 그대로 쓴다 — 자산탭
"주식 총평가액"·종목별 비중 차트와 같은 소스·같은 캐시라 금액이 어긋나지 않고, 동기화 시 무효화도
overview 캐시 무효화에 그대로 얹힌다. 이 응답 자체는 캐싱하지 않는다(ETF 프로필은 7일 전역 캐시).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.constants import CASH_EQUIVALENT_MARKET
from app.schemas.portfolio import IndexExposureGroup, IndexExposureMember, IndexExposureResponse, RegionExposure
from app.services.etf_index_classifier import IndexClass, classify_holding, is_domestic_listed
from app.services.etf_profile_service import get_etf_profiles_with_status
from app.services.portfolio_service import build_portfolio_overview

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.utils.cache_keys import CacheStoreType

_EXCLUDED_TICKERS = frozenset({"CASH"})
_EXCLUDED_MARKETS = frozenset({CASH_EQUIVALENT_MARKET, "KR_PROPERTY"})

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
        if ticker in _EXCLUDED_TICKERS or str(market).upper() in _EXCLUDED_MARKETS:
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
