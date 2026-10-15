# 백엔드 구조 개선 계획 — 정리·병합·레이어 재설계 (2026-10-14)

## Context

기존 감사(plans 1~51)는 TODO·noqa·죽은 함수 같은 **미시적 부채를 거의 소진**했다(plan 51: "고전적 부채는 거의 남지 않았다"). 이번 요청은 백엔드의 **구조·설계** 문제를 대상으로 한다. 조사 결과 주된 문제는 다음 다섯 가지다.

1. `services/`가 65개 모듈이 평면으로 놓인 구조다(14k줄).
2. 같은 계산이 여러 곳에 구현돼 있다: 드리프트·손실수확·MVO·스냅샷 조회·KIS/키움 매도 clamp.
3. 라우터에 비즈니스 로직이 들어 있다: assets·positions·portfolios·stocks·rebalancing.
4. 알림 발송 경로가 4갈래이고, 잡 골격이 5번 복제돼 있다.
5. 미사용 config·컬럼·엔드포인트와 alembic 109개 이력이 남아 있다.

조사 중 **실버그도 확인했다**. `POST /transactions`가 `account_id` 소유권을 검사하지 않는다.

사용자 결정은 다음과 같다.
- 패키지 재편은 **단계적**으로 한다.
- 설정 API는 **`PATCH /settings` 하나로 통합**한다.
- 다음 4가지는 **모두 포함**한다: alembic squash, 미사용 컬럼 드롭, 알림 병합(M9), 배당월 override 제거.

**실행 첫 단계:** 이 계획을 `docs/plans/52-backend-restructure-2026-10-14.md`로 옮기고 `docs/plans/README.md`에 행을 추가한다. 각 배치는 **단독 브랜치/PR**로 하고, 끝날 때마다 README 상태를 갱신한다. 배치 시작 전에는 `git status`/`git diff`로 동시 세션 변경이 있는지 확인한다.

---

## 배치 0 — 실버그 (최우선, 저위험)

| # | 내용 | 파일 |
|---|---|---|
| 0-1 | `POST /transactions`에 소유권 검사를 추가한다. `req.account_id`가 있으면 `get_owned_account`로 확인한다(trades.py:88과 같은 방식) | `api/v1/transactions.py:56-79` |
| 0-2 | 계좌 생성과 batch-target-portfolio에 `invalidate_asset_account_caches`가 빠져 있어 추가한다 | `api/v1/assets.py:191-230, 449-475` |
| 0-3 | composite-signal 토글 후 리밸런싱 분석 캐시(`diagnosis_context`)가 stale 상태로 남는다. 무효화를 추가한다 | `api/v1/settings.py:412`, `api/v1/rebalancing.py:144-159` |
| 0-4 | `usd_rate or 1` 폴백 때문에 환율 조회에 실패하면 USD 예수금이 1:1로 합산된다. 실패 시 스냅샷 갱신을 건너뛰거나 마지막 환율을 쓴다 | `api/v1/positions.py:219` |
| 0-5 | `account_id: str`을 `uuid.UUID()`로 수동 파싱해 잘못된 값이 500을 낸다. 타입 `UUID` 파라미터로 바꿔 422가 나게 한다 | `portfolio_analysis.py:30,49`, `dividends.py:36,53,75`, `tax.py:26,45,75` |
| 0-6 | `monthly_report` 잡에 dedup이 없어 재시작·misfire 때 중복 발송될 수 있다. `durable_state` 키를 추가한다. 배치 E에서 병합하더라도 선행한다 | `jobs/monthly_report.py` |

각 수정에는 **회귀 테스트**를 붙이고, 그 테스트가 수정 전 코드에서 실패하는지 확인한다.

### 배치 0 구현 결과 (2026-10-14, 브랜치 `refactor/backend-plan52-batch0-a`, PR #126)

| # | 결과 |
|---|---|
| 0-1 | **수정**. `account_id`가 있으면 `get_owned_account`(활성 계좌만)로 확인한다. 계좌 삭제가 soft delete이고 프론트 거래 폼도 활성 계좌만 보여주므로 trades와 같은 기준이다 |
| 0-2 | 계좌 생성만 **수정**. batch-target-portfolio는 **불필요로 정정**했다. `target_portfolio_id`를 담는 캐시 응답은 고아 `GET /assets/{id}`(`account_detail_key`, 배치 A 삭제 대상)뿐이다 |
| 0-3 | **수정**. `invalidate_rebalancing_analysis_cache_all`을 호출한다. drift-summary와 action-items는 캐시가 없어 대상이 아니다 |
| 0-4 | **실버그 아님으로 정정**. `fetch_usd_krw`는 실패해도 캐시 값이나 `usd_krw_fallback_rate`(1300)를 돌려주므로 `usd_rate or 1` 분기에 도달하지 않는다. 가독성 정리는 배치 B5(스냅샷 재계산 추출)에서 같이 한다 |
| 0-5 | **수정**. 8개 라우트를 `uuid.UUID | None` 쿼리로 바꿨다. 프론트 호출부는 모두 빈 값을 보내지 않는다(`|| undefined`·조건부 params) |
| 0-6 | **수정**. `monthly_report_sent_key(user, YYYY-MM)`(45일 TTL)를 발송 전에 조회하고, 성공 시 AlertHistory와 같은 커밋으로 기록한다 |

회귀 테스트 13개를 추가했다(0-5는 parametrize 8개). 모두 수정 전 코드에서 실패하는 것을 확인했다.

검증: 백엔드 **2624 passed**(기준선 2610 → +14), 커버리지 90.99%. ruff·format·mypy 클린. 프론트는 변경하지 않았다.

## 배치 A — 삭제 (죽은 코드·불필요 기능)

- **고아 엔드포인트 3개**
  - `GET /assets/{account_id}`와 그 전용 캐시 `account_detail_key`
  - `GET /transactions/{tx_id}`
  - `GET /challenges/{challenge_id}`
- **종목별 배당월 override 기능 전체 제거**
  - 백엔드: `/dividends/ticker-settings*` 3개 라우트(`dividends.py:88-`), `ticker_settings_service`, `_dividend_queries.load_user_dividend_overrides`와 그 소비처(배당 계산)
  - 프론트: `api/dashboard.ts:64-73` 래퍼, "수동" 배지 3곳
  - `user_ticker_settings` 테이블에 다른 용도가 없으면 배치 G에서 드롭한다. 실행 시점에 확인한다.
- **미사용 config:** `app_secret_key`, `supabase_jwt_secret`, `fmp_api_key`(`core/config.py:14,25,66` 및 `:97` 검증)
  - `render.yaml:15`, `.github/workflows/ci.yml:41`, `backend/.env.example:3,25` 주석도 함께 정리한다.
- **호환 별칭·잔재**
  - `asset_aggregator.py:36-40` 테스트 호환 별칭 5개 → 테스트가 공개 이름을 쓰도록 바꾼다.
  - `cache_store.ping()`
  - `invalidate_account_caches` 별칭(`cache_keys.py:533`)
  - `economic_indicator_service.sync_calendar_to_cache` 단일 호출 래퍼
- **KIS 사용자 단위 토큰 promote 경로**(`kis/auth.py:~140-192`): 제거된 전역 자격증명의 잔재다. 운영 DB에 `account_id IS NULL` 행이 0건인지 확인한 뒤 제거한다.
- **stale 주석:** `models/asset.py:42-44,65`(TOSS 누락, 전역 자격증명 언급)
- **프론트 중복 클라이언트:** `/dividends/by-ticker` 2개, `/portfolio/overview` 래퍼 3개를 1개씩으로 줄인다.

### 배치 A 구현 결과 (2026-10-14, 같은 브랜치)

| 항목 | 결과 |
|---|---|
| 고아 GET 3개 | **삭제**. 계좌 상세 캐시(`account_detail_key`, `TTL_ACCOUNT_DETAIL`)는 지우기만 하는 키가 되므로 함께 제거했다(자격증명 삭제·계좌 동기화 쪽 무효화 포함). 그 결과 `invalidate_asset_account_caches`의 `account_id` 인자와 `sync_account_now`의 `user_id` 인자가 쓰이지 않게 돼 함께 뺐다. 소유권 테스트 3개(챌린지, 보안 2)는 DELETE·`GET /assets/{id}/positions`로 대상을 옮겨 유지했다 |
| 배당월 override | **전체 제거**: 라우트 3개, `ticker_settings_service.py`, `load_user_dividend_overrides`, fetcher·calculator·orchestrator·overview_enrichment의 `overrides`/`override_months`, 응답 필드 `dividend_months_is_manual`. 프론트에서는 래퍼 2개, 타입 필드, "수동/자동" 배지(모바일)와 "배당월 설정" 열(데스크톱), 칩 파란 톤, `dividendFreqInfo`의 `isManual` 인자를 제거했다. PUT은 저장 후 24시간 배당 캐시도 비우지 않는 반쯤 연결된 상태였다. **`UserTickerSettings` 모델과 테이블은 배치 G에서 드롭한다** |
| 미사용 config 3개 | **삭제**: `config.py`, `render.yaml`, CI, `.env.example` 2개, conftest, `backend/CLAUDE.md`. 설정이 `extra="ignore"`이므로 Render에 남은 환경변수는 무해하다 |
| 호환 별칭·잔재 | **삭제**: `asset_aggregator` 별칭 5개(운영 코드도 별칭으로 호출하고 있었다. 테스트 patch는 같은 모듈의 공개 이름으로, import는 정의 모듈 `composition_calculator`로 옮겼다), `invalidate_account_caches`, `cache_store.ping`, `sync_calendar_to_cache`(`get_calendar_events`에 흡수) |
| stale 주석 | **수정**: 값 목록 대신 `app.enums.AssetType`/`DataSource`를 가리키게 했다. "전역 자격증명 폴백" 문구 3곳도 고쳤다 |
| 프론트 중복 클라이언트 | `api/dashboard.ts`의 `fetchDividendByTicker`/`TickerDividendItem`(테스트만 사용)을 **삭제**했다. `/portfolio/overview` 래퍼 3개는 일반·계좌별·`lite`로 용도가 달라 **유지(정정)** |
| KIS 사용자 단위 토큰 promote | **제외(정정)**. 살아 있는 기능이다. 자격증명 확인 단계에서 발급한 토큰을 계좌 생성 시 옮겨 KIS 토큰 발급 속도 제한을 피한다(`assets.py` create_account) |

검증: 백엔드 **2607 passed**(삭제 기능 테스트 17개 제거), 커버리지 91.13%. ruff·format·mypy 클린. 프론트 **127 files / 1667 passed**, tsc·eslint·prettier·build 클린.

## 배치 B — 중복 병합 (같은 로직 단일 출처화)

| # | 중복 | 통합 방향 |
|---|---|---|
| B1 | `insight_service._check_rebalancing_opportunity`(:149-235)가 드리프트를 하드코딩 5/10%p로 재계산한다. `_check_tax_loss_harvest`(:243)도 손실수확을 재구현하고 private `tax_service._get_rates`에 접근한다 | `rebalancing/drift_summary_service.get_drift_summaries`와 `tax_action_service.build_loss_harvest_actions`를 재사용한다. 그러면 홈 인사이트와 "지금 할 일"이 서로 모순되지 않는다 |
| B2 | MVO 공분산 블록이 4곳(`portfolio_optimizer:77,166`, `goal_portfolio_optimizer:386,549`)에 있고 `_MIN_RETURN_DAYS`와 유효심볼 필터도 중복이다 | `services/mvo_core.py` 하나로 모은다(공분산·필터·상수). 두 optimizer는 목적함수만 남긴다 |
| B3 | `_execute_kiwoom_sells_with_clamp`와 `_execute_sells_with_clamp`는 인자만 다른 복사본이다(diff로 확인) | 공통 `_sell_clamp.py`를 만들고 `BrokerOrderAdapter`(get_domestic_balance / get_overseas_balance / place_order 콜러블)로 파라미터화한다. 키움이 `app.kis.order.is_overseas_market`을 import하던 것도 공용 위치로 옮긴다. **실자금 경로이므로 기존 executor 테스트를 전부 그대로 통과시켜야 한다**. 해외 보유수량 키는 계획 55 A1 이후 브로커별로 다르다(키움은 잔고 market이 "US" 센티널이라 ticker 단독, KIS는 실제 거래소명이라 `ticker:market`) — 공용화 시 어댑터가 키 함수를 주입하게 한다 |
| B4 | 스냅샷/포지션 조회가 흩어져 있다. "최신 스냅샷 JOIN 활성계좌"가 2곳, 수기 포지션(`snapshot_id IS NULL`)이 5곳, 계좌 최신 스냅샷이 같은 파일 안에 2곳 있다 | `_position_queries` + `_snapshot_queries` + `position_aggregator`를 `queries/positions.py`(배치 F 이후 위치)로 합치고 5곳을 교체한다 |
| B5 | 입금 변경 후 "오늘 스냅샷 재계산" 블록이 `assets.py:251-342`와 `external.py:313-331`에 복붙돼 있다 | `snapshot_service.recompute_today_snapshot(account)`로 추출한다. `positions.py` save/sync의 합계·스냅샷 공식도 같은 함수를 쓴다 |
| B6 | 환율·종목가 알림 라우터가 약 70% 중복이다. 스키마 validator, create 핸들러, limit/캐시 정책이 불일치한다 | `_alert_crud`를 list/create까지 확장하고 공통 Base 스키마를 `schemas/alert.py`로 옮긴다. 페이지네이션·캐시 정책을 통일한다 |
| B7 | `rebalancing_alerts.py`에서 AGGREGATE와 PER_ACCOUNT 분기가 중복이다(:152-258 vs :278-381). 20필드 수동 매퍼도 있다 | scope 파라미터로 핸들러 본문을 공유하고, 매퍼는 `from_attributes`로 바꾼다 |
| B8 | `RebalancingPlanLegSummary` 빌더가 `rebalancing_plan.py:32-58`과 `rebalancing_plan_public.py:40-76`에 2개 있다 | 서비스 함수 하나로 합쳐 "actionable" 판정을 단일화한다 |
| B9 | `invalidate_asset_account_caches`가 goal 키 3개를 인라인으로 지운다(`cache_keys.py:510-512`) | `invalidate_goal_recommendation_caches`를 호출한다 |
| B10 | `goal_feasibility`(46줄)와 `trend_calculator`(48줄)가 단일 함수 모듈이다 | 각각 `goal_return_solver`와 `returns_calculator`에 흡수한다 |

## 배치 C — 레이어 정리 (라우터 → 서비스, 의존 방향)

- **라우터의 비즈니스 로직을 서비스로 옮긴다** (우선순위 순)
  1. `assets.update_account`/`create_account` → `asset_service`(B5와 연계)
  2. `portfolios.create/update` 항목 재구성, M:N diff, reorder → `portfolio_crud_service`
  3. `stocks.py:128-302` 가격 폴백 체인과 배치 해석 → `price_service.resolve_prices`. private import(`_price_via_kis`, `_search_naver`, `_has_korean`)는 없앤다
  4. `rebalancing.analyze_portfolio`(:68-160)와 `expected-metrics`의 포트폴리오 로드·필터 → 서비스
  5. `rebalancing_execution.py:176-232` 결과 집계
  6. `external.py:94-118` N+1(계좌별 `get_latest_snapshot`) → 배치 조회
- **역방향 의존을 없앤다**
  - `action_items_service`가 `jobs.dca_cash_shortfall`을 import한다 → `find_dca_cash_shortfalls`를 `dca_service`로 옮긴다.
  - `sync_all_service`가 `jobs.asset_sync._sync_accounts`를 import한다 → 서비스로 옮기고, 잡은 서비스를 호출만 한다.
  - `utils/currency.py:41`이 services를 lazy import한다 → 환율 fetch를 주입하거나 위치를 옮긴다.
- **순환 import 1건을 해소한다** (`kis/auth.py` ↔ `credential_service`)
  - `credential_crypto.py`(encrypt/decrypt 순수 함수)와 `broker_credentials.py`로 나눈다. `broker_credentials.py`는 verify·delete·`get_kis_user_credentials`와 기존 `asset_credential_service`를 합친 것이다.
- **모듈 경계를 넘는 private import를 정리한다:** 공개 API로 승격하거나 경계 안으로 이동한다.
  - `_upsert_snapshot`(4곳)은 `upsert_snapshot`으로 승격한다.
  - 나머지: `tax_service._get_rates`/`_OVERSEAS_MARKETS`, `goal_portfolio_optimizer._optimize_goal_portfolio`, `diagnosis_service._build_tax_preview`, `alert_check._mark_composite_alert_sent_today`
  - 반대로 같은 모듈 안에서만 쓰는 public 함수는 private으로 바꾼다(조사 목록 기준).
- **불필요한 lazy import(약 120개)를 정리한다:** 순환이 없는 것만 top-level로 올린다.
  - ⚠️ **patch 함정:** `send_push_to_user`/email sender처럼 lazy import 덕분에 patch가 먹던 곳은, 올리는 순간 patch가 **에러 없이 무력화된다**. 해당 테스트의 patch 대상을 사용처 모듈 경로로 바꾸고, 바꾼 뒤 테스트가 실제로 mock을 타는지(assert_called) 확인한다.
- **스키마·응답 규약을 통일한다**
  - 라우터 inline Pydantic 34개를 `schemas/settings.py`·`schemas/alert.py`·`schemas/stock.py`·`schemas/external.py`로 옮긴다.
  - `response_model`이 없는 49개 라우트에 모델을 붙인다. 프론트 타입과 대조한다.
- **의존성 스타일을 통일한다**
  - cache는 `CacheStore = Depends(...)` 하나로 쓴다.
  - `get_db`는 `app.api.deps`에서만 가져온다.
  - 소유권 확인은 `get_owned_or_404`/`get_owned_account` 2종으로 수렴한다(raw select+404 제거).
  - 페이지네이션은 `PaginationDep`으로 바꾼다: `assets.py:92`, `rebalancing_plan.py:81`, `rebalancing_execution.py:162`, alerts/history.
  - 누락된 `@limiter.limit`을 보강한다: assets 7개, positions 2개.
  - 캐시 무효화는 쓰기 서비스 함수 안으로 옮긴다(transactions/external/trades의 무효화 불일치 해소).

## 배치 D — 설정 API `PATCH /settings` 단일화

- 백엔드:
  - `SettingsPatch`(모든 필드 Optional) 하나와 **필드→무효화 훅 스펙 테이블**을 만든다. goal 관련 필드는 goal 캐시를, composite 필드는 분석 캐시를 무효화한다.
  - 검증 규칙(daily-cap 범위, income-bracket enum 등)은 스키마 validator로 옮긴다.
  - `get_settings`(:229-282) 매핑은 `SettingsResponse.model_validate`로, `update_goal`의 `if not None` 체인(:323-344)은 `model_dump(exclude_unset=True)`로 바꾼다.
- 프론트: settings API 클라이언트를 `patchSettings(partial)`로 바꾸고 호출처를 교체한다.
- 기존 PUT 7개와 단일필드 setter(income-bracket, auto-rebalancing-daily-cap 등)는 **같은 PR에서 삭제**한다. 외부 소비자 없음은 nestlio가 external만 사용하는 것으로 확인했다.

## 배치 E — 알림 계층 재설계 + M9 병합

1. **`run_per_user_job` 러너**: `jobs/_job_helpers.py`에 만든다. 하는 일은 다음과 같다.
   - 사용자 쿼리 → Semaphore → 사용자별 세션 → `resolve_notification_email` → dedup → `report_job_failure`
   - 적용 대상: goal_achievement, monthly_report, challenge_deposit_reminder, challenge_monthly_wrap, digest, drift
   - `notification_email or user.email` 15곳은 헬퍼 하나로 바꾼다.
   - `asset_sync`와 `rebalancing_auto_execution:122`의 실패는 Sentry로 보낸다(`report_job_failure`).
2. **발송 단일 경로**: `alerts/_dispatch.dispatch_dual_channel_alert`로 모은다.
   - 대상: `rebalancing/plan_notifications.py` 수기 블록 6개, `rebalancing/alert_check.py:126-190`, `alert_service.notify_and_record_trigger`, `goal_achievement._notify_goal`
   - "이메일 성공 시에만 푸시" 같은 의미 차이는 dispatch 옵션으로 보존한다.
3. **dedup 일원화**: durable dedup 키와 TTL을 `cache_keys.py`에서 `utils/dedup_keys.py`로 분리한다. 잡 파일의 로컬 키(challenge, dca)도 여기로 모은다. `AlertHistory` 조회 기반 dedup(goal 월1회, digest 일1회)은 durable 키로 바꾼다.
4. **M9 병합** (plans/50)
   - ⓐ digest가 `composite_alert_sent_key`를 공유한다. 같은 날 등급 전환 메일이 이미 갔으면 다이제스트는 "변화 없음"으로 축약한다.
   - ⓑ 월간 리포트와 챌린지 결산을 1통으로 합친다(day 1 09:00). 잡 하나와 템플릿 섹션을 합친다.
   - ⓒ DCA 부족과 목표 달성을 저녁 요약 1통으로 합친다(18:45). 러너만 공유하고, 수집기는 2개다.
   - `scheduler.py` 등록을 갱신하고, 기존 dedup 키에서 마이그레이션되는 첫 실행에 중복 발송이 없게 한다.
5. **email_service 래퍼 22개**를 템플릿→이벤트 매핑 테이블로 압축한다. `push_service.send_push_to_user`의 로깅 래퍼는 `send_push`로 흡수한다.

## 배치 G — DB 정리 (컬럼 드롭 → squash)

1. **드롭 마이그레이션** (실행 시점에 0참조인지 재확인)
   - `asset_snapshots.amount_original`
   - `kis_tokens`/`kiwoom_tokens`/`toss_tokens`의 `token_type`
   - `rebalancing_plans.composite_level_at_plan`
   - `users.needs_password_reset`: 프론트 판독부(14곳)를 먼저 제거한다.
   - `user_ticker_settings`: 배치 A 결과에 따라 결정한다.
   - 선택: 토큰 테이블 3개를 `broker_tokens(broker, …)` 하나로 통합. 조사상 거의 동일 구조이고 `_token_cache`가 이미 공통이다. 영향 범위를 보고 같은 배치에서 결정한다.
2. **alembic squash** (마지막에, 단독 PR)
   1. 운영 Supabase `growlio_alembic_version`이 head인지 확인한다.
   2. `pg_dump --schema-only`로 growlio 테이블 스키마를 기준 덤프로 남긴다.
   3. 109개 → baseline 1개로 압축한다. **nestlio 테이블은 제외**한다(같은 `public` 스키마를 공유하므로 autogenerate 대상 필터를 확인한다).
   4. `scripts/bootstrap_alembic.py`를 갱신한다. 기존 DB는 버전 포인터를 새 baseline으로 재스탬프하고, 신규 DB는 upgrade한다.
   5. `render.yaml` preDeploy 순서와 CI의 upgrade/downgrade -1 단계를 조정한다.
   - 검증: 빈 Docker DB에 upgrade한 스키마와 기존 head 스키마를 `pg_dump --schema-only`로 diff해 0이어야 한다.

## 배치 F — services 도메인 패키지 단계적 재편 (로직 변경 이후, PR당 1클러스터)

순서는 결합도가 낮은 것부터다: `market_signal/`(+economic_indicator) → `etf/` → `backtest/` → `tax/` → `goal/` → `market_data/` → `portfolio/` → `accounts/` → `notifications/`(email·push·email_templates). 기존 하위 패키지(rebalancing/, alerts/, dividend/)는 그대로 둔다. 쿼리 헬퍼는 `services/queries/`로 모은다.

각 PR의 규칙:
- **re-export shim을 두지 않는다.** plan 34에서 shim이 테스트 전용 죽은 코드로 드리프트한 전례가 있다. import와 문자열 patch 경로를 **스크립트로 일괄 치환**한다.
  - 치환 스크립트는 정확한 모듈 경로 문자열만 바꾼다. `feedback_mechanical_rename_import_source` 교훈에 따라 동명 심볼 오치환이 없는지 diff로 검토한다.
- 치환 후 실제 import를 시도해 존재하지 않는 patch 대상이 없는지 검사한다(`pkgutil`로 각 patch 문자열 resolve). lazy import 기반 patch는 배치 C에서 정리됐는지 확인한다.
- `backend/CLAUDE.md` 서비스 목록을 같은 PR에서 갱신한다.

---

## 재사용할 기존 자산

- `api/_account_deps.get_owned_account` / `get_owned_or_404`: 소유권 확인
- `api/deps.PaginationDep`: 페이지네이션
- `api/v1/_alert_crud.register_alert_reactivate_delete`: 알림 CRUD 확장 기반
- `services/alerts/_dispatch.dispatch_dual_channel_alert`: 알림 발송 단일 경로
- `jobs/_job_helpers.run_alert_job` / `report_job_failure`: 러너 확장 기반
- `utils/durable_state.get_durable/set_durable(commit=False)`: dedup
- `rebalancing/drift_summary_service.get_drift_summaries`, `tax_action_service.build_loss_harvest_actions`: B1
- `providers/http_client`, `_retry`, `_token_cache`, `_error_mapping`: 브로커 계층은 이미 통합돼 있으므로 재작업하지 않는다
- 테스트 `conftest.py` 팩토리(`make_account`/`make_snapshot`/`make_user_settings`)와 실DB 접속 차단 가드
- goal 계열 이동 시 `tests/snapshots/goal_recommendation.json` 스냅샷 하네스로 출력 동일성을 검증한다(plan 43 방식)

## 범위 밖 (변경 없음)

- 브로커 클라이언트 패키지(kis/kiwoom/toss의 client·auth): 이미 공통 계층을 쓴다. 예외 클래스 공통 base 정도만 B3에서 필요하면 반영한다.
- 토스 주문 API(미구현 기능 신규 개발), 정기 자동매수, 프론트 대형 컴포넌트(plan 51 이관분)

## 검증 (배치마다)

```bash
make lint && make typecheck
make test-backend-cov          # 80% 게이트, 기준선 2610 passed / 90.99%
make test-frontend             # D·A(프론트 영향 배치)
cd backend && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head   # G
```

- 배치 0: 회귀 테스트가 수정 전 코드에서 실패하는지 확인한다.
- B3(주문 실행)·E(알림): 실행기와 발송 경로 테스트를 전부 그대로 통과해야 한다. 알림은 테스트에서 mock 호출 횟수(중복 발송 0)를 단언한다.
- F: 각 PR 전후 `pytest --collect-only` 수가 같아야 하고, goal 스냅샷 하네스는 바이트 단위로 일치해야 한다.
- G: 빈 DB baseline 스키마와 기존 head 스키마의 `pg_dump --schema-only` diff가 0이어야 한다.
- D·E 이후 `make dev`로 설정 화면 토글과 알림 테스트 발송 버튼을 수동 확인한다.
- Windows에서 pytest가 `N passed` 후 `-1073741819`로 끝나는 것은 실패가 아니다.
