# Backend CLAUDE.md

## Commands

### 설치
```bash
# Python 3.11+ required
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
# 마이그레이션 롤백 (1단계)
cd backend && uv run alembic downgrade -1

# 현재 마이그레이션 상태 확인
cd backend && uv run alembic current

# 마이그레이션 히스토리 전체 조회
cd backend && uv run alembic history --verbose
```

### Tests
```bash
# 전체 테스트 (pytest-asyncio, asyncio_mode="auto")
cd backend && uv run pytest

# 단일 파일
cd backend && uv run pytest tests/test_asset_service.py -v

# 특정 테스트 필터
cd backend && uv run pytest -k "test_name" -x  # -x: 첫 실패 시 중단
cd backend && uv run pytest --tb=short         # 짧은 트레이스백 (출력 줄이기)

# 커버리지 리포트
cd backend && uv run pytest --cov=app --cov-report=term-missing
```

> 테스트는 실제 DB 없이 mocked `AsyncSession` 사용 (`tests/conftest.py`). `KIS_CRED_ENCRYPTION_KEY`, `APP_SECRET_KEY` 등 환경변수는 `tests/conftest.py`에서 자동 override됨. `.env` 파일 없어도 테스트 실행 가능.
> **주요 fixtures:** `mock_db` (AsyncSession mock, scalars/execute/commit 포함), `mock_redis` (get/set/setex mock), `make_account` (AssetAccount stub), `make_snapshot` (AssetSnapshot stub), `make_user_settings` (UserSettings stub).

**테스트 위치:** `backend/tests/` — 현재 목록은 `cd backend && uv run pytest --collect-only -q` 확인.

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
- `MIGRATION_DATABASE_URL` — Supabase 전용 마이그레이션 DB URL (로컬 Docker는 `DATABASE_URL`과 동일)
- `REDIS_URL`
- `KIS_CRED_ENCRYPTION_KEY` — 32-byte hex (64자). KIS/키움 자격증명 AES-256 암호화 키
- `ALLOWED_ORIGINS` — CORS 허용 출처 (쉼표 구분, 예: `http://localhost:5173`)
- `FRONTEND_URL` — 이메일 링크 생성용 프론트엔드 URL

**Supabase** (`supabase.com > Project Settings > API`):
- `SUPABASE_PROJECT_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET` — Settings > API > JWT Settings

**외부 API**:
- `DART_API_KEY` — opendart.fss.or.kr
- `FRED_API_KEY` — fred.stlouisfed.org (미국 경제지표)
- `FMP_API_KEY` — financialmodelingprep.com (증시 캘린더)

**금융결제원 오픈뱅킹**:
- `OPEN_BANKING_CLIENT_ID`, `OPEN_BANKING_CLIENT_SECRET`
- `OPEN_BANKING_REDIRECT_URI`, `OPEN_BANKING_BASE_URL`

**SMTP** (알림 이메일):
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TIMEOUT`

**FCM (Android 푸시 알림)**:
- `FIREBASE_CREDENTIALS_JSON` — Firebase 서비스 계정 JSON (한 줄 문자열)

**모니터링**:
- `METRICS_TOKEN` — Prometheus `/metrics` 엔드포인트 Bearer 토큰
- `SENTRY_DSN`, `SENTRY_RELEASE` — Sentry 오류 추적 (선택)

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
        ├── dashboard.py      # 대시보드 집계 라우터 (get_dashboard_summary 구현은 asset_aggregator.py)
        ├── dart.py           # DART OpenAPI 공시 라우터 (dart_service.py 연동)
        ├── dividends.py      # 배당금 요약 + 예상 배당금
        ├── invest.py         # DCA 분석
        ├── open_banking.py   # 오픈뱅킹 계좌 연결
        ├── portfolio.py      # 전체 계좌 통합 조회 (/overview)
        ├── portfolios.py     # 저장된 포트폴리오 CRUD (백테스트·리밸런싱 공용)
        ├── rebalancing.py    # 리밸런싱 추천
        ├── settings.py       # KIS/LS 자격증명 + 목표 설정
        ├── stocks.py         # 종목 검색
        ├── tax.py            # 세금 추정 요약 (GET /tax/summary?year=YYYY)
        ├── transactions.py   # 입출금/배당 내역 CRUD
        ├── ws_prices.py        # WebSocket: /api/v1/ws/prices — 실시간 주가 구독 (클라이언트당 개별 연결)
        ├── economic_indicators.py  # 미국 경제지표 + FRED 캘린더 (/economic-indicators)
        ├── insights.py             # 스마트 인사이트 & 포트폴리오 진단 (/insights)
        ├── market_signals.py       # VIX·장단기 금리차·Fear&Greed 복합 신호 (/market-signals)
        ├── positions.py            # 포지션 CRUD + 현재가 sync (assets.py 하위, /assets/{id}/positions)
        ├── exchange_rate_alerts.py # 환율 알림 CRUD (alerts.py 하위, /alerts/exchange-rate)
        ├── rebalancing_alerts.py   # 리밸런싱 드리프트 알림 (alerts.py 하위, /alerts/rebalancing)
        └── stock_price_alerts.py   # 주가 알림 CRUD (alerts.py 하위, /alerts/stock-price)

services/
  ├── asset_service.py        # 계좌별 sync 함수 (대시보드 집계는 asset_aggregator.py로 분리됨)
  ├── auth_service.py         # 회원가입/로그인/JWT 발급
  ├── alert_service.py        # 알림 생성·조회
  ├── backtest_service.py     # 백테스트 엔진
  ├── credential_service.py   # AES-256 자격증명 암호화/복호화
  ├── dart_service.py         # DART OpenAPI 연동 (기업 공시)
  ├── dca_service.py          # DCA(정기투자) 분석 + 목표 타임라인
  ├── dividend_constants.py   # 배당 관련 상수 정의 (배당 주기, fallback 수익률 등)
  ├── dividend_providers.py   # 배당 데이터 제공자 추상화
  ├── dividend/               # 배당 서비스 패키지 (리팩토링됨)
  │   ├── calculator.py       # 순수 계산 함수 — DB·외부 API 의존 없음, 단위 테스트 용이
  │   └── orchestrator.py     # DB·Redis·외부 fetch 조율, get_dividend_data() 등 구현
  ├── dividend_fetcher.py     # 멀티소스 폴백 체인: Naver → yfinance → KIS ETF → pykrx → FDR → KIS 일반 → DART → 정적 폴백
  ├── email_service.py        # 이메일 발송
  ├── portfolio_service.py    # 포트폴리오 overview 집계 (portfolio.py 라우터에서 분리)
  ├── price_service.py        # 현재가 조회 (Yahoo Finance → KIS 우선순위). Yahoo Finance 함수는 yahoo_price.py로 분리됨
  ├── tax_service.py          # 연도별 세금 추정: 배당소득세·해외 양도세·종합과세 경계
  ├── rebalancing_execution_service.py  # 리밸런싱 주문 실행
  ├── rebalancing_service.py  # 리밸런싱 추천
  ├── asset_aggregator.py     # 대시보드 집계 (get_dashboard_summary), XIRR·연환산 수익률·벤치마크 계산
  ├── dividend_aggregator.py  # 배당금 집계 (get_dividend_summary)
  ├── snapshot_service.py     # 스냅샷 upsert·포지션 sync 헬퍼 (_upsert_snapshot, sync_snapshot_positions)
  ├── _snapshot_queries.py    # latest_snapshot_subquery() — account_id별 max(snapshot_date) SQLAlchemy 서브쿼리 헬퍼
  ├── yahoo_price.py          # Yahoo Finance 가격 조회 유틸 (티커 변환, 개별/배치 조회, 수익률 계산)
  ├── alert_calculator.py           # 알림 조건 판단 로직 (alert_service.py에서 분리)
  ├── alert_repository.py           # 알림 DB 쿼리 레이어 (alert_service.py에서 분리)
  ├── backtest_metrics.py           # 백테스트 성과 지표 계산 (backtest_service.py 서브모듈)
  ├── composition_calculator.py     # 자산 구성 비중 계산
  ├── trend_calculator.py           # 월별 자산 추이 계산
  ├── returns_calculator.py         # 수익률 계산 (XIRR 등)
  ├── economic_calendar_service.py  # FRED 경제 캘린더 이벤트 조회
  ├── economic_indicator_service.py # 미국 주요 경제지표 조회·캐싱
  ├── email_templates.py            # 이메일 HTML 템플릿 모듈 (email_service.py에서 분리)
  ├── factor_service.py             # 팩터 분석 (모멘텀·가치·품질)
  ├── insight_service.py            # 포트폴리오 진단 & 인사이트 생성
  ├── market_data_fetcher.py        # 시장 데이터 수집 유틸 (VIX, 금리차 등)
  ├── market_signal_service.py      # 복합 시장 위험 신호 평가
  ├── portfolio_optimizer.py        # 포트폴리오 최적화 (효율적 프론티어)
  ├── position_aggregator.py        # 복수 계좌 포지션 집계
  ├── push_service.py               # FCM 푸시 알림 발송
  ├── rebalancing_strategy_service.py # 리밸런싱 전략 로직 (rebalancing_service.py에서 분리)
  └── risk_service.py               # 포트폴리오 리스크 지표 계산 (VaR, 변동성 등)

kis/                          # KIS OpenAPI 클라이언트
kiwoom/                       # 키움증권 API 클라이언트 (auth, balance, client, order, constants)
providers/                    # 금융 데이터 provider
  ├── base.py                 # Provider 추상 베이스
  ├── http_client.py          # 공통 HTTP 클라이언트
  ├── kis_provider.py         # KIS API provider
  ├── kiwoom_provider.py      # 키움증권 API provider
  ├── manual_provider.py      # 수동 입력 provider
  ├── openbanking.py          # 오픈뱅킹 토큰 갱신 (`ensure_ob_token_fresh`)
  └── openbanking_provider.py # 오픈뱅킹 계좌 조회 provider
utils/
  ├── cache_keys.py           # Redis 캐시 키 빌더 (`dividend_ticker_summary_key` 등)
  ├── circuit_breaker.py      # 인메모리 서킷 브레이커 (CircuitOpenError). 임계값: KIS/Kiwoom 5회 실패→60s 차단, Yahoo/DART 5회→120s, OpenBanking 3회→90s
  #                             **인메모리 상태** — 서버 재시작 시 모든 브레이커 상태 초기화됨 (Redis 미사용).
  #                             새 외부 API 추가 시: `get_circuit_breaker(name, fail_threshold, reset_timeout)` 호출 후 `try/except CircuitOpenError` 패턴으로 감쌈.
  ├── currency.py             # USD/KRW Redis 캐싱 (`get_usd_krw_rate`, `cache_usd_krw_rate`)
  ├── metrics.py              # Prometheus 커스텀 메트릭 (broker_sync_duration, alert_trigger_count 등) — `/metrics` 엔드포인트로 노출
  ├── pnl.py                  # 포지션 P&L 순수 계산 함수 (eval_value, invested_value, pnl_pct)
  └── redis_lock.py           # Redis 분산 락 — 동일 계좌 동시 sync 방지
limiter.py                    # slowapi 레이트 리미터. 엔드포인트에 @limiter.limit("X/minute") 데코레이터로 적용
                              # 예: @limiter.limit("60/minute") — request: Request 파라미터 필수
jobs/                         # APScheduler 정기 작업
  ├── asset_sync.py           # 15:30 KST intraday + 18:00 KST daily 전체 계좌 스냅샷
  ├── dca_auto_buy.py         # 매일 09:00 KST DCA 자동매수
  ├── deposit_monitor.py      # 15:35 KST + 18:05 KST 예수금 모니터링
  ├── economic_indicator_sync.py  # 08:00 KST 경제지표 갱신 + 08:05 KST 알림 체크
  ├── exchange_rate_alert.py  # 5분 간격 환율 알림 체크
  ├── goal_achievement.py     # 매일 18:45 KST 투자 목표 달성도 확인
  ├── monthly_report.py       # 매월 1일 09:00 KST 월간 리포트 발송
  ├── price_publisher.py      # 30초 간격 WebSocket 실시간 가격 브로드캐스트
  ├── rebalancing_alert.py    # 매일 08:30 KST 리밸런싱 드리프트 초과 시 이메일 알림
  ├── stock_price_alert.py    # 10분 간격 주가 알림 체크
  └── token_refresh.py        # 매일 06:00 KST KIS + 오픈뱅킹 토큰 갱신 (모든 활성 유저)

> **새 job 추가:** `jobs/` 에 파일 생성 후 `app/scheduler.py`의 `init_scheduler()`에 `scheduler.add_job()` 호출로 등록. `timezone="Asia/Seoul"` 필수.
```

**자격증명 암호화:** KIS/키움 App Key/Secret은 `credential_service.py`의 AES-256으로 DB 저장. `encrypt()`/`decrypt()` 호출 필수.

**현재가 조회 우선순위:** `price_service.py` — Yahoo Finance(yfinance, API 키 불필요) → KIS API. yfinance는 `run_in_executor`로 동기 함수 비동기 실행.

**오픈뱅킹 토큰 자동 갱신:** `providers/openbanking.py`의 `ensure_ob_token_fresh(settings_row, db)` — 만료 1시간 전 `refresh_access_token()` 호출 후 DB commit. `sync_openbanking_account()`와 `token_refresh.py` 양쪽에서 호출됨.

**USD/KRW 환율 캐싱:** `app/utils/currency.py`의 `get_usd_krw_rate(redis)` → Redis `usd_krw_rate` 키 조회(TTL: `settings.redis_cache_ttl_seconds`) → 없으면 `settings.usd_krw_fallback_rate` fallback. KIS API 성공 시 `cache_usd_krw_rate(redis, rate)` 호출로 갱신. 테스트 패치 경로: `app.utils.currency.cache_usd_krw_rate`.

**월별 추이 SQL (`_get_monthly_trend`):** `asset_accounts` JOIN + `is_active = TRUE` 필터 필수. 누락 시 비활성·삭제 계좌 스냅샷이 합산되어 금액이 수배 부풀림. 스냅샷은 `date.today()` 기준 저장 — 월말 스냅샷 개념 없음, "해당 월 마지막 sync일" 값이 월별 대표값으로 사용됨.

**인증:** JWT Bearer 토큰. `api/deps.py`의 `get_current_user` 의존성 주입. Access 30분, Refresh 7일.

**미들웨어 스택 (`main.py` lifespan):** Request ID 주입 → 보안 헤더(X-Content-Type-Options, X-Frame-Options, X-XSS-Protection) → HTTP 요청 로깅 → slowapi 레이트 리미팅 → 예외 핸들러(자격증명 정보 자동 redact).
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
- yfinance는 동기 라이브러리. `asyncio.get_running_loop().run_in_executor(None, fn)` 패턴으로 실행.
- 동시 호출은 `asyncio.Semaphore(5)` 제한.

**Pydantic v2 스타일**
- ORM 모델 매핑 스키마는 `model_config = {"from_attributes": True}` 필수.
- `Optional[X]` 대신 `X | None` 사용.

**새 라우터/모델 추가**
- 새 라우터는 `api/v1/router.py`에 `include_router()`로 등록 필수.
- 새 모델은 `alembic/env.py`에 import 필요 — 누락 시 autogenerate가 해당 테이블 변경 감지 못함.

**Rate Limiting**
- `@limiter.limit("X/minute")` 데코레이터 적용 시 함수 시그니처에 `request: Request` 파라미터 필수.
  ```python
  @router.get("/endpoint")
  @limiter.limit("60/minute")
  async def my_endpoint(request: Request, ...):
  ```
