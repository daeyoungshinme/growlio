# 모바일 최적화 재감사·수정 계획 (docs/plans/102)

## Context
모바일 라운드(53·58·67·72·79)를 여러 번 거쳐 기본기는 갖춰졌다. viewport `interactive-widget`, `h-dvh`, safe-area, `--bottom-nav-h`, Android 뒤로가기, lazy 청크, 가상 스크롤, `inputMode` 63/63이 모두 들어가 있다. 그래서 이번 감사(셸·공통 / 홈·자산·계획·설정 / 리밸런싱 3영역, 코드 리딩 390px 기준)에서 남은 것은 아래 다섯 축이다.
1. **모달 구조 결함**: `Modal`이 스크롤 본문을 호출자에게 맡긴다. 그래서 일부 폼은 아예 스크롤이 안 되고, 저장 버튼이 키보드에 가린다.
2. **터치에서 안 보이는 정보**: `title`에만 있는 정보와 hover 전용 `Tooltip`.
3. **작은 터치 타겟과 규칙 위반 누적**: 인라인 `min-h-[44px]` 44건, 백테스트 칩 약 24px.
4. **67에서 보류된 구조 항목**: 포트폴리오 바텀시트, 탭 4단 중첩.
5. **네이티브 셸 잔여**: 인증 페이지 safe-area, 키보드, 뒤로가기 판정.

목표는 이 다섯 축을 정리해 "실주문·입력·숫자 읽기" 동선에서 막히는 곳을 없애는 것이다.

## 0. 계획서 저장
- 이 내용을 `docs/plans/102-mobile-optimization-2026-10-31.md`로 저장한다.
- `docs/plans/README.md` 인덱스에 행을 추가하고, 67 행에 "잔여 → 102"을 적는다.
- 브랜치: `chore/mobile-optimization-2026-10-31`.

---

## Phase A — 막히는 버그 (최우선, 저위험)
**A1. `Modal`에 `ModalBody` 추가**
- 위치: `components/common/Modal.tsx`. 형태: `flex-1 overflow-y-auto px-6 py-4 min-h-0`.
- 아래 모달들을 `ModalBody` + `ModalFooter` 구조로 전환한다.
  - `assets/TradeFormModal.tsx:172`: 현재 스크롤 자체가 안 된다(확인함). 저장 버튼은 footer로 옮기고, 기록 목록은 본문 안에 둔다. `<form id>` + footer 버튼에 `form=` 속성을 쓴다.
  - `assets/BankAccountModal.tsx:257`, `assets/TransactionModal.tsx:302`
  - `assets/realEstate/RealEstateAccountModal.tsx:218`, `RealEstateEditModal.tsx:214`
  - `settings/ChangePasswordModal.tsx`, `settings/DeleteAccountModal.tsx`
  - `rebalancing/GoalRecommendationOptionsModal.tsx:300`(28px 버튼), `RebalancingAlertModal`, `GoalCandidateManagerModal` 확인
  - `StockAccountModal.tsx:409`, `StockPositionsModal.tsx:242`: 자체 footer를 `ModalFooter`로 바꿔 하단 safe-area를 확보한다.
- 기존 `ModalFooter` 사용처(`ChallengeFormModal`·`GoalSettingWizard`·`TacticalApplyConfirmModal`·`InvestPlanPage`)의 본문 래퍼도 `ModalBody`로 통일한다.

**A2. `ConfirmModal` 확인 버튼 고정**
- `common/ConfirmModal.tsx:42`: `children`은 `ModalBody`에, 버튼은 `ModalFooter`에 둔다. 비교표처럼 긴 내용이 확인 버튼을 밀어내지 않게 한다.

**A3. 효율 분석 가로 넘침**
- `rebalancing/RebalancingStrategyCard.tsx:88`: `grid-cols-2` → `grid-cols-1 sm:grid-cols-2`. 고정폭 합이 약 185px인데 칸은 약 150px뿐이다.

**Phase A 결과 (2026-10-31, 완료)**
- `ModalBody`를 신설했다.
- `ModalBody`+`ModalFooter`로 전환: TradeFormModal(스크롤 불가 해소, `form=` 연결), BankAccount, RealEstate 2종, ChangePassword, DeleteAccount
- 버튼만 `ModalFooter`로 이동(28→44px): GoalRecommendationOptions, GoalCandidateManager
- 그 외 모달
  - StockAccountModal: 자체 footer를 `ModalFooter`로 교체
  - StockPositionsModal: 세로 배치를 유지하고 safe-area 패딩과 44px만 적용
  - TransactionModal: 폼이 `shrink-0`이라 잘리던 문제 → 폼과 목록을 한 스크롤 영역으로 합침. 추가 버튼은 목록 위에 두는 게 자연스러워 footer로 옮기지 않음
- **변경하지 않음**
  - RebalancingAlertModal: 이미 `sticky bottom-0` 저장 바가 있다.
  - 기존 `ModalFooter` 사용처 4곳의 본문 래퍼: 패딩(`pt-2 pb-6`)이 달라 `ModalBody`로 통일하면 시각이 바뀐다. 동작 문제가 없어 보류했다.
- A2 ConfirmModal: 본문만 스크롤하고 버튼은 고정했다.
- A3 효율 분석: 모바일 1열로 바꿨다.
- 검증: 프론트 1915 tests(+2), lint·format·typecheck 클린. 390px 실브라우저는 미확인.

## Phase B — 터치에서 안 보이는 정보
**B1. `common/InfoTip` 신설**
- 탭하면 팝오버가 열리고, 바깥 탭이나 Esc로 닫힌다. 뷰포트 경계 안으로 클램프한다.
- 기존 `Tooltip.tsx`(hover 전용) 사용처 3곳을 대체한다: `StockAccountTaxFields:50`, `BacktestMetricsTable:27`, `RegionAllocationView:79`.
- 대체 후 사용처가 없으면 `Tooltip.tsx`를 삭제하고 `frontend/CLAUDE.md` common 목록을 갱신한다.
- 설명이 빠진 지표에도 붙인다: `RebalancingStrategyCard:168` Sharpe, `TacticalBacktestSection:119` 샤프, 백테스트 모바일 카드의 CAGR·MDD.

**B2. `title`에만 있는 정보를 화면에 표시하거나 탭→토스트로**
- 패턴은 `StockAccountCard.tsx:99` 재사용.
- 잘린 금액: `StockAccountCard.tsx:199-243`(3열 + truncate → 모바일 2열 + 예수금 전폭 검토), `InvestmentSnapshotCard.tsx:51,61,75`, `HeroSummaryCard.tsx:115`, `DividendTab.tsx:183-211`
- 비활성 사유: `RebalancingTable.tsx:148`, `alertModal/AlertActionsSection.tsx:99` → 버튼 아래에 작은 안내문으로 표시
- 미니바: `PortfolioListSection.tsx:154,163` → InfoTip 또는 범례 텍스트
- 버튼 설명: `UnifiedPortfolioEditor.tsx:295,308`, `PortfolioPage.tsx:269`, `AutomationStatusBar.tsx:41`, `AnalysisPanel.tsx:144`, `PortfolioListSection.tsx:217`(기준 지정 의미)
- `TaxPositionTable.tsx:83`: 원시 `pos.market` → `marketLabel()`

**Phase B 결과 (2026-10-31, 완료)**
- B1 `common/InfoTip`을 신설했다. 탭으로 열리고, 바깥 탭·Esc·스크롤로 닫힌다. 뷰포트에 맞춰 위치를 조정하고, Esc는 캡처 단계에서 처리해 모달보다 먼저 닫힌다.
  - `Tooltip.tsx` 사용처 3곳을 대체하고 Tooltip은 삭제했다.
  - Sharpe(효율 분석·전술 백테스트)에 붙였다.
  - 백테스트 모바일 카드에는 CAGR·MDD 한 줄 설명을 화면에 표시했다.
- B2 처리 내역
  - StockAccountCard: 모바일 2열 + 예수금 전폭으로 바꾸고, `fmtKrw` 전체 값을 표시해 truncate·title을 없앴다. 예수금 연필은 제거했다(C4 선반영).
  - InvestmentSnapshotCard: `fmtKrw`로 바꿨다. DividendTab: truncate → break-keep.
  - 비활성 사유
    - 리밸런싱 실행(데스크톱): 기존 안내문에 합쳤다.
    - 알림 "지금 계획 생성": 이미 화면 문구가 있어 title만 제거했다.
    - 투자현황 수동 계좌 "갱신": `aria-disabled` + 누르면 토스트.
  - 포트폴리오 카드: 미니바 구성을 상위 3개 글로 표시했다. 기준 지정 버튼은 상태별 aria-label로 바꿨다. 수정/삭제는 44px로 키웠다(C2 선반영).
  - 분석 패널 실시간 재분석 아이콘에 "실시간" 라벨을 붙였다.
  - TaxPositionTable: `marketLabel()`을 적용했다.
- **유지**
  - HeroSummaryCard 원 단위 title: 같은 값의 이중 표기라 U1 결정대로 둔다.
  - UnifiedPortfolioEditor 버튼 2개의 title: 라벨만으로 의미가 전달되어 보조 설명으로 남긴다.
- 검증: 프론트 1916 tests(Tooltip 테스트 5건 제거·InfoTip 6건 추가), lint·format·typecheck 클린.

## Phase C — 터치 타겟·규칙 스윕 (기계적)
**C1. 인라인 `min-h-[44px]` 44건 → `constants/uiSizes.ts` 상수**
- 대표 파일: `ActionItemsCard`, 인증 페이지 링크, `SettingsPage:265,273`, `InvestPlanPage`, `DividendPlanSection`, `RebalancingDividendSection`, `CollapsibleSection`, `ToggleSwitch`
- 44px 미만 인라인: `RebalancingAccountSyncSection:98,113,123`(40px), `TaxPositionTable` QtyInput(40px), `GoalCandidateManagerModal:166`(`min-h-9`)
- 작업 후 grep으로 `min-h-\[44px\]`가 `uiSizes.ts` 외 0건인지 확인한다.

**C2. 리밸런싱 소형 버튼**
- 백테스트: 기간 칩, 전체 선택/해제, 체크박스 행(`BacktestTab.tsx:68-185`)
- 차트 보기 칩 → `SegmentedControl`(`BacktestResultChart.tsx:145`)
- 실행 모달
  - 시장가/지정가 토글(`RebalancingExecutionModal.tsx:48`) → `SegmentedControl`
  - 취소 버튼(`RebalancingExecutionModal.tsx:132`)
  - 주문 방식 버튼(`RebalancingConfirmStep.tsx:62`)
  - 재조회(`RebalancingOrderRows.tsx:97`)
  - 매수 종목 추가 select(`RebalancingConfirmStep.tsx:291`)
- "동기화하고 다시 분석"(`RebalancingTable.tsx:113`)
- 다시 시도: `AnalysisPanel.tsx:174,214`, `RecommendationCard.tsx:340`
- 포트폴리오 수정/삭제 36→44px(`PortfolioListSection.tsx:177,187`)
- 모바일 카드에도 "호가단위로 보정" 안내 표시(`RebalancingPriceInput.tsx:55`)

**C3. 토글 통일**
- `MarketSignalAlertSection.tsx:37,63`, `ChallengeFormModal.tsx:301`, `SettingsPage.tsx:315-363` → `ToggleRow`(행 전체가 탭 영역)

**C4. 공용화·잔여 규칙**
- `SegmentedControl`을 `portfolio/allocation/` → `common/`으로 옮긴다. 사용처 11곳 import 갱신, CLAUDE.md 목록 갱신.
  - 기계적 리네임 시 import source를 반드시 확인한다(lucide/recharts 동명 export 함정).
- `RebalancingWeightTable.tsx:25` `text-[11px]` → `text-xs`
- 인라인 로딩 → `SkeletonCard`(`PortfolioExecutionTab.tsx:68`, `RebalancingHistoryTab.tsx:377`)
- `AllocationHistoryChart.tsx:215`의 `<tr onClick>` → 행 안 `button`(44px, 키보드 지원)
- 중첩 버튼 해소: `RebalancingStatusCard.tsx:35-77`(Space 키 preventDefault 포함), `PortfolioListSection.tsx:108-129`
- 고정폭 3열 정리
  - 입력이 든 곳: `ChallengeFormModal:159`, `AlertScheduleSection:19`, `TacticalWeightsEditor:244`
  - 긴 금액이 든 곳: `SavingsSimulatorCard:209,221`, `DcaOutlook:153`, `DividendPlanSection:149`
  - 처리: `grid-cols-2 sm:grid-cols-3` 등으로 바꾼다.
- 환율·주가 알림 폼 `flex-wrap min-w` → `grid grid-cols-2`(`ExchangeRateAlertSection:77`, `StockPriceAlertSection:122`)
- `StockAccountCard.tsx:219` 예수금 연필 제거(⚙과 같은 `onEdit`, 67 결정 완결)
- `Tabs` underline 변형 가로 스크롤에 끝 페이드 힌트 추가(`Tabs.tsx:55`)

**Phase C 결과 (2026-10-31, 완료)**
- C1: 인라인 `min-h-[44px]`는 실제로 46건이었다.
  - 대부분 전폭 버튼·링크·입력처럼 높이만 필요한 곳이었다. 기존 `TOUCH_TARGET_*`는 `min-w`와 flex 정렬까지 붙여서, 그대로 치환하면 레이아웃이 바뀐다.
  - 그래서 `TOUCH_HEIGHT_MIN`/`TOUCH_HEIGHT_MIN_MOBILE_ONLY`를 신설했다. 46건과 `inputStyles` 2건을 치환했다.
  - 40px이던 계좌 동기화 버튼 3개와 세금 수량 입력은 44px로 올렸다.
  - `GoalCandidateManagerModal` select는 이미 36px(`min-h-9`)이라 유지했다. 컴팩트 상수를 쓰면 select에 flex가 붙는다.
- C2
  - 백테스트: 칩·전체 선택은 36px, 체크박스 행·날짜 입력은 모바일 44px로 키웠다. 차트 보기는 `SegmentedControl`로 바꿨다.
  - 실행 모달: 시장가/지정가, 주문 방식, 취소, 매수 종목 추가 select, 재조회, 지정가·수량 입력을 44px로 키웠다.
  - "다시 시도" 3곳도 44px로 키웠다.
  - 시장가/지정가는 `SegmentedControl`(36px 칩)로 바꾸면 오히려 작아진다. 그래서 기존 버튼에 44px와 `aria-pressed`만 붙였다.
  - 호가단위 안내는 이미 모바일에도 보이고 있었다.
- C3
  - 시장신호 알림 2개와 챌린지 알림을 `ToggleRow`로 바꿨다.
  - 설정의 생체 인증·푸시 행은 유지했다. 이미 행 전체가 44px 버튼이고 `aria-pressed`가 있으며, 아이콘 메뉴 목록의 일부다.
- C4
  - `SegmentedControl`을 `common/`으로 옮겼다(11곳).
  - 월별 자산 표 행에 키보드로 펼칠 수 있는 월 버튼을 넣었다.
  - 진단 포트폴리오 행: Space로 페이지가 스크롤되던 것과, 안쪽 버튼의 키 입력이 행까지 전파되던 것을 고쳤다.
  - 알림 폼을 2열 그리드로 바꿨다. underline `Tabs`에는 끝 페이드를 넣었다.
  - `SkeletonCard` 2곳, `text-[11px]` 1곳을 고쳤다.
  - **유지**
    - `PortfolioListSection` 중첩 버튼: 이미 target 확인과 preventDefault가 되어 있었다.
    - 고정 3열 6곳: `fmtKrw`가 축약형(최대 "9,999만원"·"12.34억원")이라 390px 3열에 들어간다. `DcaOutlook`은 데스크톱 전용이다.

## Phase D — 구조 개선 (중위험, 별도 커밋)
**D1. 리밸런싱 › 포트폴리오: 포트폴리오 목록 → "선택 1장 + 변경(바텀시트)"** (67 보류분)
- 모바일(`!useIsSmUp`)에서만 적용한다. 바텀시트는 기존 `Modal`(모바일 바텀시트 동작)을 재사용하고 새 컴포넌트는 만들지 않는다.
- 선택 상태는 `useSelectedPortfolio`/URL `portfolioId`를 그대로 쓴다. 생성 버튼은 시트 안에 둔다.
- 대상: `PortfolioListSection.tsx:420-449`, `RebalancingPage.tsx:262`

**D2. 탭 4단 → 3단**
- 전술 백테스트 차트 칩과 백테스트 결과 차트 칩은 차트 카드 내부 `SegmentedControl`(C2)로 흡수한다.
- `TacticalBacktestSection.tsx:90`의 segmented는 접힘 섹션 제목 행으로 내린다.

**D3. 백테스트 차트 모바일**
- `BacktestResultChart.tsx:141,181`: 모바일 x축 interval을 약 5개 라벨로, 높이 240으로 줄인다. 범례는 차트 아래 줄바꿈 리스트로 뺀다.

**D4. 모바일 카드 없는 표**
- `TacticalStatusParts.tsx:148`(overflow-x 없음 → 카드/2열 행), `TacticalBacktestSection.tsx:113`, `AllocationHistoryChart.tsx:180`
- `AchievementTable.tsx:122` 데스크톱 `max-h` 중첩 스크롤 → "더 보기"

**D5.** `RebalancingAccountSyncSection`을 분석 "상세" disclosure 안으로 옮긴다(`AnalysisPanel.tsx:202`).

**Phase D 결과 (2026-10-31, 완료)**
- D1
  - 모바일에서 포트폴리오가 2개 이상이면 선택 카드 1장과 "다른 포트폴리오 보기 (N개)"만 보인다. 누르면 `Modal` 시트에 기존 목록(드래그 포함)이 열린다.
  - 시트에서 고르기·수정·자동화 설정을 누르면 시트가 닫힌다. 삭제는 확인창이 위에 뜨므로 시트를 유지한다.
  - 선택 카드에는 순서 핸들을 그리지 않는다. 생성 버튼은 헤더에 그대로 두었다.
- D2: 기간 `SegmentedControl`은 유지했다. CollapsibleCard 헤더 전체가 토글 버튼이라 안에 넣으면 버튼이 중첩된다. 차트 칩은 C2에서 이미 흡수했다.
- D3: 모바일 차트 높이를 240으로, x축 라벨을 약 5개로 줄였다. 범례는 Recharts 기본 줄바꿈을 그대로 쓴다.
- D4
  - `AchievementTable` 데스크톱의 `max-h` 내부 스크롤을 없앴다. 대신 최근 12행과 "더 보기"를 두고, 모바일과 상태를 공유한다.
  - `WeightsCompare`·전술 백테스트 표·월별 자산 표는 유지했다. 3~4열에 값이 짧고, 넘칠 수 있는 곳에는 이미 `overflow-x-auto`가 있다.
- D5: 계좌 데이터 갱신을 `RebalancingTable`의 "상세 정보" 안으로 옮겼다. 접힌 상태에서도 부제에 "계좌 갱신"이 보인다.

## Phase E — 네이티브 셸 (실기기 확인 필요)
- **E1. 인증 페이지 safe-area**
  - 대상: `LoginPage:39`, `RegisterPage:89`, `ResetPasswordPage:60,117`, `FindAccountPage:31`, `ForgotPasswordPage:30`, `AuthCallbackPage:97`, `RebalancingPlanConfirmPage:112`
  - 처리: `min-h-screen min-h-dvh` + `pt-[env(safe-area-inset-top)]`. 공용 `AuthLayout` 래퍼 하나로 묶는다.
- **E2. 뒤로가기 판정**
  - 현재 `AppLayout.tsx:46`은 `body.style.overflow` 값으로 모달 여부를 판정한다.
  - `useModalBehavior`의 모달 스택에서 `hasOpenModal()`을 export해 대체한다.
- **E3. 키보드**
  - `AndroidManifest.xml`에 `android:windowSoftInputMode="adjustResize"`를 명시한다.
  - 전역 `focusin` 처리: 입력이 `visualViewport` 아래에 있으면 `scrollIntoView({block:"center"})`. `AppLayout`에 한 번만 등록한다.
  - `@capacitor/keyboard` 의존성은 추가하지 않는다.

**Phase E 결과 (2026-10-31, 코드 완료 — 실기기 미확인)**
- E1: `layout/AuthLayout`을 신설했다(safe-area 상하 + `min-h-dvh`). 인증 페이지 6개(재설정은 2분기)와 계획 확인 페이지에 적용했다. 모두 AppLayout 밖이라 패딩이 두 번 들어가지 않는다.
- E2: `useModalBehavior`에 `hasOpenModal()`을 추가했다. 뒤로가기(`AppLayout`)와 스와이프(`useSwipeNavigation`) 판정을 이것으로 바꿨다.
- E3: 매니페스트에 `adjustResize`를 넣었다. `hooks/useRevealFocusedInput`을 AppLayout에 한 번 등록했다. 포커스 후 `SCROLL_INTO_VIEW_DELAY`가 지나서도 입력이 `visualViewport` 아래에 있으면 `block:center`로 올린다.
- 검증
  - 프론트 1928 tests(+12), lint·typecheck 클린
  - 규칙 grep 0건: `min-h-[44px]`(uiSizes 제외), `text-[10/11px]`, 옛 SegmentedControl 경로, overflow 판정, Tooltip import
- 확인하지 못한 것
  - 390px 실브라우저: Playwright 미설치이고 로그인 seed가 없다.
  - Android 실기기: 상태바 겹침, 키보드가 입력을 가리는지, 모달 위 뒤로가기.

---

## 재사용
- `Modal`/`ModalFooter`/`useModalBehavior`, `SegmentedControl`, `ToggleRow`, `CollapsibleSection`, `SkeletonCard`
- `constants/uiSizes.ts` 상수 4종, `useIsSmUp`, `marketLabel()`, `fmtKrw`
- 탭→토스트 패턴(`StockAccountCard.tsx:99`)

## 검증
- Phase마다 `make lint`, `make typecheck`, `make test-frontend`(커버리지 임계)를 실행한다.
- 테스트 추가
  - `ModalBody`/`ModalFooter` 렌더 구조
  - `InfoTip` 탭 열림, 바깥 탭·Esc 닫힘
  - `ConfirmModal` footer
  - 모바일 포트폴리오 바텀시트 선택 → URL `portfolioId` 반영
  - `hasOpenModal` 뒤로가기 분기
- 규칙 grep 0건 확인
  - `min-h-\[44px\]`(uiSizes 제외)
  - `text-\[1[01]px\]`
  - 정보성 `title=`(Sidebar 데스크톱 제외)
  - `Tooltip` import
- 390px 시각 확인: `npm run dev` 후 Playwright 모바일 뷰포트로 확인한다.
  - 대상: 매매 기록 모달 스크롤, 효율 분석, 리밸런싱 포트폴리오, 백테스트
  - 로그인 seed가 없으면(운영 Supabase 제약, 53·67과 동일) 미수행 사실을 보고한다.
- Phase E는 Android 실기기에서 확인한다: 상태바 겹침, 키보드가 입력을 가리는지, 모달 열린 상태 뒤로가기.
