# 리밸런싱 탭 전체 감사 → 정리·리팩터링 계획

## Context
사용자 요청: 리밸런싱 탭(진단/추천/전술/포트폴리오/이력) 전체를 분석해 불필요한 코드·리팩터링·개선점을 찾고 수정 계획 수립.
3개 영역(프론트 컴포넌트 / 프론트 데이터계층 / 백엔드 rebalancing 도메인)을 병렬 감사했고, 핵심 항목은 코드에서 직접 재확인함(✅ 표시).
결과: 단순 정리 외에 **보안 1건·실주문/알림 경로 실버그 다수**가 섞여 있어, 위험도 순 배치로 나눈다.

**범위 제외/분리**: 전술(Tactical) 관련 파일은 2026-10-20~21 미커밋 진행 중 작업 → 배치 F로 분리, 해당 작업 커밋 이후에만 착수. 실행 전 `git status`/`git diff`로 다른 세션 변경 확인(동시 세션 규칙).

**산출물**: 실행 첫 단계로 이 계획을 `docs/plans/62-rebalancing-tab-review-2026-10-21.md`(61은 미병합 브랜치 `fix/tech-debt-2026-10-20`에 있음)로 저장하고 `docs/plans/README.md` 인덱스에 추가.

---

## 배치 A — 보안·실버그 (백엔드, 최우선)
| # | 문제 | 위치 | 수정 |
|---|---|---|---|
| A1 ✅ | **IDOR**: 타 유저 portfolio_id로 전략/팩터 조회 가능 (user_id 필터 없음, 팩터 캐시키도 user 미포함) | `services/rebalancing/strategy_service.py:224`, `services/factor_service.py:184` | `Portfolio.user_id == user_id` 조건 추가, `factor_analysis_portfolio_key`에 user_id 포함. 타 유저 404 테스트 |
| A2 ✅ | 같은 AsyncSession을 `asyncio.gather`로 동시 사용(캐시 미스 시 실패) | `strategy_service.py:247` | 순차 await로 변경(drift_summary_service의 기존 규칙과 동일) |
| A3 ✅ | 알림 job 10분 간격 vs `is_alert_execution_time` ±4분 → 위상에 따라 notify_time 매일 누락 | `scheduler.py:67`, `utils/market_hours.py:71` | rebalancing_alert job을 5분 간격으로(자동실행 job과 동일). 당일 중복발송 dedup 이미 있음 확인 |
| A4 | 매도/매수 leg 승인이 `deadline_at` 경과 후에도 실행됨(만료 job 15분 주기 사이) | `services/rebalancing/plan_execution.py:47` `_lock_and_claim` | 잠금 후 `deadline_at <= now`면 EXPIRED 처리 + 409. 공개 승인 페이지 POST도 동일 경로인지 확인 |
| A5 | 일일 거래한도 합산이 CASH·부동산·BUY_ONLY에서 건너뛸 매도까지 `abs(diff_krw)` 합 → 약 2배 과대 | `plan_generation.py:371` vs `:165` | 실제 빌드된 주문의 `qty×reference_price`로 계산(오늘 누적과 같은 기준) |
| A6 | TWO_PHASE 3단계에서 예산 부족 매수 `remaining`을 버림 → 결과·이력 미기록 | `_kis_order_executor.py:221` | SKIPPED로 결과에 포함(`clamp_buy_orders_to_budget`와 동일 표기) |
| A7 | 이력 저장 실패 시 leg는 EXECUTED인데 API는 FAILED, 결과 메일 없음 | `plan_execution.py:181`, `rebalancing_plan.py:130`, `execution_service.py:183` | 주문 결과 기준으로 상태 응답, 이력 저장 실패는 로그+Sentry만 |
| A8 | AUTO 실행 job: 계획 생성 실패 시 rollback 없음·notify 미격리 → 이후 알림 전부 중단 | `jobs/rebalancing_auto_execution.py:115-140` | `alert_check.py:446-460` 패턴대로 알림별 try/rollback |
| A9 | 키움은 TWO_PHASE 무시 / 자동실행 계좌 검증에 is_active 누락 / plan 목록 `limit` 상한 없음 | `execution_service.py:378`, `rebalancing_alerts.py:59`, `rebalancing_plan.py:82` | 키움+TWO_PHASE는 요청 단계에서 거부(또는 문서화), `active_accounts_stmt` 사용, `Query(le=100)` |

## 배치 B — 프론트 실버그 (작은 수정)
- B1 ✅ 데스크톱 주문표 시장가 행이 7칸(헤더 6) — `RebalancingPriceInput.tsx:29` 빈 `<td/>` + `RebalancingOrderTable.tsx:350,481` 꼬리 `<td/>` 정리.
- B2 ✅ "부족 -5만원" 이중 마이너스 — `RebalancingConfirmStep.tsx:150` → `Math.abs`; 색상은 `CashSummaryBar`와 통일(배치 D2에서 컴포넌트 통합).
- B3 `prefillName` 미초기화로 다음 새 포트폴리오에 이전 추천 이름 남음 — `RebalancingPage.tsx:112-114,280` → 단일 `prefill` 상태 객체.
- B4 탭이 URL 변경에 반응 안 함(푸시 딥링크로 같은 페이지 내 이동 시) — `RebalancingPage.tsx:46` `useState` 미러 제거, `searchParams`에서 파생. `openExecution`/`openRecOptions`도 같은 일회성 소비 패턴.
- B5 분석 응답 경합(포트폴리오 빠른 전환 시 이전 결과 표시) — `hooks/useAnalysisState.ts:45` → portfolioId 키 `useQuery`로 전환(배치 E3와 함께).
- B6 모바일 주문카드에 매수계좌 제거(×) 없음 — `RebalancingMobileCard.tsx`에 `REMOVE_BUY_ACCOUNT` 추가.
- B7 `tradableAccounts`가 매 렌더 새 배열 → 하위 useMemo 3개 무력화 — `hooks/rebalancingExecution/index.ts:116` useMemo.
- B8 기타: `dark:hover:bg-gray-750`(없는 클래스, `RebalancingHistoryTab.tsx:55`), `RebalancingStrategyCard.tsx:143,159` null이면 "+%p", 시장신호 GREEN 라벨 "안정"(StatusCard) vs "안전"(Badge) 불일치.

## 배치 C — 캐시 무효화·쿼리 정의 정리 (프론트)
- C1 `invalidateRebalancingAlertData`에 `driftSummary` 추가(알림 저장 후 "알림 미설정" 60초 잔존), 중복 라인 제거 — `utils/queryInvalidation.ts:157-165`.
- C2 `invalidatePortfolioData`에 `rebalancingAlerts`·`portfolioExpectedMetrics` 추가; `reorderPortfolios` 후 무효화(`PortfolioManageTab.tsx:197`).
- C3 `invalidateSettingsData`와 동일한 래퍼 6개 삭제(`queryInvalidation.ts:109-112,190-213`), `useGoalSettings.ts:214` 이중 무효화 제거.
- C4 `queryOptions()` 팩토리 도입(`api/queryOptions.ts` 또는 각 api 파일): `portfolios`·`marketSignal`·`compositeSignalStatus`·`driftSummary`·`settings` — 12곳+ 중복 정의의 staleTime 불일치 해소. RebalancingPage 프리페치도 이 팩토리 재사용. `usePortfolios()` 훅 추가.
- C5 `QUERY_KEYS.portfolioRisk(id?)` 잔재 인자 제거, `rebalancingExecutionDetail(id)` 키 추가(`RebalancingHistoryTab.tsx:45` ad-hoc 키 교체).
- 백엔드 대응: 포트폴리오 수정 시 rebalancing-strategy 캐시 무효화 누락(`api/v1/portfolios.py:227,249`).

## 배치 D — 죽은 코드·중복 제거 (동작 불변)
**프론트**
- D1 `RebalancingStatusCard` props(`signalDisplay`/`showAllInsights`/`showDriftRows`/`statusOnly`) → `variant: "home" | "diagnosis"`; 미사용 `"banner"` 분기·`SIGNAL_BG`·`SIGNAL_LABEL`/`SIGNAL_BADGE_CLASS` 삭제 후 `MarketSignalLevelBadge` 재사용.
- D2 죽은 prop: `onExecuted`(RebalancingTable→ExecutionModal→hook), `onSwitchToPerAccount`(RebalancingAlertModal), 중복 prop `portfolioName`/`portfolioId`/`hasFrontier`. 미사용 `executionEligibleAccounts`·`brokerAccounts`(`useRebalancingAlertForm.ts:71`), `PortfolioManageTab.tsx:182` 빈 effect, `useRebalancingExecution.ts` 미사용 재노출, `useMarketSignalDigestToggle` → `useSettingsToggle` 일반화.
- D3 중복 UI 통합: 실행 결과 목록(`RebalancingHistoryTab.tsx:111-198` ↔ `RebalancingResultSection.tsx:67-150`) → 공용 `OrderResultList` + 기존 `SideBadge`/`StatusBadge`; ConfirmStep 전역 현금 배너 ↔ `CashSummaryBar`; 계좌 동기화 로직 2곳 → `useSyncAccounts`; 자동실행 계좌 선택기 2곳(`AlertAutoModeSection`/`AlertQuickDcaSection`) → `AccountPicker`.
- D4 `rebalancingTradeMath.ts`: 지정가 추정 계산 3곳(`OrderTable:22`, `PriceInput:31`, `MobileCard:165`) → `estimateLimitKrw()`, tradable 체크 일원화.
- D5 하드코딩 → 기존 유틸: 손익색 `pnlColor`/`PROFIT_COLOR`(utils/colors.ts), 부호 퍼센트 `fmtPct`(+`%p` 변형), raw `"CASH"` → `CASH_TICKER`, 수수료 문구를 `TRADING_FEE_RATE`에서 도출, `CASH_EQUIVALENT_TICKER` import 경로 통일.
- D6 stale 주석 2건(`rebalancingTradeMath.ts:31`, `RecommendationComparisonPreview.tsx:46`).

**백엔드**
- D7 "비거래 항목 스킵" 규칙 7곳 상이(일부 CASH_EQUIVALENT 누락, order_builder는 ticker `"REAL_ESTATE"`로 판정) → `is_non_tradable(ticker, market)` 단일 헬퍼. **주의: 판정 결과가 바뀌는 지점은 테스트로 고정 후 적용**.
- D8 복합신호 조회 4곳 → `get_composite_signal_for_user()` 헬퍼; alert+portfolio+email/FCM 조인 6곳 → `_alert_queries.py`로; 게이트 차단 알림 3종(`plan_notifications.py:107-264`)·alert_check/alert_test 발송부 → 기존 `services/alerts/_dispatch.dispatch_dual_channel_alert` 재사용.
- D9 죽은 코드: `alert_check.py:140-153` 미사용 `mode` 계산 블록과 `__all__` 재노출·미사용 import, `service._item_attr` 레거시 dict 지원, 항상 `[]`인 `untracked_holdings`(프론트 렌더 포함), 중복 필드 `total_current_annual_dividend`, `OverlapCandidateIn`(테스트 전용), 비동기 불필요 `_load_credentials`, `broker_balance_service.py:60` 이중 체크, 중복 상수(`_AUTO_EXECUTION_ASSET_TYPES`, 브로커 타입 튜플, 5.0 임계치).
- D10 `plan_service.py` barrel 축소(테스트만 쓰는 재노출 → 서브모듈 직접 import, patch 경로 재타겟), plan_* "구 1025줄" 히스토리 주석·`order_builder.py:3,272` stale 주석 정리. `cancel_buy_leg`/`reject_sell_leg` 통합.
- D11 ORM 컬럼에 대한 방어적 `getattr(..., default)` 38건 → 직접 속성(기본값 불일치 `trigger_condition` 포함).

## 배치 E — 구조 리팩터링 (선택, 회귀 위험 중)
- E1 드리프트 계산 기준 통일: 대시보드 drift_summary(`service.py:495-504` 자체 base, `>=`) vs 분석/알림(`compute_base_value_krw`, `>`), CASH 포함 여부, 계좌 스코프(`account_ids` vs `resolve_effective_account_ids`). **사용자에게 보이는 숫자가 바뀌므로 기준 하나로 확정 후 진행.**
- E2 KIS/키움 주문 실행기 ~70% 중복 → 브로커 어댑터(주문·보유수량·예산조회) + 공통 루프; `_execute_buys_within_budget`를 `clamp_buy_orders_to_budget`로 대체.
- E3 `AnalysisPanel`/`useAnalysisState` 다중선택 잔재 제거 + `useQuery` 전환, 수동/자동 분석의 예수금 기준 통일(`fetchAllBrokerBalances` 1회). B5 해소.
- E4 `useRebalancingUrlState()` 훅 + `rebalancingUrl()` 빌더(현재 setSearchParams 복붙 6곳, `/rebalancing?rtab=` 수동 문자열 ~15곳). B4와 함께.
- E5 대형 컴포넌트 분해: `RebalancingOrderTable`(508, 매도/매수×모바일/데스크톱 4중 복제 → `OrderRow({side})`), `RebalancingHistoryTab`(506), `RecommendationCard`(→`useRecommendationTargets`), `GoalRecommendationOptionsModal`(→`usePctDraft`+`PctField`, `INPUT_SM`), `RebalancingConfirmStep`, `AlertAutoModeSection`. 백엔드 80줄+ 함수: `_process_rebalancing_alert`, `build_pending_plan_for_alert`, `get_rebalancing_strategy`, `_build_target_items`.
- E6 `rebalancingExecution/index.ts` ↔ `useRebalancingPrices/Balances` 순환 import → `getActionableItems`를 utils로 이동; 주문키 `` `${side}_${ticker}_${acc}` `` 10곳 → `orderKey()` 헬퍼.
- E7 성능: `auto_execution_time=None` AUTO 알림이 5분마다 전체 분석 재실행(`market_hours.py:61`) — 실행시각 기본값 부여 검토; 테스트 알림 엔드포인트 이중 로드.

## 배치 F — 전술(Tactical) 신규 코드 (해당 작업 커밋 후)
- `TacticalStatusView`에 `key={status.portfolio_id}`(`TacticalAllocationTab.tsx:410`, 이전 포트폴리오 적용상태 누수 버그).
- GET `/tactical`에서 국면 전진+commit 제거(07:40 job과 경합) — `api/v1/tactical.py:65-77`.
- apply가 부동산 등 포트폴리오 항목 전체 삭제 → 서버측 호환성 검증(`tactical_allocation_service.py:318`); apply 후 rebalancing-strategy 캐시·`portfolioExpectedMetrics` 무효화; `invalidatePortfolioData`에 `tacticalStatusBase`.
- 스키마를 `schemas/`로 이동·응답 타입화, `economic_indicator_service` private 함수 import 정리, 백테스트에 `fred_circuit.is_available()` 체크.
- 프론트: `REGIME_ORDER`/라벨 중복 → `tacticalLabels.ts`, `pnlColor`, `pickedId/setSelectedId` 명명, 선택 포트폴리오 URL 반영, 413줄 파일 분해.

## 이관/보류 (이번 범위 밖)
- `components/portfolio-analysis/Tax*` 파일 위치 이동(InvestPlanPage 전용), index key 정리, 공용 `Button` 컴포넌트 채택 — 저가치.
- 동일 티커 다시장 가격 키 충돌(`order_builder.py:126`, `overview_enrichment.py:105`) — 실사례 확인 후.

---

## 실행 순서·커밋 단위
A(백엔드 보안·실버그) → B(프론트 실버그) → C(무효화) → D(정리) → E(구조, 사용자 확인 후 항목별) → F(전술 커밋 후).
배치마다 별도 커밋(`fix:`/`refactor:` + `(plans/62 배치 X)` 관례). 각 실버그 수정은 회귀 테스트 동반.

## 핵심 재사용 대상
`services/alerts/_dispatch.dispatch_dual_channel_alert`, `_order_quantity_guard.clamp_buy_orders_to_budget`, `_alert_queries.py`, `active_accounts_stmt`, `utils/queryInvalidation.ts` 헬퍼, `useSettingsToggle`, `useAutoRebalancingDailyCap`, `MarketSignalLevelBadge`, `SideBadge`/`StatusBadge`(RebalancingBadges.tsx), `CashSummaryBar`, `pnlColor`/`fmtPct`, `INPUT_SM`, `CollapsibleCard`/`useCollapsible`.

## 검증
- 배치별: `make lint`, `make typecheck`, `make test-backend`(최종 `make test-backend-cov` 80% 게이트), `make test-frontend`.
- 신규 테스트: A1 타 유저 portfolio_id 404, A3 job 간격 vs 창 커버리지, A4 마감 후 승인 409, A5 한도 합산 기준, A6 SKIPPED 기록, A8 알림 1건 실패 시 다음 알림 진행, B1 표 셀 수, B2 "부족" 문구, B3 prefill 초기화, C1 무효화 키.
- 수동: `make dev` 후 리밸런싱 탭 5개 탭 순회 — 진단 카드·포트폴리오 분석→실행 모달(시장가/지정가 표 정렬, 모바일 390px 카드)·이력 탭 결과 목록·딥링크(`/rebalancing?rtab=이력`을 같은 페이지에서 이동).
- 문서: 파일 추가/삭제 시 `frontend/CLAUDE.md`·`backend/CLAUDE.md` 목록 갱신, `docs/plans/README.md` 상태 표 갱신.
