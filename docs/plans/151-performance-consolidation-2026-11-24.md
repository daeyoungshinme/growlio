# 계획 151 — 전체 속도 개선 (중복 계산·중복 호출·불필요 정보 정리)

> 작성 2026-11-24. 상태: 배치 0(#321)·A(#322) 완료, 배치 B 구현. 운영 기준선 수집 대기. 배치 0 → A → B → C → D 순서, 배치별 PR.

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

## 배치 A — 빠른 개선 — 구현 2026-11-24

| # | 내용 | 결과 |
|---|---|---|
| 1 | `/stocks/price`·`prices-batch`(`_price_entries`)가 해외 종목마다 `refresh_usd_krw`(매번 Yahoo) | `get_live_or_cached_usd_krw`(캐시 우선). `/stocks/exchange-rate`는 원래 캐시 우선. `positions.py` 수동 현재가 동기화는 **유지** — 사용자가 누르는 쓰기 경로이고 스냅샷에 남길 환율이라 실시간이 맞다 |
| 2 | 시세 실패 음성 캐시 | 현재가: 별도 키 `price_miss_key`(10분, `TTL_PRICE_MISS`) — 표식이 있으면 Naver·pykrx·Yahoo를 건너뛰고 **KIS는 계속 시도**(계좌마다 결과가 다름). 기간 수익률: 같은 키에 `PRICE_RETURN_MISS`("null", 10분) |
| 3 | TTL | `TTL_TAX_ACTION_ITEMS` 120→900(입력 변경 무효화 전부 확인). `TTL_MONTHLY_TREND`는 **변경 안 함** — 호출부가 대시보드 계산(자체 15분 캐시)과 nestlio뿐이라 늘려도 효과 없음 |
| 4 | 국내 시세 per-ticker 스레드 무제한 | `_domestic_price_sem`(4) — Yahoo 슬롯과 분리(긴 yf 다운로드 뒤에 줄 서지 않게) |
| 5 | 팩터·프론티어가 `_yfinance_sem` 우회 | 조회만 `run_yf_bounded`로. 순수 계산 executor는 그대로 |
| 6 | 죽은 코드 | `dip_buy_calculator.completed_tiers` 삭제, `insight_service` "병렬" docstring 수정. 감사가 지목한 `isRetryableError`는 `shouldRetryQuery`가 쓰므로 **유지** |
| 7 | 네이티브 환율 5분 폴링 | **하지 않음** — 계획134가 "전역 환율 미갱신"을 고치려고 넣은 폴링이고, 백엔드는 캐시 우선이라 요청 비용이 거의 없다 |
| 8 | 홈 묶음 행이 마운트 시 drift-summary | 펼칠 때만 조회(로딩 중 `SkeletonCard`) |
| 9 | `PortfolioManageTab` drift-summary가 `/portfolios` 대기 | 대기 제거(서버가 빈 목록이면 `[]`) |
| 10 | 계좌별 전체 overview까지 24h persist | `PERSIST_SUBKEYS`로 overview는 `lite`·`all`만, gcTime 프리픽스는 `persistQueryPrefixes()`로 같은 범위 |
| 11 | 홈 "데이터 갱신"이 `invalidateSyncData`(27종) | 증권사 동기화가 아니라 다시 받기라 `refetchActiveData` |
| 12 | 환전 계획 다른 기간 프리페치 | **하지 않음** — 프리페치는 124의 즉시 전환, `dataUpdatedAt` 재프리페치는 128 A4(동기화 뒤 다른 기간 탭 옛 달러) 수정이고 신선 캐시는 이미 건너뛴다 |
| 13 | 중복 포매터 | `fmtUsdWhole` 2중 정의 → `utils/format.ts`, 환율 알림 화면 `toLocaleString` → `fmtFxRate`. `PendingPlanRow` 로컬 `fmtUsd`(쉼표+센트 고정)·`ChartTrendList` `fmtNum`은 같은 출력의 공용 함수가 없어 유지, `ExchangeRateAlertSection`의 쿼리는 `useAlertCrud`가 같은 키·함수로 받아 캐시 공유라 유지 |

## 배치 B — 홈 요청 통합 — 구현 2026-11-24

| # | 내용 | 결과 |
|---|---|---|
| 1 | 홈이 숫자 몇 개 때문에 lite overview·적립 분석을 따로 받음 | `/dashboard`에 `stock_pnl`·`goal_expected_month` 추가, 홈·부팅 프리페치 7→5. **주식 평가손익은 계획과 달리 `build_asset_totals`가 아니라 대시보드 계산 안에서 lite overview(`in_total`, 30분 캐시·계좌관리 탭과 공유)를 불러 쓴다** — 두 엔진이 스냅샷 계좌에서 다르게 계산해(overview는 스냅샷 `invested_amount`·`unrealized_pnl`, 총자산은 포지션 현재가 재평가) 바꾸면 히어로와 자산 탭 숫자가 어긋난다. 엔진 통일은 C. 목표 진행률은 원래 같은 식(`goal_achievement_pct`)이라 예상월만 `dca_service.compute_goal_expected_month`(goal_timeline과 같은 계산, 투영 곡선·월별 실적 없이 — 동등성 테스트)로. 부가 조회 실패는 격리하되 **DB 오류는 rollback 없이 올린다**(같은 세션을 쓰는 챌린지 루프 ORM 만료 방지). 대시보드 요약의 미사용 `monthly_trend` 계산 제거 — 월간 리포트가 직접 조회. `dca-analysis`는 persist 대상에서 제외(홈 미사용, 월별 투영 배열이 큼) |
| 2 | `/dashboard`가 콜드 배당 체인 대기 | **보류** — 종목별 배당 캐시가 24h라 외부 체인은 하루 1회 수준. 분리하려면 백그라운드 계산 + 짧은 캐시가 필요해, 배치 0의 `dashboard_summary_timing.dividends_ms` 실측을 보고 결정 |
| 3 | 딥링크 진입에도 홈 프리페치 | `isHomeEntryPath` — `/`·`/dashboard`·모르는 경로일 때만(부팅 2곳). 로그인 직후는 홈으로 가므로 그대로 |
| 4 | 내비 배지가 목록 다음에 `/challenges/summary` 추가 요청 | `useChallengeNudge`가 목록(`this_month_satisfied` 등)으로 같은 판정. 백엔드 엔드포인트는 구버전 앱 호환으로 유지 |

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
