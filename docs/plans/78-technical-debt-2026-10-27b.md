# 78. 기술부채 감사 2차 (2026-10-27)

## Context

계획 77(PR #161)이 오늘 main에 병합되어 "미병합 감사 브랜치"는 없다. 정적 검사도 0건이다(ruff·format·mypy·tsc·eslint·prettier, TODO/FIXME 0).

남은 부채는 계획 62(리밸런싱 탭 감사)의 C·D·E·F 이관분이었다. 코드와 대조해 아직 유효한 항목만 골랐다. E4(`rebalancingUrl` 빌더)와 D9의 `OverlapCandidateIn`은 이미 해소되었거나 실사용 중이었다.

상태: **A1~A4·B1~B3·C1~C6·D1 완료**. 브랜치 `fix/tech-debt-2026-10-27b`, 배치별 커밋.

## 배치 A — 백엔드 판정 단일화·죽은 코드

- **A1 (62 D7, 실버그)**: 비거래 항목(예수금·현금성 자산·부동산) 제외 규칙이 8곳에 따로 있었다.
  - 세 곳이 `CASH_EQUIVALENT`(market `CASH`)를 빠뜨려 시세 조회 대상으로 취급했다.
    - 기대지표 API(`api/v1/rebalancing.py`)
    - 미보유 시세 보완(`overview_enrichment`)
    - 보유 종목 후보 시드(`goal_candidate_service`)
  - `app/constants.is_non_tradable(ticker, market)`로 단일화했다.
  - 회귀 테스트 3건은 수정 전 코드에서 실패하는 것을 확인했다.
- **A2 (62 D9)**: 죽은 코드를 지웠다.
  - `alert_check._process_rebalancing_alert`에서 계산만 하고 읽지 않던 AUTO 게이트 블록. 실제 강등 사유는 호출부의 `automation_note`가 계산한다. 이 블록 때문에만 있던 인자 2개도 함께 제거했다.
  - await가 없던 async 자격증명 로더 2개를 동기 함수로 바꿨다.
  - `_AUTO_EXECUTION_ASSET_TYPES` 대신 `ORDER_EXECUTABLE_ASSET_TYPES`를 쓴다.
  - 응답 필드 `total_current_annual_dividend`는 `current_portfolio_annual_dividend`와 같은 값이라 제거했다.
  - `untracked_holdings`(항상 `[]`)는 프론트에서만 제거했다. 백엔드는 기본값 `[]`로 남겨 둔다. 구버전 PWA 번들이 `.forEach`로 읽기 때문이며, **다음 정리 때 제거**한다.
- **A3 (62 D10 일부)**: plan_*의 "구 1025줄" 히스토리 주석을 정리하고 `cancel_buy_leg`/`reject_sell_leg`의 내부를 공통화했다. barrel(`plan_service`)은 운영 코드 6곳이 써서 유지한다.
- **A4 (62 D8 전반)**: `diagnosis_service.fetch_composite_signal()`을 추가했다.
  - 복합신호 조회와 `check_composite_signal` 인자 전개를 3곳(진단 배너 API·drift-summary·알림 추가 트리거)이 공유한다.
  - 예외 처리와 로그 이벤트는 호출부에 남겼다.
  - 테스트 patch는 실제 조회 지점(`diagnosis_service.fetch_market_and_risk_signal`)으로 옮겼다.

## 배치 B — 프론트 쿼리 정의·캐시

- **B1 (62 C3)**: `invalidateSettingsData`와 몸체가 같던 래퍼 6개를 제거했다.
  - `useSettingsToggle`의 `invalidate`를 선택값으로 바꿨다(기본 settings만 무효화).
  - `useMarketSignalDigestToggle`도 이 팩토리로 옮겼다.
  - 목표 저장 시 settings가 두 번 무효화되던 문제도 정리했다.
- **B2 (62 C4)**: `src/api/queryOptions.ts`를 새로 만들어 portfolios·settings·market-signal·drift-summary·composite-signal-status를 TanStack `queryOptions`로 한 곳에 정의했다. 26개 파일이 이 정의를 쓰게 바꿨다.
  - 포트폴리오 쿼리는 13곳 중 6곳이 staleTime을 빠뜨려 전역 SHORT로 동작했다. 모두 MEDIUM으로 통일했다.
  - 시장신호 쿼리의 staleTime 불일치(MEDIUM 2곳, LONG 1곳)는 MEDIUM으로 맞췄다.
  - `queryFn`은 화살표로 감쌌다. 일부 export만 목킹한 테스트가 모듈을 로드할 때 깨지지 않게 하기 위해서다.
  - 계획에 있던 `usePortfolios()` 훅은 만들지 않았다. `useQuery(portfoliosQuery)`로 충분하다.
- **B3 (62 C5)**: `portfolioRisk(id?)`의 잔재 인자를 없애 유저 단위 상수로 바꿨다. `rebalancingExecutionDetail(id)` 키를 추가했다.

## 배치 C — 프론트 중복·죽은 prop

- **C1 (62 D1)**: `RebalancingStatusCard`를 진단 탭 전용으로 정리했다. 유일한 호출부가 `signalDisplay="none"`과 `showAllInsights`만 넘겼으므로 다음 홈 변형 잔재를 제거했다.
  - 시장신호 배지·배너, `SIGNAL_BG`
  - `showDriftRows`·`maxDriftRows`·`storageKey` prop
  - "분석하기" 링크
- **C2 (62 D2)**: `RebalancingAlertModal.onSwitchToPerAccount`를 제거했다. 아무도 넘기지 않았고, 화면 전환은 Router가 다시 조회된 `alert_scope`로 처리한다. `useRebalancingAlertForm`의 미사용 반환값도 정리했다.
- **C3 (62 D3)**: 공용 컴포넌트 두 개를 만들었다.
  - `alertModal/AutoExecutionAccountPicker`: AUTO 상세 설정과 적립식 빠른 설정에 글자 단위로 복제돼 있던 계좌 선택기.
  - `OrderResultList`: 실행 직후 결과 화면과 실행 이력 상세가 공유한다. 데스크탑 표의 실패 사유는 잘리지 않게 줄바꿈으로 표시한다.
- **C4 (62 D4)**: 지정가 원화 환산 3곳을 `rebalancingTradeMath.estimateLimitKrw`·`limitPriceKrw`로 합쳤다.
- **C5 (62 D5·F)**: `CASH_TICKER`·`pnlColor`·`REGIME_ORDER`(tacticalLabels)를 사용하게 했다.
  - 배당 증감(초록/빨강 배경)과 위험 변화(감소=빨강)는 손익 색 관례가 아니라서 그대로 두었다.
- **C6 (62 E6)**: 순환 import를 끊었다.
  - `getActionableItems`를 `rebalancingTradeMath`로 옮겨 `rebalancingExecution/index` ↔ `useRebalancingPrices`의 런타임 순환을 해소했다.
  - 잔고·가격 훅의 타입 import도 `types.ts`로 바꿨다. madge로 확인한 hooks·components/rebalancing의 순환은 0이다.
  - 주문 키 템플릿 18곳은 `orderKey()`로 바꿨다.

## 배치 D — 성능

- **D1 (62 E7)**: 실행 시각이 없는 AUTO 알림은 장중 5분마다 평가 대상이다. 드리프트가 없거나 게이트가 차단해도 claim을 풀어서, 매 tick마다 개요·분석·전술 게이트를 다시 계산했다.
  - 이제 이런 결과에도 일자 claim(`rebalancing_auto_claim_key`)을 유지한다. 다음 tick은 `get_durable`로 확인하고 바로 건너뛴다.
  - 계획에서는 별도 키를 만들 예정이었지만 기존 claim 키를 재사용했다. 키가 하나라 상태가 엇갈릴 여지가 없다.
  - 지정 시각 알림과 수동 실행 락 경합(`PlanGenerationInProgress`)은 기존처럼 claim을 푼다.
  - **영향(사용자 승인)**: 그날 첫 평가에서 드리프트가 없으면, 장중에 새로 생긴 드리프트는 다음 거래일에 처리된다.

## 이관 (이번 범위 밖)

- 62 D11: ORM `getattr(…, default)` 43건. 관련 함수를 수정할 때 함께 정리한다.
- 62 E2: `_execute_buys_within_budget` → `clamp_buy_orders_to_budget` 통합. 주문 실행 경로라 별도 계획으로 둔다.
- 62 E5: 대형 파일·함수 분해.
  - 컴포넌트: TacticalAllocationTab 691줄, RebalancingOrderTable 519줄.
  - 함수: `build_pending_plan_for_alert` 131줄 외.
- 62 F 잔여: `api/v1/tactical.py` 인라인 스키마 → `schemas/`, `_fred_get_observations` private import 10곳, 백테스트 `fred_circuit.is_available()`(지금은 `return_exceptions=True`라 무해).
- 62 D8 나머지: 게이트 차단 알림 3종 → `dispatch_dual_channel_alert`. 각자 durable dedupe를 가지고 있어 동작 차이 검토가 먼저 필요하다.
- `untracked_holdings` 백엔드 필드 제거(구버전 PWA가 사라진 뒤).
- 77 이관 유지: `idx_portfolio_item_members_item` 중복 인덱스, 동일 티커 다시장 가격 키 충돌, 67 잔여, 65 B4, 66 P3.
- 메이저 업그레이드(react 19·recharts 3·tailwind 4·TS 7·plugin-react 6)는 별도 계획으로 둔다.

## 검증

- 백엔드: ruff·format·mypy 클린, `pytest --cov` 3032 passed, 91.72%.
  - 회귀 테스트(수정 전 코드에서 실패 확인):
    - `test_overview_enrichment::TestNonTradableItemsSkipped`
    - `test_goal_recommendation::test_existing_items_from_positions_filters_cash_and_property`
    - `test_rebalancing_api::test_excludes_cash_and_real_estate_items_and_returns_metrics`
    - `test_rebalancing_auto_execution::TestOncePerDayEvaluation` 4건
- 프론트: tsc·eslint·prettier 클린, `vitest --coverage` 1825 passed(임계값 통과). madge 순환 0(hooks·components/rebalancing).
- 마이그레이션 없음(`alembic heads` = `at1` 단일).

## 배포 전후 확인

- **77 이월(필수)**: 11-02(월) 09:00 KST 전에 공유 Supabase의 `alembic current`가 `at1`인지 확인한다. 10-27 감사 시점에는 `ig2`였고 #161 배포 전이었다. 아니면 Render 배포 로그를 확인한다. 11-02 이후에는 `alert_history`에 연말 리마인더가 1건만 있는지 본다.
- D1 배포 후: 실행 시각 없는 AUTO 알림의 `rebalancing_auto_*` 로그가 하루 1회 수준으로 줄었는지 본다. 드리프트가 있는 날은 첫 개장 tick에 계획이 생성되는지 확인한다.
