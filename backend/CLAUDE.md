# Backend CLAUDE.md

> 파일 목록은 **한 줄 요약 + 코드만 봐선 모르는 함정**만 적는다. 설계 경위·변경 이력은 `docs/plans/`와 git log에 있다 — 여기에 다시 쓰지 말 것.

## Commands

```bash
cd backend && uv sync --extra dev                     # 설치 (uv.lock 기준, = make install-backend)
cd backend && uv run uvicorn app.main:app --reload    # 서버 localhost:8000, Swagger /docs (APP_ENV=development)

# DB
cd backend && uv run alembic upgrade head
cd backend && uv run alembic revision --autogenerate -m "description"
cd backend && uv run alembic downgrade -1
cd backend && uv run alembic current / history --verbose

# Tests (pytest-asyncio, asyncio_mode="auto")
cd backend && uv run pytest
cd backend && uv run pytest tests/test_asset_service.py -v
cd backend && uv run pytest -k "test_name" -x --tb=short
cd backend && uv run pytest --cov=app --cov-report=term-missing   # CI 게이트

# Lint & Type
cd backend && uv run ruff check .    # E/F/I/UP/B/SIM/C90/ASYNC/PT/RUF100, E712·B008·SIM108·PT001 제외, max-complexity 15
cd backend && uv run mypy app/
```

- **RUF100**: 불필요한 `# noqa`도 오류 — 필요 없어진 noqa는 지운다.
- **mypy `platform = "linux"` 고정**: CI(Linux)와 로컬(Windows)의 `sys.platform` stub 분기 차이 방지.
- **pyproject 의존성에 extras 표기(`pkg[extra]`) 금지**: Dependabot(uv)이 `No update possible`로 조용히 건너뛰어 영영 갱신되지 않는다. extra가 끌어오는 패키지를 직접 나열한다(`uvicorn[standard]` 등을 이렇게 풀어 둠).

### Alembic 주의

- autogenerate는 `app/models/__init__.py`에 모델 import가 있어야 인식한다(`env.py`는 `import app.models`로 패키지만 읽는다).
- `env.py`의 `include_name`이 비교 대상을 growlio 테이블로 한정한다(nestlio와 `public` 공유 — 필터 없으면 nestlio 테이블 드롭 제안). 그래서 **모델에서 지운 테이블의 드롭은 autogenerate가 못 잡으니 직접 쓴다.**
- 인덱스는 모델 `__table_args__`에도 선언 — 마이그레이션에만 있으면 다음 autogenerate가 드롭을 제안한다.
- 버전 포인터는 `alembic_version`이 아니라 **`growlio_alembic_version`**(`env.py`의 `VERSION_TABLE`). 기본 테이블을 쓰면 nestlio와 리비전을 덮어써 `Can't locate revision ...`. 이 테이블이 없는 기존 DB는 `upgrade head` 전에 `python scripts/bootstrap_alembic.py` 1회(멱등) — `render.yaml` preDeployCommand도 이 순서. `public.alembic_version`(nestlio)은 건드리지 않는다.
- 운영 이미지(`backend/Dockerfile`)는 의존성만 설치하고 프로젝트는 설치하지 않는다(`--no-install-project`). `scripts/*`의 `import app`은 `ENV PYTHONPATH=/app`에 의존하므로 이 줄을 지우면 preDeploy가 `ModuleNotFoundError`로 실패한다. CI `docker-build` 잡이 scripts/ 작업 경로 import로 이를 확인한다.

### Tests 주의

- 실제 DB 없이 mocked `AsyncSession`(`tests/conftest.py`). 환경변수(`KIS_CRED_ENCRYPTION_KEY` 등)도 conftest가 override — `.env` 없이 실행 가능.
- 주요 fixtures: `mock_db`, `mock_cache`(in-memory get/set/setex), `make_account`, `make_snapshot`, `make_user_settings`.
- **Windows**: 전체 실행이 `N passed` 후 exit `-1073741819`(0xC0000005)로 끝나는 건 네이티브 확장 teardown 이슈 — 테스트 실패 아님. 판정은 `N passed` 출력과 CI 기준.
- 테스트 목록: `uv run pytest --collect-only -q`.

### Environment (`backend/.env`, `.env.example` 참고)

- `APP_ENV=development` — `/docs` 활성화
- `DATABASE_URL` — asyncpg URL. Supabase면 **Transaction Pooler(6543)** 권장 — Session Pooler(5432)는 프로젝트 전체 동시 연결 15개를 공유해 좀비 `uvicorn --reload` 하나로도 `EMAXCONNSESSION`
- `MIGRATION_DATABASE_URL` — Supabase 마이그레이션용 (로컬 Docker는 `DATABASE_URL`과 동일)
- `KIS_CRED_ENCRYPTION_KEY` — 64자 hex. KIS/키움/토스 자격증명 AES-256 키
- `ALLOWED_ORIGINS`(CORS, 쉼표 구분) · `FRONTEND_URL`(이메일 링크) · `API_SEMAPHORE_LIMIT` · `CACHE_TTL_SECONDS`
- Supabase: `SUPABASE_PROJECT_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- 외부 API: `DART_API_KEY`, `FRED_API_KEY`
- 이메일(Resend HTTP API — 클라우드 SMTP 포트 차단 회피): `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_TIMEOUT`
- FCM: `FIREBASE_CREDENTIALS_JSON`(한 줄 JSON) · 모니터링: `METRICS_TOKEN`, `SENTRY_DSN`, `SENTRY_RELEASE`
- 그 외 튜닝값(rate limit·circuit breaker·DB pool·환율 fallback 등)은 `app/core/config.py` `Settings` — 전부 기본값 있음

---

## Architecture (`backend/app/`)

### 데이터 모델 (핵심만 — 전체는 `app/models/`)

- `AssetAccount` — 계좌 마스터. `asset_type`(`app/enums.py` `AssetType`) × `data_source`(MANUAL/KIS_API/KIWOOM_API/TOSS_API) 조합으로 동작 결정. 토스 자격증명은 AES-256, 모의투자 없음. ISA 필드(`isa_open_date`/`isa_type`/`isa_manual_cumulative_pnl_krw`). `tax_type`·`investment_horizon`은 `Portfolio`에도 같은 컬럼 — 목표 역산 추천이 (기간, 세제유형) 매칭에 사용
- `AssetSnapshot` — 일별 계좌 스냅샷. `(account_id, snapshot_date)` unique
- `Position` — 보유 포지션. `snapshot_id IS NULL` = 현재 포지션, NOT NULL = 스냅샷 시점
- `Transaction` — DEPOSIT/WITHDRAWAL/DIVIDEND/INTEREST. INTEREST는 금융소득 종합과세 판정 전용 — **입출금 흐름 집계는 DEPOSIT/WITHDRAWAL을 명시 필터**하는 관례 유지
- `TradeRecord` — 수기 매수/매도(`price_krw`). 기간별 매수 수익률 + KIS 실전 외 계좌의 해외 양도세 실현손익에 사용. `Transaction`과 **의도적으로 분리**(섞으면 유형 필터 없는 입출금 집계 오염). Position을 자동 수정하지 않음. 브로커 sync는 체결내역을 가져오지 않음
- `InvestmentChallenge` — DEPOSIT/RETURN_PCT/TARGET_VALUE. `account_id`는 DEPOSIT만. 진행률·스트릭은 저장 안 하고 매 조회 재계산
- `UserSettings` — 브로커 자격증명(AES-256), 투자·입금 목표, 추천 옵션, 알림 옵트인. `PUT /settings/goal`은 **보낸 키만** 바꾼다(`model_fields_set` — 명시적 null은 비우고 생략은 유지). `challenge_reminders_enabled`는 챌린지별 알림 ON으로 첫 챌린지 생성 시 자동 True(이중 게이트 방지)

### API 라우터 (`api/v1/`, 전부 `router.py`에서 등록)

> 라우터 추가/prefix 변경 시 이 목록도 갱신.

```
assets.py                계좌 CRUD + 동기화 트리거, 브로커 자격증명 검증·삭제, ISA 누적손익 수동입력
auth.py                  /me, /sync-profile, /find-account, /account/delete. 로그인·가입·refresh는 프론트가 Supabase에 직접 — 백엔드엔 없음
alerts.py                알림 목록·읽음 (+ 하위 /alerts/*: exchange_rate_alerts.py / stock_price_alerts.py / rebalancing_alerts.py)
backtest.py              백테스트
dashboard.py             대시보드 집계(구현은 asset_aggregator) + GET /dashboard/action-items
dividends.py             배당 요약·예상·균등화 — ?account_id= 미지정 시 전체 통합
invest.py                DCA 분석 + GET /invest/goal-feasibility(저장 없음) + GET /invest/fx-plan(환전 계획, 저장 없음)
challenges.py            적립 챌린지 CRUD + 진행률 (/challenges/summary는 네비 배지용 경량)
portfolios.py            포트폴리오 CRUD — 항목은 단독 종목 또는 지수 그룹(group). index-group-suggestions는 **항상 전체 계좌 기준**, 범위 밖 종목은 in_scope=False
portfolio_analysis.py    /portfolio/{overview,allocation-history,risk,rebalancing-strategy,index-exposure}
rebalancing.py           리밸런싱 추천 + 목표 역산 추천(goal-recommendation/{by-horizon,by-age}) + expected-metrics
rebalancing_execution.py 주문 실행·이력 + 미체결 취소(POST /history/results/{id}/cancel)
rebalancing_plan.py      대기 플랜 조회/취소/승인 (인증 필요)
rebalancing_plan_public.py 이메일 링크 토큰 액션 — **인증 없음, Depends(get_current_user) 사용 금지**
settings.py              DART 키 + 목표/알림 설정 (브로커 자격증명은 assets.py 소관)
stocks.py                종목 검색 + GET /stocks/index-region
tax.py                   /tax/{summary,overseas-positions,overseas-realized,isa-status,pension-contribution,action-plan}
transactions.py          입출금/배당 CRUD
trades.py                수기 매매 CRUD + GET /trades/period-summary (기본 KST 이번 달, 미래 기간 400)
economic_indicators.py   GET /economic-indicators/inflation-summary 하나뿐
insights.py              인사이트·진단
market_signals.py        복합 시장 신호
tactical.py              전술 배분 — GET /tactical(켠 목록), GET /tactical/market(포트폴리오 무관 시장 입력 — **/{portfolio_id}보다 먼저 선언**), GET/PUT/DELETE /{id}, POST /{id}/apply(목표만 저장, **주문 없음**; fraction<1은 분할 적용), GET /{id}/backtest
positions.py             포지션 CRUD + 현재가 sync (/assets/{id}/positions)
external.py              자매 앱 nestlio 전용(같은 Supabase JWT, growlio 프론트 미사용). 조회 로직은 services/external_queries.py. POST /external/transactions의 external_ref는 멱등 키(같은 키 재전송 → duplicate=True로 기존 행)
_account_deps.py         계좌 소유권 검증(get_owned_account) + get_owned_or_404 재노출
_alert_crud.py           환율/주가 알림 공용 reactivate·delete 팩토리
```

### Services (`services/`)

> 접미사 관례: `*_service.py`(DB/외부 API 유스케이스), `*_calculator.py`/`*_aggregator.py`(순수 계산), 접미사 없음(도메인 유틸). 강제 아님. 파일 추가/삭제 시 이 목록도 갱신.
> 도메인 패키지(`accounts/`·`portfolio/`·`market_data/`·`notifications/`·`goal/`·`etf/`·`tactical/`·`tax/`·`market_signal/`·`backtest/`·`rebalancing/`·`alerts/`·`dividend/`)는 re-export shim 없이 `app.services.<pkg>.<module>`로 import·patch한다. 평면에 남은 건 단일 도메인 모듈뿐(아래 "기타").

**계좌·동기화 (`accounts/`)**
- `credential_service.py` — AES-256 암복호화
- `asset_service.py` — 계좌별 sync + `sync_account_now`(assets `/sync` 전용)
- `asset_credential_service.py` — 브로커 자격증명 검증·삭제
- `sync_all_service.py` — "전체 갱신" 백그라운드 배치(락·진행상태는 in-memory 캐시). `sync_accounts`(세마포어 3)는 `jobs/asset_sync`도 재사용. 계좌별로 **짧게 스코프된 `AsyncSessionLocal()`을 새로 연다** — 브로커 응답 대기 중 커넥션 점유로 풀 고갈 방지. 계좌 수만큼 동시 호출하는 새 엔드포인트도 이 패턴
- `snapshot_service.py` — 스냅샷 upsert·포지션 sync 헬퍼. 수동 계좌 예수금 변경 → 오늘 스냅샷 재작성은 `write_manual_deposit_snapshot`(포지션 복사 포함 — 빠뜨리면 오늘 스냅샷에서 보유종목이 사라진다)
- 쿼리 헬퍼: `_snapshot_queries.py`(최신 스냅샷 서브쿼리), `_account_queries.py`(활성 계좌 — `active_accounts_stmt()`/`active_broker_accounts_stmt()`)

**포트폴리오·자산 집계 (`portfolio/`)**
- `asset_aggregator.py` — 대시보드 집계, XIRR·연환산·벤치마크, 월별 추이(`get_monthly_trend`)
- `portfolio_service.py` — overview 집계. 부분집합 총자산 반복 계산은 `prefetch_accounts_snapshot_positions()`/`compute_total_assets_krw()`로 1회 조회 재사용
- `portfolio_history_service.py` · `position_aggregator.py` · `returns_calculator.py`
- `composition_calculator.py` — 자산 구성. `exclude_real_estate()`는 목표 진행률·필요수익률 등 "투자자산" 계산 전용(대시보드 총자산 표시엔 미적용)
- `period_purchase_service.py` — 기간별 매수 수익률. 스냅샷 수량·평단 변화로 추정, 수기 BUY 기록 있으면 기록 우선. **해외는 `avg_price_usd`로 역산 후 그 스냅샷 `usd_rate`로 환산**(원화 평단은 매일 재환산돼 역산 불가). 기록 market과 브로커 포지션 market이 달라 `_position_key_aligner`로 정렬
- 쿼리 헬퍼: `_position_queries.py`, `_portfolio_queries.py`

**시세 (`market_data/`)**
- `price_service.py` — 현재가(Yahoo → KIS). `yahoo_price.py` — Yahoo 유틸. **브로커 잔고는 국내 market을 전부 "KOSPI"로 채운다** — `to_yf_symbol()`이 `_kosdaq_tickers`(FDR, 매일 07:00 갱신)로 `.KQ` 교정. 저장된 market은 매칭 키라 바꾸지 않음. pykrx 상장목록은 KRX 로그인 요구로 사용 불가
- `price_sync_sources.py` — 국내 Naver/pykrx 폴백 (Yahoo 클라우드 IP 차단 대비)
- `stock_search_service.py` — 네이버(한글)/Yahoo(영문·티커) 검색
- `market_data_fetcher.py` — 팩터·리스크용 배치 수익률 (개별 현재가와 별개)

**리밸런싱 (`rebalancing/`)**
- `service.py` — 리밸런싱 추천. 지수 그룹은 그룹 행 하나(`shares_to_trade=None`, 종목별은 `members`)
- `group_expansion.py` — 그룹 행 → 종목 단위 매매 전개. 그룹 차이는 **노출 단위**(멤버 `leverage` 배수). **그룹 행은 수량이 없으므로 수량 기반 소비처를 새로 만들면 반드시 `expand_group_items`/`iter_trade_items`로 펼칠 것**
- `order_builder.py` — 주문 생성 공용(AUTO·원클릭·플랜). 시장 게이트 단일 판정 `is_market_signal_blocking_auto_mode`(CAUTIOUS=RED, STRICT=YELLOW·RED, TACTICAL=같은 포트폴리오 확정 국면 RISK_OFF면 매수 보류 — 호출부 5곳이 `tactical_regime_for_gate()` 결과를 함께 넘김). `clamp_orders_to_max_value()` 1건당 상한. 방법론 `docs/plans/21-market-signal-methodology.md`
- `plan_service.py` — AUTO 2단계 플랜 진입점, 하위 3모듈 심볼 재노출. **테스트 patch는 `plan_service.X`가 아니라 실제 호출부 서브모듈 경로로**
  - `plan_generation.py` — 플랜 생성. 게이트 차단 시 `TaxGateBlocked`/`MarketSignalGateBlocked`/`DailyValueCapBlocked` sentinel(플랜 미생성)
  - `plan_execution.py` — leg 실행/취소/만료. 매수는 대기 후 자동(실행 직전 시장 게이트 재확인), 매도는 이메일 승인. 토큰은 SHA-256 해시만 저장, `FOR UPDATE`로 중복 방지. `token_consumed_at`만 찍힌 채 30분 넘은 PENDING은 `fail_stuck_consumed_legs()`가 FAILED 마감(재실행 안 함)
  - `plan_notifications.py` — 플랜 알림 (차단 안내는 하루 1회 durable dedup)
- `quick_execute_service.py` — "지금 계획 생성". 상태 enum만 반환, 문구는 라우터가 조립. 계좌 소유권 검증은 콜백 주입(**서비스→API 계층 import 금지**)
- `execution_service.py` — 주문 조율. 실제 주문은 `_kis_order_executor.py`/`_kiwoom_order_executor.py`(FULL 매수는 실행 직전 가용현금으로 예산 clamp), 공용 `_order_executor_common.py`(국내 지정가 호가 보정 `snap_domestic_limit_price` 포함), `_order_quantity_guard.py`(매도→보유수량, 매수→예산), `_broker_order_flow.py`(매도 clamp·FULL 예산 clamp 흐름 — 브로커 차이는 `BrokerOrderOps`로 주입)
- `order_cancel_service.py` — 실행 주문의 미체결분 취소(체결 조회 없이 요청, 증권사 거부=CANCEL_FAILED). **KIS 국내 취소는 주문 응답의 `KRX_FWDG_ORD_ORGNO`(`order_org_no`) 저장이 필수** — 없으면 취소 불가. 증권사 거부는 `BrokerOrderRejectedError`가 아니라 클라이언트의 `KisApiError`/`KiwoomApiError`로 먼저 온다. 취소 가능 판정(`cancel_block_reason`·활성 계좌 유형)은 `order_cancel_rules.py` — 실행 직후 결과·이력 상세·취소 요청이 같은 규칙을 쓴다. **토큰 발급은 DB commit을 하므로 주문 행 `FOR UPDATE` 전에** 받고 잠근 뒤 재확인
- `krx_tick.py` — 국내 지정가 호가단위 보정(ETF·ETN 5원, 매수 내림·매도 올림)
- `alert_check.py` — 드리프트 알림(10분 job). 복합신호 on/off는 **유저 단위**
- `drift_summary_service.py` — 이탈 요약(drift-summary·action-items 공유, 같은 세션이라 순차)
- `strategy_service.py` · `alert_scope.py` · `alert_test.py` · `diagnosis_service.py`(설명 전용, alert 아님) · `overview_enrichment.py` · `_alert_queries.py`
- `broker_balance_service.py` — 3사 실시간 잔고. **주문 실행은 KIS/키움만**(토스 주문 API 미구현)

**목표 역산 추천 (`goal/`)**
- `goal_recommendation_service.py` — 전체 자산 기준 진입점. 필요수익률 역산 → MVO. 추천은 자동 반영 안 됨(수동 적용). 결과 1h 캐시 + stale 키(1d) — 미스여도 stale 즉시 반환 후 `BackgroundTasks`로 재계산(기간별·연령대도 같은 SWR, 갱신은 `refresh_recommendation_in_background` 공용). 무효화 함수는 stale 키도 함께 지운다. **추천 캐시 키(전체·기간별·연령대 각 1h/stale)는 사용자별 세대를 포함 — 무효화는 `invalidate_goal_recommendation_caches`(세대 교체)로만, 세대는 설정을 읽기 *전에* `get_goal_recommendation_generation`으로 잡아 넘긴다**(계산 중 저장된 설정을 옛 결과가 덮던 경합). sync 무효화는 `positions_changed=True`일 때만 추천 캐시 삭제. `compute_recommendation_drift()`는 프론트 `recommendationDrift.ts`와 **동일 로직 — 임계값 함께 맞출 것**
- `_goal_recommendation_common.py` — 세 진입점 공용 헬퍼·계산 골격(`import ... as _grc`, patch 경로도 여기 하나). **단 외부 조회(`get_historical_returns`/`fetch_yf_daily_returns`/`build_portfolio_overview`)는 테스트가 진입점 모듈 경로로 patch하므로 진입점에 남기고 인자로 넘긴다**(옮기면 patch 수백 곳 무효화). 추천 출력은 `tests/test_goal_recommendation_snapshots.py`가 고정 — 리팩터링 후 반드시 통과, 의도적 변경 시만 `UPDATE_GOAL_SNAPSHOTS=1`
- `goal_age_recommendation_service.py`(연령대) · `goal_horizon_recommendation_service.py`(투자기간 × 세제유형, 최대 15조합, IRP 안전자산 30% 하한)
- `goal_portfolio_optimizer.py` — MVO(SLSQP). **배당 목표 사전검증은 `class_bounds` 그룹 예산도 반영 필수** — 종목 상한만 보면 SLSQP 전체 실패(빈 추천)
- `goal_candidate_service.py` — 후보 관리(락). `pension_ineligibility_reason()`은 종목명 브랜드 휴리스틱 — 신규 ETF 브랜드는 `_KR_ETF_BRAND_PREFIXES`에 추가
- `goal_return_solver.py` — 역산 순수 함수 + `build_feasibility_preview`(마법사·nestlio 공유)
- `recommendation_universe.py` — 큐레이션 ETF 유니버스. `index_key_from_base_index`는 중복 분석·지수 분류 공용 — **복제 금지**

**ETF·지수 (`etf/`)**
- `etf_profile_service.py` — 총보수·기초지수(국내 Naver `totalFee`, 해외 yfinance `netExpenseRatio` — 둘 다 이미 % 단위)
- `etf_overlap_service.py` — 후보 중복(SAME_INDEX + 주간 상관 ≥0.97 & 변동성비 ≤1.5). 상장시장이 다른 후보끼리는 비교 안 함(의도된 병존)
- `etf_index_classifier.py` — 보유 종목 → 추종 지수 분류. 지수 패턴은 `recommendation_universe.py`와 공유 — 수정 시 중복 분석·dedup에도 반영됨
- `index_exposure_service.py` — 지수별 비중 + 리밸런싱 지수 그룹 제안

**전술 배분 (`tactical/`, QQQ/SPY)**
- `tactical_allocation_service.py` — 국면 판정(매크로 확정등급 × 추세, 서로 다른 KST 날짜 2회 확정 — 백테스트도 같은 함수), 제안 비중(비중표 → 틸트 → 웅덩이), 목표 교체. **QQQ·SPY·DIA는 지수 그룹 비중** — 적용 시 기존 그룹은 보존하고 비중만. QLD·SSO 0%면 짝 그룹의 레버리지 멤버로(전량 매도 방지). `ASSET_LABELS`는 프론트 `tacticalLabels.ASSET_LABEL`과 같게. 알림 판정은 `last_regime != notified_regime`
- `tactical_tilt.py`(QQQ↔SPY 월 1회, 기본 끔) · `tactical_dip.py`(웅덩이 투입, 공격 국면만, 기본 끔) · `tactical_hints.py`(다음 전환 조건)
- `tactical_backtest.py` — 실시간과 같은 판정 함수 사용. 매크로는 VIX로만 근사(`macro_note` 고지). **계산 방식 변경 시 `tactical_backtest_key` 버전을 올려 캐시 무효화**

**세금 (`tax/`)**
- `tax_service.py` — 연도별 세금 추정·종합과세·건보 피부양자. 해외 실현손익은 직접 조회하지 않고 `overseas_realized_krw` 인자로 받음
- `overseas_realized_service.py` — 해외 실현손익. KIS 실전은 브로커(TTTS3039R), 그 외는 해외 SELL `TradeRecord`(KIS 실전 계좌 기록은 이중 집계 방지로 무시). 성공 시만 1h 캐시
- `tax_action_service.py` — 절세 액션 플랜(조합만). 세법 수치는 `_DEDUCTION_RULES` 연도별 테이블
- `pension_contribution_service.py` · `isa_service.py`

**알림 (`alerts/`)**
- `alert_service.py` — 공통 저장·조회·격리 루프(rollback 뒤 행 객체는 refresh 후 사용). 체크 함수 re-export 없음 — 구현 모듈에서 직접 import
- `exchange_rate_service.py` · `stock_price_service.py` · `calculator.py`(조건 판단)
- `market_signal_alert_service.py` — 등급 전환 즉시 알림 + 08:30 요약. `check_composite_signal`을 alert_check·diagnosis와 공유
- `_dispatch.py` — 이메일+푸시 2채널, 하나라도 성공하면 AlertHistory 저장. 단독 푸시는 `send_push_safely`(예외 로깅 후 삼킴)
- `tax_reminder_service.py` · `recommendation_drift_alert_service.py`(추천 변화 3%p↑ — 프론트와 임계값 동일)

**시장 신호 (`market_signal/`)**
- `market_signal_service.py` — 8종 지표 복합 점수. `get_confirmed_composite_level()`(hysteresis 2회)은 AUTO 게이트·알림 전용, raw는 배너용. 지표 조회는 `market_signal_indicators.py`, 점수는 `market_signal_scoring.py` — 외부는 `market_signal_service`에서 import. **지표끼리 내부 호출하므로 patch는 `market_signal_indicators.*` 경로**
- `economic_indicator_service.py`(CPI)
- `technical_indicators.py`(순수, pandas는 함수 내부 import — 기동 시 로드 방지) · `technical_signal_service.py`(QQQ/SPY/DIA 6h 캐시)

**기타**
- `factor_service.py` · `insight_service.py` · `risk_service.py` · `portfolio_optimizer.py`(효율적 프론티어)
- `estimation.py` — Ledoit-Wolf 공분산·James-Stein 기대수익률 축소(고정 노이즈분산 사용 — 표본분산 재사용 시 축소 상쇄 버그). `goal/goal_portfolio_optimizer`·`portfolio_optimizer` 공용이라 평면
- `action_items_service.py` — 홈 "지금 할 일" 최대 5건. 이탈 포트폴리오 2개↑면 `REBALANCE_GROUP_ID`("rebalance:all", 프론트 `api/dashboard.ts`와 같은 값) 1행. 소스별 실패 격리, 결과 캐시 없음
- `challenge_service.py` — 스트릭 단위는 "월 순입금>0"(목표액 수정해도 과거 스트릭 불변)
- `dca_service.py` · `dca_cash_shortfall_service.py`(적립 자동매수 전 예수금 부족 판정, 잡·action-items 공유. 해외 매수 시장 판정 `buy_market`은 fx_plan도 사용) · `backtest/`(`backtest_service.py` + `backtest_metrics.py`) · `dart_service.py`
- `fx_plan_service.py` — 환율 1년 위치(백분위·이평 이격·1개월 ±1σ)와 해외 적립 필요 달러의 분할 환전 구간. **예측 아님**. 현재값은 실시간 캐시(없으면 1년 일봉 마지막 종가, `rate_is_live`), Yahoo `USDKRW=X` 1년 일봉은 통계용(6h 캐시). 구간 알림 등록은 프론트가 기존 환율 알림 API로
- `dividend/` — `fetcher.py`(폴백 체인 Naver → yfinance → KIS ETF → FDR(+pykrx 펀더멘털) → KIS → DART → 정적), `sync_sources.py`, `orchestrator.py`(`get_dividend_data`), `aggregator.py`, `calculator.py`(순수), `plan_service.py`, `drip_service.py`, `constants.py`, `_dividend_queries.py`
- `auth_service.py` — Supabase JWT 검증(JWKS, aud=authenticated) + 탈퇴 재인증. 자체 JWT 발급 없음
- `external_queries.py` — nestlio 전용 조회(멱등 조회, 월 순입금, 계좌 범위 XIRR) · `_settings_queries.py`

**알림 발송 채널 (`notifications/`)**
- `email_service.py` · `email_templates/`(`_shared`·`alerts`·`rebalancing`·`market_signal`·`reports`, `__init__.py` 전체 재노출) · `push_service.py`(폐기 토큰 별도 세션 삭제, 토큰은 기기 단위)

### 그 외 패키지

```
schemas/        Pydantic(라우터 인라인 스키마 금지 — 알림은 schemas/alert.py). rebalancing/ 패키지는 __init__.py 재노출(from app.schemas.rebalancing import X 유지). service_dtypes.py는 서비스 내부 TypedDict
core/
  config.py     Settings(pydantic-settings)
  database.py   async engine/session, Base
  job_runner.py report_job_failure(로그+Sentry 스택) · report_handled_failure(루프 안 삼키는 항목 실패 — 스택 없는 capture, 자격증명 지역변수 보호) · run_per_user(유저별 동시성·실패 격리) — jobs와 알림 서비스 공용. **`except`+`logger.error`만으로는 Sentry에 안 간다**(structlog는 stdlib logging 미경유)
  logging.py    structlog 시크릿 redact + yfinance 404 소음 필터. 계좌번호·이메일은 utils/masking.py.
                **응답·DB·알림에 예외 사유는 str(e) 대신 public_error_message(e)** (SQL 파라미터·URL의 계좌번호 유출 방지)
  cache_store.py in-memory TTL 캐시(LRU 20,000). **프로세스 로컬** — 워커/인스턴스 2개↑면 적중률 급락·무효화 미전파(render.yaml은 단일 전제)
kis/            KIS 클라이언트. **해외 거래소 코드 체계가 둘**: 주문/잔고 NASD/NYSE/AMEX vs 시세 NAS/NYS/AMS.
                KIS는 NYSE Arca ETF(SPY·VOO 등)를 AMEX로 분류 → exchange_master.resolve_kis_overseas_market()로 주문·시세 직전 보정(키움은 무보정)
kiwoom/         키움 클라이언트 (rate limit 4/s, return_code=5 = rate limit)
toss/           토스 Open API. **Open API → IP 관리에 서버 IP 등록 필수**(미등록 403 edge-blocked). 샌드박스 없음, rate 1/s
providers/
  http_client.py broker_request(retry_on_request_error=False)는 주문 접수 4곳 전용 — 응답 유실 시 중복 주문 방지(5xx도 재시도 안 함).
                잔고 연속조회는 상한 20페이지, **상한 도달·연속키 반복 시 부분 목록 대신 raise**(부분 결과는 나머지 보유를 "매도됨"으로 만듦)
  kis_/kiwoom_/toss_/manual_provider.py, _token_cache.py, _retry.py, _overseas_cache.py, _error_mapping.py
  _overseas_name_enrichment.py  해외 이름·시장 보강(7일 캐시). 시장 미확정 시 NASDAQ 폴백 → 키움 주문 stex_tp 오라우팅 위험이라 경고 로그 + 1h만 캐시
utils/
  cache_keys.py       캐시 키 + TTL (휘발성)
  durable_state.py    Postgres AppState KV — 재시작에도 유지할 상태. 다중 프로세스 선점은 claim_durable()(get→set은 경합에 안전하지 않음)
  circuit_breaker.py  KIS/키움/토스 5회→60s, Yahoo/DART/Naver/FDR 5회→120s, FRED 4회→300s (재시작 시 초기화)
  kst.py              today_kst()/now_kst()/kst_day_start() — "오늘 보냈나" 비교는 kst_day_start
  pykrx_util.py       **pykrx 호출은 반드시 `with quiet_pykrx() as stock:` 안에서** — 동시 호출 시 프로세스 크래시(락 직렬화)
  naver_retry.py      Naver 모바일 API는 `naver_get_json` + `except NAVER_FAILURES` → `log_naver_failure`
  currency.py · masking.py · inproc_lock.py(단일 프로세스 전제) · market_hours.py · metrics.py · pnl.py
limiter.py      slowapi. 키는 rate_limit_key(JWT sub / X-Forwarded-For 첫 hop — Vercel→Render 프록시라 client.host는 공용).
                **인증 없이 상태를 바꾸거나 토큰을 받는 라우트는 ip_rate_limit_key + peer_rate_limit_key 두 데코레이터를 겹친다**(tests/test_rate_limit_key.py가 검사)
enums.py        도메인 StrEnum — 매직 스트링 대신
constants.py    DOMESTIC/OVERSEAS_MARKETS, POSITION_STOCK_ASSET_TYPES, BROKER_API_ASSET_TYPES·BROKER_API_DATA_SOURCES(잔고 조회), ORDER_EXECUTABLE_ASSET_TYPES(주문·취소, 토스 제외), is_non_tradable(). **새 브로커는 여기에만 추가**(서비스별 로컬 집합 금지 — 토스 연동 때 7곳 누락)
exceptions.py   AppError 계열(전역 핸들러가 변환) + SyncError 계열
scheduler.py    init_scheduler()의 jobs 스펙 리스트. 예외를 밖으로 던진 잡은 리스너가 스택 없이 Sentry로 보낸다
```

### Jobs (`jobs/`, APScheduler)

| 파일 | 주기 (KST) | 비고 |
|---|---|---|
| `asset_sync.py` | 15:30 intraday + 18:00 daily | 전체 계좌 스냅샷 |
| `exchange_rate_alert.py` / `stock_price_alert.py` | 5분 / 10분 | |
| `rebalancing_alert.py` | 10분(:00·:10…) | 드리프트 알림 |
| `rebalancing_auto_execution.py` | 장중 5분 | AUTO 플랜 생성(실행 안 함). **스케줄 준수**: DRIFT_ONLY/SCHEDULE_ONLY는 `is_auto_schedule_day`일 때만(빠지면 월간 AUTO가 매 거래일 실행). 알림마다 `claim_durable`로 원자적 선점 |
| `rebalancing_plan_buy_execution.py` | 1분 | 대기 지난 매수 leg 실행 |
| `rebalancing_plan_sell_expiry.py` | 15분 | 매도 승인 만료 + stuck leg 마감 |
| `market_signal_alert.py` / `market_signal_daily_digest.py` | 1시간 / 08:30 | 등급 전환 / 요약(옵트인) |
| `tactical_regime_check.py` | 07:40 | 국면 확정·틸트 + 국면/웅덩이 알림. 주문 없음 |
| `dca_cash_shortfall.py` | 18:30 | 적립 자동매수 1~3일 전 예수금 부족 알림. 판정은 `services/dca_cash_shortfall_service.py`(action-items와 공유) |
| `goal_achievement.py` | 18:45 | |
| `monthly_report.py` / `challenge_monthly_wrap.py` | 매월 1일 09:00 / 09:30 | |
| `challenge_deposit_reminder.py` | 매월 25일 09:00 | 옵트인 |
| `year_end_tax_reminder.py` | 11~12월 매주 월 09:00 | 옵트인 |
| `recommendation_drift_alert.py` | 매주 월 09:15 | 옵트인 |
| `token_refresh.py` | 06:00 | 실패는 스택 없는 capture_message(자격증명 지역변수 전송 방지) |
| `startup_warmup.py` | 기동 직후 1회 | 환율·시장신호·JWKS 예열 |
| `cache_sweep.py` / `app_state_sweep.py` | 15분 / 04:10 | 만료 캐시 / durable row 청소 |
| `_job_helpers.py` | — | job 공통 헬퍼(`run_alert_job`·`peak_rss_mb`). 유저별 루프 `run_per_user`·`report_job_failure`는 `core/job_runner.py`(알림 서비스도 쓰므로 core) |

- **새 job**: 파일 생성 → `scheduler.py` `init_scheduler()` jobs 리스트에 `(함수, 트리거, id)` 추가(cron은 `kst(...)` 헬퍼) → `tests/test_scheduler.py` `EXPECTED_JOB_IDS` 갱신.

### 스케줄러 실행 제약 (운영)

- 잡은 전부 웹 프로세스 안 APScheduler(메모리 jobstore). **Render 무료 플랜은 15분 무요청 시 잠들고, 그동안 AUTO 실행 포함 모든 잡이 멈춘다.** `keep-alive.yml`(cron 10분)은 GitHub 스로틀로 실측 2~9시간 간격이라 효과 없음 — 외부 핑(UptimeRobot 등 5분)이나 유료 플랜 필요.
- 재시작 사이 놓친 실행은 복구 안 됨. `misfire_grace_time`(900초)은 살아 있는 동안의 지연만 커버 — 월/주 1회 잡은 서비스 쪽 "오늘 이미 발송" dedup 유지.
- 단일 인스턴스 전제 — 2개↑(무중단 재배포 겹침 포함)면 잡이 중복 실행된다.

### 횡단 관심사

- **현재가**: Yahoo(yfinance) → KIS. yfinance는 `run_in_executor`.
- **USD/KRW**: `utils/currency.get_usd_krw_rate(cache)` → 캐시 없으면 `settings.usd_krw_fallback_rate`. KIS 성공 시 `cache_usd_krw_rate()`. 테스트 patch 경로 `app.utils.currency.cache_usd_krw_rate`.
  - **함정**: fallback(1300)은 평가액 환산용. 환율로 알림 발동·위치 판정을 하면 `fetch_usd_krw(..., allow_fallback=False)`(없으면 0.0) 또는 `get_live_or_cached_usd_krw`의 실값 여부로 거를 것 — 고정값이 실환율로 쓰이면 BELOW 알림 거짓 발동.
- **월별 추이 SQL(`get_monthly_trend`)**: `asset_accounts` JOIN + `is_active = TRUE` 필수(누락 시 비활성 계좌 합산으로 수배 부풀림). 월말 스냅샷 없음 — 해당 월 마지막 sync일 값이 대표값.
- **브로커 예수금**: `deposit_krw`는 **D+2 정산 후 예수금**(키움 `d2_entra`, KIS `prvs_rcdl_excc_amt`) — D+0을 쓰면 매도대금이 빠져 며칠간 총자산이 어긋남. 부재 시 D+0 폴백 + 경고 로그. FULL 매수 예산은 별도(키움 `orderable_krw`, KIS `get_orderable_cash()`). `deposit_usd`는 해외 조회 실패 시 `None`으로 기존 값 유지, 확정 `0.0`일 때만 갱신.
- **인증**: 백엔드는 토큰을 발급하지 않는다. `api/deps.py` `get_current_user`가 Supabase JWKS로 검증만. nestlio도 같은 JWT로 `/external/*`.
- **미들웨어(`main.py`)**: slowapi, CORS, GZip, Request ID, 보안 헤더, 요청 로깅. `RequestValidationError`는 NaN/Infinity를 None으로 바꿔 422(기본 핸들러는 500). 그 외 예외는 `redact_secrets()` 후 500. 백엔드 CSP는 API 응답용 — 실제 프론트 CSP는 `frontend/vercel.json`.

---

## Absolute Rules

**자격증명**: KIS/키움 App Key·Secret, 토스 Client ID·Secret은 `credential_service.encrypt()` 후 저장, 읽을 때 `decrypt()`. 평문 저장·로그 출력 금지.

**금액**: `Numeric(18, 2)` / `Mapped[float | None]`. 해외 `avg_price` 포함 **모든 금액은 KRW 저장**(프론트가 USD × 환율 변환 후 전송).

**SQLAlchemy async**
```python
row = await db.scalar(select(Model).where(...))
rows = (await db.execute(select(Model).where(...))).scalars().all()
db.add(obj); await db.commit(); await db.refresh(obj)
```
- Boolean 필터는 `Model.is_active == True`(E712 제외라 noqa 불필요). 활성 계좌는 `_account_queries`의 stmt 헬퍼 우선.

**FK cascade**: `user_id` → `ondelete="CASCADE"`, `account_id` → `ondelete="SET NULL"`(내역 보존).

**로깅**: `structlog`, 이벤트명 snake_case + key=value — `logger.info("account_synced", account_id=str(account.id), positions=len(positions))`.

**날짜/시각 (KST)**
- 운영 서버는 UTC. 사용자 기준 "오늘"(스냅샷 날짜·연도·dedup)은 `date.today()`/`datetime.now()` 금지 → `app.utils.kst`의 `today_kst()`/`now_kst()`/`KST`.
- 예외: 미국 데이터 소스 기준이 필요한 곳(FRED `realtime_start` 등)은 `economic_indicator_service._fred_today()`(US Central).
- DB 타임스탬프(`created_at` 등)는 `datetime.now(UTC)`.
- `alert_history.alert_type`은 `String(40)` — 새 타입 문자열은 40자 이하(`tests/test_alert_type_length.py`가 검사, 초과 시 조용히 저장 실패).

**HTTP 에러**: 사용자 노출 메시지는 한국어. 서비스는 `app.exceptions`의 `AppError` 하위(`BadRequestError`·`NotFoundError`·`ConflictError`·`UnprocessableError` 등)를 raise — `HTTPException`은 라우터·의존성에서만. 서비스에서 `except AppError: raise`로 다시 올려야 하는 곳(아래 `except Exception`이 502로 덮는 경로)을 놓치지 말 것.

**yfinance**: 동기 라이브러리 → `asyncio.get_running_loop().run_in_executor(None, fn)`. 동시성은 `yahoo_price._yfinance_sem` 재사용(새 세마포어 금지).

**Pydantic v2**: ORM 매핑 스키마는 `model_config = {"from_attributes": True}`. `Optional[X]` 대신 `X | None`.

**계좌 소유권**: account_id를 받는 라우터는 직접 조회 금지 → `get_owned_account`/`get_owned_or_404`(타 유저 계좌는 404로 통일).

**새 라우터/모델**: 라우터는 `api/v1/router.py`에 `include_router()`. 모델은 `app/models/__init__.py`에 import. E2E 순서: 모델 → 스키마 → 서비스 → 라우터 → router 등록 → models/__init__ import → 마이그레이션 → 테스트 → 이 문서 목록 갱신.

**Rate Limiting**: `@limiter.limit("X/minute")`를 달면 시그니처에 `request: Request` 필수.
```python
@router.get("/endpoint")
@limiter.limit("60/minute")
async def my_endpoint(request: Request, ...):
```
