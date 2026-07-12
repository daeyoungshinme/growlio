"""목표 역산 추천 엔진의 큐레이션 ETF 후보 유니버스.

기대수익률/배당수익률은 여기 하드코딩하지 않고 항상 실시간 조회한다
(`price_service.get_historical_returns`, `dividend_sync_sources.*`) — 데이터 신선도 유지 목적.
"""

MAX_GOAL_CANDIDATE_TICKERS = 20
"""사용자가 등록 가능한 목표 역산 추천 후보 종목 최대 개수 (`api/v1/settings.py` 검증에서 공유)."""

RECOMMENDATION_UNIVERSE: list[dict[str, str]] = [
    {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "market": "NYSE"},
    {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "market": "NYSE"},
    {"ticker": "VTI", "name": "Vanguard Total Stock Market ETF", "market": "NYSE"},
    {"ticker": "QQQ", "name": "Invesco QQQ Trust", "market": "NASDAQ"},
    {"ticker": "SCHD", "name": "Schwab US Dividend Equity ETF", "market": "NYSE"},
    {"ticker": "VYM", "name": "Vanguard High Dividend Yield ETF", "market": "NYSE"},
    {"ticker": "069500", "name": "KODEX 200", "market": "KOSPI"},
    {"ticker": "360750", "name": "TIGER 미국S&P500", "market": "KOSPI"},
    {"ticker": "133690", "name": "TIGER 미국나스닥100", "market": "KOSPI"},
    {"ticker": "458730", "name": "TIGER 미국배당다우존스", "market": "KOSPI"},
]
