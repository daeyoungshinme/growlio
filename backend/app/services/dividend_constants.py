"""배당금 관련 정적 상수 및 ETF 판별 유틸리티."""

# (ticker, market.upper()) → 확정 배당지급월 리스트
# yfinance는 배당락일 기준이라 지급월과 다를 수 있으므로, 알려진 종목은 여기서 고정값 사용.
# 사용자 수동 override(UserTickerSettings)가 항상 최우선임.
KNOWN_DIVIDEND_SCHEDULES: dict[tuple[str, str], list[int]] = {
    # 한국 종목
    ("005930", "KOSPI"): [4, 5, 8, 11],  # 삼성전자
    ("005935", "KOSPI"): [4, 5, 8, 11],  # 삼성전자우
    # 한국 ETF
    ("367380", "KOSPI"): [2, 5, 8, 11],  # ACE 미국나스닥100
    ("402970", "KOSPI"): [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],  # ACE 미국배당다우존스 (월배당)
    ("414520", "KOSPI"): [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],  # ACE 미국배당다우존스 (월배당)
    ("438100", "KOSPI"): [2, 5, 8, 11],  # ACE 미국나스닥100미국채혼합50액티브 (분기배당)
    # 해외 ETF
    ("QQQ", "NASDAQ"): [4, 7, 10, 12],  # Invesco QQQ Trust
    ("SPY", "NYSE"): [1, 4, 7, 10],  # SPDR S&P 500
    ("SCHD", "NYSE"): [3, 6, 9, 12],  # Schwab US Dividend Equity
}

# (ticker, market.upper()) → (annual_dps, dividend_yield_decimal)
# yfinance/KIS/DART 모두 ETF 분배금 데이터를 반환하지 못할 때의 정적 폴백.
# DPS는 분기별 공시 후 수동 업데이트 필요.
KNOWN_DIVIDEND_INFO: dict[tuple[str, str], tuple[float, float]] = {
    # 한국 주식 (우선주 포함) — 동적 소스 전체 실패 시 최후 보루
    ("005930", "KOSPI"): (1444.0, 0.026),  # 삼성전자: 연간 1,444원, ~2.6%
    ("005935", "KOSPI"): (1494.0, 0.028),  # 삼성전자우: 연간 1,494원, ~2.8% (우선주 프리미엄 +50원)
    # 한국 ETF
    ("367380", "KOSPI"): (100.0, 0.0085),  # ACE 미국나스닥100: 연간 ~100원, ~0.85%
    ("402970", "KOSPI"): (50.0, 0.035),  # ACE 미국배당다우존스: 연간 ~50원, ~3.5%
    ("414520", "KOSPI"): (50.0, 0.035),  # ACE 미국배당다우존스: 연간 ~50원, ~3.5%
    ("438100", "KOSPI"): (30.0, 0.012),  # ACE 미국나스닥100미국채혼합50액티브: 연간 ~30원, ~1.2%
}

# KRX 상장 ETF 코드 앞 3자리 prefix 집합 (국내 ETF 판별용)
# Security.is_etf DB 필드가 실제 사용되기 전까지 prefix 기반으로 판별
_ETF_CODE_PREFIXES: frozenset[str] = frozenset(
    [
        "069",
        "102",
        "114",
        "122",
        "229",
        "233",
        "251",
        "252",
        "261",
        "278",
        "305",
        "329",
        "360",
        "367",
        "379",
        "402",
        "411",
        "414",
        "438",
    ]
)


def is_korean_etf(ticker: str, market: str) -> bool:
    return market.upper() in ("KOSPI", "KOSDAQ") and ticker[:3] in _ETF_CODE_PREFIXES
