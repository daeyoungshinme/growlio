# 토스증권 Open API 상수 (https://openapi.tossinvest.com)
#
# 토스는 KIS/키움과 달리 모의투자(샌드박스) 도메인이 없다 — 단일 운영 도메인.
# 인증은 OAuth2 Client Credentials(사용자가 토스 WTS `설정 → Open API`에서 발급한
# client_id/client_secret). 계좌/자산/주문 계열 호출은 `X-Tossinvest-Account` 헤더에
# `GET /api/v1/accounts`로 얻은 accountSeq를 넣어야 한다.
#
# 주의: 토스 `Open API → IP 관리`에 등록된 IP에서만 호출이 허용된다 — 미등록 IP는
# 403 `edge-blocked`. Growlio 백엔드(Render)의 아웃바운드 IP를 사용자가 등록해야 한다.

TOSS_BASE_URL = "https://openapi.tossinvest.com"

TOSS_TOKEN_PATH = "/oauth2/token"  # nosec B105 — API 경로, 비밀번호 아님
TOSS_ACCOUNTS_PATH = "/api/v1/accounts"
TOSS_HOLDINGS_PATH = "/api/v1/holdings"
TOSS_BUYING_POWER_PATH = "/api/v1/buying-power"
TOSS_EXCHANGE_RATE_PATH = "/api/v1/exchange-rate"

TOSS_TOKEN_CACHE_KEY = "toss_token:account:{account_id}"  # nosec B105 — 캐시 키 템플릿
TOSS_ACCTSEQ_CACHE_KEY = "toss_acctseq:{account_id}"
TOSS_ACCTSEQ_CACHE_TTL = 86400  # accountSeq는 사실상 불변 — 24h 캐시로 accounts 1req/s 제한 완화

ACCOUNT_HEADER = "X-Tossinvest-Account"
