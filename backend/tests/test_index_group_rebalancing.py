"""지수 그룹 리밸런싱(plans/74) — 그룹 합산 분석·주문 전개·검증·제안."""

import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.portfolio import (
    IndexExposureGroup,
    IndexExposureMember,
    IndexExposureResponse,
    PortfolioCreate,
)
from app.schemas.rebalancing import TickerAccountInfo
from app.services.etf.index_exposure_service import build_index_group_suggestions
from app.services.goal.goal_recommendation_service import fold_into_portfolio_groups
from app.services.rebalancing.group_expansion import expand_group_items, iter_trade_items
from app.services.rebalancing.order_builder import build_rebalancing_orders
from app.services.rebalancing.service import analyze_rebalancing


def _sp500_group(weight: float = 40, with_alt: bool = True) -> dict:
    members = [{"ticker": "SPY", "market": "NYSE", "name": "SPDR S&P 500", "role": "MEMBER"}]
    if with_alt:
        members.append({"ticker": "360750", "market": "KOSPI", "name": "TIGER 미국S&P500", "role": "DOMESTIC_ALT"})
    return {
        "ticker": "VOO",
        "name": "Vanguard S&P 500",
        "market": "NYSE",
        "weight": weight,
        "group_key": "US_SP500",
        "group_label": "S&P 500",
        "members": members,
    }


def _portfolio(items: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name="지수 포트폴리오", base_type="STOCK_ONLY", items=items)


def _pos(ticker: str, market: str, value: float, price: float, account_id: str = "acc-general") -> dict:
    return {
        "ticker": ticker,
        "market": market,
        "name": ticker,
        "value_krw": value,
        "current_price": price,
        "qty": value / price,
        "account_id": account_id,
    }


def _overview(positions: list[dict], cash: float = 0.0, tax_type: str = "GENERAL") -> dict:
    stock = sum(p["value_krw"] for p in positions)
    return {
        "total_assets_krw": stock + cash,
        "total_stock_krw": stock,
        "all_positions": positions,
        "accounts": [{"id": "acc-general", "asset_type": "STOCK_KIS", "tax_type": tax_type}],
    }


class TestGroupAnalysis:
    def test_members_are_summed_and_not_sold_as_untracked(self):
        """VOO+SPY+TIGER 합계 40% = 목표 40% → 이탈 없음, SPY·TIGER가 전량 매도로 잡히지 않는다."""
        portfolio = _portfolio([_sp500_group(40), {"ticker": "QQQ", "name": "QQQ", "market": "NASDAQ", "weight": 60}])
        overview = _overview(
            [
                _pos("VOO", "NYSE", 200_000, 100_000),
                _pos("SPY", "NYSE", 100_000, 100_000),
                _pos("360750", "KOSPI", 100_000, 20_000),
                _pos("QQQ", "NASDAQ", 600_000, 100_000),
            ]
        )
        result = analyze_rebalancing(portfolio, overview)
        assert [i.ticker for i in result.items] == ["VOO", "QQQ"]
        group = result.items[0]
        assert group.group_key == "US_SP500"
        assert group.name == "S&P 500"
        assert group.current_value_krw == 400_000
        assert group.weight_diff_pct == 0
        assert group.shares_to_trade is None
        assert {m.ticker for m in group.members} == {"VOO", "SPY", "360750"}
        assert all(m.shares_to_trade == 0 for m in group.members)

    def test_group_underweight_buys_primary(self):
        portfolio = _portfolio([_sp500_group(100)])
        overview = _overview([_pos("SPY", "NYSE", 300_000, 100_000)], cash=700_000)
        group = analyze_rebalancing(portfolio, overview).items[0]
        assert group.diff_krw == 700_000
        voo = next(m for m in group.members if m.ticker == "VOO")
        assert voo.target_value_krw == 700_000
        # VOO 미보유·가격 없음 → 수량은 실행 직전 라이브 시세로 계산
        assert voo.shares_to_trade is None
        assert next(m for m in group.members if m.ticker == "SPY").shares_to_trade == 0


class TestGroupExpansion:
    def _group(self, positions: list[dict], weight: float, cash: float = 0.0):
        portfolio = _portfolio(
            [_sp500_group(weight), {"ticker": "CASH", "name": "", "market": "KRW", "weight": 100 - weight}]
        )
        return analyze_rebalancing(portfolio, _overview(positions, cash=cash)).items[0]

    def test_buy_goes_to_domestic_alt_in_tax_deferred_account(self):
        group = self._group(
            [_pos("VOO", "NYSE", 100_000, 100_000), _pos("360750", "KOSPI", 100_000, 20_000)], 75, 200_000
        )
        expanded = expand_group_items([group], "ISA")
        assert [(m.ticker, m.diff_krw) for m in expanded] == [("360750", 100_000)]
        assert expanded[0].shares_to_trade == 5  # 기준 400,000 × 75% - VOO 100,000 → 200,000/20,000=10 - 5

    def test_buy_stays_on_primary_without_alt(self):
        portfolio = _portfolio([_sp500_group(100, with_alt=False)])
        group = analyze_rebalancing(portfolio, _overview([_pos("VOO", "NYSE", 100_000, 100_000)], cash=100_000)).items[
            0
        ]
        expanded = expand_group_items([group], "PENSION_SAVINGS")
        assert [m.ticker for m in expanded] == ["VOO"]

    def test_sell_non_primary_smallest_first_then_primary(self):
        """초과 250,000 → TIGER(100k) 전량 → SPY(150k 중 150k) 전량 → 대표 VOO는 그대로."""
        positions = [
            _pos("VOO", "NYSE", 300_000, 100_000),
            _pos("SPY", "NYSE", 150_000, 50_000),
            _pos("360750", "KOSPI", 100_000, 20_000),
        ]
        group = self._group(positions, 30, cash=450_000)  # base 1,000,000 → 목표 300,000, 현재 550,000
        expanded = expand_group_items([group], "GENERAL")
        trades = {m.ticker: (m.target_value_krw, m.shares_to_trade) for m in expanded}
        assert trades == {"360750": (0, -5), "SPY": (0, -3)}

    def test_sell_overflows_into_primary(self):
        positions = [_pos("VOO", "NYSE", 400_000, 100_000), _pos("SPY", "NYSE", 100_000, 50_000)]
        group = self._group(positions, 20, cash=500_000)  # 목표 200,000, 현재 500,000 → 300,000 매도
        trades = {m.ticker: (m.target_value_krw, m.shares_to_trade) for m in expand_group_items([group], "GENERAL")}
        assert trades == {"SPY": (0, -2), "VOO": (200_000, -2)}

    def test_iter_trade_items_flattens_only_traded_members(self):
        positions = [_pos("VOO", "NYSE", 400_000, 100_000), _pos("SPY", "NYSE", 100_000, 50_000)]
        group = self._group(positions, 40, cash=500_000)  # 목표 400,000 → SPY 100,000만 매도
        assert [m.ticker for m in iter_trade_items([group])] == ["SPY"]

    def test_orders_use_buy_account_tax_type(self):
        group = self._group([_pos("360750", "KOSPI", 100_000, 20_000)], 50, cash=300_000)
        ticker_account_map = {
            "360750": [
                TickerAccountInfo(
                    account_id="isa-1", account_name="ISA", asset_type="STOCK_KIS", quantity=5, tax_type="ISA"
                )
            ]
        }
        orders = build_rebalancing_orders([group], ticker_account_map, "BUY_ONLY", "MARKET", "isa-1")
        assert [(o.ticker, o.side, o.quantity) for o in orders] == [
            ("360750", "BUY", 5)
        ]  # 기준 400,000 × 50% = 200,000 → 10주 - 5


class TestGroupValidation:
    def _body(self, items: list[dict]) -> dict:
        return {"name": "p", "items": items}

    def _group_item(self, **group) -> dict:
        return {
            "ticker": "VOO",
            "market": "NYSE",
            "name": "VOO",
            "weight": 100,
            "group": {"key": "US_SP500", "label": "S&P 500", **group},
        }

    def test_primary_and_alt_removed_from_members(self):
        body = PortfolioCreate(
            **self._body(
                [
                    self._group_item(
                        members=[{"ticker": "VOO", "market": "NYSE"}, {"ticker": "360750", "market": "KOSPI"}],
                        domestic_alt={"ticker": "360750", "market": "KOSPI"},
                    )
                ]
            )
        )
        assert body.items[0].group.members == []

    def test_overseas_domestic_alt_rejected(self):
        with pytest.raises(ValidationError, match="국내 상장"):
            PortfolioCreate(**self._body([self._group_item(domestic_alt={"ticker": "SPY", "market": "NYSE"})]))

    def test_member_also_standalone_rejected(self):
        items = [
            {**self._group_item(members=[{"ticker": "SPY", "market": "NYSE"}]), "weight": 50},
            {"ticker": "SPY", "market": "NYSE", "weight": 50},
        ]
        with pytest.raises(ValidationError, match="중복"):
            PortfolioCreate(**self._body(items))


def test_suggestions_pick_overseas_primary_and_domestic_alt():
    exposure = IndexExposureResponse(
        total_stock_krw=1_000_000,
        groups=[
            IndexExposureGroup(
                key="US_SP500",
                label="S&P 500",
                kind="INDEX",
                value_krw=500_000,
                pct_of_stock=50,
                pct_of_etf=50,
                domestic_krw=100_000,
                overseas_krw=400_000,
                members=[
                    IndexExposureMember(
                        ticker="SPY", name="SPY", market="NYSE", listing="OVERSEAS", value_krw=400_000, pct_of_stock=40
                    ),
                    IndexExposureMember(
                        ticker="379800",
                        name="KODEX 미국S&P500",
                        market="KOSPI",
                        listing="DOMESTIC",
                        value_krw=100_000,
                        pct_of_stock=10,
                    ),
                ],
            ),
            IndexExposureGroup(
                key="STOCK",
                label="개별주",
                kind="STOCK",
                value_krw=500_000,
                pct_of_stock=50,
                pct_of_etf=None,
                domestic_krw=500_000,
                overseas_krw=0,
                members=[],
            ),
        ],
    )
    result = build_index_group_suggestions(exposure)
    assert [g.key for g in result.groups] == ["US_SP500"]
    g = result.groups[0]
    assert (g.primary.ticker, g.domestic_alt.ticker) == ("SPY", "379800")
    # 큐레이션 유니버스의 같은 지수 ETF가 후보 뒤에 붙는다
    assert [c.ticker for c in g.primary_candidates][:2] == ["SPY", "VOO"]
    assert "360750" in [c.ticker for c in g.domestic_alt_candidates]


def test_fold_into_portfolio_groups():
    item = SimpleNamespace(
        ticker="VOO",
        market="NYSE",
        group_key="US_SP500",
        members=[SimpleNamespace(ticker="SPY", market="NYSE")],
    )
    folded = fold_into_portfolio_groups([("SPY", "NYSE", 30.0), ("VOO", "NYSE", 10.0), ("QQQ", "NASDAQ", 60.0)], [item])
    assert sorted(folded) == [("QQQ", "NASDAQ", 60.0), ("VOO", "NYSE", 40.0)]


def test_orm_group_property_serializes_to_schema():
    from app.models.portfolio import PortfolioItem as PortfolioItemRow
    from app.models.portfolio import PortfolioItemMember
    from app.schemas.portfolio import PortfolioItem as PortfolioItemSchema

    row = PortfolioItemRow(
        ticker="VOO", market="NYSE", name="VOO", weight=40, group_key="US_SP500", group_label="S&P 500"
    )
    row.members = [
        PortfolioItemMember(ticker="SPY", market="NYSE", name="SPY", role="MEMBER"),
        PortfolioItemMember(ticker="360750", market="KOSPI", name="TIGER", role="DOMESTIC_ALT"),
    ]
    item = PortfolioItemSchema.model_validate(row)
    assert item.group is not None
    assert [m.ticker for m in item.group.members] == ["SPY"]
    assert item.group.domestic_alt is not None
    assert item.group.domestic_alt.ticker == "360750"
    assert (
        PortfolioItemSchema.model_validate(PortfolioItemRow(ticker="QQQ", market="NASDAQ", name="", weight=60)).group
        is None
    )


class TestLeveragedMembers:
    """정방향 레버리지(QLD 등)는 기초 지수 그룹에 노출 기준(평가액 × 배수)으로 합산된다."""

    @pytest.mark.parametrize(
        ("ticker", "market", "name", "expected"),
        [
            ("QLD", "NASDAQ", "ProShares Ultra QQQ", (2.0, "US_NASDAQ100")),
            ("TQQQ", "NASDAQ", "ProShares UltraPro QQQ", (3.0, "US_NASDAQ100")),
            ("409820", "KOSPI", "KODEX 미국나스닥100레버리지(합성 H)", (2.0, "US_NASDAQ100")),
            ("122630", "KOSPI", "KODEX 레버리지", (2.0, "KR_KOSPI200")),
            ("SQQQ", "NASDAQ", "ProShares UltraPro Short QQQ", (1.0, None)),
            ("114800", "KOSPI", "KODEX 인버스", (1.0, None)),
            ("252670", "KOSPI", "KODEX 200선물인버스2X", (1.0, None)),
        ],
    )
    def test_classifier(self, ticker, market, name, expected):
        from app.services.etf.etf_index_classifier import classify_holding

        cls = classify_holding(ticker, market, name, None)
        assert cls.kind == "LEVERAGED"
        assert (cls.leverage, cls.index_key) == expected

    def _exposure(self, include_qqq: bool = True) -> IndexExposureResponse:
        groups = []
        if include_qqq:
            groups.append(
                IndexExposureGroup(
                    key="US_NASDAQ100",
                    label="나스닥 100",
                    kind="INDEX",
                    value_krw=1_000_000,
                    pct_of_stock=50,
                    pct_of_etf=50,
                    domestic_krw=0,
                    overseas_krw=1_000_000,
                    members=[
                        IndexExposureMember(
                            ticker="QQQ",
                            name="QQQ",
                            market="NASDAQ",
                            listing="OVERSEAS",
                            value_krw=1_000_000,
                            pct_of_stock=50,
                        )
                    ],
                )
            )
        groups.append(
            IndexExposureGroup(
                key="LEVERAGED",
                label="레버리지·인버스",
                kind="LEVERAGED",
                value_krw=1_500_000,
                pct_of_stock=50,
                pct_of_etf=50,
                domestic_krw=0,
                overseas_krw=1_500_000,
                members=[
                    IndexExposureMember(
                        ticker="QLD",
                        name="QLD",
                        market="NASDAQ",
                        listing="OVERSEAS",
                        value_krw=1_000_000,
                        pct_of_stock=40,
                        underlying_index_key="US_NASDAQ100",
                        leverage=2,
                    ),
                    IndexExposureMember(
                        ticker="SQQQ",
                        name="SQQQ",
                        market="NASDAQ",
                        listing="OVERSEAS",
                        value_krw=500_000,
                        pct_of_stock=10,
                    ),
                ],
            )
        )
        return IndexExposureResponse(total_stock_krw=2_000_000 if include_qqq else 1_500_000, groups=groups)

    def test_suggestion_merges_leveraged_but_not_as_primary(self):
        g = build_index_group_suggestions(self._exposure()).groups[0]
        assert g.key == "US_NASDAQ100"
        assert [(m.ticker, m.leverage) for m in g.members] == [("QQQ", 1.0), ("QLD", 2.0)]
        assert g.exposure_krw == 3_000_000
        assert "QLD" not in [c.ticker for c in g.primary_candidates]
        assert g.primary.ticker == "QQQ"

    def test_leveraged_only_uses_curated_primary(self):
        result = build_index_group_suggestions(self._exposure(include_qqq=False))
        assert [g.key for g in result.groups] == ["US_NASDAQ100"]
        assert result.groups[0].primary.ticker == "QQQ"
        assert [m.ticker for m in result.groups[0].members] == ["QLD"]

    def _group(self, weight: float, cash: float, qqq: float = 1_000_000, qld: float = 1_000_000):
        item = {
            "ticker": "QQQ",
            "name": "QQQ",
            "market": "NASDAQ",
            "weight": weight,
            "group_key": "US_NASDAQ100",
            "group_label": "나스닥 100",
            "members": [{"ticker": "QLD", "market": "NASDAQ", "name": "QLD", "role": "MEMBER", "leverage": 2}],
        }
        positions = [_pos("QQQ", "NASDAQ", qqq, 500_000), _pos("QLD", "NASDAQ", qld, 100_000)]
        portfolio = _portfolio([item, {"ticker": "CASH", "name": "", "market": "KRW", "weight": 100 - weight}])
        return analyze_rebalancing(portfolio, _overview(positions, cash=cash)).items[0]

    def test_group_current_value_is_exposure(self):
        group = self._group(30, cash=8_000_000)  # 기준 1,000만, 노출 300만 = 30%
        assert group.current_value_krw == 3_000_000
        assert group.weight_diff_pct == 0
        assert next(m for m in group.members if m.ticker == "QLD").current_value_krw == 1_000_000

    def test_selling_leveraged_reduces_exposure_by_multiplier(self):
        group = self._group(25, cash=8_000_000)  # 목표 노출 250만 → 50만 감축 = QLD 25만원 매도
        trades = {m.ticker: m.diff_krw for m in expand_group_items([group], "GENERAL")}
        assert trades == {"QLD": -250_000}

    def test_sell_overflows_from_leveraged_into_primary(self):
        group = self._group(5, cash=8_000_000)  # 목표 노출 50만 → 250만 감축: QLD 전량(노출 200만) + QQQ 50만
        trades = {m.ticker: m.diff_krw for m in expand_group_items([group], "GENERAL")}
        assert trades == {"QLD": -1_000_000, "QQQ": -500_000}

    def test_leveraged_domestic_alt_rejected(self):
        with pytest.raises(ValidationError, match="레버리지"):
            PortfolioCreate(
                name="p",
                items=[
                    {
                        "ticker": "QQQ",
                        "market": "NASDAQ",
                        "weight": 100,
                        "group": {
                            "key": "US_NASDAQ100",
                            "domestic_alt": {"ticker": "409820", "market": "KOSPI", "leverage": 2},
                        },
                    }
                ],
            )


class TestSuggestionScope:
    """제안은 전체 계좌 기준 — 분석 대상 밖 계좌에만 있는 종목은 in_scope=False로 함께 넣는다."""

    def _exposure(self) -> IndexExposureResponse:
        return TestLeveragedMembers()._exposure()

    def test_out_of_scope_members_marked_and_sorted_last(self):
        names = {("QQQ", "NASDAQ"): ["해외"], ("QLD", "NASDAQ"): ["해외"]}
        g = build_index_group_suggestions(self._exposure(), in_scope_keys=set(), account_names=names).groups[0]
        assert [(m.ticker, m.in_scope, m.account_names) for m in g.members] == [
            ("QQQ", False, ["해외"]),
            ("QLD", False, ["해외"]),
        ]

    def test_in_scope_members_first(self):
        g = build_index_group_suggestions(self._exposure(), in_scope_keys={("QLD", "NASDAQ")}).groups[0]
        assert [m.ticker for m in g.members] == ["QLD", "QQQ"]
        assert g.members[0].in_scope

    def test_no_scope_means_all_in_scope(self):
        g = build_index_group_suggestions(self._exposure()).groups[0]
        assert all(m.in_scope for m in g.members)


def test_group_owner_map_maps_members_to_primary_with_leverage():
    """plans/77 B2 — 그룹 대표·멤버·국내 대체 → (대표 키, 배수). 일반 항목은 담지 않는다."""
    from types import SimpleNamespace

    from app.services.rebalancing.group_expansion import group_owner_map

    items = [
        SimpleNamespace(
            ticker="QQQ",
            market="NASDAQ",
            group_key="NDX100",
            members=[
                SimpleNamespace(ticker="QLD", market="NYSE", leverage=2.0),
                SimpleNamespace(ticker="133690", market="KOSPI", leverage=None),
            ],
        ),
        SimpleNamespace(ticker="AAPL", market="NASDAQ", group_key=None, members=[]),
    ]
    assert group_owner_map(items) == {
        ("QQQ", "NASDAQ"): (("QQQ", "NASDAQ"), 1.0),
        ("QLD", "NYSE"): (("QQQ", "NASDAQ"), 2.0),
        ("133690", "KOSPI"): (("QQQ", "NASDAQ"), 1.0),
    }
