"""etf_index_classifier — 보유 종목 → 추종 지수 분류 (순수 함수)."""

import pytest

from app.services.etf_index_classifier import classify_holding, index_label
from app.services.etf_profile_service import EtfProfile
from app.services.recommendation_universe import guess_tracking_index, resolve_tracking_index


def _etf(long_name: str | None = None, base_index: str | None = None) -> EtfProfile:
    return EtfProfile(ter_pct=0.1, base_index=base_index, issuer=None, long_name=long_name, tracking_error_pct=None)


class TestIndexGrouping:
    @pytest.mark.parametrize("market", ["NYSE", "AMEX", "US", "NASDAQ"])
    def test_spy_resolves_regardless_of_stored_market(self, market):
        # SPY는 NYSE Arca 상장이라 브로커/Yahoo에 따라 market이 제각각으로 저장된다.
        cls = classify_holding("SPY", market, "SPY", None)
        assert (cls.kind, cls.index_key, cls.label) == ("INDEX", "US_SP500", "S&P 500")

    def test_qqq_without_index_name_in_long_name(self):
        cls = classify_holding("QQQ", "NASDAQ", "Invesco QQQ Trust", _etf("Invesco QQQ Trust, Series 1"))
        assert cls.index_key == "US_NASDAQ100"

    @pytest.mark.parametrize(
        ("ticker", "name", "profile"),
        [
            ("360750", "TIGER 미국S&P500", _etf(base_index="S&P 500")),
            ("379800", "KODEX 미국S&P500TR", None),
            ("360200", "ACE 미국S&P500", None),
        ],
    )
    def test_domestic_sp500_etfs_share_key_with_spy(self, ticker, name, profile):
        assert classify_holding(ticker, "KOSPI", name, profile).index_key == "US_SP500"

    def test_hedged_product_merges_into_base_index_with_flag(self):
        cls = classify_holding("448290", "KOSPI", "TIGER 미국S&P500선물(H)", None)
        assert (cls.index_key, cls.hedged) == ("US_SP500", True)

    def test_synthetic_hedged_suffix_detected(self):
        cls = classify_holding("999999", "KOSPI", "ACE 미국나스닥100(합성 H)", None)
        assert (cls.index_key, cls.hedged) == ("US_NASDAQ100", True)

    def test_dia_is_dow_industrial_not_dividend(self):
        name = "SPDR Dow Jones Industrial Average ETF Trust"
        assert classify_holding("DIA", "AMEX", name, _etf(name)).index_key == "US_DJIA"
        assert guess_tracking_index(name) == "US_DJIA"

    def test_schd_and_korean_dow_dividend_share_key(self):
        assert classify_holding("SCHD", "NYSE", "Schwab US Dividend Equity ETF", _etf()).index_key == (
            "US_DIV_DOWJONES100"
        )
        assert classify_holding("458730", "KOSPI", "TIGER 미국배당다우존스", None).index_key == "US_DIV_DOWJONES100"

    def test_naver_base_index_groups_unknown_index_by_raw_name(self):
        a = classify_holding("091160", "KOSPI", "KODEX 반도체", _etf(base_index="KRX 반도체"))
        b = classify_holding("091230", "KOSPI", "TIGER 반도체", _etf(base_index="KRX  반도체"))
        assert a.kind == "INDEX"
        assert a.index_key == b.index_key
        assert a.label == "KRX 반도체"


class TestCoveredCall:
    def test_nasdaq_covered_call_is_separate_from_nasdaq100(self):
        cls = classify_holding("441680", "KOSPI", "TIGER 미국나스닥100커버드콜(합성)", None)
        assert cls.index_key == "US_COVERED_CALL_NASDAQ100"
        assert guess_tracking_index("TIGER 미국나스닥100커버드콜(합성)") == "US_COVERED_CALL_NASDAQ100"

    def test_jepq_shares_key_with_korean_nasdaq_covered_call(self):
        cls = classify_holding("JEPQ", "NASDAQ", "JPMorgan Nasdaq Equity Premium Income ETF", _etf())
        assert cls.index_key == "US_COVERED_CALL_NASDAQ100"

    def test_other_base_covered_call_gets_derived_key(self):
        cls = classify_holding("472150", "KOSPI", "TIGER 미국배당다우존스타겟커버드콜1호", None)
        assert cls.index_key == "COVERED_CALL:US_DIV_DOWJONES100"
        assert cls.label == "미국배당다우존스 커버드콜"
        # 중복 분석·후보 dedup 쪽에서는 원 지수로 오인하지 않는다
        assert guess_tracking_index("TIGER 미국배당다우존스타겟커버드콜1호") is None

    def test_unknown_base_covered_call(self):
        cls = classify_holding("999998", "KOSPI", "KODEX 테슬라커버드콜채권혼합액티브", None)
        assert cls.index_key == "COVERED_CALL_OTHER"
        assert index_label("COVERED_CALL_OTHER") == "기타 커버드콜"


class TestLeveragedAndOthers:
    @pytest.mark.parametrize(
        ("ticker", "market", "name", "profile"),
        [
            ("TQQQ", "NASDAQ", "ProShares UltraPro QQQ", _etf("ProShares UltraPro QQQ")),
            ("XXXX", "NYSE", "Direxion Daily Semiconductor Bull 3X Shares", _etf()),
            ("122630", "KOSPI", "KODEX 레버리지", None),
            ("252670", "KOSPI", "KODEX 200선물인버스2X", None),
            ("409820", "KOSPI", "KODEX 미국나스닥100레버리지(합성 H)", None),
        ],
    )
    def test_leveraged_and_inverse_bucket(self, ticker, market, name, profile):
        assert classify_holding(ticker, market, name, profile).kind == "LEVERAGED"

    def test_short_term_bond_is_not_inverse(self):
        name = "Vanguard Short-Term Bond ETF"
        assert classify_holding("BSV", "NYSE", name, _etf(name)).kind == "OTHER_ETF"

    @pytest.mark.parametrize("name", ["KODEX 미국S&P500동일가중", "TIGER 미국S&P500배당귀족"])
    def test_index_variants_are_not_merged_into_base(self, name):
        assert classify_holding("999997", "KOSPI", name, None).kind == "OTHER_ETF"

    def test_individual_stocks(self):
        assert classify_holding("005930", "KOSPI", "삼성전자", None).kind == "STOCK"
        assert classify_holding("AAPL", "NASDAQ", "Apple Inc.", None).kind == "STOCK"

    def test_overseas_etf_with_unknown_index(self):
        cls = classify_holding("ARKK", "AMEX", "ARK Innovation ETF", _etf("ARK Innovation ETF"))
        assert cls.kind == "OTHER_ETF"


def test_resolve_tracking_index_uses_overseas_ticker_map():
    assert resolve_tracking_index("QQQ", "AMEX", "", None) == "US_NASDAQ100"
    # 국내상장은 ticker 맵을 쓰지 않는다
    assert resolve_tracking_index("SPY", "KOSPI", "", None) is None


class TestExposureRegion:
    """실제 투자지역 — 상장시장이 아니라 무엇에 투자하는지 기준(국내상장 미국 ETF는 해외)."""

    @pytest.mark.parametrize(
        ("ticker", "market", "name", "profile", "expected"),
        [
            ("SPY", "AMEX", "SPDR S&P 500 ETF Trust", None, "OVERSEAS"),
            ("AAPL", "NASDAQ", "Apple Inc", None, "OVERSEAS"),
            ("TQQQ", "NASDAQ", "ProShares UltraPro QQQ", None, "OVERSEAS"),
            ("360750", "KOSPI", "TIGER 미국S&P500", None, "OVERSEAS"),
            ("448290", "KOSPI", "TIGER 미국S&P500선물(H)", None, "OVERSEAS"),
            ("069500", "KOSPI", "KODEX 200", None, "DOMESTIC"),
            ("005930", "KOSPI", "삼성전자", None, "DOMESTIC"),
            ("122630", "KOSPI", "KODEX 레버리지", None, "DOMESTIC"),
            ("409820", "KOSPI", "KODEX 미국나스닥100레버리지(합성 H)", None, "OVERSEAS"),
            ("091160", "KOSPI", "KODEX 반도체", _etf(base_index="KRX 반도체"), "DOMESTIC"),
            ("381170", "KOSPI", "TIGER 미국테크TOP10 INDXX", None, "OVERSEAS"),
            ("441680", "KOSPI", "TIGER 미국나스닥100커버드콜(합성)", None, "OVERSEAS"),
            ("161510", "KOSPI", "PLUS 고배당주", None, None),
        ],
    )
    def test_region(self, ticker, market, name, profile, expected):
        assert classify_holding(ticker, market, name, profile).region == expected

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("PLUS 고배당주", None),
            ("KODEX 종합채권(AA-이상)액티브", None),
            ("TIGER 미국고배당", "US_HIGH_DIVIDEND"),
            ("Vanguard High Dividend Yield ETF", "US_HIGH_DIVIDEND"),
            ("Vanguard Total Bond Market ETF", "US_TOTAL_BOND"),
        ],
    )
    def test_korean_generic_names_not_mapped_to_us_index(self, name, expected):
        assert guess_tracking_index(name) == expected
