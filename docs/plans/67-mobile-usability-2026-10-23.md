# 67. 모바일 사용성·불필요 정보 정리 (2026-10-23)

## Context
사용자 요청: "모바일 사용자 측면에서 사용성 개선, 불필요한 정보 제거·수정할 부분 검토".
계획 53(2026-10-14)은 Phase A만 끝났고 B·C는 미착수다. 이번에 3개 영역을 현재 코드로 다시 감사했다(홈·공통 / 자산·리밸런싱 / 계획·설정).

**재감사 결과**
- 53의 B·C 항목은 대부분 유효하다.
- 이미 해결된 항목(재작업 금지):
  - AnalysisPanel의 segmented·title (64 S3)
  - RecommendationCard 칩 (64 S2)
  - AllocationCard 접힘 (58)
  - RiskMetricsCard 접힘·key
  - MarketSignalBanner 자동펼침
- 새로 드러난 축은 **같은 숫자·안내문의 반복 노출**과 **세로 스크롤 길이**다.
  - 홈 약 2.4화면
  - 리밸런싱 › 포트폴리오: 10종목 기준 약 3,000px 이상
  - 계획 › 적립 계획: 매우 긺

**산출물**
1. 이 내용을 `docs/plans/67-mobile-usability-2026-10-23.md`로 저장하고 README 인덱스에 추가한다. 53 B·C 중 유효한 항목은 67로 흡수하고 53에 "67로 이관"이라고 적는다.
2. 아래 Phase 1 → 2 → 3 순서로 구현한다(Phase마다 커밋).
3. Phase 4는 계획 53 Phase D(실기기 확인)를 그대로 유지한다.

**주의**
- `GoalAdjustTab.tsx`에는 다른 세션(계획 66)의 미커밋 변경이 있다. 해당 항목(P1-8)은 그 커밋 이후에 하거나 해당 hunk만 건드린다.
- 착수 전에 `git status`로 다시 확인한다.

---

## Phase 1 — 불필요·중복 정보 제거 (가장 체감 큼, 저위험) — **완료(2026-10-23)**

**진행 기록**
- P1-1~P1-6 완료. 계획과 다르게 처리한 점:
  - P1-3: 상태 행이 `RebalancingStatusCard`의 `statusOnly` 분기다. 시장 신호 배지는 `signalDisplay`와 무관하게 표시한다.
  - P1-4: 숨김 대신 한 줄 행으로 축소했다. 연속 적립 스트릭은 동기부여 지표라 유지한다.
  - 추가: Hero 스켈레톤을 실제 카드 모양으로 바꿨다. 도넛 툴팁이 금액으로 비중을 역조회하던 버그를 payload 사용으로 고쳤다.
- P1-7: 진단 카드를 기본 접힘으로 바꿨다(펼침 상태 기억). 카드별 AutomationStatusBar는 **유지**했다. 선택하지 않은 포트폴리오의 자동화 여부를 목록에서 훑는 용도라 중복이 아니라고 판단했다.
- P1-8: `TacticalAllocationTab` 부제·footer 반복을 제거했고, 추천 결과 도넛은 모바일에서 숨겼다. **`GoalAdjustTab.tsx`는 미변경** — 다른 세션(계획 66)의 미커밋 변경과 충돌을 피하려고, 그 커밋 이후 MODE_INTRO와 상단 안내 중복을 정리하기로 했다.
- P1-9·P1-10 완료.
  - HHI title은 화면 설명 한 줄로 옮겼다.
  - 이력·실행결과의 실패 사유를 화면에 표시했다(P2-1을 앞당김).
- P1-11: HHI는 이미 "상세 지표" 접힘 안에 있었다. 남은 집중도 표기는 탭마다 의미가 달라(자산유형/종목/지수) 유지했다.
- P1-12~P1-15 완료. 처리 방식:
  - 배당 연도별 텍스트 목록은 차트에 없는 전년 대비 증감률을 담고 있어 **유지**했다.
  - 월별 달성률 표는 모바일 중첩 스크롤을 6행 + 더 보기로 바꿨다(Phase 3 항목을 앞당김).
- P1-16: 세금 추정 카드의 종합과세·건보 경고를 하나의 박스(`FinancialIncomeThresholdNotice`)로 합쳤다. 아래 두 가지는 **보류**했다.
  - `HealthInsuranceRiskCard`(한도 현황 탭)는 다른 하위 탭이라 그대로 둔다.
  - 한도 현황 탭의 각주 4개 병합.
- P1-17 완료. 처리 방식:
  - 공용 `ToggleRow`(행 전체 label)를 추가해 알림 설정 5개 토글에 적용했다.
  - 즉시 알림은 접힘 없는 카드로 바꿨다.
  - 알림 이력의 중첩 스크롤을 제거했다.
  - 설정 요약을 "N/7개 켜짐"으로 바꿨다.
  - 푸시 토글 이동은 **보류**했다. 기기 권한 설정이라 "앱 설정" 위치가 맞다고 판단했다.
- 추가: `CollapsibleSection` 기본 토글을 44px로, `CollapsibleCard`·`CollapsibleSection` 힌트를 gray-500으로 바꿨다.
- 검증: 프론트 1745 tests 통과. tsc·eslint(src)·prettier 클린.

### 홈 (`pages/DashboardPage.tsx`, `components/dashboard/*`)
- **P1-1. 수익률 3종 혼재**
  - 현황: Hero "누적 수익률"(`HeroSummaryCard.tsx:115-117`), Snapshot 평가손익 %(`InvestmentSnapshotCard.tsx:79`), 목표칩 XIRR(`InvestmentGoalCard.tsx:215`)이 한 화면에 나온다.
  - 조치: Hero 수익률 옆에 기준을 화면에 표시한다("입금 대비"처럼). Snapshot %는 "매입원가 대비"로 명시한다.
- **P1-2. 주식 평가액 3회 노출**
  - Hero 범례에서 금액을 빼고 %만 남긴다. 모바일은 범례를 Hero 하단 전폭 행으로 옮기고 `w-[136px]`·`!pr-2`·`-mr-2` 꼼수를 제거한다.
  - Snapshot 접힘 힌트는 손익으로 바꾼다.
  - 정밀도는 `fmtKrw`/`fmtKrwShort` 중 하나로 통일한다.
- **P1-3. 리밸런싱 상태 4중 노출**
  - 현황: 지금 할 일, `RebalancingStatusCard`, 시장신호 배지, 네비 점.
  - 조치: 모바일 홈의 `RebalancingStatusCard`를 1줄 상태 행(상태 + "분석하기" 링크)으로 축소한다.
- **P1-4. 챌린지 3중 노출**
  - `ChallengeProgressCard`는 같은 action item이 있으면 숨긴다.
  - `ChallengeEmptyStateCard`는 목표 카드 안 1줄 링크로 바꾼다.
- **P1-5. 지금 할 일 행 밀도**
  - `ActionItemsCard.tsx:26-37`의 CTA 텍스트 줄을 제거한다(행 전체가 링크라 chevron과 중복). 기한은 제목 옆으로 옮긴다.
  - 3개까지만 보이고 나머지는 "N개 더 보기"로 접는다.
  - 오류 시 `null` 대신 1줄 재시도를 보여준다.
- **P1-6. 라벨·문구 오류**
  - "전체 진행률" → "자산 목표 진행률"(`InvestmentGoalCard.tsx:51`)
  - "모든 목표 순항 중"에서 미설정 목표를 제외한다(`:289`).
  - `SetupTargetPortfolioBanner.tsx:30`은 문구를 줄이고 `line-clamp-2`를 적용한다.

### 리밸런싱
- **P1-7. 포트폴리오 탭 이탈 4중 노출**
  - 카드 배지와 WeightDiffBadge만 남긴다.
  - `RebalancingDiagnosisCard`는 1줄 상태로 축소한다.
  - 중복된 AutomationStatusBar(`PortfolioListSection.tsx:218` vs `AnalysisPanel.tsx:152`)는 AnalysisPanel 쪽만 남긴다.
- **P1-8. 목표 조정 반복 안내문**
  - "목표만 바꾸고 주문은 안 나가요"가 4회 나온다: `GoalAdjustTab.tsx:58-62,79-81`, `TacticalAllocationTab.tsx:211`, footer. → 1회만 남긴다.
  - 추천 결과의 리스트+도넛(`RecommendationResultPanel.tsx:81,91`)은 모바일에서 도넛을 숨긴다.
  - 매크로 배지 설명 문단은 1줄로 줄인다.
- **P1-9. MarketSignalBanner 알림 상태 footer**
  - 현재 3줄+링크가 항상 보인다(`:146-174`). 헤더 아이콘 + "알림 받는 중"으로 축소한다.
- **P1-10. 개발자 용어 정리**
  - 이력 모바일의 `order_no` 모노스페이스 → 펼침으로 이동
  - "HHI 1234" → "분산도" 라벨
  - Sortino 소수 3자리 → 2자리
- **P1-11. 집중도 표기 정리**
  - 현재 집중도 표기가 5곳이다. 탭당 1개만 남긴다: 진단 = 자산유형 집중도, 포트폴리오 = 최대 종목 비중. HHI는 상세 안으로 넣는다.

### 계획·설정
- **P1-12. 상시 안내 문단 삭제/축소**
  - 대상:
    - `InvestPlanPage.tsx:210-213,292-294`
    - `TaxPlannerSection.tsx:75-82` (4문장)
    - 시뮬레이터 안내 3회(`InvestPlanPage.tsx:357`, `SavingsSimulatorCard.tsx:83-86,282-286`): intro와 footer 삭제
  - 조치: 삭제하거나 1줄로 줄인다.
- **P1-13. 달성률·배당수익률 중복**
  - 달성률 3회(`DividendPlanSection.tsx:133,240` + 배지): hero 값만 남긴다.
  - 배당수익률 2블록(`:216-233` vs `:303-316`): 하나로 합친다.
  - 연도별 텍스트 목록(`:451-473`)은 차트와 중복이므로 삭제한다.
- **P1-14. "더 빨리 달성하려면?" 2곳**
  - 대상: `GoalTimelineCard.tsx:143-246`, `DividendPlanSection.tsx:294-345`
  - 조치: 기본 접힘으로 바꾸고 시나리오는 1개 + 더보기로 줄인다.
- **P1-15. 같은 내용 반복**
  - GoalTimeline의 "계획 대비"와 "상태" 2열(`:102-119`)을 1열로 합친다.
  - AchievementTable 면책문구 2회(`:54-57`)는 카드당 1회만 남긴다.
- **P1-16. 세금 경고·각주 중복**
  - 금융소득 2,000만원 경고(종합과세+건보)를 하나로 합친다(`TaxOptimizationCard.tsx:100-150`).
  - 건보 경고 중복(`HealthInsuranceRiskCard.tsx:102-109`)을 정리한다.
  - 한도 현황 탭의 각주 4개를 섹션 끝 1개로 합친다.
- **P1-17. 설정 정리**
  - 1개 토글뿐인 "즉시 알림" collapsible을 인라인으로 바꾼다.
  - 푸시 토글을 알림 설정 페이지로 이동한다(설정에는 링크).
  - 알림 이력 탭의 `max-h-64` 중첩 스크롤을 제거한다.

---

## Phase 2 — 실자금·오판 위험 있는 사용성 (High) — **완료(2026-10-23)**

**진행 기록**
- P2-1: Phase 1 커밋에서 처리했다.
- P2-2: `RebalancingConfirmStep`(잔고 조회·자동 조정), `RebalancingExecutionModal`(재조회), `RebalancingPriceCell`(재조회 아이콘)을 모바일 44px로 키웠다.
- P2-3: 체크박스를 44px label로 감쌌다. `{종목명} 주문 선택`·`주문 수량`·`지정가` aria-label을 달고, 라이트모드 선택 배경은 `bg-indigo-50`으로 바꿨다.
- P2-4: `ModalFooter`(`common/Modal.tsx`)를 추가해 적립 설정·배당 설정·챌린지·목표 마법사 모달 4곳의 버튼을 스크롤 본문 밖으로 옮겼다. 마법사도 함께 손봤다.
  - 2단계 "다음" 비활성 사유를 표시한다.
  - 6단계 "완료"를 보조 버튼으로 바꿨다(Phase 3 항목을 앞당김).
- P2-5: `--bottom-nav-h: 4rem`(`index.css`)을 단일 기준으로 삼았다.
  - BottomNav 항목 높이를 이 값으로 고정했다. 그 결과 Modal(avoidBottomNav), Toaster, AppLayout 하단 여백, 리밸런싱 고정 실행 바가 같은 값을 쓴다.
  - 고정 실행 바는 `bottom-16`으로 safe-area를 빼먹던 문제도 함께 해결했다.
  - Toaster: `z-[80]`, 좌우 여백, 탭하면 닫힘.
  - 주문 가능한 계좌가 없으면 고정 바에 비활성 버튼 대신 "증권계좌 연동" 링크를 보여준다.
- 검증: 프론트 테스트 전부 통과, tsc 클린.

- **P2-1. 실행 결과·이력의 실패 사유가 잘리거나 hover에만 있음**
  - 대상: `RebalancingResultSection.tsx:88`(truncate 160px), `RebalancingHistoryTab.tsx:136,186`(title)
  - 조치: 빨간 보조줄로 화면에 표시한다.
- **P2-2. 실주문 모달 터치 타겟**
  - 대상:
    - `RebalancingConfirmStep.tsx:248`(잔고 조회 약 20px)
    - `:166`
    - `RebalancingExecutionModal.tsx:89`(재조회)
    - `RebalancingPriceCell.tsx:50-55`
  - 조치: `TOUCH_TARGET_MIN_MOBILE_ONLY`를 적용한다.
- **P2-3. `RebalancingMobileCard.tsx:62-77,152` 주문 카드**
  - 체크박스 20px·라벨 없음 → 행 label + 44px로 바꾼다.
  - 수량·지정가 입력에 aria-label을 추가한다.
  - 선택 배경 `bg-indigo-950/20`을 라이트모드 색으로 고친다.
- **P2-4. 모달 sticky footer**
  - 현황: 키보드가 저장/다음 버튼을 가린다. 대상은 `InvestPlanPage.tsx:480` 편집 모달, `ChallengeFormModal.tsx:310`, `GoalSettingWizard.tsx:91`.
  - 조치: `common/Modal`에 `footer` 슬롯(sticky, `pb-[env(safe-area-inset-bottom)]`)을 추가하고 3곳에 적용한다.
- **P2-5. sticky 실행 바**
  - `RebalancingTable.tsx:211`의 `bottom-16`과 실제 네비 높이(약 66px)가 다르다.
  - 하단 네비 높이를 CSS 변수 `--bottom-nav-h` 하나로 통일하고 `Modal.tsx:35`·`Toaster.tsx:30`·sticky 바에서 공유한다.
  - Toaster는 `z-[80]`, `left-3 right-3`, 탭하면 닫히게 한다.
  - 거래 가능한 계좌가 없으면 비활성 버튼 대신 "계좌 연동" 링크를 보여준다.

---

## Phase 3 — 스크롤 길이·밀도·가독성 스윕

### 섹션 통합 / 기본 접힘
- **리밸런싱 › 포트폴리오** (`RebalancingTable.tsx:153-207`)
  - 배당·미추적·분석 시점·계좌 갱신·상세 지표를 "상세" disclosure 하나로 묶는다.
  - 포트폴리오 카드 목록은 선택된 것 1장 + "변경"으로 줄인다(목록은 바텀시트).
- **`RebalancingWeightTable` 모바일**
  - 1줄: "매수 3주 · 45만원"(text-sm)
  - 2줄: 현재→목표 %
  - 가격·수수료는 펼침으로 옮긴다.
  - WeightBar와 Diff 배지 중 하나를 제거한다.
- **계획 › 적립 계획**
  - DCA 차트를 모바일 240px로 줄인다.
  - AchievementTable 월별 `max-h-[360px]` 중첩 스크롤을 제거하고 6행 + 더보기로 바꾼다.
- **계획 › 절세**: 플래너는 자동 펼침을 끄고 "손실수확 가능" 배지만 보여준다(`TaxOptimizationCard.tsx:38`).
- **중첩 스크롤 제거**:
  - `TransactionHistoryTab.tsx:268`(70vh, window virtualizer로 전환)
  - `AllocationHistoryChart.tsx:162`
  - `RecommendationComparisonPreview.tsx:72`
- **이력 탭**: 플랜 30·실행 50개를 한 번에 그린다 → 10개 + 더보기로 바꾼다.
- **홈**:
  - `space-y-3 sm:space-y-6`
  - Snapshot 모바일 2열 + 평가손익 전폭
  - `.card` 모바일 `p-4`
  - 스켈레톤을 실제 카드 모양에 맞춘다

### 탭 위계 (1단 pill / 2단 underline / 3단 segmented)
- `AccountHistoryTab.tsx:40` pill → segmented
- `DividendTab.tsx` 3단에 pill(종목별/월별) → segmented

### 가독성 일괄
- **차트 글자 크기**: `CHART_TICK_FONT_SIZE = 12` 상수를 신설하고 `fontSize: 11` 사용처 6파일과 `TreemapCell` 10/11px를 바꾼다. `MonthlyDividendChart`의 `#9CA3AF` 색도 고친다.
- **저대비**: 중요 라벨의 `text-gray-400` → `text-gray-500 dark:text-gray-400`. 대상은 Hero·Snapshot·Goal·온보딩·Collapsible 힌트·세금 섹션 제목 4곳(`text-sm font-semibold`).
- **목표 앞섬 색**: 빨강 → 에메랄드(`InvestmentGoalCard.tsx:78,247,435,517`).
- **원시 market 코드**: `utils/`에 `marketLabel()`을 신설하고 StockHoldingsTable·PeriodPurchasesTab·DividendTab·PositionsTable·PortfolioItemRow에 적용한다.
- **모바일에서 숨김·잘림 해제** (`break-keep`·`flex-wrap` 적용):
  - `GoalTimelineCard` 예상 달성일
  - `TaxPlannerSection`·`TaxOptimizationCard:64`의 `hidden sm:inline`
  - DividendTab 3열 라벨
  - TaxOptimization 공식
  - AutoInvestStatusBanner
  - ChallengeCard 제목
  - Pension 합산 한도
  - DCAProjectionChart·TaxPlannerSection 헤더
- **고정폭 그리드 조정**:
  - SavingsSimulator 프리셋 → `grid-cols-2`
  - InvestPlanPage 펼침 → `grid-cols-3` 대신 2열
  - 환율·주가 알림 폼 → `grid-cols-2`
  - `w-36` 입력 → `flex-1`
  - ChallengeMonthGrid → 최근 12개월 + 연도 + 금액 표시
- **StockAccountCard**: 예수금 칸의 연필을 제거한다(⚙과 같은 `onEdit`).

### 터치 타겟 일괄 (`TOUCH_TARGET_MIN_MOBILE_ONLY` 재사용)
- 홈:
  - 온보딩 CTA
  - "분석하기"
  - 목표 토글
  - CollapsibleSection
  - AmountUnitButtons
  - RiskMetricsCard 헤더
- 각종 "다시 시도"
- 계획·설정·인증:
  - 마법사 "채우기"
  - `TaxPositionTable` QtyInput
  - 알림 재활성화·추가·검색 결과
  - NotificationEmailSection
  - DividendPlanSection 링크
  - "내역 추가"
  - 인증 페이지 하단 링크
- 리밸런싱:
  - RebalancingAccountSyncSection 버튼
  - RebalancingDividendSection 토글
  - MarketSignalBanner 설정 링크
- 인증 페이지 레이아웃: wrapper `px-4`, 카드 `p-6 sm:p-8`.

### hover 전용 정보 → 탭 가능
- `common/InfoTip`을 신설한다. 탭하면 팝오버, 바깥 탭이나 Esc로 닫는다. 기존 `Tooltip.tsx`는 hover 전용이라 대체한다.
- 대상:
  - Hero 금액·수익률 기준
  - Snapshot
  - "점검 권장" 사유
  - PortfolioListSection 미니바
  - HHI
  - Sharpe/Sortino
  - SettingsPage 알림 요약(`max-w-[50%]` 대신 줄바꿈)
- `ToggleSwitch` 행 전체를 label로 만든다(44px 행). 설정 토글 3패턴은 스위치 하나로 통일한다.

### 기타
- `AlertAutoModeSection.tsx:284`에 `inputMode`를 추가한다.
- 마법사 2단계 "다음" 비활성 사유를 표시한다. 6단계 "완료"는 보조 버튼으로 바꾼다.
- 클릭 가능한 `div`(`PortfolioListSection.tsx:108`, `RebalancingStatusCard.tsx:54` 중첩 버튼)를 `button`/role로 바꾸고 중첩을 해소한다.

## Phase 4 — 실기기 확인 후 (계획 53 Phase D 유지)
- safe-area-inset-top
- `h-screen` → `h-dvh`
- 모달 스크롤 잠금 대상 `<main>`
- 키보드 `interactive-widget`
- 뒤로가기 동작
- 일부(sticky footer)는 P2-4에서 먼저 처리한다.

---

## 재사용
- 공용 컴포넌트:
  - `common/SegmentedControl`
  - `common/ConfirmModal`
  - `common/CollapsibleCard` / `CollapsibleSection`(상태 key 패턴)
  - `common/Modal`(`useModalBehavior`)
- 상수: `TOUCH_TARGET_MIN_MOBILE_ONLY` / `TOUCH_TARGET_MIN`
- 함수: `fmtKrw`·`fmtKrwShort`
- 패턴: StockAccountCard의 탭→토스트, AllocationCard의 모바일 기본 접힘+기억 패턴

## 검증
- Phase마다 `make lint`, `make typecheck`, `make test-frontend`(커버리지 임계) 실행.
- 변경 동작별 테스트 추가: 접힘 기본값, 중복 제거 후 1회만 렌더, InfoTip 탭 열림/닫힘, Modal footer, marketLabel 유닛.
- 390px 시각 확인: `npm run dev` 후 Playwright로 모바일 뷰포트 스크린샷을 찍는다(홈·자산·리밸런싱 포트폴리오·계획 적립/절세·설정). 로그인 가능한 seed가 없으면 그 사실을 보고한다.
- 홈과 리밸런싱 포트폴리오 탭은 전후 `document.scrollHeight`를 비교해 길이가 줄었는지 확인한다.
- 파일을 추가하면(InfoTip, marketLabel, 차트 상수) `frontend/CLAUDE.md`의 목록을 갱신하고, `docs/plans/README.md` 상태표도 갱신한다.
