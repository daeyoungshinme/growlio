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
> **주요 fixtures:** `mock_db` (AsyncSession mock, scalars/execute/commit/get 포함), `mock_cache` (in-memory 캐시 store mock — get/set/setex), `make_account` (AssetAccount stub), `make_snapshot` (AssetSnapshot stub), `make_user_settings` (UserSettings stub).

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
- `KIS_CRED_ENCRYPTION_KEY` — 32-byte hex (64자). KIS/키움 자격증명 AES-256 암호화 키
- `ALLOWED_ORIGINS` — CORS 허용 출처 (쉼표 구분, 예: `http://localhost:5173`)
- `FRONTEND_URL` — 이메일 링크 생성용 프론트엔드 URL
- `API_SEMAPHORE_LIMIT` — 외부 API 동시 호출 제한 세마포어 크기
- `CACHE_TTL_SECONDS` — 환율 등 in-memory 캐시 기본 TTL
- 기타 튜닝용 env var(환율 fallback, KIS/Kiwoom rate limit, circuit breaker 임계값, DB pool 설정 등)는 `app/core/config.py`의 `Settings` 클래스 참고 — 전부 기본값 있어 운영 필수 아님

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

- `AssetAccount` — 계좌 마스터. `asset_type`(BANK_ACCOUNT/DEPOSIT/STOCK_KIS/STOCK_KIWOOM/STOCK_OTHER/CASH_OTHER/REAL_ESTATE/OTHER)과 `data_source`(MANUAL/KIS_API/KIWOOM_API) 조합으로 동작 결정. ISA 계좌는 `isa_open_date`/`isa_type`(GENERAL/PREFERENTIAL)/`isa_manual_cumulative_pnl_krw`로 의무가입 만기·수동입력 누적손익 관리. `tax_type`(GENERAL/ISA/PENSION_SAVINGS/IRP/OVERSEAS_DEDICATED)은 세제 성격(리밸런싱 세금 계산·매도 우선순위에 사용), `investment_horizon`(SHORT_TERM/MID_TERM/LONG_TERM/null)은 투자기간 그룹핑 태그 — 둘 다 `Portfolio`에도 동일 컬럼 존재하며 목표 역산 추천(`goal_recommendation_service.py`, 프론트 `RecommendationCard`)이 어느 포트폴리오가 어느 (기간, 세제유형) 조합을 담당하는지 매칭하는 데 사용
- `AssetSnapshot` — 일별 계좌 스냅샷(자산 금액 집계용). `(account_id, snapshot_date)` unique constraint
- `Position` — 계좌 보유 포지션(릴레이셔널 테이블, 과거 `AssetAccount.manual_positions`/`AssetSnapshot.positions` JSONB 패턴 대체). `snapshot_id IS NULL` → 계좌 현재 포지션, `snapshot_id NOT NULL` → 스냅샷 시점 포지션
- `Transaction` — 입출금/배당 내역. `transaction_type` = DEPOSIT/WITHDRAWAL/DIVIDEND
- `UserSettings` — KIS/키움 자격증명(AES-256 암호화 저장), 투자 목표, 연간 입금 목표, 단기 목표 추천 최소 주식비중(`goal_short_term_equity_floor_pct`)

> 위는 핵심 모델만 표기 — `Portfolio`/`RebalancingExecution`/`RebalancingAlert`/`AlertHistory`/`KisToken`/`KiwoomToken` 등 전체 목록은 `app/models/` 참고.

```
API Request
  └── api/v1/router.py        # 모든 라우터 등록
        ├── assets.py         # 계좌 CRUD + 동기화 트리거, ISA 누적손익 수동입력(PATCH /{account_id}/isa-pnl-override)
        ├── auth.py           # 로그인/회원가입/토큰 refresh
        ├── alerts.py         # 알림 목록 + 읽음 처리
        ├── backtest.py       # 백테스트 실행
        ├── dashboard.py      # 대시보드 집계 라우터 (get_dashboard_summary 구현은 asset_aggregator.py)
        ├── dividends.py      # 배당금 요약 + 예상 배당금 + 월별 균등화 제안 — /summary, /positions, /by-ticker 모두 ?account_id= 옵션 지원(미지정 시 전체 계좌 통합)
        ├── invest.py         # DCA 분석 + 목표 설정 마법사용 필요수익률·적립액 프리뷰(GET /invest/goal-feasibility, 저장 없음)
        ├── portfolios.py     # 저장된 포트폴리오 CRUD (백테스트·리밸런싱 공용)
        ├── portfolio_analysis.py  # 포트폴리오 분석 API (prefix: /portfolio) — /overview, /allocation-history, /risk(?portfolio_id=), /rebalancing-strategy. /overview·/allocation-history는 ?account_id= 옵션 지원(미지정 시 전체 계좌 통합, PortfolioPage 투자현황 탭 계좌 필터 전용)
        ├── rebalancing.py    # 리밸런싱 추천 + 투자기간별 목표 역산 추천(GET /rebalancing/goal-recommendation/by-horizon)
        ├── rebalancing_execution.py  # 리밸런싱 실행 API — 주문 실행·이력 조회
        ├── rebalancing_plan.py       # 리밸런싱 대기 플랜 조회/취소/승인 (인증 필요, 앱 내 사용)
        ├── rebalancing_plan_public.py  # 리밸런싱 대기 플랜 토큰 기반 액션 (인증 없음, 이메일 링크 전용 — `Depends(get_current_user)` 사용 금지)
        ├── settings.py       # KIS/LS 자격증명 + 목표 설정
        ├── stocks.py         # 종목 검색 + ETF 추종지수 지역 판별(GET /stocks/index-region)
        ├── tax.py            # 세금 추정 요약(GET /tax/summary?year=YYYY&account_id=) + 해외 포지션(GET /tax/overseas-positions?account_id=) + ISA 만기 현황(GET /tax/isa-status) + 연금 납입 현황(GET /tax/pension-contribution) — account_id 미지정 시 전체 계좌 통합
        ├── transactions.py   # 입출금/배당 내역 CRUD
        ├── ws_prices.py        # WebSocket: /api/v1/ws/prices — 실시간 주가 구독 (연결 관리는 app/ws/connection_manager.py)
        ├── economic_indicators.py  # 미국 CPI/Core CPI 인플레이션 요약(GET /economic-indicators/inflation-summary) — 리밸런싱 화면 InflationSummaryCard로 프론트 연동됨. 이 엔드포인트만 존재 (지표 목록/구독/캘린더/알림 job은 프론트 미연동이라 제거됨)
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
  ├── asset_service.py        # 계좌별 sync 함수 + sync_account_now(캐시 무효화·API 응답 포맷 포함, assets.py `/sync` 전용) — 대시보드 집계는 asset_aggregator.py로 분리됨
  ├── asset_credential_service.py  # 계좌 KIS/키움 자격증명 검증(verify_kis_credentials)·삭제(delete_kis_credentials/delete_kiwoom_credentials) — assets.py 라우터에서 분리
  ├── sync_all_service.py     # "전체 갱신" 백그라운드 배치 동기화 — jobs/asset_sync.py의 _sync_accounts 재사용, in-memory 캐시(core/cache_store.py)로 락/진행상태 관리 (POST /assets/sync-all, GET /assets/sync-all/status)
  ├── auth_service.py         # 회원가입/로그인/JWT 발급
  ├── alerts/                 # 범용 알림 도메인 패키지 (환율/주가/시장신호 체크 + 공통 이력)
  │   ├── alert_service.py    # 알림 공통 저장·조회(save_alert_history/apply_alert_trigger/list_alert_history). `check_and_trigger_alerts`/`check_and_trigger_stock_price_alerts`/`check_rebalancing_alerts` 등은 순환 참조 회피용 `__getattr__` 지연 re-export shim(실제 구현은 alerts/exchange_rate_service.py·alerts/stock_price_service.py·rebalancing/alert_check.py·rebalancing/alert_test.py·rebalancing/order_builder.py) — 의도된 설계, 제거 대상 아님
  │   ├── exchange_rate_service.py # 환율 알림 조건 체크 서비스 (구 exchange_rate_alert_service.py)
  │   ├── stock_price_service.py   # 주가 알림 조건 체크 서비스 (구 stock_price_alert_service.py)
  │   ├── market_signal_alert_service.py # 시장 위험 신호 등급 변화(GREEN/YELLOW/RED 전환) 감지 및 즉시 알림 + 매일 08:30 KST 요약 다이제스트(`send_market_signal_daily_digest`, 옵트인). `check_composite_signal`(리스크+시장신호 복합 판정)을 제공해 rebalancing/alert_check.py·rebalancing/diagnosis_service.py와 공유. 등급전환 알림 발송 성공 시 rebalancing/alert_check.py의 `_mark_composite_alert_sent_today` dedup 키를 공유 갱신 — 같은 날 두 서비스가 같은 신호로 중복 발송하지 않도록 함
  │   ├── calculator.py       # 알림 조건 판단 로직 (구 alert_calculator.py, alert_service.py에서 분리)
  │   └── tax_reminder_service.py # 연말(11~12월) 절세 리마인더 콘텐츠 조합(`build_reminder_content` — 손실수확 후보·연금공제 잔여한도·ISA 만기, tax_service/pension_contribution_service/isa_service 재사용) + 유저별 발송(`send_year_end_tax_reminder`, 알릴 내용 없으면 스킵)
  ├── rebalancing/            # 리밸런싱 도메인 패키지 (분석·실행·계획·전략·알림)
  │   ├── service.py          # 리밸런싱 추천 (구 rebalancing_service.py)
  │   ├── strategy_service.py # 리밸런싱 전략 로직 (구 rebalancing_strategy_service.py, service.py에서 분리)
  │   ├── order_builder.py    # AUTO 실행·원클릭 실행·대기 플랜 생성이 공유하는 주문 생성 로직(build_rebalancing_orders/refresh_live_prices/filter_drifting_items) — 구 rebalancing_order_builder.py. `clamp_orders_to_max_value()`는 1건당 거래대금이 `settings.auto_rebalancing_max_order_value_krw`(기본 5천만원)를 넘지 않도록 축소하는 안전장치 — `plan_service.generate_pending_plan_for_alert()`(AUTO/quick-execute 공용 대기 플랜 생성 경로)가 호출. `is_market_signal_blocking_auto_mode()`/`is_tax_impact_blocking_auto_mode()`는 각각 시장신호·세금영향 게이트 판정 순수 함수(대칭 설계) — plan_service.py가 계획 생성 시점과 매수 실행 직전(시장신호만 재확인) 두 시점에 호출
  │   ├── alert_check.py      # 리밸런싱 드리프트 알림 체크(SCHEDULE/DRIFT/BOTH, 10분 간격 job의 메인 루프) — 구 rebalancing_alert_service.py에서 책임별로 3분할된 것 중 하나. 시장신호 게이팅은 alerts/market_signal_alert_service.py의 `check_composite_signal`을 재사용. 복합신호 알림 on/off는 포트폴리오 단위가 아닌 **유저 단위** 설정(마이그레이션 `cs2_composite_signal_user_level`). AUTO 모드 알림이 시장신호 게이트로 이번만 NOTIFY로 강등되면 그 사유를 `automation_note`로 이메일 본문·발송 이력에 노출
  │   ├── alert_scope.py      # 리밸런싱 알림 alert_scope(AGGREGATE↔PER_ACCOUNT) 전환 (구 rebalancing_alert_service.py에서 분리)
  │   ├── alert_test.py       # 리밸런싱 알림 즉시 테스트 발송 (구 rebalancing_alert_service.py에서 분리)
  │   ├── plan_service.py     # AUTO 리밸런싱 2단계 플랜(계획 생성 → 매수 대기/매도 승인 → 실행) 생명주기 관리 — 매수는 대기시간 경과 후 자동 실행(취소 가능), 매도는 이메일 승인 필요(당일 장마감 미응답 시 자동 만료). 토큰은 SHA-256 해시만 저장, `FOR UPDATE`로 중복 실행 방지 (구 rebalancing_plan_service.py). `build_pending_plan_for_alert()`가 세금영향(`RebalancingAlert.tax_impact_gate_mode`) 또는 시장신호 게이트로 계획 생성을 막으면 각각 `TaxGateBlocked`/`MarketSignalGateBlocked` sentinel을 반환(플랜 미생성) — `notify_tax_gate_blocked()`/`notify_market_signal_gate_blocked()`가 알림당 하루 1회(Postgres 기반 durable_state dedup — 재시작에도 유지) 이메일/푸시/이력으로 보류 사유를 안내. `execute_due_buy_legs()`는 대기시간이 지난 매수 leg 실행 직전 시장신호 게이트를 재확인(계획 생성 시점 이후 상황 악화 대응, 차단되면 조용히 다음 1분 tick에 재시도). leg 실행 자체가 예외로 실패하면(개별 종목 주문 실패와는 별개) `_notify_leg_execution_failed()`가 이메일/푸시로 안내
  │   ├── execution_service.py # 리밸런싱 주문 실행 조율 — 실제 주문은 _kis_order_executor.py/_kiwoom_order_executor.py로 분리 (구 rebalancing_execution_service.py)
  │   ├── _kis_order_executor.py  # KIS 단일/TWO_PHASE 리밸런싱 주문 실행 (execution_service.py에서 분리)
  │   ├── _kiwoom_order_executor.py # Kiwoom 국내 단일 주문 실행 (execution_service.py에서 분리)
  │   ├── _order_executor_common.py # KIS/Kiwoom 주문 실행 결과 처리 공용 헬퍼 (양쪽 executor 공용)
  │   ├── _order_quantity_guard.py # clamp_sell_orders() — 매도 수량을 실제 보유 수량으로 clamp (양쪽 executor 공용)
  │   ├── diagnosis_service.py # 진단 화면 표시용 시장상황/리스크/세금영향 코멘트 생성 — needs_rebalancing 알림 판정과는 완전히 분리된 설명 전용 로직, alert 아님 (구 rebalancing_diagnosis_service.py)
  │   ├── overview_enrichment.py # 목표 포트폴리오 중 미보유 종목의 배당수익률·현재가 보완(collect_dividend_map/enrich_overview_with_prices) — rebalancing.py analyze_portfolio 엔드포인트 전용, 헬퍼를 라우터에서 분리
  │   ├── broker_balance_service.py # KIS/키움 계좌 실시간 잔고 조회(fetch_broker_balance) — rebalancing.py broker-balance 엔드포인트 전용, 헬퍼를 라우터에서 분리
  │   └── _alert_queries.py   # RebalancingAlert portfolio_id+user_id 조회 헬퍼 (rebalancing_alerts.py 라우터에서 분리, 구 _rebalancing_alert_queries.py)
  ├── backtest_service.py     # 백테스트 엔진 (상관관계 분석은 correlation_service.py로 분리됨)
  ├── correlation_service.py  # 포트폴리오 내 종목 간 월별 수익률 상관관계 분석 — backtest_service.py에서 분리 (별도 스키마 CorrelationRequest/Result 사용)
  ├── credential_service.py   # AES-256 자격증명 암호화/복호화
  ├── dart_service.py         # DART OpenAPI 연동 — dividend/fetcher.py 폴백 체인의 배당 데이터 소스 (fetch_dart_dividend)
  ├── dca_service.py          # DCA(정기투자) 분석 + 목표 타임라인
  ├── goal_recommendation_service.py  # 목표 역산 포트폴리오 추천 API 진입점 2종(전체 자산 기준/투자기간별) — 목표금액/월적립액/목표연도 → 필요 수익률 역산 → MVO 최적화 호출로 최소분산 포트폴리오 추천. 배당 목표(`annual_dividend_goal`)가 있으면 필요 배당수익률도 제약으로 함께 전달(전체 자산 기준만, 큐레이션 후보로 달성 불가하면 fail-soft로 무시). 자동 반영 안 됨 — 사용자가 확인 후 수동 적용
  ├── goal_portfolio_optimizer.py  # 목표 역산 추천 전용 MVO 최적화 엔진(SLSQP, DB 의존 없는 순수 계산) — goal_recommendation_service.py 서브모듈
  ├── goal_candidate_service.py  # 목표 역산 추천 후보 종목 관리/영속화(세제유형별 필터링, 동시요청 lost-update 방지 락) — goal_recommendation_service.py 서브모듈
  ├── goal_return_solver.py   # 목표 역산에 필요한 연평균 수익률(`solve_required_annual_return_pct`)·월 적립액(`solve_required_monthly_deposit`) 역산 순수 계산 함수 — goal_recommendation_service.py 서브모듈이자 invest.py의 `GET /invest/goal-feasibility`(목표 설정 마법사 전용, 저장 없는 미리보기)가 직접 호출
  ├── recommendation_universe.py  # 목표 역산 추천의 큐레이션 ETF 후보 유니버스 + 자산군(AssetClass)/추종지수 지역(IndexRegion) 필터링
  ├── dividend/               # 배당 서비스 패키지 — 루트에 흩어져 있던 파일들을 전부 이 아래로 통합
  │   ├── constants.py        # 배당 관련 정적 상수 + ETF 판별 유틸 (구 dividend_constants.py)
  │   ├── sync_sources.py     # 외부 소스별 동기 배당 조회 함수(Yahoo/Naver/pykrx/FDR) — fetcher.py 폴백 체인이 호출 (구 dividend_sync_sources.py)
  │   ├── fetcher.py          # 멀티소스 폴백 체인: Naver → yfinance → KIS ETF → pykrx → FDR → KIS 일반 → DART → 정적 폴백 (구 dividend_fetcher.py)
  │   ├── calculator.py       # 순수 계산 함수 — DB·외부 API 의존 없음, 단위 테스트 용이
  │   ├── orchestrator.py     # DB·캐시·외부 fetch 조율, get_dividend_data() 등 구현 (ticker 설정 CRUD는 ticker_settings_service.py로 분리됨)
  │   ├── ticker_settings_service.py # 사용자별 배당월 수동 설정(UserTickerSettings) CRUD — orchestrator.py에서 분리
  │   ├── aggregator.py       # 트랜잭션 기반 배당금 집계 (get_dividend_summary, 구 dividend_aggregator.py)
  │   ├── plan_service.py     # 연배당/월배당 계획 및 목표 달성 현황 서비스 (구 dividend_plan_service.py)
  │   ├── drip_service.py     # 배당 월별 균등화 제안 (calc_monthly_optimization) — 순수 함수
  │   └── _dividend_queries.py # 배당 관련 DB 쿼리 헬퍼
  ├── price_sync_sources.py   # [현재가 조회 그룹] Yahoo 클라우드 IP 차단 대비 국내종목 Naver/pykrx 폴백 가격 조회
  ├── email_service.py        # 이메일 발송
  ├── portfolio_service.py    # 포트폴리오 overview 집계 (portfolio.py 라우터에서 분리)
  ├── portfolio_history_service.py  # 포트폴리오 월별 자산 배분 이력 (portfolio_service.py에서 분리)
  ├── price_service.py        # [현재가 조회 그룹] 현재가 조회 (Yahoo Finance → KIS 우선순위). Yahoo Finance 함수는 yahoo_price.py로 분리됨
  ├── stock_search_service.py # 종목명·티커 검색 — 네이버 금융(한글)/Yahoo Finance(영문·티커) 연동 (stocks.py 라우터에서 분리)
  ├── tax_service.py          # 연도별 세금 추정: 배당소득세·해외 양도세·종합과세 경계 (연금 납입 현황은 pension_contribution_service.py로 분리됨)
  ├── pension_contribution_service.py # 연금저축/IRP 계좌군 세액공제 한도(600만원/900만원) 납입 현황 — tax_service.py에서 분리
  ├── isa_service.py          # ISA 계좌 의무가입 3년 만기 현황 계산 — `isa_open_date` 기준, 수동입력 누적손익(`isa_manual_cumulative_pnl_krw`) 반영
  ├── asset_aggregator.py     # 대시보드 집계 (get_dashboard_summary), XIRR·연환산 수익률·벤치마크 계산
  ├── snapshot_service.py     # 스냅샷 upsert·포지션 sync 헬퍼 (_upsert_snapshot, sync_snapshot_positions, get_latest_snapshot_with_positions)
  ├── _snapshot_queries.py    # latest_snapshot_subquery() — account_id별 max(snapshot_date) SQLAlchemy 서브쿼리 헬퍼
  ├── _account_queries.py     # 활성 계좌 조회 쿼리 헬퍼 (is_active == True 필터, 브로커 계좌 필터, 비활성 포함 단건 조회)
  ├── _position_queries.py    # 포지션 DB 쿼리 헬퍼
  ├── _settings_queries.py    # UserSettings 조회/get-or-create + has_active_kis_credentials 쿼리 헬퍼 (settings.py 라우터에서 분리)
  ├── _portfolio_queries.py   # 연결된 포트폴리오 목록·활성 알림 threshold 조회 헬퍼 (rebalancing.py 라우터에서 분리)
  ├── yahoo_price.py          # [현재가 조회 그룹] Yahoo Finance 가격 조회 유틸 (티커 변환, 개별/배치 조회, 수익률 계산)
  ├── backtest_metrics.py           # 백테스트 성과 지표 계산 (backtest_service.py 서브모듈)
  ├── composition_calculator.py     # 자산 구성 비중 계산. `exclude_real_estate(total_assets_krw, by_type)` — 목표 진행율·필요수익률 등 "투자자산" 기준 계산 전용 헬퍼(부동산 순자산 제외, 대시보드 총자산 표시에는 미적용). MVO 후보·DCA 복리 곡선 둘 다 부동산 가치 상승을 모델링하지 않아 부동산 포함 총자산을 그대로 쓰면 진행율이 왜곡됨 — asset_aggregator.py/dca_service.py/invest.py의 목표 관련 계산이 호출
  ├── trend_calculator.py           # 월별 자산 추이 계산
  ├── returns_calculator.py         # 수익률 계산 (XIRR 등)
  ├── economic_indicator_service.py # 미국 CPI/Core CPI 조회·캐싱 + FRED 발표 캘린더 조회(fetch_inflation_summary 전용, 구 economic_calendar_service.py 병합됨)
  ├── email_templates.py            # 이메일 HTML 템플릿 모듈 (email_service.py에서 분리)
  ├── factor_service.py             # 팩터 분석 (모멘텀·가치·품질)
  ├── insight_service.py            # 포트폴리오 진단 & 인사이트 생성
  ├── market_data_fetcher.py        # [팩터·리스크용 배치 수익률 그룹] 시장 데이터 수집 유틸 (VIX, 금리차 등) — 개별 현재가 조회(price_service.py 등)와는 별개 책임
  ├── market_signal_service.py      # 복합 시장 위험 신호 평가
  ├── portfolio_optimizer.py        # 포트폴리오 최적화 (효율적 프론티어)
  ├── position_aggregator.py        # 복수 계좌 포지션 집계
  ├── push_service.py               # FCM 푸시 알림 발송
  └── risk_service.py               # 포트폴리오 리스크 지표 계산 (VaR, 변동성 등)

> 새 서비스 파일 추가/삭제 시 이 목록도 함께 갱신.

schemas/                      # Pydantic 요청/응답 스키마
  ├── _validators.py          # 공용 field_validator 헬퍼
  ├── asset.py / auth.py / backtest.py / invest.py / portfolio.py
  ├── transaction.py           # 입출금/배당 내역 스키마 (구 asset.py, transactions.py 라우터 전용)
  ├── dashboard.py              # 대시보드 응답 스키마 (구 asset.py, dashboard.py 라우터 전용)
  ├── rebalancing/             # 리밸런싱 스키마 패키지 (구 rebalancing.py 단일 파일, 453줄 → 책임별 분리) — `__init__.py`가 전체 재노출하므로 `from app.schemas.rebalancing import X` 호출부는 변경 없음
  │   ├── analysis.py          # 분석 결과: TickerAccountInfo/RebalancingItem/CurrentHolding/TaxImpactItem/DiagnosisContext/RebalancingAnalysis
  │   ├── execution.py         # 실행/실행이력: ExecutionOrderItem/ExecutionRequest/KisBalance*/OrderResult/ExecutionResult/RebalancingExecution*
  │   ├── drift.py             # 드리프트 요약(대시보드 경량 조회): DriftedItem/PortfolioDriftSummary
  │   ├── alert.py             # 알림 설정: RebalancingAlertCreate/AlertScopeUpdate/TestAlertResponse/RebalancingAlertResponse
  │   ├── plan.py               # 대기 플랜: RebalancingPlanItemOut/RebalancingPlanLegSummary/PlanTokenPreview 등
  │   └── goal.py               # 목표 역산 추천/복합신호 배너: GoalRecommendation*/CompositeSignalStatus
  └── service_dtypes.py       # 서비스 계층 내부 TypedDict (DB/외부 API 응답 형태 고정)

core/                         # 설정·DB·in-memory 캐시 store (구 app/config.py·app/database.py)
  ├── config.py                # Settings(pydantic-settings) — env var 로딩
  ├── database.py              # SQLAlchemy async engine/session, Base
  └── cache_store.py           # 프로세스 내 in-memory TTL 캐시 store 싱글톤, get_cache_store/close_cache_store (단일 프로세스 배포 전제 — 구 Redis 클라이언트 대체)
kis/                          # KIS OpenAPI 클라이언트 (auth, balance, client, constants, domestic_quote, order, overseas_quote)
kiwoom/                       # 키움증권 API 클라이언트 (auth, balance, client, order, constants). `client.py`는 KIS와 동일한 `AsyncRateLimiter`로 초당 `kiwoom_rate_per_second`(기본 4.0, 관측 유량 5/s 대비 20% 버퍼) 건 제한 — `providers/http_client.py`의 rate-limit 응답 감지도 키움 `return_code=5`(EGW00201과 동일 의미)에 대응
providers/                    # 금융 데이터 provider
  ├── base.py                 # Provider 추상 베이스
  ├── http_client.py          # 공통 HTTP 클라이언트
  ├── kis_provider.py         # KIS API provider
  ├── kiwoom_provider.py      # 키움증권 API provider
  ├── manual_provider.py      # 수동 입력 provider
  ├── _token_cache.py         # 토큰 캐싱 헬퍼
  ├── _retry.py               # 토큰 갱신 재시도 공용 헬퍼
  ├── _overseas_cache.py      # KIS/키움 공용 해외 잔고 조회 캐시 헬퍼(has_overseas 캐시 플래그로 해외 보유 없는 계좌의 API 콜 스킵)
  ├── _overseas_name_enrichment.py # 해외 포지션 종목명 한글/영문 혼재 방지 — 동기화 시점에 티커 기준 영문 캐노니컬 이름 조회(stock_search_service.resolve_english_name) 후 캐싱, 조회 실패 시 브로커 원본명 폴백
  └── _error_mapping.py       # KIS/키움 공용 HTTP 에러 매핑 (5xx/4xx 분기, ConnectError/TimeoutException) — 브로커별 에러 메시지 키(msg1 vs return_msg)만 파라미터로 받음
utils/
  ├── cache_keys.py           # 캐시 키 빌더 + TTL 상수 (`dividend_ticker_summary_key` 등) — Tier1(휘발성) 캐시 전용, get_cached_json/set_cached_json/invalidate_* 포함
  ├── circuit_breaker.py      # 인메모리 서킷 브레이커 (CircuitOpenError). KIS/Kiwoom 5회→60s, Yahoo/DART/Naver/FDR 5회→120s, FearGreedAPI 3회→120s, FRED 4회→300s. 재시작 시 상태 초기화됨.
  ├── currency.py             # USD/KRW 캐싱 (`get_usd_krw_rate`, `cache_usd_krw_rate`)
  ├── durable_state.py        # Postgres(`AppState` 테이블) 기반 key-value durable state — get_durable/set_durable/delete_durable. 재시작에도 유지돼야 하는 상태(시장신호 등급 마지막 값, 알림 dedup 플래그) 전용, cache_keys.py의 휘발성 캐시와는 별개
  ├── inproc_lock.py          # 프로세스 내 락 — 동일 계좌 동시 sync 방지, 콜드 캐시 single-flight 중복 조회 방지 (구 redis_lock.py, 단일 프로세스 배포 전제로 대체)
  ├── market_hours.py         # KRX/NYSE 개장 여부 판단
  ├── metrics.py              # Prometheus 커스텀 메트릭 (broker_sync_duration, alert_trigger_count 등) — `/metrics` 엔드포인트로 노출
  └── pnl.py                  # 포지션 P&L 순수 계산 함수 (eval_value, invested_value, pnl_pct)
limiter.py                    # slowapi 레이트 리미터 (@limiter.limit("X/minute") 데코레이터, request: Request 파라미터 필수)
jobs/                         # APScheduler 정기 작업
  ├── asset_sync.py           # 15:30 KST intraday + 18:00 KST daily 전체 계좌 스냅샷
  ├── exchange_rate_alert.py  # 5분 간격 환율 알림 체크
  ├── goal_achievement.py     # 매일 18:45 KST 투자 목표 달성도 확인
  ├── monthly_report.py       # 매월 1일 09:00 KST 월간 리포트 발송
  ├── price_publisher.py      # 30초 간격 WebSocket 실시간 가격 브로드캐스트
  ├── rebalancing_alert.py    # 10분 간격(app/scheduler.py:44) — 리밸런싱 드리프트 초과 시 이메일 알림(SCHEDULE/DRIFT/BOTH 조건 체크)
  ├── market_signal_alert.py  # 1시간 간격 — 시장 위험 신호 등급 전환(GREEN/YELLOW/RED) 감지 시 즉시 알림
  ├── market_signal_daily_digest.py  # 매일 08:30 KST — 등급 전환 여부와 무관하게 현재 시장 신호를 요약 발송(옵트인, 기본 OFF)
  ├── year_end_tax_reminder.py       # 11~12월 매주 월요일 09:00 KST — 손실수확 후보·연금공제 잔여한도·ISA 만기 현황 요약 발송(옵트인, 기본 OFF). 알릴 내용이 없으면 스킵
  ├── rebalancing_auto_execution.py  # 장 중 5분 간격 — AUTO 모드 리밸런싱 대기 플랜 생성(계획 이메일 발송, 실행은 안 함). 시장신호·세금영향 게이트로 차단되면 보류 알림 발송(services/rebalancing/plan_service.py 참고)
  ├── rebalancing_plan_buy_execution.py  # 1분 간격 — 대기시간 지난 매수 leg 자동 실행. 실행 직전 시장신호 게이트를 재확인(대기 중 상황 악화 대응) — 차단되면 조용히 다음 tick 재시도
  ├── rebalancing_plan_sell_expiry.py  # 매일 15:31 KST — 당일 미응답 매도 승인 요청 만료 처리
  ├── stock_price_alert.py    # 10분 간격 주가 알림 체크
  ├── token_refresh.py        # 매일 06:00 KST KIS 계좌별 토큰 갱신
  └── _job_helpers.py         # job 공통 헬퍼 유틸리티
```

> **새 job 추가:** `jobs/` 에 파일 생성 후 `app/scheduler.py`의 `init_scheduler()`에 `scheduler.add_job()` 호출로 등록. `timezone="Asia/Seoul"` 필수.

**자격증명 암호화:** KIS/키움 App Key/Secret은 `credential_service.py`의 AES-256으로 DB 저장. `encrypt()`/`decrypt()` 호출 필수.

**현재가 조회 우선순위:** `price_service.py` — Yahoo Finance(yfinance, API 키 불필요) → KIS API. yfinance는 `run_in_executor`로 동기 함수 비동기 실행.

**USD/KRW 환율 캐싱:** `app/utils/currency.py`의 `get_usd_krw_rate(cache)` → in-memory 캐시 `usd_krw_rate` 키 조회(TTL: `settings.cache_ttl_seconds`) → 없으면 `settings.usd_krw_fallback_rate` fallback. KIS API 성공 시 `cache_usd_krw_rate(cache, rate)` 호출로 갱신. 테스트 패치 경로: `app.utils.currency.cache_usd_krw_rate`.

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
- 새 기능 E2E 순서: 모델(`models/`) → 스키마(`schemas/`) → 서비스(`services/`) → 라우터(`api/v1/`) → `router.py` 등록 → `alembic/env.py` import → 마이그레이션 생성 → 테스트 → 관련 CLAUDE.md 목록/설명 갱신

**Rate Limiting**
- `@limiter.limit("X/minute")` 데코레이터 적용 시 함수 시그니처에 `request: Request` 파라미터 필수.
  ```python
  @router.get("/endpoint")
  @limiter.limit("60/minute")
  async def my_endpoint(request: Request, ...):
  ```
