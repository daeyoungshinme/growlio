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
# Ruff 린터 (E/F/I/UP/B/SIM/C90/ASYNC/PT 규칙, E712·B008·SIM108·PT001 제외)
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
- `API_SEMAPHORE_LIMIT` — 외부 API 동시 호출 제한 세마포어 크기
- `REDIS_CACHE_TTL_SECONDS` — 환율 등 Redis 캐시 기본 TTL
- 기타 튜닝용 env var(환율 fallback, KIS/Kiwoom rate limit, circuit breaker 임계값, DB pool 설정 등)는 `app/config.py`의 `Settings` 클래스 참고 — 전부 기본값 있어 운영 필수 아님

**Supabase** (`supabase.com > Project Settings > API`):
- `SUPABASE_PROJECT_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET` — Settings > API > JWT Settings

**외부 API**:
- `DART_API_KEY` — opendart.fss.or.kr
- `FRED_API_KEY` — fred.stlouisfed.org (미국 경제지표)
- `FMP_API_KEY` — financialmodelingprep.com (증시 캘린더, 현재 코드에서 미사용 — 예약된 설정)

**이메일 알림** (Resend HTTP API — Render 등 클라우드의 outbound SMTP 포트 차단을 피하기 위해 SMTP 대신 HTTPS API 사용):
- `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_TIMEOUT`

**FCM (Android 푸시 알림)**:
- `FIREBASE_CREDENTIALS_JSON` — Firebase 서비스 계정 JSON (한 줄 문자열)

**모니터링**:
- `METRICS_TOKEN` — Prometheus `/metrics` 엔드포인트 Bearer 토큰
- `SENTRY_DSN`, `SENTRY_RELEASE` — Sentry 오류 추적 (선택)

---

## Architecture (`backend/app/`)

### 데이터 모델

- `AssetAccount` — 계좌 마스터. `asset_type`(BANK_ACCOUNT/DEPOSIT/STOCK_KIS/STOCK_KIWOOM/STOCK_OTHER/CASH_OTHER/REAL_ESTATE/OTHER)과 `data_source`(MANUAL/KIS_API/KIWOOM_API) 조합으로 동작 결정
- `AssetSnapshot` — 일별 계좌 스냅샷(자산 금액 집계용). `(account_id, snapshot_date)` unique constraint
- `Position` — 계좌 보유 포지션(릴레이셔널 테이블, 과거 `AssetAccount.manual_positions`/`AssetSnapshot.positions` JSONB 패턴 대체). `snapshot_id IS NULL` → 계좌 현재 포지션, `snapshot_id NOT NULL` → 스냅샷 시점 포지션
- `Transaction` — 입출금/배당 내역. `transaction_type` = DEPOSIT/WITHDRAWAL/DIVIDEND
- `UserSettings` — KIS/키움 자격증명(AES-256 암호화 저장), 투자 목표, 연간 입금 목표

> 위는 핵심 모델만 표기 — `Portfolio`/`RebalancingExecution`/`RebalancingAlert`/`AlertHistory`/`KisToken`/`KiwoomToken` 등 전체 목록은 `app/models/` 참고.

```
API Request
  └── api/v1/router.py        # 모든 라우터 등록
        ├── assets.py         # 계좌 CRUD + 동기화 트리거
        ├── auth.py           # 로그인/회원가입/토큰 refresh
        ├── alerts.py         # 알림 목록 + 읽음 처리
        ├── backtest.py       # 백테스트 실행
        ├── dashboard.py      # 대시보드 집계 라우터 (get_dashboard_summary 구현은 asset_aggregator.py)
        ├── dividends.py      # 배당금 요약 + 예상 배당금 + 월별 균등화 제안
        ├── invest.py         # DCA 분석
        ├── portfolios.py     # 저장된 포트폴리오 CRUD (백테스트·리밸런싱 공용)
        ├── portfolio_analysis.py  # 포트폴리오 분석 API (prefix: /portfolio) — /overview, /allocation-history, /risk(?portfolio_id=), /rebalancing-strategy
        ├── rebalancing.py    # 리밸런싱 추천
        ├── rebalancing_execution.py  # 리밸런싱 실행 API — 주문 실행·이력 조회
        ├── rebalancing_plan.py       # 리밸런싱 대기 플랜 조회/취소/승인 (인증 필요, 앱 내 사용)
        ├── rebalancing_plan_public.py  # 리밸런싱 대기 플랜 토큰 기반 액션 (인증 없음, 이메일 링크 전용 — `Depends(get_current_user)` 사용 금지)
        ├── settings.py       # KIS/LS 자격증명 + 목표 설정
        ├── stocks.py         # 종목 검색
        ├── tax.py            # 세금 추정 요약 (GET /tax/summary?year=YYYY)
        ├── transactions.py   # 입출금/배당 내역 CRUD
        ├── ws_prices.py        # WebSocket: /api/v1/ws/prices — 실시간 주가 구독 (연결 관리는 app/ws/connection_manager.py)
        ├── economic_indicators.py  # 미국 경제지표 + FRED 캘린더 (/economic-indicators) — CPI/Core CPI 요약(`/inflation-summary`)은 리밸런싱 화면 InflationSummaryCard로 프론트 연동됨. 그 외 전체 지표 목록/구독/알림 job은 프론트 미연동
        ├── insights.py             # 스마트 인사이트 & 포트폴리오 진단 (/insights)
        ├── market_signals.py       # VIX·장단기 금리차·Fear&Greed 복합 신호 (/market-signals)
        ├── positions.py            # 포지션 CRUD + 현재가 sync (assets.py 하위, /assets/{id}/positions)
        ├── exchange_rate_alerts.py # 환율 알림 CRUD (alerts.py 하위, /alerts/exchange-rate)
        ├── rebalancing_alerts.py   # 리밸런싱 드리프트 알림 (alerts.py 하위, /alerts/rebalancing)
        ├── stock_price_alerts.py   # 주가 알림 CRUD (alerts.py 하위, /alerts/stock-price)
        ├── _account_deps.py        # 계좌 소유권 검증 헬퍼(get_owned_account) + api/deps.py의 get_owned_or_404 재노출
        └── _alert_crud.py          # 환율/주가 알림 라우터 공용 reactivate·delete 엔드포인트 팩토리(register_alert_reactivate_delete)

> 라우터 등록/prefix 변경 시 이 표도 함께 갱신.

services/
> 파일명 접미사 컨벤션: `*_service.py`(DB/외부 API 연동 포함 유스케이스), `*_calculator.py`/`*_aggregator.py`(순수 계산·집계, 부수효과 없음), 접미사 없는 파일(`yahoo_price.py`, `backtest_metrics.py` 등)은 특정 도메인 유틸 모음. 강제 통일 대상 아님 — 새 파일 추가 시 참고용.
  ├── asset_service.py        # 계좌별 sync 함수 (대시보드 집계는 asset_aggregator.py로 분리됨)
  ├── sync_all_service.py     # "전체 갱신" 백그라운드 배치 동기화 — jobs/asset_sync.py의 _sync_accounts 재사용, Redis로 락/진행상태 관리 (POST /assets/sync-all, GET /assets/sync-all/status)
  ├── auth_service.py         # 회원가입/로그인/JWT 발급
  ├── alerts/                 # 범용 알림 도메인 패키지 (환율/주가/시장신호 체크 + 공통 이력)
  │   ├── alert_service.py    # 알림 공통 저장·조회(save_alert_history/apply_alert_trigger/list_alert_history). `check_and_trigger_alerts`/`check_and_trigger_stock_price_alerts`/`check_rebalancing_alerts` 등은 순환 참조 회피용 `__getattr__` 지연 re-export shim(실제 구현은 alerts/exchange_rate_service.py·alerts/stock_price_service.py·rebalancing/alert_check.py·rebalancing/alert_test.py·rebalancing/order_builder.py) — 의도된 설계, 제거 대상 아님
  │   ├── exchange_rate_service.py # 환율 알림 조건 체크 서비스 (구 exchange_rate_alert_service.py)
  │   ├── stock_price_service.py   # 주가 알림 조건 체크 서비스 (구 stock_price_alert_service.py)
  │   ├── market_signal_alert_service.py # 시장 위험 신호 등급 변화(GREEN/YELLOW/RED 전환) 감지 및 즉시 알림. `check_composite_signal`(리스크+시장신호 복합 판정)을 제공해 rebalancing/alert_check.py·rebalancing/diagnosis_service.py와 공유. 등급전환 알림 발송 성공 시 rebalancing/alert_check.py의 `_mark_composite_alert_sent_today` dedup 키를 공유 갱신 — 같은 날 두 서비스가 같은 신호로 중복 발송하지 않도록 함
  │   └── calculator.py       # 알림 조건 판단 로직 (구 alert_calculator.py, alert_service.py에서 분리)
  ├── rebalancing/            # 리밸런싱 도메인 패키지 (분석·실행·계획·전략·알림)
  │   ├── service.py          # 리밸런싱 추천 (구 rebalancing_service.py)
  │   ├── strategy_service.py # 리밸런싱 전략 로직 (구 rebalancing_strategy_service.py, service.py에서 분리)
  │   ├── order_builder.py    # AUTO 실행·원클릭 실행·대기 플랜 생성이 공유하는 주문 생성 로직(build_rebalancing_orders/refresh_live_prices) — 구 rebalancing_order_builder.py
  │   ├── alert_check.py      # 리밸런싱 드리프트 알림 체크(SCHEDULE/DRIFT/BOTH, 10분 간격 job의 메인 루프) — 구 rebalancing_alert_service.py에서 책임별로 3분할된 것 중 하나. 시장신호 게이팅은 alerts/market_signal_alert_service.py의 `check_composite_signal`을 재사용. 복합신호 알림 on/off는 포트폴리오 단위가 아닌 **유저 단위** 설정(마이그레이션 `cs2_composite_signal_user_level`)
  │   ├── alert_scope.py      # 리밸런싱 알림 alert_scope(AGGREGATE↔PER_ACCOUNT) 전환 (구 rebalancing_alert_service.py에서 분리)
  │   ├── alert_test.py       # 리밸런싱 알림 즉시 테스트 발송 (구 rebalancing_alert_service.py에서 분리)
  │   ├── plan_service.py     # AUTO 리밸런싱 2단계 플랜(계획 생성 → 매수 대기/매도 승인 → 실행) 생명주기 관리 — 매수는 대기시간 경과 후 자동 실행(취소 가능), 매도는 이메일 승인 필요(당일 장마감 미응답 시 자동 만료). 토큰은 SHA-256 해시만 저장, `FOR UPDATE`로 중복 실행 방지 (구 rebalancing_plan_service.py)
  │   ├── execution_service.py # 리밸런싱 주문 실행 조율 — 실제 주문은 _kis_order_executor.py/_kiwoom_order_executor.py로 분리 (구 rebalancing_execution_service.py)
  │   ├── _kis_order_executor.py  # KIS 단일/TWO_PHASE 리밸런싱 주문 실행 (execution_service.py에서 분리)
  │   ├── _kiwoom_order_executor.py # Kiwoom 국내 단일 주문 실행 (execution_service.py에서 분리)
  │   ├── _order_executor_common.py # KIS/Kiwoom 주문 실행 결과 처리 공용 헬퍼 (양쪽 executor 공용)
  │   ├── _order_quantity_guard.py # clamp_sell_orders() — 매도 수량을 실제 보유 수량으로 clamp (양쪽 executor 공용)
  │   ├── diagnosis_service.py # 진단 화면 표시용 시장상황/리스크/세금영향 코멘트 생성 — needs_rebalancing 알림 판정과는 완전히 분리된 설명 전용 로직, alert 아님 (구 rebalancing_diagnosis_service.py)
  │   └── _alert_queries.py   # RebalancingAlert portfolio_id+user_id 조회 헬퍼 (rebalancing_alerts.py 라우터에서 분리, 구 _rebalancing_alert_queries.py)
  ├── backtest_service.py     # 백테스트 엔진
  ├── credential_service.py   # AES-256 자격증명 암호화/복호화
  ├── dart_service.py         # DART OpenAPI 연동 — dividend_fetcher.py 폴백 체인의 배당 데이터 소스 (fetch_dart_dividend)
  ├── dca_service.py          # DCA(정기투자) 분석 + 목표 타임라인
  ├── goal_recommendation_service.py  # 목표 역산 포트폴리오 추천 (목표금액/월적립액/목표연도 → 필요 수익률 역산 → 기존 종목+큐레이션 ETF 중 MVO로 최소분산 포트폴리오 추천). 자동 반영 안 됨 — 사용자가 확인 후 수동 적용
  ├── goal_return_solver.py   # 목표 역산에 필요한 연평균 수익률을 구하는 순수 계산 함수 (goal_recommendation_service.py 서브모듈)
  ├── recommendation_universe.py  # 목표 역산 추천의 큐레이션 ETF 후보 유니버스 상수
  ├── dividend_constants.py   # 배당 관련 상수 정의 (배당 주기, fallback 수익률 등)
  ├── dividend_sync_sources.py # 외부 소스별 동기 배당 조회 함수(Yahoo/Naver/pykrx/FDR) — dividend_fetcher.py 체인이 호출
  ├── dividend_plan_service.py # 연배당/월배당 계획 및 목표 달성 현황 서비스
  ├── dividend/               # 배당 서비스 패키지 (리팩토링됨)
  │   ├── calculator.py       # 순수 계산 함수 — DB·외부 API 의존 없음, 단위 테스트 용이
  │   ├── orchestrator.py     # DB·Redis·외부 fetch 조율, get_dividend_data() 등 구현
  │   ├── drip_service.py     # 배당 월별 균등화 제안 (calc_monthly_optimization) — 순수 함수
  │   └── _dividend_queries.py # 배당 관련 DB 쿼리 헬퍼
  ├── dividend_fetcher.py     # 멀티소스 폴백 체인: Naver → yfinance → KIS ETF → pykrx → FDR → KIS 일반 → DART → 정적 폴백
  ├── price_sync_sources.py   # Yahoo 클라우드 IP 차단 대비 국내종목 Naver/pykrx 폴백 가격 조회
  ├── email_service.py        # 이메일 발송
  ├── portfolio_service.py    # 포트폴리오 overview 집계 (portfolio.py 라우터에서 분리)
  ├── portfolio_history_service.py  # 포트폴리오 월별 자산 배분 이력 (portfolio_service.py에서 분리)
  ├── price_service.py        # 현재가 조회 (Yahoo Finance → KIS 우선순위). Yahoo Finance 함수는 yahoo_price.py로 분리됨
  ├── tax_service.py          # 연도별 세금 추정: 배당소득세·해외 양도세·종합과세 경계
  ├── asset_aggregator.py     # 대시보드 집계 (get_dashboard_summary), XIRR·연환산 수익률·벤치마크 계산
  ├── dividend_aggregator.py  # 배당금 집계 (get_dividend_summary)
  ├── snapshot_service.py     # 스냅샷 upsert·포지션 sync 헬퍼 (_upsert_snapshot, sync_snapshot_positions, get_latest_snapshot_with_positions)
  ├── _snapshot_queries.py    # latest_snapshot_subquery() — account_id별 max(snapshot_date) SQLAlchemy 서브쿼리 헬퍼
  ├── _account_queries.py     # 활성 계좌 조회 쿼리 헬퍼 (is_active == True 필터, 브로커 계좌 필터, 비활성 포함 단건 조회)
  ├── _position_queries.py    # 포지션 DB 쿼리 헬퍼
  ├── _settings_queries.py    # UserSettings 조회/get-or-create + has_active_kis_credentials 쿼리 헬퍼 (settings.py 라우터에서 분리)
  ├── _portfolio_queries.py   # 연결된 포트폴리오 목록·활성 알림 threshold 조회 헬퍼 (rebalancing.py 라우터에서 분리)
  ├── yahoo_price.py          # Yahoo Finance 가격 조회 유틸 (티커 변환, 개별/배치 조회, 수익률 계산)
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
  └── risk_service.py               # 포트폴리오 리스크 지표 계산 (VaR, 변동성 등)

> 새 서비스 파일 추가/삭제 시 이 목록도 함께 갱신.

schemas/                      # Pydantic 요청/응답 스키마
  ├── _validators.py          # 공용 field_validator 헬퍼
  ├── asset.py / auth.py / backtest.py / invest.py / portfolio.py
  ├── rebalancing/             # 리밸런싱 스키마 패키지 (구 rebalancing.py 단일 파일, 453줄 → 책임별 분리) — `__init__.py`가 전체 재노출하므로 `from app.schemas.rebalancing import X` 호출부는 변경 없음
  │   ├── analysis.py          # 분석 결과: TickerAccountInfo/RebalancingItem/CurrentHolding/TaxImpactItem/DiagnosisContext/RebalancingAnalysis
  │   ├── execution.py         # 실행/실행이력: ExecutionOrderItem/ExecutionRequest/KisBalance*/OrderResult/ExecutionResult/RebalancingExecution*
  │   ├── drift.py             # 드리프트 요약(대시보드 경량 조회): DriftedItem/PortfolioDriftSummary
  │   ├── alert.py             # 알림 설정: RebalancingAlertCreate/AlertScopeUpdate/TestAlertResponse/RebalancingAlertResponse
  │   ├── plan.py               # 대기 플랜: RebalancingPlanItemOut/RebalancingPlanLegSummary/PlanTokenPreview 등
  │   └── goal.py               # 목표 역산 추천/복합신호 배너: GoalRecommendation*/CompositeSignalStatus
  └── service_dtypes.py       # 서비스 계층 내부 TypedDict (DB/외부 API 응답 형태 고정)

kis/                          # KIS OpenAPI 클라이언트 (auth, balance, client, constants, domestic_quote, order, overseas_quote)
kiwoom/                       # 키움증권 API 클라이언트 (auth, balance, client, order, constants)
providers/                    # 금융 데이터 provider
  ├── base.py                 # Provider 추상 베이스
  ├── http_client.py          # 공통 HTTP 클라이언트
  ├── kis_provider.py         # KIS API provider
  ├── kiwoom_provider.py      # 키움증권 API provider
  ├── manual_provider.py      # 수동 입력 provider
  └── _retry.py               # 토큰 갱신 재시도 공용 헬퍼
utils/
  ├── cache_keys.py           # Redis 캐시 키 빌더 (`dividend_ticker_summary_key` 등)
  ├── circuit_breaker.py      # 인메모리 서킷 브레이커 (CircuitOpenError). KIS/Kiwoom 5회→60s, Yahoo/DART 5회→120s. 재시작 시 상태 초기화됨.
  ├── currency.py             # USD/KRW Redis 캐싱 (`get_usd_krw_rate`, `cache_usd_krw_rate`)
  ├── market_hours.py         # KRX/NYSE 개장 여부 판단
  ├── metrics.py              # Prometheus 커스텀 메트릭 (broker_sync_duration, alert_trigger_count 등) — `/metrics` 엔드포인트로 노출
  ├── pnl.py                  # 포지션 P&L 순수 계산 함수 (eval_value, invested_value, pnl_pct)
  └── redis_lock.py           # Redis 분산 락 — 동일 계좌 동시 sync 방지
limiter.py                    # slowapi 레이트 리미터 (@limiter.limit("X/minute") 데코레이터, request: Request 파라미터 필수)
jobs/                         # APScheduler 정기 작업
  ├── asset_sync.py           # 15:30 KST intraday + 18:00 KST daily 전체 계좌 스냅샷
  ├── dca_auto_buy.py         # 매일 09:00 KST DCA 자동매수
  ├── economic_indicator_sync.py  # 08:00 KST 경제지표 갱신 + 08:05 KST 알림 체크
  ├── exchange_rate_alert.py  # 5분 간격 환율 알림 체크
  ├── goal_achievement.py     # 매일 18:45 KST 투자 목표 달성도 확인
  ├── monthly_report.py       # 매월 1일 09:00 KST 월간 리포트 발송
  ├── price_publisher.py      # 30초 간격 WebSocket 실시간 가격 브로드캐스트
  ├── rebalancing_alert.py    # 매일 08:30 KST 리밸런싱 드리프트 초과 시 이메일 알림
  ├── market_signal_alert.py  # 10분 간격 — 시장 위험 신호 등급 전환(GREEN/YELLOW/RED) 감지 시 즉시 알림
  ├── rebalancing_auto_execution.py  # 장 중 5분 간격 — AUTO 모드 리밸런싱 대기 플랜 생성(계획 이메일 발송, 실행은 안 함)
  ├── rebalancing_plan_buy_execution.py  # 1분 간격 — 대기시간 지난 매수 leg 자동 실행
  ├── rebalancing_plan_sell_expiry.py  # 매일 15:31 KST — 당일 미응답 매도 승인 요청 만료 처리
  ├── stock_price_alert.py    # 10분 간격 주가 알림 체크
  ├── token_refresh.py        # 매일 06:00 KST KIS 계좌별 토큰 갱신
  └── _job_helpers.py         # job 공통 헬퍼 유틸리티
```

> **새 job 추가:** `jobs/` 에 파일 생성 후 `app/scheduler.py`의 `init_scheduler()`에 `scheduler.add_job()` 호출로 등록. `timezone="Asia/Seoul"` 필수.

**자격증명 암호화:** KIS/키움 App Key/Secret은 `credential_service.py`의 AES-256으로 DB 저장. `encrypt()`/`decrypt()` 호출 필수.

**현재가 조회 우선순위:** `price_service.py` — Yahoo Finance(yfinance, API 키 불필요) → KIS API. yfinance는 `run_in_executor`로 동기 함수 비동기 실행.

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
- 새 기능 E2E 순서: 모델(`models/`) → 스키마(`schemas/`) → 서비스(`services/`) → 라우터(`api/v1/`) → `router.py` 등록 → `alembic/env.py` import → 마이그레이션 생성 → 테스트

**Rate Limiting**
- `@limiter.limit("X/minute")` 데코레이터 적용 시 함수 시그니처에 `request: Request` 파라미터 필수.
  ```python
  @router.get("/endpoint")
  @limiter.limit("60/minute")
  async def my_endpoint(request: Request, ...):
  ```
