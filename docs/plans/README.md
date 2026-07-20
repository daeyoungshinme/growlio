# 고도화 계획 인덱스 (2026-07-19 감사 기반)

2026-07-19 전체 기능 감사(`docs/mobile-ux-audit-2026-07.md`와 별개 세션, 같은 시기 병행 진행)에서 도출된 고도화 항목을 세션별로 독립 실행 가능하도록 분리했다. 각 파일은 자기완결적(self-contained)이며, 서로 다른 파일이 건드리는 코드 영역이 최대한 겹치지 않도록 설계했다.

**7~9번은 2026-07-20 별도 세션에서 자산탭/계획탭/설정탭을 개별 감사한 결과** — 1~6번(전부 리밸런싱 탭 관련)과는 다른 화면을 다루므로 코드 충돌은 거의 없으나, 9번은 4번과 `SettingsPage.tsx` 알림 섹션을 공유할 수 있어 하단 표에 별도 표시했다.

**2026-07-20 오후, 사용자가 동일 취지 요청("불필요 기능 제거·병합 + 탭 UI/UX 개선 + 고도화 계획")을 다시 해서 9개 계획 전체를 현재 코드와 재대조 검증했다.** 결과: 2번만 다른 세션이 이미 처리 완료(커밋 `9a32a7f`), 나머지 8개는 파일:라인 참조까지 포함해 계획서 내용이 그대로 유효함(코드 드리프트 없음). 상세는 하단 상태표 참고.

## ⚠️ 실행 전 필수 확인사항

이 프로젝트는 **여러 터미널/세션에서 동시에 작업되는 경우가 잦다** (git status에 낯선 미커밋 변경이 자주 나타남 — 다른 세션의 진행 중 작업일 수 있음). 아래 계획 중 하나를 집어 실행하기 전에 반드시:

1. `git status` / `git diff`로 계획이 언급하는 파일들이 이미 다른 세션에 의해 수정되지 않았는지 확인
2. 계획서에 적힌 "현재 코드 상태"(파일:라인)가 실제 코드와 다르면, 계획서 내용보다 **현재 코드를 우선** — 계획서는 작성 시점의 스냅샷일 뿐
3. 완료 후 이 README의 상태 표를 갱신하고, 만약 다른 계획 파일이 영향받는 코드를 건드렸다면 해당 파일에도 메모 남기기

## 계획 목록

| # | 파일 | 요약 | 영역 | 의존성 | 리스크 |
|---|---|---|---|---|---|
| 1 | [01-auto-gate-tax-impact.md](01-auto-gate-tax-impact.md) | AUTO 자동매매 게이트에 세금영향(양도세 추정치) 반영 | 백엔드(rebalancing) | 없음 | 높음 (실제 자금 이동 로직) |
| 2 | [02-threshold-recommendation-dedup.md](02-threshold-recommendation-dedup.md) | 드리프트 임계값 추천 로직 백엔드 dead code 제거 — **완료(커밋 `9a32a7f`)** | 백엔드(rebalancing) | — | 낮음 |
| 3 | [03-recommendation-diagnosis-linkage.md](03-recommendation-diagnosis-linkage.md) | 추천 비중 재계산 시점을 추적해 "추천이 바뀌었어요" 알림/배지 추가 | 백엔드+프론트(goal_recommendation) | 없음 | 중간 (스키마 추가) |
| 4 | [04-notification-center-unification.md](04-notification-center-unification.md) | 알림 관리 화면 분산(설정 페이지 vs 리밸런싱 알림 모달) 완화 | 프론트(신규 화면) | 없음 | 중간 (신규 라우트/화면) |
| 5 | [05-backtest-tab-relocation.md](05-backtest-tab-relocation.md) | RebalancingPage "백테스팅" 최상위 탭 → 하위로 격하 | 프론트(RebalancingPage) | 없음 | 낮음 |
| 6 | [06-mobile-ux-carryover.md](06-mobile-ux-carryover.md) | 2026-07-13 감사 보류 항목 잔여분 처리 (RebalancingExecutionModal 공용 Modal화, Toaster 스택 제한) | 프론트(common) | 없음 | 낮음 |
| 7 | [07-assets-tab-audit.md](07-assets-tab-audit.md) | 자산탭(`/assets`) 감사 — 정렬 토글 버그, 종목 검색, 부동산 요약 카드 등 | 프론트(assets/portfolio) | 없음 | 낮음 |
| 8 | [08-invest-plan-tab-audit.md](08-invest-plan-tab-audit.md) | 계획탭(`/invest-plan`) 감사 — 추천 미리보기, 목표변경 이력 왜곡 확인, Tax 컴포넌트 폴더 정리 | 프론트(invest) | 없음 | 낮음~중간 |
| 9 | [09-settings-tab-audit.md](09-settings-tab-audit.md) | 설정탭(`/settings`) 감사 — 푸시알림 토글 부재, 비밀번호 변경, 알림이력 페이지네이션 | 프론트(settings) | **④와 같은 파일(`SettingsPage.tsx` 알림 섹션)을 다룰 수 있음 — 조율 필요** | 중간 |

**동시 진행 가능 조합**: 2번이 완료되어 1번의 `order_builder.py` 충돌 우려는 해소됨 — 1·3·4·5·6 전부 서로 다른 파일을 건드려 병렬 진행 가능. **7·8은 1~6과 완전히 다른 화면(자산탭/계획탭)이라 아무 때나 병렬 진행 가능. 9번은 4번과 `SettingsPage.tsx` 알림 섹션이 겹칠 수 있으니 동시 진행 시 순서 조율(먼저 끝낸 쪽이 커밋, 나머지가 rebase) 권장.**

## 상태 (2026-07-20 코드 재검증 + 저위험 5개 항목 구현 완료)

| # | 상태 | 완료일 | 비고 |
|---|---|---|---|
| 1 | 미착수 | | 사용자가 "세금 영향 추가 반영"으로 방향 확정(리스크 지표는 반영 안 함). 재검증: `diagnosis_service.py:99`(`_build_tax_preview`), `plan_service.py:165`(`build_pending_plan_for_alert`) 파일:라인 여전히 정확, `tax_impact_gate_mode`/`max_tax_impact_krw` 필드 아직 없음 — 실제 자금이동 로직이라 이번 라운드(저위험 5개)에는 포함하지 않음. 계획 내용 그대로 유효 |
| 2 | **완료** | 2026-07-20 이전 (커밋 `9a32a7f`) | 다른 세션이 이미 처리함 — `order_builder.py`의 `recommend_drift_threshold_pct`/관련 상수 삭제, `test_rebalancing_alert_service.py` 테스트 44줄 삭제, 프론트 주석도 "백엔드에 대응 함수 없음"으로 이미 갱신됨. 재작업 불필요 |
| 3 | 미착수 | | 재검증: `recommendationDrift.ts`/`computeRecommendationDrift` 코드베이스에 없음 — Phase A 그대로 미착수 (스키마 변경 없는 프론트 전용이지만 이번 라운드 범위 밖) |
| 4 | 미착수 | | 재검증: `SettingsPage.tsx`에 "리밸런싱 비중 이탈 알림 및 자동 실행 설정은 [리밸런싱 탭]에서 설정합니다" 텍스트 링크 그대로 존재, `RebalancingAlertSummaryCard` 미생성 (이번 라운드 범위 밖) |
| 5 | **완료** | 2026-07-20 | `REBALANCING_PAGE_TABS`에서 "백테스팅" 제거(3탭: 진단/포트폴리오/이력), "포트폴리오" 탭 하단에 `CollapsibleCard`(기본 접힘, `useCollapsible` localStorage 영속화)로 `BacktestTab` 인라인 진입점 추가. `RebalancingPage.tsx` |
| 6 | **완료** | 2026-07-20 | `git log -S`로 `bottom-[calc(3.75rem+...)]` 오프셋이 `Toaster.tsx`와 동일 패턴(하단 네비 위 공간만 채워 네비 탭 유지)임을 확인해 의도된 설계로 판단 → `Modal.tsx`에 `avoidBottomNav` prop 추가(모바일 전용 오프셋+z-40, 데스크탑은 기존과 동일) 후 `RebalancingExecutionModal.tsx`를 `<Modal avoidBottomNav>`로 완전 전환, 독자 마크업/`useModalBehavior` 직접호출 제거 |
| 7 | **일부 완료** | 2026-07-20 | 1~3번 구현: `StockHoldingsTable.tsx` 정렬 state를 `{key,dir}`로 확장해 재클릭 시 asc/desc 토글(`aria-sort` 정확 반영) + 종목명/티커 검색 입력 추가 + `RealEstateSection.tsx`에 `RealEstateSummaryCard`(시세·담보대출·순자산·매입차익 합계) 신규, `AssetManagementPage.tsx` 부동산 탭에 배치. 4·5번(하드코딩 3분류 구조 정리, "배당" 레이블 중복)은 낮은 우선순위로 범위 밖 유지 |
| 8 | **일부 완료** | 2026-07-20 | 1·3번 구현: `GoalRecommendationPreviewCard.tsx` 신규(계획탭 상단, 목표달성 필요수익률 vs 추천 기대수익률 요약 + 기존 딥링크) — `InvestPlanPage.tsx`의 기존 텍스트 링크를 이 카드로 교체. `components/invest/{TaxPlannerSection,TaxSimulationCard,TaxRecommendationList,TaxPositionTable,GeumtSimulationSection}.tsx` 5개 파일을 `components/tax/`로 이동(순수 리팩터링, `frontend/CLAUDE.md` 컴포넌트 디렉토리 목록에 `tax` 추가). 2번(목표변경 시 과거 달성률 왜곡 여부 조사)은 범위 밖 유지 |
| 9 | **일부 완료** | 2026-07-20 | 1·4번 구현: `stores/pushNotificationStore.ts`(Zustand) 신규로 `usePushNotifications.ts`(App.tsx 전역 마운트)가 등록 상태(unsupported/requesting/denied/registered/disabled/error)를 갱신, `retryPushRegistration()`/`disablePushNotifications()` export 추가 → `SettingsPage.tsx` "앱 설정"에 생체인증과 동일 패턴의 푸시 알림 토글 행 추가(거부 시 안내 문구). `AlertHistorySection`에 `limit` state 기반 "더 보기" 버튼 추가(백엔드 `skip`/`limit` 페이지네이션은 이미 지원되고 있었음 — 신규 구현 불필요, 프론트만 추가). 2번(로그인 상태 비밀번호 변경, Supabase/백엔드 JWT 책임소재 확인 필요)·3번(4번과 조율 필요, 범위 밖)·5번(DART 링크, 낮은 우선순위)은 범위 밖 유지 |

## 이번 감사에서 "이미 구현되어 있어 재작업 불필요"로 확인된 것 (참고용, 계획 없음)

- 단기/중기/장기 × ISA/연금저축/IRP/일반/해외전용 계좌 특성별 목표 역산 추천 — `GET /rebalancing/goal-recommendation/by-horizon` + `RecommendationCard.tsx`(리밸런싱 › 포트폴리오 탭)
- drift + 시장신호(거시 8종) + 리스크지표(VaR/베타/분산도) + 세금영향 복합 진단 — `rebalancing/diagnosis_service.py`
- 포트폴리오별/계좌별(AGGREGATE/PER_ACCOUNT) 독립 알림 + AUTO 2단계 실행(매수 자동/매도 승인)
