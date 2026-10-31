"""전술 제안 비중을 포트폴리오 목표에 적용하는 계획(순수 함수).

적용 가능 여부, 현재 비중·그룹 요약, 할 일 판정, 분할 적용 보간, 지수 그룹(대표·멤버·국내 대체) 재구성을 맡는다.
DB 쓰기는 `tactical_allocation_service.apply_regime_to_portfolio`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from app.exceptions import BadRequestError, ConflictError
from app.models.portfolio import (
    GROUP_ROLE_DOMESTIC_ALT,
    GROUP_ROLE_MEMBER,
    Portfolio,
    PortfolioItem,
    PortfolioItemMember,
)
from app.services.tactical.tactical_regime import (
    _ASSET_META,
    _GROUP_KEY_ASSET,
    _LEVERAGED_PAIR,
    ASSET_GROUP_KEYS,
    REGIMES,
    TACTICAL_ASSETS,
    Regime,
    proposed_weights_for,
)

if TYPE_CHECKING:
    from app.models.tactical import TacticalStrategy
    from app.schemas.portfolio import IndexGroupSuggestion


def check_apply_allowed(
    portfolio: Portfolio, strategy: TacticalStrategy | None, fraction: float
) -> tuple[TacticalStrategy, Regime]:
    """제안 비중 적용 전 검증 — None이 아님이 확인된 전략과 적용할 확정 국면을 돌려준다.

    `fraction<1`(분할 적용)은 전술 자산만으로 구성된 포트폴리오에서만, 같은 국면에서 한 번만 허용한다 — 다른 종목을
    절반만 줄이는 건 전술 배분이 관리하는 범위가 아니고, 두 번째부터는 나머지 적용(fraction=1)이다.
    """
    if strategy is None:
        raise BadRequestError(detail="전술 배분을 먼저 켜주세요.")
    regime = strategy.last_regime
    if regime not in REGIMES:
        raise ConflictError(detail="아직 국면이 확정되지 않았습니다. 잠시 후 다시 시도해주세요.")
    if fraction < 1 and not is_tactical_managed(portfolio):
        raise BadRequestError(
            detail="전술 자산 외 종목이 있는 포트폴리오는 나눠서 적용할 수 없습니다. 한 번에 적용해주세요."
        )
    if fraction < 1 and strategy.partial_regime == regime:
        # 현재 목표에서 다시 절반을 보간하면 75%가 된다 — 두 번째는 나머지(전체) 적용만 허용
        raise BadRequestError(detail="이미 절반을 적용했어요. 나머지를 적용해주세요.")
    return strategy, regime


def tactical_asset_of(item: Any) -> str | None:
    """포트폴리오 항목이 어느 전술 자산인지 — 나스닥100·S&P500·다우 지수 그룹은 대표 종목과 무관하게 QQQ·SPY·DIA,
    그룹이 아닌 단독 항목은 ticker가 전술 자산일 때만. 그 외(다른 지수 그룹·개별 종목)는 None."""
    group_key = getattr(item, "group_key", None)
    if group_key:
        return _GROUP_KEY_ASSET.get(group_key)
    return item.ticker if item.ticker in TACTICAL_ASSETS else None


def _current_weights(portfolio: Portfolio) -> dict[str, float]:
    """현재 목표 비중 — 전술 자산은 자산 키(그룹은 QQQ·SPY·DIA)로, 나머지는 ticker 키로."""
    out: dict[str, float] = {}
    for item in portfolio.items:
        key = tactical_asset_of(item) or item.ticker
        out[key] = round(out.get(key, 0.0) + float(item.weight), 2)
    return out


def current_groups(portfolio: Portfolio) -> dict[str, dict[str, Any]]:
    """전술 자산별 지수 그룹 구성 요약(화면 보조 문구용) — 그룹이 아닌 자산은 넣지 않는다."""
    out: dict[str, dict[str, Any]] = {}
    for item in portfolio.items:
        asset = tactical_asset_of(item)
        if asset and getattr(item, "group_key", None):
            members = getattr(item, "members", None) or []
            out[asset] = {
                "label": item.group_label or "",
                "primary": item.ticker,
                "member_count": sum(1 for m in members if m.role == GROUP_ROLE_MEMBER),
                "domestic_alt": next((m.ticker for m in members if m.role == GROUP_ROLE_DOMESTIC_ALT), None),
            }
    return out


def is_tactical_managed(portfolio: Portfolio) -> bool:
    """포트폴리오가 전술 자산(나스닥100·S&P500·다우 지수 그룹 포함)만으로 구성됐는지 — 아니면 적용 시 다른 종목이
    지워진다는 경고 대상."""
    return all(tactical_asset_of(item) is not None for item in portfolio.items)


def pending_action(strategy: TacticalStrategy, portfolio: Portfolio) -> Literal["APPLY", "PARTIAL"] | None:
    """확정 국면의 제안 비중을 아직 적용하지 않았으면 "APPLY", 절반만 적용했으면 "PARTIAL" — 홈 "지금 할 일"용.

    프론트 `tacticalNextAction`의 action 톤과 같은 판정(적립 연동 모드는 호출부가 거른다). 전환 확인 중이면
    다음 거래일 재확인 후 적용하라는 안내뿐이라 할 일로 보지 않는다. 제안 비중은 저장된 틸트·웅덩이 단계로
    계산하므로(`apply_regime_to_portfolio`와 같은 `market={}`) 시세를 조회하지 않는다.
    """
    regime = strategy.last_regime
    if regime is None or strategy.pending_regime:
        return None
    if strategy.partial_regime == regime:
        return "PARTIAL"
    if strategy.applied_regime != regime:
        return "APPLY"
    proposed = proposed_weights_for(strategy, regime, {})
    current = _current_weights(portfolio)
    if any(round(current.get(a, 0.0), 1) != round(proposed.get(a, 0.0), 1) for a in TACTICAL_ASSETS):
        return "APPLY"
    return None


def interpolate_weights(current: dict[str, float], target: dict[str, float], fraction: float) -> dict[str, float]:
    """현재 목표에서 제안 비중 쪽으로 `fraction`만큼 이동(0.1%p 단위). 반올림 오차는 현금이 흡수한다."""
    out = {a: round(current.get(a, 0.0) + (target.get(a, 0.0) - current.get(a, 0.0)) * fraction, 1) for a in target}
    out["CASH"] = round(100.0 - sum(v for a, v in out.items() if a != "CASH"), 1)
    return out


class _MemberSpec(NamedTuple):
    ticker: str
    market: str
    name: str
    role: str
    leverage: float = 1.0


class _GroupSpec(NamedTuple):
    """다시 만들 지수 그룹 항목 — 대표 종목(ticker/market/name) + 라벨 + 멤버."""

    ticker: str
    market: str
    name: str
    label: str
    members: list[_MemberSpec]


def _weights_to_apply(
    portfolio: Portfolio, strategy: TacticalStrategy, regime: str, fraction: float
) -> dict[str, float]:
    weights = proposed_weights_for(strategy, regime, {})
    if fraction < 1:
        weights = interpolate_weights(_current_weights(portfolio), weights, fraction)
    return weights


def _existing_groups(portfolio: Portfolio) -> dict[str, Any]:
    return {
        asset: item
        for item in portfolio.items
        if getattr(item, "group_key", None) and (asset := tactical_asset_of(item)) is not None
    }


def needs_group_suggestions(
    portfolio: Portfolio, strategy: TacticalStrategy, regime: str, fraction: float = 1.0
) -> bool:
    """적용 시 새로 만들 지수 그룹이 있는지 — 있을 때만 호출부가 보유 종목 기반 그룹 제안을 조회한다."""
    weights = _weights_to_apply(portfolio, strategy, regime, fraction)
    existing = _existing_groups(portfolio)
    return any(weights.get(a, 0) > 0 and a not in existing for a in ASSET_GROUP_KEYS)


def _group_from_item(item: Any) -> _GroupSpec:
    return _GroupSpec(
        ticker=item.ticker,
        market=item.market,
        name=item.name,
        label=item.group_label or "",
        members=[_MemberSpec(m.ticker, m.market, m.name, m.role, float(m.leverage or 1)) for m in (item.members or [])],
    )


def _group_from_suggestion(asset: str, suggestion: IndexGroupSuggestion | None) -> _GroupSpec:
    """새 그룹 — 대표 종목은 전술 자산(판정·백테스트 기준 ETF), 멤버·국내 대체는 보유 종목 기반 제안에서."""
    from app.services.etf.etf_index_classifier import index_label

    name, market = _ASSET_META[asset]
    label = suggestion.label if suggestion else index_label(ASSET_GROUP_KEYS[asset])
    members: list[_MemberSpec] = []
    if suggestion is not None:
        alt = suggestion.domestic_alt
        skip = {asset} | ({alt.ticker} if alt else set())
        members = [
            _MemberSpec(m.ticker, m.market, m.name, GROUP_ROLE_MEMBER, m.leverage)
            for m in suggestion.members
            if m.ticker not in skip
        ]
        if alt is not None:
            members.append(_MemberSpec(alt.ticker, alt.market, alt.name, GROUP_ROLE_DOMESTIC_ALT))
    return _GroupSpec(ticker=asset, market=market, name=name, label=label, members=members)


def _plan_groups(
    portfolio: Portfolio,
    weights: dict[str, float],
    suggestions: dict[str, IndexGroupSuggestion] | None,
) -> dict[str, _GroupSpec]:
    """비중>0인 QQQ·SPY·DIA의 그룹 구성 — 기존 그룹은 그대로, 없으면 제안으로 새로. 레버리지 규칙 반영.

    QLD·SSO 비중>0이면 단독 항목으로 관리하므로 짝 그룹 멤버에서 뺀다(한 종목은 한 항목에만). 0%면 예전 단독
    항목이었던 경우 짝 그룹의 레버리지 멤버로 옮긴다 — 목표에 없는 종목으로 전량 매도되지 않고 그룹이 비중을
    넘을 때 먼저 팔린다(group_expansion).
    """
    existing = _existing_groups(portfolio)
    groups: dict[str, _GroupSpec] = {}
    for asset, group_key in ASSET_GROUP_KEYS.items():
        if weights.get(asset, 0) <= 0:
            continue
        if asset in existing:
            groups[asset] = _group_from_item(existing[asset])
        else:
            groups[asset] = _group_from_suggestion(asset, (suggestions or {}).get(group_key))

    standalone = {item.ticker for item in portfolio.items if not getattr(item, "group_key", None)}
    for lev, (pair, multiple) in _LEVERAGED_PAIR.items():
        spec = groups.get(pair)
        if spec is None:
            continue
        members = [m for m in spec.members if m.ticker != lev]
        if weights.get(lev, 0) <= 0:
            held = next((m for m in spec.members if m.ticker == lev), None)
            if held is not None:
                members.append(held)
            elif lev in standalone:
                name, market = _ASSET_META[lev]
                members.append(_MemberSpec(lev, market, name, GROUP_ROLE_MEMBER, multiple))
        groups[pair] = spec._replace(members=members)
    return groups


def _new_item(portfolio: Portfolio, asset: str, weight: float, idx: int, spec: _GroupSpec | None) -> PortfolioItem:
    if spec is None:
        name, market = _ASSET_META[asset]
        return PortfolioItem(
            portfolio_id=portfolio.id, ticker=asset, name=name, market=market, weight=weight, sort_order=idx
        )
    return PortfolioItem(
        portfolio_id=portfolio.id,
        ticker=spec.ticker,
        name=spec.name,
        market=spec.market,
        weight=weight,
        sort_order=idx,
        group_key=ASSET_GROUP_KEYS[asset],
        group_label=spec.label or None,
        members=[
            PortfolioItemMember(
                ticker=m.ticker, market=m.market, name=m.name, role=m.role, leverage=m.leverage, sort_order=i
            )
            for i, m in enumerate(spec.members)
        ],
    )
