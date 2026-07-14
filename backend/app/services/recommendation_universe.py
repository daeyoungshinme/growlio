"""목표 역산 추천 엔진의 큐레이션 ETF 후보 유니버스.

기대수익률/배당수익률은 여기 하드코딩하지 않고 항상 실시간 조회한다
(`price_service.get_historical_returns`, `dividend_sync_sources.*`) — 데이터 신선도 유지 목적.

`asset_class`(EQUITY/BOND/CASH)는 기간별(단기/중기/장기) 추천(`get_horizon_recommendations`)에서
후보를 필터링하는 데 쓰인다 — 단기 추천은 BOND/CASH만, 장기 추천은 EQUITY만 후보로 사용한다.

`index_region`(DOMESTIC/OVERSEAS)은 상장거래소가 아니라 **추종 지수의 지역**을 나타낸다.
`133690 TIGER 미국나스닥100`처럼 KRX(국내) 상장이지만 해외지수를 추종하는 ETF가 있어
상장거래소만으로는 구분할 수 없다 — 세제유형별(ISA/연금저축/IRP는 해외지수, 일반은 국내지수)
후보 선호도 필터링(`goal_recommendation_service._TAX_TYPE_INDEX_REGION_PREFERENCE`)에 쓰인다.
"""

import re

from app.constants import DOMESTIC_MARKETS

MAX_GOAL_CANDIDATE_TICKERS = 20
"""사용자가 등록 가능한 목표 역산 추천 후보 종목 최대 개수 (`api/v1/settings.py` 검증에서 공유)."""

RECOMMENDATION_UNIVERSE: list[dict[str, str]] = [
    {
        "ticker": "SPY",
        "name": "SPDR S&P 500 ETF",
        "market": "NYSE",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
    },
    {
        "ticker": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "market": "NYSE",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
    },
    {
        "ticker": "VTI",
        "name": "Vanguard Total Stock Market ETF",
        "market": "NYSE",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
    },
    {
        "ticker": "QQQ",
        "name": "Invesco QQQ Trust",
        "market": "NASDAQ",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
    },
    {
        "ticker": "SCHD",
        "name": "Schwab US Dividend Equity ETF",
        "market": "NYSE",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
    },
    {
        "ticker": "VYM",
        "name": "Vanguard High Dividend Yield ETF",
        "market": "NYSE",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
    },
    {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI", "asset_class": "EQUITY", "index_region": "DOMESTIC"},
    {
        "ticker": "360750",
        "name": "TIGER 미국S&P500",
        "market": "KOSPI",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
    },
    {
        "ticker": "133690",
        "name": "TIGER 미국나스닥100",
        "market": "KOSPI",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
    },
    {
        "ticker": "458730",
        "name": "TIGER 미국배당다우존스",
        "market": "KOSPI",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
    },
    {
        "ticker": "153130",
        "name": "KODEX 단기채권",
        "market": "KOSPI",
        "asset_class": "CASH",
        "index_region": "DOMESTIC",
    },
    {
        "ticker": "357870",
        "name": "TIGER CD금리투자KIS(합성)",
        "market": "KOSPI",
        "asset_class": "CASH",
        "index_region": "DOMESTIC",
    },
    {
        "ticker": "114260",
        "name": "KODEX 국고채3년",
        "market": "KOSPI",
        "asset_class": "BOND",
        "index_region": "DOMESTIC",
    },
    {
        "ticker": "SHY",
        "name": "iShares 1-3 Year Treasury Bond ETF",
        "market": "NASDAQ",
        "asset_class": "BOND",
        "index_region": "OVERSEAS",
    },
    {
        "ticker": "BND",
        "name": "Vanguard Total Bond Market ETF",
        "market": "NASDAQ",
        "asset_class": "BOND",
        "index_region": "OVERSEAS",
    },
]

_KNOWN_OVERSEAS_TRACKING_KRX_TICKERS: frozenset[str] = frozenset(
    c["ticker"]
    for c in RECOMMENDATION_UNIVERSE
    if c["index_region"] == "OVERSEAS" and c["market"].upper() in DOMESTIC_MARKETS
)
"""국내(KRX 등) 상장이지만 해외지수를 추종하는 것으로 알려진 큐레이션 티커 집합.

`resolve_index_region()`이 명시적 태그가 없는 후보(주로 과거에 시딩되어 `index_region`
필드가 없는 기존 사용자 저장값)를 재분류하는 데 사용 — 마이그레이션 없이 자동 보정된다.
"""


def resolve_index_region(ticker: str, market: str, explicit: str | None) -> str:
    """후보 종목이 추종하는 지수의 지역(DOMESTIC/OVERSEAS)을 판별한다.

    우선순위: 명시적 태그 > 해외상장(자명하게 해외지수) > 큐레이션 목록 매칭 > 기본값(국내상장은 DOMESTIC).
    """
    if explicit:
        return explicit
    if market.upper() not in DOMESTIC_MARKETS:
        return "OVERSEAS"
    if ticker in _KNOWN_OVERSEAS_TRACKING_KRX_TICKERS:
        return "OVERSEAS"
    return "DOMESTIC"


_CASH_NAME_PATTERN = re.compile(r"단기채|파킹|CMA|머니마켓|Money\s*Market|CD\s*금리", re.IGNORECASE)
_BOND_NAME_PATTERN = re.compile(r"채권|국고채|회사채|Bond|Treasury", re.IGNORECASE)


def guess_asset_class(name: str) -> str:
    """종목명 패턴으로 자산군(EQUITY/BOND/CASH)을 추정한다.

    검색 API(네이버/야후 오토컴플릿) 응답에는 펀드 유형 정보가 없어 종목명 키워드로만 추정하는
    휴리스틱이다 — 확정 근거가 아니므로 "후보 ETF 관리"에서 기본값으로만 제안하고 사용자가 항상
    수정할 수 있어야 한다. CASH를 BOND보다 먼저 검사하는 이유는 "단기채"처럼 두 패턴에 모두
    걸릴 수 있는 이름을 현금성으로 우선 분류하기 위함(`RECOMMENDATION_UNIVERSE`의
    KODEX 단기채권 = CASH 관례와 일치).
    """
    if _CASH_NAME_PATTERN.search(name):
        return "CASH"
    if _BOND_NAME_PATTERN.search(name):
        return "BOND"
    return "EQUITY"
