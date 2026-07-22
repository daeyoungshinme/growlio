# 키움증권 REST API 상수 (https://api.kiwoom.com)

KIWOOM_REAL_BASE_URL = "https://api.kiwoom.com"
KIWOOM_MOCK_BASE_URL = "https://mockapi.kiwoom.com"  # KRX 종목만 지원

# 국내주식 API ID — 실계좌/모의계좌 동일값, 도메인(base_url)으로 구분
API_ID_DOMESTIC_DEPOSIT = "kt00001"  # 예수금상세현황요청
API_ID_DOMESTIC_BALANCE = "kt00018"  # 계좌평가잔고내역요청
API_ID_DOMESTIC_BUY = "kt10000"  # 국내주식 매수주문
API_ID_DOMESTIC_SELL = "kt10001"  # 국내주식 매도주문

# 해외(미국)주식 API ID — 실측 기준(openapi.kiwoom.com/guide/apiguide, 미국주식>계좌, 2026-07 확인).
# 국내(/api/dostk/acnt)와 경로가 다른 /api/us/acnt 하위 TR.
API_ID_OVERSEAS_BALANCE = "ust21070"  # 미국주식 원장잔고확인
API_ID_OVERSEAS_DEPOSIT = "ust21110"  # 해외주식 예수금
# TODO: 미국주식 매수/매도주문 api-id 확인 — usa/ust 체계일 가능성 높음. 주문 실행 경로는 이번 수정 범위 밖.
API_ID_OVERSEAS_BUY = "kt0XXXX"
API_ID_OVERSEAS_SELL = "kt0XXXX"

# 해외 거래소 코드 — 키움 API가 요구하는 코드값은 문서 확인 후 확정 필요(KIS와 다를 수 있음)
KIWOOM_OVERSEAS_MARKET_CODES = {
    "NYSE": "NYSE",  # TODO: 실제 코드값 확인
    "NASDAQ": "NASD",  # TODO: 실제 코드값 확인
    "AMEX": "AMEX",  # TODO: 실제 코드값 확인
}

KIWOOM_TOKEN_CACHE_KEY = "kiwoom_token:account:{account_id}"  # nosec B105 — 캐시 키 템플릿
