# Backend CLAUDE.md

## Commands

### 설치
```bash
# 가상환경 생성 (최초 1회)
cd backend && uv venv

uv pip install -e ".[dev]"
```

### 실행
```bash
# 백엔드 서버 (localhost:8000, Swagger UI: /docs)
cd backend && uv run uvicorn app.main:app --reload
```

### Database
```bash
# 마이그레이션 실행
cd backend && uv run alembic upgrade head

# 새 마이그레이션 생성
cd backend && uv run alembic revision --autogenerate -m "description"
```

> **주의:** autogenerate는 `alembic/env.py`에 모델 import 필요. 새 모델 추가 시 env.py 확인.

```bash
# 현재 마이그레이션 상태 확인
cd backend && uv run alembic current
```

### Tests
```bash
# 전체 테스트 (pytest-asyncio, asyncio_mode="auto")
cd backend && uv run pytest

# 단일 파일
cd backend && uv run pytest tests/test_asset_service.py -v

# 특정 테스트 필터
cd backend && uv run pytest -k "test_name" -x  # -x: 첫 실패 시 중단
```

> 테스트는 실제 DB 없이 mocked `AsyncSession` 사용 (`conftest.py`). `KIS_CRED_ENCRYPTION_KEY`, `APP_SECRET_KEY` 등 환경변수는 `conftest.py`에서 자동 override됨. `.env` 파일 없어도 테스트 실행 가능.

**테스트 파일:** `test_asset_service.py`, `test_auth_api.py`, `test_credential_service.py`, `test_dividend_service.py`, `test_portfolio_summary.py`, `test_price_service.py`, `test_rebalancing_service.py`, `test_security.py`

### Lint & Type Check
```bash
# Ruff 린터 (E/F/I/UP/B/SIM 규칙, E712 제외)
cd backend && uv run ruff check .

# Mypy 타입 체크
cd backend && uv run mypy app/
```

### Environment
`backend/.env` (`.env.example` 참고):
- `APP_ENV=development` — `/docs` Swagger UI 활성화 여부 제어
- `APP_SECRET_KEY` — JWT 서명 키
- `DATABASE_URL` — PostgreSQL asyncpg URL
- `REDIS_URL`
- `KIS_CRED_ENCRYPTION_KEY` — 32-byte hex (64자). KIS/키움 자격증명 AES-256 암호화 키

**Supabase** (`supabase.com > Project Settings > API`):
- `SUPABASE_PROJECT_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET` — Settings > API > JWT Settings

**DART**:
- `DART_API_KEY` — opendart.fss.or.kr

**금융결제원 오픈뱅킹**:
- `OPEN_BANKING_CLIENT_ID`, `OPEN_BANKING_CLIENT_SECRET`
- `OPEN_BANKING_REDIRECT_URI`, `OPEN_BANKING_BASE_URL`

**SMTP** (환율 알림 이메일):
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`

---

## Architecture (`backend/app/`)

### 데이터 모델

- `AssetAccount` — 계좌 마스터. `asset_type`(BANK_ACCOUNT/DEPOSIT/STOCK_KIS/STOCK_KIWOOM/STOCK_OTHER/CASH_OTHER/REAL_ESTATE/OTHER)과 `data_source`(MANUAL/KIS_API/KIWOOM_API/OPEN_BANKING) 조합으로 동작 결정
- `AssetSnapshot` — 일별 계좌 스냅샷. `positions` JSONB에 종목 배열 저장. `(account_id, snapshot_date)` unique constraint
- `Transaction` — 입출금/배당 내역. `transaction_type` = DEPOSIT/WITHDRAWAL/DIVIDEND
- `UserSettings` — KIS/키움 자격증명(AES-256 암호화 저장), 투자 목표, 연간 입금 목표

```
API Request
  └── api/v1/router.py        # 모든 라우터 등록
        ├── assets.py         # 계좌 CRUD + 동기화 트리거
        ├── auth.py           # 로그인/회원가입/토큰 refresh
        ├── alerts.py         # 알림 목록 + 읽음 처리
        ├── backtest.py       # 백테스트 실행
        ├── dashboard.py      # 대시보드 집계 (get_dashboard_summary)
        ├── dividends.py      # 배당금 요약 + 예상 배당금
        ├── invest.py         # DCA 분석
        ├── open_banking.py   # 오픈뱅킹 계좌 연결
        ├── portfolio.py      # 전체 계좌 통합 조회 (/overview)
        ├── portfolios.py     # 저장된 포트폴리오 CRUD (백테스트·리밸런싱 공용)
        ├── rebalancing.py    # 리밸런싱 추천
        ├── settings.py       # KIS/LS 자격증명 + 목표 설정
        ├── stocks.py         # 종목 검색
        ├── tax.py            # 세금 추정 요약 (GET /tax/summary?year=YYYY)
        └── transactions.py   # 입출금/배당 내역 CRUD

services/
  ├── asset_service.py        # 계좌별 sync 함수 + 대시보드 집계
  ├── auth_service.py         # 회원가입/로그인/JWT 발급
  ├── alert_service.py        # 알림 생성·조회
  ├── backtest_service.py     # 백테스트 엔진
  ├── credential_service.py   # AES-256 자격증명 암호화/복호화
  ├── dart_service.py         # DART OpenAPI 연동 (기업 공시)
  ├── dca_service.py          # DCA(정기투자) 분석 + 목표 타임라인
  ├── dividend_constants.py   # 배당 관련 상수 정의 (배당 주기, fallback 수익률 등)
  ├── dividend_providers.py   # 배당 데이터 제공자 추상화
  ├── dividend_service.py     # 배당금 집계 + yfinance 배당수익률 추정
  ├── dividend_fetcher.py     # 멀티소스 폴백 체인: Naver → yfinance → KIS ETF → pykrx → FDR → KIS 일반 → DART → 정적 폴백
  ├── email_service.py        # 이메일 발송
  ├── portfolio_service.py    # 포트폴리오 overview 집계 (portfolio.py 라우터에서 분리)
  ├── price_service.py        # 현재가 조회 (Yahoo Finance → KIS → LS 우선순위)
  ├── tax_service.py          # 연도별 세금 추정: 배당소득세·해외 양도세·종합과세 경계
  ├── rebalancing_execution_service.py  # 리밸런싱 주문 실행
  └── rebalancing_service.py  # 리밸런싱 추천

kis/                          # KIS OpenAPI 클라이언트
kiwoom/                       # 키움증권 API 클라이언트 (auth, balance, client, order, constants)
providers/                    # 오픈뱅킹 provider (base.py + openbanking.py)
utils/
  └── currency.py             # USD/KRW Redis 캐싱 (`get_usd_krw_rate`, `cache_usd_krw_rate`)
limiter.py                    # slowapi 레이트 리미터. 엔드포인트에 @limiter.limit("X/minute") 데코레이터로 적용
                              # 예: @limiter.limit("60/minute") — request: Request 파라미터 필수
jobs/                         # APScheduler 정기 작업
  ├── asset_sync.py           # 매일 18:00 KST 전체 계좌 스냅샷
  ├── exchange_rate_alert.py  # 환율 알림 정기 작업
  ├── rebalancing_alert.py    # 매일 18:30 KST 리밸런싱 드리프트 초과 시 이메일 알림
  └── token_refresh.py        # 매일 06:00 KST KIS + 오픈뱅킹 토큰 갱신 (모든 활성 유저)
```

**자격증명 암호화:** KIS/키움 App Key/Secret은 `credential_service.py`의 AES-256으로 DB 저장. `encrypt()`/`decrypt()` 호출 필수.

**현재가 조회 우선순위:** `price_service.py` — Yahoo Finance(yfinance, API 키 불필요) → KIS API. yfinance는 `run_in_executor`로 동기 함수 비동기 실행.

**오픈뱅킹 토큰 자동 갱신:** `providers/openbanking.py`의 `ensure_ob_token_fresh(settings_row, db)` — 만료 1시간 전 `refresh_access_token()` 호출 후 DB commit. `sync_openbanking_account()`와 `token_refresh.py` 양쪽에서 호출됨.

**USD/KRW 환율 캐싱:** `app/utils/currency.py`의 `get_usd_krw_rate(redis)` → Redis `usd_krw_rate` 키 조회(TTL: `settings.redis_cache_ttl_seconds`) → 없으면 `settings.usd_krw_fallback_rate` fallback. KIS API 성공 시 `cache_usd_krw_rate(redis, rate)` 호출로 갱신. 테스트 패치 경로: `app.utils.currency.cache_usd_krw_rate`.

**월별 추이 SQL (`_get_monthly_trend`):** `asset_accounts` JOIN + `is_active = TRUE` 필터 필수. 누락 시 비활성·삭제 계좌 스냅샷이 합산되어 금액이 수배 부풀림. 스냅샷은 `date.today()` 기준 저장 — 월말 스냅샷 개념 없음, "해당 월 마지막 sync일" 값이 월별 대표값으로 사용됨.

**인증:** JWT Bearer 토큰. `api/deps.py`의 `get_current_user` 의존성 주입. Access 30분, Refresh 7일.

**미들웨어 스택 (`main.py` lifespan):** Request ID 주입 → 보안 헤더(X-Content-Type-Options, X-Frame-Options, X-XSS-Protection) → HTTP 요청 로깅 → slowapi 레이트 리미팅 → 예외 핸들러(자격증명 정보 자동 redact).

**LS증권 통합:** 구현 시도 후 완전 제거됨. DB 컬럼은 `migration g1h2i3j4k5l6_remove_ls_securities.py`로 삭제, 잔여 주석도 정리 완료. 재구현 시 migration downgrade 필요.

---

## Absolute Rules

**자격증명 암호화**
- KIS/키움 App Key·Secret은 반드시 `credential_service.encrypt()` 후 DB 저장, 읽을 때 `decrypt()` 호출.
- 평문 자격증명을 DB에 직접 저장하거나 로그에 출력 금지.

**금액 단위**
- 금액 컬럼 타입: `Numeric(18, 2)` / Python `Mapped[float | None]`.
- 해외 종목 `avg_price` 포함 **모든 금액은 KRW 저장** — 프론트에서 USD × 환율 변환 후 전송.

**SQLAlchemy async 패턴**
```python
# 단일 행
row = await db.scalar(select(Model).where(...))
# 다중 행
result = await db.execute(select(Model).where(...))
rows = result.scalars().all()
# 저장
db.add(obj); await db.commit(); await db.refresh(obj)
```
- Boolean 필터: `Model.is_active == True  # noqa: E712` (SQLAlchemy 연산자 호환)

**FK cascade 규칙**
- `user_id` FK → `ondelete="CASCADE"` (유저 삭제 시 연관 데이터 전부 삭제)
- `account_id` FK → `ondelete="SET NULL"` (계좌 삭제 시 내역은 보존)

**로깅**
- `structlog` 사용. 이벤트명 snake_case, 구조화 key=value 형식:
  ```python
  logger.info("account_synced", account_id=str(account.id), positions=len(positions))
  ```

**HTTP 에러 메시지**
- `HTTPException(status_code=..., detail="한국어 메시지")` — 사용자 노출 메시지는 한국어.

**yfinance 비동기 호출**
- yfinance는 동기 라이브러리. `asyncio.get_event_loop().run_in_executor(None, fn)` 패턴으로 실행.
- 동시 호출은 `asyncio.Semaphore(5)` 제한.

**Pydantic v2 스타일**
- ORM 모델 매핑 스키마는 `model_config = {"from_attributes": True}` 필수.
- `Optional[X]` 대신 `X | None` 사용.
