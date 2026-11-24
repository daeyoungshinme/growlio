# 계획 151 — 전체 속도 개선 (중복 계산·중복 호출·불필요 정보 정리)

> 작성 2026-11-24. 상태: 배치 0 구현(운영 기준선 수집 대기). 배치 0 → A → B → C → D 순서, 배치별 PR.

## Context

사용자 요청: 프로젝트 전체 속도 개선 — 불필요·중복 코드 통합, 중복 정보 통합, 불필요한 API 호출 정리.
72·102·125·126에서 커넥션 반납·single-flight·lazy 로딩·enabled 게이팅은 이미 정리됨(프론트 번들·숨김 UI 게이팅은 문제 없음 확인).
남은 병목은 **네트워크보다 백엔드의 "같은 보유 종목 평가를 엔드포인트마다 따로 재계산"**:

- 홈 콜드 로드 ≈ 10~12 요청이 동시에 떠서 `build_asset_totals`(무캐시)·`build_portfolio_overview`(single-flight 없음)·`get_drift_summaries`(무캐시)를 각자 돌림 → 풀(5+2) 경쟁.
- 총자산 계산 구현이 6갈래(`composition_calculator.build_asset_totals`, `portfolio_service.build_portfolio_overview/_calc_account_amounts/compute_total_assets_krw`, `risk_service._load_positions_and_cash`, tax, `dividend/orchestrator._collect_positions`) — 스냅샷 없는 증권계좌 처리 규칙이 서로 달라 홈 총액과 개요 총액이 어긋날 수 있음.
- `/dashboard`가 콜드 캐시에서 외부 배당 체인(Naver→Yahoo→KIS→FDR→DART)을 기다린 뒤 응답하고, 응답 스키마가 버리는 필드(`monthly_trend`·`dividend_monthly_breakdown`·`annual_dividends_received`)까지 계산.

산출물: `docs/plans/151-performance-consolidation-2026-11-24.md`(이 내용) + `docs/plans/README.md` 행 추가. 배치별 PR(스택).

## 원칙
- 배치 0 계측을 먼저 해서 전후를 `http_request duration_ms`(이미 있는 로그)로 비교한다 — 지금까지 실측 없이 "구현(실측 대기)"으로 끝난 계획이 많았음.
- `_yf_download_lock`(yahoo_price.py:39)은 계획79의 동시 호출 경쟁 수정이라 **풀지 않는다**. 대신 다운로드 횟수를 줄인다.
- 결과값이 바뀌는 통합(배치 C)은 기존 값과 동등성 테스트를 먼저 쓰고 진행.

---

## 배치 0 — 계측 (작음) — 구현 2026-11-24

조사 결과 요청 단위 `http_request duration_ms`(+Prometheus 히스토그램)는 있었지만 **요청당 DB 쿼리 수**와 **함수 단계별 시간**이 없어 N+1·중복 계산을 로그로 확인할 수 없었다. 서비스 단계 로그도 request_id가 묶이지 않아 요청과 이어 볼 수 없었다.

구현
- `app/core/request_metrics.py` — ContextVar 카운터. `core/database.py` `after_cursor_execute`가 쿼리마다 더하고, `main.py` `log_requests`가 `http_request`에 `db_queries`·`db_ms`를 싣는다(SQLAlchemy가 드라이버 greenlet에 `gr_context`를 넘겨 이벤트에서도 같은 카운터, gather 분기도 공유).
- `add_request_id`가 `structlog.contextvars.bind_contextvars(request_id=…)` — `*_timing` 줄에 request_id가 붙는다.
- `app/core/timing.py` `StepTimer`(단계 `*_ms` + `total_ms` + 구간 `db_queries`)·`elapsed_ms`. goal 추천의 로컬 `_mark`·fx_plan의 `_elapsed_ms` 중복을 이것으로 통합.
- 계측 이벤트: `dashboard_summary_timing`(init·monthly_trend·dividends·asset_totals·xirr), `asset_totals_timing`(무캐시 — 호출 횟수 확인용), `portfolio_overview_timing`(캐시 미스만, lite·scope·accounts), `drift_summary_timing`(prelude·market·portfolios), `action_items_timing`(소스 8개별), 기존 `goal_recommendation_timing`·`fx_plan_timing`.
- `backend/scripts/summarize_timing_logs.py` — Render 로그 텍스트 → 경로별 p50/p95/max·평균 db_queries, `*_timing` 단계별 분포, `--by-request`로 한 요청 안에서 2번 이상 돈 계산.

기준선 수집 절차(배포 후, 사용자)
1. 배치 0을 main에 머지해 Render 배포.
2. 앱을 평소처럼 사용(콜드 시작 1회 이상 포함 — 15분 이상 쉰 뒤 홈 진입) 후 Render Logs를 텍스트로 저장.
3. `cd backend && uv run python scripts/summarize_timing_logs.py render.log --by-request` 결과를 아래 표에 붙인다. 이후 배치마다 같은 절차로 비교.

| 지표 | 기준선 | A 후 | B 후 | C 후 |
|---|---|---|---|---|
| `/api/v1/dashboard` p50/p95 · db_queries | | | | |
| `/api/v1/dashboard/action-items` p50/p95 · db_queries | | | | |
| `/api/v1/portfolio/overview` p50/p95 | | | | |
| `/api/v1/rebalancing/drift-summary` p50/p95 | | | | |
| `asset_totals_timing` 요청당 횟수 | | | | |
| `portfolio_overview_timing` 미스 횟수/요청 | | | | |

## 배치 A — 빠른 개선 (리스크 낮음, 1 PR)
백엔드
1. `/stocks/price`·`/stocks/prices-batch`(`api/v1/stocks.py:95,135`)와 `positions.py:214`의 `refresh_usd_krw`(매번 Yahoo) → `get_live_or_cached_usd_krw`(미스일 때만).
2. 시세 실패 음성 캐시: `price_service.py:149` 성공만 캐시 → 짧은 음성 TTL(10분, 배당 음성 캐시 패턴 재사용). `get_historical_returns`(`price_service.py:217-240`, 125 B6 잔여)도 동일.
3. TTL 상향(무효화 훅이 이미 있는 것만): `TTL_TAX_ACTION_ITEMS` 120→900, `TTL_MONTHLY_TREND` 300→900 (`utils/cache_keys.py`). 동기화 시 무효화 경로 존재 재확인.
4. 국내 시세 per-ticker gather 동시성 제한(`price_service.py:107-110`, `asyncio.Semaphore`) — 기본 스레드풀 포화로 인증(`deps.py:30` to_thread)까지 줄 서는 것 방지.
5. `portfolio_optimizer.py:249`·`factor_service.py:209,252`가 `_yfinance_sem`을 우회 → 기존 세마포어 경유로 통일.
6. 죽은 코드: `dip_buy_calculator.completed_tiers`, `insight_service.py:72` 잘못된 "병렬" docstring.

프론트
7. 환율 5분 폴링을 네이티브에서 끔(`api/queryOptions.ts:54`, 다른 폴링과 같은 조건 재사용).
8. 홈 `ActionItemsCard.tsx:20-22,47` drift-summary를 그룹 행 **펼칠 때**만 조회.
9. `PortfolioManageTab.tsx:111-114` drift-summary의 `/portfolios` 대기 게이트 제거(빈 배열 반환 확인됨).
10. 영속화 범위 축소: `shouldPersistQuery`(`constants/queryConfig.ts:39`)가 `["portfolio-overview", accountId]` 전체 응답까지 24h 저장 → `lite`·`all`만.
11. 데스크톱 "데이터 갱신" 버튼(`DashboardPage.tsx:89-96`)이 실제 동기화를 안 한다면 `invalidateSyncData`(27종) → `refetchActiveData`(125 D2와 동일). 동기화 버튼이면 유지.
12. `FxPlanCard.tsx:197-204` 다른 기간 프리페치를 `dataUpdatedAt` 변화마다가 아니라 마운트당 1회/세그먼트 hover·focus 시로.
13. 중복 포매터 정리: `PendingPlanRow.tsx:95` 로컬 `fmtUsd`→`fmtUsdPrice`, `fmtUsdWhole` 2중 정의(`FxPlanCard.tsx:55`·`FxExtraNeedsSection.tsx:35`)→`utils/format.ts`, `ExchangeRateAlertSection.tsx` `toLocaleString`→`fmtFxRate`, `ChartTrendList.tsx:13` `fmtNum`. `ExchangeRateAlertSection.tsx:41-48` 쿼리 재정의→`exchangeRateAlertsQuery`. 미사용 `isRetryableError`(`api/retryPolicy.ts`) 삭제.

## 배치 B — 홈 요청 통합 (중간, 1 PR)
1. `/dashboard` 응답에 홈 히어로용 `total_stock_krw`·`unrealized_pnl_krw`(+기존 `stock_return_pct`)와 목표 진행 `goal_progress_pct`(dca `goal_timeline.current_progress_pct`와 같은 정의) 추가 → `HeroSummaryCard.tsx:149-162`·`InvestmentGoalCard.tsx:48-50`이 `/dashboard`만 사용. 홈에서 `/portfolio/overview?lite`·`/invest/dca-analysis` 조회 제거(계좌관리 탭의 lite 사용은 유지), `prefetch.ts`에서도 제거(7→5).
   - 주의: 두 엔진 총액 규칙 차이(스냅샷 없는 증권계좌) — 히어로 수치가 바뀌면 배치 C의 규칙 통일과 함께 판단. 값 차이 있으면 사용자 확인.
2. `/dashboard` 크리티컬 패스에서 배당 분리: `asset_aggregator.py:217` `get_dividend_summary` 대기 제거 → 배당 캐시가 있으면 쓰고 없으면 `null`(목표 칩은 `/dividends/summary` 폴백 또는 다음 갱신). 응답이 버리는 `monthly_trend`·`dividend_monthly_breakdown`·`annual_dividends_received` 계산은 `jobs/monthly_report.py` 전용 함수로 분리.
3. 부팅 프리페치는 진입 경로가 `/`·`/dashboard`일 때만(`main.tsx:83`, `App.tsx:118-121`) — 푸시·메일 딥링크 진입 시 홈 무거운 요청이 해당 페이지와 경쟁하지 않게.
4. 챌린지 배지: `/challenges/summary` 추가 요청 대신 `/challenges` 목록의 `progress.this_month_satisfied`로 `needs_attention` 계산 가능한지 확인 후 전환(`useNavBadges.ts:47-50`, `useChallengeNudge.ts`).

## 배치 C — 백엔드 공용 계산 (큼, 1~2 PR, 동등성 테스트 선행)
1. **원천 보유 데이터 1회 조회·캐시**: 사용자별 "활성 계좌 + 최신 스냅샷 + 스냅샷 포지션 + 현재 포지션" 로더를 하나로(기존 `prefetch_accounts_snapshot_positions` 확장), 대시보드 캐시와 같은 무효화 그룹(`cache_invalidation`)에 묶음.
   - `build_asset_totals`·`build_portfolio_overview`(lite/full × all/in_total 4변형)·`compute_total_assets_krw`가 이 결과에서 파생 → 변형별 DB 재조회 제거, lite는 full에서 파생.
   - 스냅샷 없는 증권계좌 규칙을 하나로 통일(현재 `composition_calculator.py:136-150` vs `portfolio_service.py:76-85`). `portfolio_service.py:69-82`는 `utils/pnl.py` 호출로.
2. `build_portfolio_overview`에 single-flight(`get_dashboard_summary` 패턴 재사용).
3. `get_drift_summaries` 짧은 결과 캐시(2~5분, 포지션·목표 변경 무효화) — `/dashboard/action-items`·`/rebalancing/drift-summary`가 공유. drift·insights 포트폴리오별 overview 루프(N+1, 125 B3)를 C1 결과 슬라이싱으로.
4. DCA(`dca_service.py:112`)·TARGET_VALUE 챌린지(`challenge_service.py:228`, 챌린지별 N+1)·`/invest/goal-feasibility`(`invest.py:83`, 무캐시)가 캐시된 대시보드 요약/C1 결과의 `investable_assets_krw` 사용.
5. 리스크·팩터·프론티어·전술이 같은 종목(QQQ·SPY·^GSPC·USDKRW=X) 일봉을 따로 받음 → 종목·거래일 단위 종가 캐시(기존 `daily_returns_key` 확장)로 공유해 `_yf_download_lock` 대기 감소.

## 배치 D — 요청당 오버헤드 (중간, 선택)
- `get_current_user`(`deps.py:56`) 사용자 행 60초 캐시(JWT `sub` 키, 탈퇴·비활성 시 무효화) → 요청마다 SELECT+COMMIT 제거.
- `pool_pre_ping` 제거 검토(`pool_recycle=280` 존재) — Supabase pooler 끊김 재현 시험 후 결정.
- Naver `requests.get`(`utils/naver_retry.py:52`)→ `requests.Session`, 검색·FRED·DART의 매 호출 `httpx.AsyncClient` 생성 → `providers/http_client.py` 공용 클라이언트.
- 중복 인덱스 정리(`idx_snapshots_user_id`, `idx_asset_snapshots_account_date`) — 마이그레이션 필요(수동 적용), 효과 작으면 보류.

## 하지 않음 / 보류
- yfinance 전역 락 해제(계획79 경쟁 버그 재발).
- BaseHTTPMiddleware 4겹 → 순수 ASGI 통합(효과 대비 위험, 배치 0 수치 보고 판단).
- 번들: 이미 lazy·청크 분리 양호. `DividendTab` lazy 정도만 여유 있으면.

## 핵심 파일
- 백엔드: `services/portfolio/{composition_calculator,portfolio_service,asset_aggregator}.py`, `services/rebalancing/drift_summary_service.py`, `services/action_items_service.py`, `services/insight_service.py`, `services/dca_service.py`, `services/challenge_service.py`, `services/market_data/{price_service,yahoo_price,market_data_fetcher}.py`, `utils/cache_keys.py`, `api/v1/{stocks,positions,dashboard}.py`, `schemas/dashboard.py`, `api/deps.py`
- 프론트: `api/{prefetch,queryOptions}.ts`, `hooks/{useDashboardData,useNavBadges}.ts`, `components/dashboard/{HeroSummaryCard,InvestmentGoalCard,ActionItemsCard}.tsx`, `constants/queryConfig.ts`, `pages/DashboardPage.tsx`, `main.tsx`, `App.tsx`

## 검증
- 배치마다: `uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pytest`(최종 `--cov` 91%), `D:\project\growlio\frontend`(대문자)에서 `npm run lint -- --max-warnings 0 && npm run format:check && npm run typecheck && npm run test`.
- 배치 B·C: 기존 값 동등성 테스트 — 같은 픽스처로 변경 전후 `/dashboard`·overview(4변형)·drift-summary·dca 결과 일치(규칙 통일로 의도적으로 달라지는 케이스는 테스트에 명시).
- 캐시 추가 항목마다 무효화 테스트(동기화·포지션 저장·계좌 삭제 후 새 값).
- `bash dev.sh`로 홈·자산·리밸런싱 진단을 열어 네트워크 탭 요청 수 비교, 백엔드 `duration_ms` 로그로 배치 0 기준선과 비교해 계획서에 기록.
- 완료 시 `docs/plans/README.md` 행, 파일 추가·삭제가 있으면 backend/frontend `CLAUDE.md` 목록 갱신.
