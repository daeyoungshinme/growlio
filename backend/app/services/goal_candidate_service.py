"""목표 역산 추천 후보 종목 관리/영속화.

`UserSettings.goal_candidate_tickers`(사용자가 "후보 ETF 관리"에서 등록한 후보) 조회·시딩·
세제유형별 필터링·동시 요청 간 lost-update 방지를 포함한 DB 접근 로직 — `goal_recommendation_service.py`
에서 분리한 서브모듈이다.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants import DOMESTIC_MARKETS
from app.models.asset import AssetAccount
from app.models.user import UserSettings
from app.services.recommendation_universe import (
    MAX_GOAL_CANDIDATE_TICKERS,
    RECOMMENDATION_UNIVERSE,
    guess_asset_class,
    resolve_index_region,
    resolve_tracking_index,
)

_TAX_TYPE_MARKET_GROUP: dict[str, str] = {
    "GENERAL": "DOMESTIC",
    "ISA": "DOMESTIC",
    "PENSION_SAVINGS": "DOMESTIC",
    "IRP": "DOMESTIC",
    "OVERSEAS_DEDICATED": "OVERSEAS",
}
"""세제유형별 투자 가능 시장 — ISA/연금저축/IRP/일반 계좌는 국내(국내주식+국내ETF)만,
해외전용 계좌는 해외(해외주식+해외ETF)만 추천 후보로 허용한다."""
_TAX_TYPE_INDEX_REGION_PREFERENCE: dict[str, str] = {
    "GENERAL": "DOMESTIC",
    "ISA": "OVERSEAS",
    "PENSION_SAVINGS": "OVERSEAS",
    "IRP": "OVERSEAS",
    "OVERSEAS_DEDICATED": "OVERSEAS",
}
"""세제유형별 선호 추종지수 지역(EQUITY 후보 한정) — ISA/연금저축/IRP는 국내상장이지만 해외지수를
추종하는 ETF(나스닥100 등)를, 일반 계좌는 국내지수를 추종하는 종목/ETF를 우선 추천한다.
`_TAX_TYPE_MARKET_GROUP`(상장거래소 기준)과 달리 이건 추종지수 기준이라 별개 축이다.
OVERSEAS_DEDICATED도 이 맵에 포함하는 이유는 선호 지역 좁히기가 아니라 `_apply_index_region_preference`의
큐레이션 보강(등록 후보 부족 시 `RECOMMENDATION_UNIVERSE`에서 자동 추가) 경로를 태우기 위함이다 —
`preferred_equity` 계산에서 OVERSEAS_DEDICATED는 항상 상장거래소가 해외인 후보만 통과하도록 별도
조건을 추가로 강제하므로(아래 `_apply_index_region_preference` 참고), KRX 상장·해외지수 추종 ETF가
이 세제유형 후보로 섞여 들어가지는 않는다."""


def _matches_index_region_preference(c: dict[str, str], tax_type_value: str) -> bool:
    """EQUITY 후보가 세제유형별 선호 추종지수 지역(`_TAX_TYPE_INDEX_REGION_PREFERENCE`)에 맞는지
    판별한다 — BOND/CASH는 지역 선호의 영향을 받지 않으므로 항상 True.

    `_apply_index_region_preference()`(등록된 후보 목록을 지역 선호로 좁히는 필터)와
    `_suggest_for_dividend_goal()`(배당 목표 미달성 시 큐레이션 유니버스에서 고배당 후보를
    제안하는 기능)이 같은 판별 규칙을 쓰도록 공유한다 — 전자만 적용하면 "등록 후보는 지역
    선호가 지켜지는데 제안되는 후보는 지켜지지 않는" 비일관성이 생긴다.
    """
    if c.get("asset_class", "EQUITY") != "EQUITY":
        return True
    preferred_region = _TAX_TYPE_INDEX_REGION_PREFERENCE.get(tax_type_value)
    if not preferred_region:
        return True
    # OVERSEAS_DEDICATED는 추종지수가 아니라 상장거래소가 실제 매수 가능 여부를 결정한다 — KRX
    # 상장·해외지수 추종 ETF는 이 세제유형 계좌에서 매수할 수 없으므로 항상 제외한다.
    if tax_type_value == "OVERSEAS_DEDICATED" and c["market"].upper() in DOMESTIC_MARKETS:
        return False
    return resolve_index_region(c["ticker"], c["market"], c.get("index_region")) == preferred_region


def _apply_index_region_preference(
    candidates: list[dict[str, str]], tax_type_value: str, capacity_remaining: int
) -> tuple[list[dict[str, str]], str | None, list[dict[str, str]]]:
    """EQUITY 후보를 세제유형별 선호 추종지수 지역으로 좁힌다. BOND/CASH는 영향받지 않는다.

    선호 지역에 맞는 EQUITY 후보가 사용자 등록 목록에 하나도 없으면(예: ISA인데 해외지수 추종
    ETF 미등록), 큐레이션 유니버스(`RECOMMENDATION_UNIVERSE`)에서 선호 지역·해당 세제유형이
    투자 가능한 시장에 맞는 ETF를 찾아 자동 보강한다 — 사용자가 직접 등록하지 않아도 항상
    선호 지역 위주로 추천되도록 하기 위함. 보강된 후보는 세 번째 반환값(`added`)으로 함께
    돌려주며, 호출측이 이를 `UserSettings.goal_candidate_tickers`에도 실제로 등록해 "후보 ETF
    관리" 화면에 반영해야 한다 — 계산에만 쓰이고 등록 목록엔 안 보이면 사용자가 당황하기 때문.

    `capacity_remaining`(등록 가능 잔여 슬롯, `MAX_GOAL_CANDIDATE_TICKERS - 전체 등록 후보 수`)보다
    보강 후보가 많아 전부 등록할 수 없으면(등록 한도 초과) 보강 자체를 포기한다 — 계산에 쓰인
    후보와 실제 등록되는 후보가 항상 일치하도록 하기 위한 전부 아니면 전무 규칙. 큐레이션 보강도
    실패하거나 포기되면, 선호 지역에 맞지 않는 EQUITY는 제외하고(BOND/CASH는 그대로 유지)
    `added=[]`로 반환한다 — 원본을 그대로 반환하면 이 함수의 존재 목적(세제유형별 선호 지역
    외 EQUITY 배제)이 무력화되므로, 보강이 불가능해도 필터링 자체는 포기하지 않는다.
    """
    preferred_region = _TAX_TYPE_INDEX_REGION_PREFERENCE.get(tax_type_value)
    if not preferred_region:
        return candidates, None, []

    non_equity = [c for c in candidates if c.get("asset_class", "EQUITY") != "EQUITY"]
    equity_candidates = [c for c in candidates if c.get("asset_class", "EQUITY") == "EQUITY"]
    preferred_equity = [c for c in equity_candidates if _matches_index_region_preference(c, tax_type_value)]

    if preferred_equity:
        return preferred_equity + non_equity, None, []
    if not equity_candidates:
        # 애초에 EQUITY 후보가 하나도 없던 경우(예: 시장그룹 필터에서 전부 걸러짐) — 이 함수의
        # 관심사(등록은 했지만 지역이 안 맞음)가 아니므로 큐레이션 보강 없이 그대로 통과시킨다.
        return candidates, None, []

    region_label = "해외지수 추종 ETF" if preferred_region == "OVERSEAS" else "국내지수 추종 종목/ETF"
    market_group = _TAX_TYPE_MARKET_GROUP.get(tax_type_value, "DOMESTIC")
    seen = {(c["ticker"], c["market"]) for c in candidates}
    curated_fallback = [
        c
        for c in RECOMMENDATION_UNIVERSE
        if c.get("asset_class", "EQUITY") == "EQUITY"
        and resolve_index_region(c["ticker"], c["market"], c.get("index_region")) == preferred_region
        and (c["market"].upper() in DOMESTIC_MARKETS) == (market_group == "DOMESTIC")
        and (c["ticker"], c["market"]) not in seen
    ]
    if curated_fallback and len(curated_fallback) <= capacity_remaining:
        note = (
            f"등록된 후보 중 {region_label}가 없어 큐레이션 ETF를 후보 목록에 자동 등록했습니다 — "
            "후보 ETF 관리에서 확인·삭제할 수 있습니다"
        )
        return curated_fallback + non_equity, note, curated_fallback

    note = (
        f"등록된 후보 중 {region_label}가 없어 이번 추천에서는 해당 EQUITY 후보 없이 계산했습니다 — "
        "후보 ETF 관리에서 등록해주세요"
    )
    return non_equity, note, []


def detect_duplicate_tracking_index_note(
    candidates: list[dict[str, str]], existing_items: list[tuple[str, str, str]]
) -> str | None:
    """등록된 후보 중 실제 보유 종목과 동일 지수를 추종하는 다른 티커가 남아있으면 안내
    문구를 반환한다 — 이미 저장된 `UserSettings.goal_candidate_tickers`를 자동으로 수정하지는
    않는다(`_get_or_seed_candidates`가 최초 1회만 시딩하고 이후 자동 병합하지 않는 기존
    설계와 동일 — 사용자 동의 없이 후보 목록을 바꾸지 않는다). `_seed_candidate_tickers`가
    신규 시딩 시에는 이런 중복을 만들지 않지만, 그 로직이 도입되기 전부터 서로 다른 운용사의
    동일 지수 ETF를 보유종목과 함께 등록해버린 기존 사용자(예: ACE 미국S&P500 보유 + TIGER
    미국S&P500 후보 등록)에게 정리를 권유하기 위한 용도다.

    비교 대상을 "실제 보유 종목"으로 한정하는 이유 — 등록 후보끼리(예: 세제유형 필터링 전
    `RECOMMENDATION_UNIVERSE`가 함께 포함하는 SPY/VOO/TIGER 미국S&P500)는 계좌 유형(해외전용
    증권사 계좌 vs 국내상장 ISA/연금 계좌)에 따라 의도적으로 병존하는 경우가 흔해, 후보끼리
    비교하면 정상적인 조합까지 "중복"으로 오탐한다. 배당주기가 명시된 종목(`distribution_frequency`,
    예: 446720 월배당)도 실질적으로 다른 선택지일 수 있어 비교에서 제외한다.
    """
    held_index_labels: dict[str, tuple[str, str]] = {}
    held_keys = {(t, m) for t, _, m in existing_items}
    for t, name, m in existing_items:
        idx = resolve_tracking_index(t, m, name, None)
        if idx is not None:
            held_index_labels.setdefault(idx, (t, name))

    for c in candidates:
        if (c["ticker"], c["market"]) in held_keys or c.get("distribution_frequency"):
            continue
        idx = resolve_tracking_index(c["ticker"], c["market"], c["name"], c.get("tracking_index"))
        if idx is None:
            continue
        held = held_index_labels.get(idx)
        if held is not None:
            held_ticker, held_name = held
            return (
                f"{c['name']}({c['ticker']})은 이미 보유 중인 {held_name}({held_ticker})과 동일 지수를 "
                "추종합니다 — 후보 ETF 관리에서 정리 여부를 확인해보세요"
            )
    return None


def existing_items_from_positions(pos_map: dict[str, dict]) -> list[tuple[str, str, str]]:
    """전체 계좌 실제 보유 포지션(query_latest_position_map 결과)을 추천 후보 시드로 사용."""
    return [
        (p["ticker"], p.get("name") or p["ticker"], p["market"])
        for p in pos_map.values()
        if p["ticker"] != "CASH" and p["market"] != "KR_PROPERTY"
    ]


def _seed_candidate_tickers(existing_items: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    """후보를 한 번도 등록한 적 없을 때 초기 후보(보유종목 + 큐레이션 ETF)를 구성한다.

    보유 종목을 우선 채우고 남는 자리를 큐레이션 ETF로 채우되, `MAX_GOAL_CANDIDATE_TICKERS`를
    넘지 않는다 — 저장 시 `GoalCandidateTickersUpdate` 검증(최대 개수)을 통과해야 하기 때문.

    보유 종목은 `asset_class` 태그가 없으므로 `guess_asset_class(name)`으로 추정치를 채운다 —
    이 값이 없으면 하위 로직(`c.get("asset_class", "EQUITY")`)이 전부 EQUITY로 취급해, 채권혼합
    ETF 같은 안전자산 보유종목이 IRP 안전자산 30% 하한 계산에서 위험자산으로 오분류된다.
    휴리스틱이라 부정확할 수 있으므로 "후보 ETF 관리"에서 사용자가 언제든 수정 가능해야 한다.

    큐레이션 ETF를 채울 때는 `(ticker, market)` 완전 일치뿐 아니라, 보유 종목과 동일 지수를
    추종하는 ETF(`resolve_tracking_index`)도 건너뛴다 — 예를 들어 `ACE 미국S&P500`을 이미
    보유 중이면 큐레이션 유니버스의 `TIGER 미국S&P500`(같은 S&P500 지수, 운용사만 다름)을
    중복으로 추가하지 않는다. 큐레이션 항목끼리는(예: 458730/446720 배당다우존스 분기·월배당
    쌍) 이 검사에 걸리지 않는다 — `held_indexes`는 보유 종목에서만 채워지기 때문에 큐레이션
    유니버스 자체의 의도적인 지수 중복(배당주기 차이)은 그대로 유지된다. 다만 `held_indexes`
    자체는 배당주기를 구분하지 않으므로, 458730(분기배당)을 이미 보유 중이면 자동 시딩 시
    446720(월배당)도 함께 건너뛴다 — `detect_duplicate_tracking_index_note`와 달리 자동 채움
    단계는 "배당주기까지 다르면 별개로 취급"하지 않고 보수적으로 하나만 남긴다(과다 추천보다
    과소 추천이 안전하다는 원칙). 월배당을 원하면 "후보 ETF 관리"에서 수동으로 추가하면 된다.
    """
    seen: set[tuple[str, str]] = set()
    held_indexes: set[str] = set()
    seed: list[dict[str, str]] = []
    for t, name, m in existing_items:
        if len(seed) >= MAX_GOAL_CANDIDATE_TICKERS:
            break
        if (t, m) in seen:
            continue
        seen.add((t, m))
        tracking_index = resolve_tracking_index(t, m, name, None)
        if tracking_index:
            held_indexes.add(tracking_index)
        seed.append({"ticker": t, "name": name, "market": m, "asset_class": guess_asset_class(name)})
    for c in RECOMMENDATION_UNIVERSE:
        if len(seed) >= MAX_GOAL_CANDIDATE_TICKERS:
            break
        if (c["ticker"], c["market"]) in seen:
            continue
        if c.get("tracking_index") in held_indexes:
            continue
        seen.add((c["ticker"], c["market"]))
        seed.append(c)
    return seed


async def _persist_added_candidates(
    db: AsyncSession, user_id: uuid.UUID, added: list[dict[str, str]]
) -> list[dict[str, str]]:
    """`added`를 잠금 후 재조회한 최신 `goal_candidate_tickers`에 병합해 커밋한다.

    `/goal-recommendation`과 `/goal-recommendation/by-horizon`은 완전히 독립된 요청·DB세션으로,
    둘 다 세제유형 선호 지수 지역에 맞는 큐레이션 ETF를 동시에 추가하려 할 수 있다. 각자 요청 시작
    시점에 읽은 스냅샷을 그대로 덮어쓰면 나중에 커밋하는 쪽이 먼저 커밋된 추가분을 지워버리는
    lost-update가 발생한다 — `with_for_update()`로 행을 잠그고 그 시점의 최신 값을 다시 읽어
    병합해야 두 요청의 추가분이 모두 살아남는다.

    `populate_existing=True`가 반드시 필요하다 — `settings_row`는 이 함수 호출 전에 이미 같은
    세션에서 한 번 로드돼 identity map에 올라가 있으므로, 이 옵션 없이 동일 PK를 다시 select하면
    SQLAlchemy는 DB에서 잠금만 걸 뿐 Python 객체 속성은 갱신하지 않고 기존(스테일한) 객체를
    그대로 반환한다 — 그러면 아래 `current`가 여전히 요청 시작 시점의 낡은 값이 되어 락을 걸어도
    lost-update가 재발한다.
    """
    locked_row = await db.scalar(
        select(UserSettings)
        .where(UserSettings.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_row is None:
        return added
    current = locked_row.goal_candidate_tickers or []
    seen = {(c["ticker"], c["market"]) for c in current}
    merged = current + [c for c in added if (c["ticker"], c["market"]) not in seen]
    if len(merged) > MAX_GOAL_CANDIDATE_TICKERS:
        merged = merged[:MAX_GOAL_CANDIDATE_TICKERS]
    locked_row.goal_candidate_tickers = merged
    await db.commit()
    return merged


async def _get_or_seed_candidates(
    db: AsyncSession,
    settings_row: UserSettings,
    existing_items: list[tuple[str, str, str]],
) -> list[dict[str, str]]:
    """등록된 후보 목록을 반환하거나, 한 번도 등록한 적 없으면 시딩 후 커밋한다.

    최초 시딩도 두 목표 역산 엔드포인트가 동시에 트리거할 수 있으므로 락을 걸고 재확인한다
    (`_persist_added_candidates`와 동일한 lost-update 방지 목적 — `populate_existing=True`가
    빠지면 이미 로드된 `settings_row`의 스테일한 속성이 그대로 반환되어 락이 무의미해진다).
    """
    candidate_dicts = getattr(settings_row, "goal_candidate_tickers", None)
    if candidate_dicts is None:
        user_id = getattr(settings_row, "user_id", None)
        locked_row = (
            await db.scalar(
                select(UserSettings)
                .where(UserSettings.user_id == user_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if user_id is not None
            else None
        )
        candidate_dicts = locked_row.goal_candidate_tickers if locked_row is not None else None
        if candidate_dicts is None:
            candidate_dicts = _seed_candidate_tickers(existing_items)
            target_row = locked_row if locked_row is not None else settings_row
            target_row.goal_candidate_tickers = candidate_dicts
            await db.commit()
    return candidate_dicts


async def _active_account_tax_types(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """활성 계좌들의 tax_type 목록을 조회한다 (전체 탭의 단일세제유형 판별용)."""
    rows = (
        (
            await db.execute(
                select(AssetAccount.tax_type).where(
                    AssetAccount.user_id == user_id,
                    AssetAccount.is_active == True,  # noqa: E712
                )
            )
        )
        .scalars()
        .all()
    )
    return list(rows)
