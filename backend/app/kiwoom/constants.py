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
# 미국주식 매수/매도주문 — 오픈소스 .NET 클라이언트(dongbin300/KiwoomRestApi.Net,
# Clients/UsStocks/KiwoomRestApiClientUsStockOrder.cs)로 교차검증. 엔드포인트도 balance.py와
# 동일하게 /api/us/ordr(국내 /api/dostk/ordr과 별도 경로) — order.py 참고.
API_ID_OVERSEAS_BUY = "ust20000"  # 미국주식 매수주문
API_ID_OVERSEAS_SELL = "ust20001"  # 미국주식 매도주문

# 해외 거래소 코드(stex_tp) — balance.py의 _STEX_TP_MARKETS(실측 확정: ND/NY/NA)와 동일 체계.
# 위 오픈소스 클라이언트의 KiwoomUsStockOrderExchangeType enum과도 일치(NA=AMEX/ND=NASDAQ/NY=NYSE).
KIWOOM_OVERSEAS_MARKET_CODES = {
    "NYSE": "NY",
    "NASDAQ": "ND",
    "AMEX": "NA",
}

KIWOOM_TOKEN_CACHE_KEY = "kiwoom_token:account:{account_id}"  # nosec B105 — 캐시 키 템플릿
