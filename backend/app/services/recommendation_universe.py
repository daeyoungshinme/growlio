"""목표 역산 추천 엔진의 큐레이션 ETF 후보 유니버스.

기대수익률/배당수익률은 여기 하드코딩하지 않고 항상 실시간 조회한다
(`price_service.get_historical_returns`, `dividend.sync_sources.*`) — 데이터 신선도 유지 목적.

`asset_class`(EQUITY/BOND/CASH)는 기간별(단기/중기/장기) 추천(`get_horizon_recommendations`)에서
후보를 필터링하는 데 쓰인다 — 단기 추천은 BOND/CASH만, 장기 추천은 EQUITY만 후보로 사용한다.

`index_region`(DOMESTIC/OVERSEAS)은 상장거래소가 아니라 **추종 지수의 지역**을 나타낸다.
`133690 TIGER 미국나스닥100`처럼 KRX(국내) 상장이지만 해외지수를 추종하는 ETF가 있어
상장거래소만으로는 구분할 수 없다 — 세제유형별(ISA/연금저축/IRP는 해외지수, 일반은 국내지수)
후보 선호도 필터링(`goal_candidate_service._TAX_TYPE_INDEX_REGION_PREFERENCE`)에 쓰인다.

`tracking_index`는 실제로 추종하는 벤치마크 지수를 나타내는 opaque 문자열 키다(예: `US_SP500`).
분산 목적의 후보 추천에서 "이미 보유한 종목과 동일 지수를 추종하는 다른 운용사 ETF"가 중복으로
섞여 들어가는 것(예: ACE 미국S&P500 보유 중인데 TIGER 미국S&P500도 추천됨)을 막기 위해
`goal_candidate_service.py`의 시딩(`_seed_candidate_tickers`)이 보유종목 기준 dedup 키로,
안내 헬퍼(`detect_duplicate_tracking_index_note`)가 "이미 등록된 후보에 정리가 필요한 중복이
있는지" 판별에 사용한다. `distribution_frequency`는 동일 지수라도 배당 지급주기가 달라 실질적
으로 다른 선택지인 경우에만 설정하는 보조 필드다(`458730 TIGER 미국배당다우존스`(분기배당)와
`446720 SOL 미국배당다우존스`(월배당)는 같은 Dow Jones U.S. Dividend 100 지수를 추종하지만
배당주기가 달라 큐레이션 유니버스에 의도적으로 함께 등록돼 있다 — `detect_duplicate_tracking_
index_note`는 `(tracking_index, distribution_frequency)` 튜플로 비교해 이 쌍을 중복으로
취급하지 않는다). 큐레이션 유니버스 밖의 보유 종목은 `guess_tracking_index()`로 이름 기반
추정하며, 매칭 실패 시 `None`(dedup 효과 없음, fail-soft) — `guess_asset_class()`와 동일한
철학이다.
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
        "tracking_index": "US_SP500",
    },
    {
        "ticker": "VOO",
        "name": "Vanguard S&P 500 ETF",
        "market": "NYSE",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
        "tracking_index": "US_SP500",
    },
    {
        "ticker": "VTI",
        "name": "Vanguard Total Stock Market ETF",
        "market": "NYSE",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
        "tracking_index": "US_TOTAL_MARKET",
    },
    {
        "ticker": "QQQ",
        "name": "Invesco QQQ Trust",
        "market": "NASDAQ",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
        "tracking_index": "US_NASDAQ100",
    },
    {
        "ticker": "SCHD",
        "name": "Schwab US Dividend Equity ETF",
        "market": "NYSE",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
        "tracking_index": "US_DIV_DOWJONES100",
    },
    {
        "ticker": "VYM",
        "name": "Vanguard High Dividend Yield ETF",
        "market": "NYSE",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
        "tracking_index": "US_HIGH_DIVIDEND",
    },
    {
        "ticker": "069500",
        "name": "KODEX 200",
        "market": "KOSPI",
        "asset_class": "EQUITY",
        "index_region": "DOMESTIC",
        "tracking_index": "KR_KOSPI200",
    },
    {
        "ticker": "360750",
        "name": "TIGER 미국S&P500",
        "market": "KOSPI",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
        "tracking_index": "US_SP500",
    },
    {
        "ticker": "133690",
        "name": "TIGER 미국나스닥100",
        "market": "KOSPI",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
        "tracking_index": "US_NASDAQ100",
    },
    {
        "ticker": "458730",
        "name": "TIGER 미국배당다우존스",
        "market": "KOSPI",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
        "tracking_index": "US_DIV_DOWJONES100",
    },
    {
        # 458730과 동일한 Dow Jones U.S. Dividend 100 지수(SCHD 추종)를 월배당으로 지급 —
        # 458730(분기배당)과 나란히 둬서 국내 상장 세제혜택 계좌(ISA/연금저축/IRP)에서도
        # 월배당 옵션을 선택할 수 있게 한다. `distribution_frequency`가 458730과 다르므로
        # dedup 로직(goal_candidate_service.py)에서 진짜 중복으로 취급되지 않는다.
        "ticker": "446720",
        "name": "SOL 미국배당다우존스",
        "market": "KOSPI",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
        "tracking_index": "US_DIV_DOWJONES100",
        "distribution_frequency": "MONTHLY",
    },
    {
        "ticker": "JEPI",
        "name": "JPMorgan Equity Premium Income ETF",
        "market": "NYSE",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
        "tracking_index": "US_COVERED_CALL_SP500",
    },
    {
        "ticker": "JEPQ",
        "name": "JPMorgan Nasdaq Equity Premium Income ETF",
        "market": "NASDAQ",
        "asset_class": "EQUITY",
        "index_region": "OVERSEAS",
        "tracking_index": "US_COVERED_CALL_NASDAQ100",
    },
    {
        "ticker": "153130",
        "name": "KODEX 단기채권",
        "market": "KOSPI",
        "asset_class": "CASH",
        "index_region": "DOMESTIC",
        "tracking_index": "KR_SHORT_BOND",
    },
    {
        "ticker": "357870",
        "name": "TIGER CD금리투자KIS(합성)",
        "market": "KOSPI",
        "asset_class": "CASH",
        "index_region": "DOMESTIC",
        "tracking_index": "KR_CD_RATE",
    },
    {
        "ticker": "114260",
        "name": "KODEX 국고채3년",
        "market": "KOSPI",
        "asset_class": "BOND",
        "index_region": "DOMESTIC",
        "tracking_index": "KR_TREASURY_3Y",
    },
    {
        "ticker": "SHY",
        "name": "iShares 1-3 Year Treasury Bond ETF",
        "market": "NASDAQ",
        "asset_class": "BOND",
        "index_region": "OVERSEAS",
        "tracking_index": "US_TREASURY_SHORT",
    },
    {
        "ticker": "BND",
        "name": "Vanguard Total Bond Market ETF",
        "market": "NASDAQ",
        "asset_class": "BOND",
        "index_region": "OVERSEAS",
        "tracking_index": "US_TOTAL_BOND",
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


_UNIVERSE_TRACKING_INDEX_BY_KEY: dict[tuple[str, str], str] = {
    (c["ticker"], c["market"]): c["tracking_index"] for c in RECOMMENDATION_UNIVERSE if "tracking_index" in c
}
"""큐레이션 유니버스의 (ticker, market) → tracking_index 조회 맵. `resolve_tracking_index()`가
큐레이션 항목을 명시적 태그 다음 우선순위로 조회하는 데 사용한다."""

_TRACKING_INDEX_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # 다우존스 배당 지수는 이름에 "배당"도 함께 들어가므로 고배당 패턴보다 먼저 검사해야 한다.
    (re.compile(r"다우존스|다우\s*배당|Dow\s*Jones", re.IGNORECASE), "US_DIV_DOWJONES100"),
    (re.compile(r"S&P\s*500", re.IGNORECASE), "US_SP500"),
    (re.compile(r"나스닥\s*100|NASDAQ\s*100", re.IGNORECASE), "US_NASDAQ100"),
    (re.compile(r"코스피\s*200|KOSPI\s*200", re.IGNORECASE), "KR_KOSPI200"),
    (re.compile(r"고배당|High\s*Dividend", re.IGNORECASE), "US_HIGH_DIVIDEND"),
    (re.compile(r"전체\s*시장|Total\s*(Stock\s*)?Market", re.IGNORECASE), "US_TOTAL_MARKET"),
    (re.compile(r"종합채권|Total\s*Bond", re.IGNORECASE), "US_TOTAL_BOND"),
    (re.compile(r"국고채\s*3년", re.IGNORECASE), "KR_TREASURY_3Y"),
    (re.compile(r"CD\s*금리", re.IGNORECASE), "KR_CD_RATE"),
    (re.compile(r"단기채권", re.IGNORECASE), "KR_SHORT_BOND"),
    (re.compile(r"1-3\s*Year\s*Treasury|미국\s*단기국채", re.IGNORECASE), "US_TREASURY_SHORT"),
]
"""종목명 → 추종 지수 라벨 정규식 매핑. 순서가 중요 — 더 구체적인 패턴(다우존스 배당)을
더 일반적인 패턴(고배당) 앞에 둬야 오분류를 피한다."""


def guess_tracking_index(name: str) -> str | None:
    """종목명 패턴으로 추종 지수 라벨을 추정한다.

    큐레이션 유니버스 밖에서 들어오는 보유 종목(예: `ACE 미국S&P500`)이 이미 등록/보유 중인
    다른 ETF와 동일 지수를 추종하는지 판별하기 위해 쓰인다(`goal_candidate_service.py`의
    중복 후보 방지 로직 전용). `guess_asset_class()`와 동일하게 확정 근거가 아닌 휴리스틱이라
    매칭되는 패턴이 없으면 `None`을 반환한다 — dedup 효과가 없을 뿐 추천 자체를 막지 않는다.
    """
    for pattern, label in _TRACKING_INDEX_PATTERNS:
        if pattern.search(name):
            return label
    return None


def resolve_tracking_index(ticker: str, market: str, name: str, explicit: str | None) -> str | None:
    """후보 종목이 추종하는 지수 라벨을 판별한다.

    우선순위: 명시적 태그 > 큐레이션 유니버스 매칭(ticker+market) > 이름 기반 휴리스틱
    (`guess_tracking_index`). 셋 다 실패하면 `None`(dedup 미적용) — `resolve_index_region()`과
    동일한 판별 우선순위 패턴이다.
    """
    if explicit:
        return explicit
    known = _UNIVERSE_TRACKING_INDEX_BY_KEY.get((ticker, market))
    if known:
        return known
    return guess_tracking_index(name)


_CASH_NAME_PATTERN = re.compile(r"단기채|파킹|CMA|머니마켓|Money\s*Market|CD\s*금리", re.IGNORECASE)
_BOND_NAME_PATTERN = re.compile(r"채권|국고채|회사채|국채|Bond|Treasury", re.IGNORECASE)


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
