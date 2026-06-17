# 키움증권 REST API 상수 (https://api.kiwoom.com)

KIWOOM_REAL_BASE_URL = "https://api.kiwoom.com"
KIWOOM_MOCK_BASE_URL = "https://mockapi.kiwoom.com"  # KRX 종목만 지원

# 국내주식 API ID — 실계좌/모의계좌 동일값, 도메인(base_url)으로 구분
API_ID_DOMESTIC_BALANCE = "kt00018"  # 계좌평가잔고내역요청
API_ID_DOMESTIC_BUY = "kt10000"  # 국내주식 매수주문
API_ID_DOMESTIC_SELL = "kt10001"  # 국내주식 매도주문

REDIS_KIWOOM_TOKEN_KEY = "kiwoom_token:account:{account_id}"
REDIS_TOKEN_TTL_BUFFER = 300  # 만료 5분 전 갱신
