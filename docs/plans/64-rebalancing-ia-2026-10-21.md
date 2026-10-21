# 리밸런싱 탭 메뉴 구조·중복 정보 재편 계획 (계획 64)

## Context
요청: 리밸런싱 탭의 구조, 중복된 정보, 전체 메뉴 구조를 검토하고 개선 계획을 세운다.
지금까지의 감사는 축이 달랐다. 62는 코드(버그·죽은코드), 63은 숫자·흐름(같은 개념을 같은 소스로)을 다뤘다. 이번 64는 **메뉴·화면 배치(IA)** 축이다. Explore 2개(탭별 화면 트리 / 앱 전체 메뉴·딥링크·타 페이지 중복)로 조사했다.

**현재 구조와 문제**
- 페이지 탭 5개: 진단·추천·전술·포트폴리오·이력 (`pages/RebalancingPage.tsx:39`).
- **추천과 전술은 둘 다 "목표 비중 자체를 바꾸는 제안"인데 별도 탭**이다. 각 탭이 대상 포트폴리오 선택기를 따로 가진다(`RecommendationApplySection.tsx:43-57`, `TacticalAllocationTab.tsx:407-420`). URL이 비어 있을 때 기본값도 서로 달라서(추천=첫 기준 포트폴리오, 전술=첫 포트폴리오, 포트폴리오 탭=선택 없음) 탭마다 다른 포트폴리오가 보인다.
- **핵심 루프(진단 → 포트폴리오에서 분석·실행)가 탭 1번과 4번에 떨어져 있다.**
- **포트폴리오 탭에 너무 많은 것이 몰려 있다.** 목록, 분석·실행(약 6단 깊이), 하단 백테스트 카드, 알림 모달이 모두 여기에 있다. 같은 동작의 진입점도 중복된다.
  - 실행 버튼 3개: `RebalancingDiagnosisCard` "지금 실행하기", 데스크톱 버튼, 모바일 고정 버튼.
  - 동기화 진입점 3개.
  - 자동화 상태 3중: 목록 상단 배너, 카드 칩, AnalysisPanel 상태바.
- 분석 모드 전환("리밸런싱 분석/효율 분석")이 segmented가 아니라 버튼 모양이다. 다중선택 잔재(`selectedIds`, "외 N개 선택됨")와 도달 불가 빈 상태도 남아 있다.
- 알림 설정 페이지에 전술 "국면 전환 알림"만 없다(전술 탭 안의 토글이 유일).
- 계획 63 P3-4의 미완 딥링크:
  - 리밸런싱 이메일이 여전히 진단 탭으로 간다(`email_service.py:132`).
  - `insight_service.py:232,244`의 링크에 `rtab`이 없다.
- 이력 탭에 낡은 문구가 있다: "진단 탭에서 다시 분석"(`RebalancingHistoryTab.tsx:356`).

**진행 상황 (브랜치 `refactor/rebalancing-ia-2026-10-21`)**
- S1 완료(e5734852): 탭 4개·`rebalancingUrl`·링크 15곳·백엔드 이메일/인사이트 링크. 추가: 전술 국면 푸시(`tactical_regime`)가 매핑이 없어 눌러도 첫 화면에 머물던 것 → 목표 조정 › 전술. 링크는 퍼센트 인코딩(공백 `%20`)이라 테스트는 `decodeURIComponent`로 비교.
- S2 완료. 계획 대비 변경: 단기·중기·장기는 select가 아니라 segmented의 항목으로 유지(최대 5개, 한 번 더 누르지 않아도 됨), **세제유형만 select** — 그래도 탭 위계는 3단. 포트폴리오 0개면 추천은 "새 포트폴리오 만들기"가 필요해 탭 전체 빈 상태로 바꾸지 않고, 전술은 기존 빈 상태 유지. `SegmentedControl`은 이미 여러 도메인이 import 중이라 이동하지 않음.
- S3 완료. 계획 대비 변경: S3-4(동기화 진입점)는 이미 세 곳 모두 공용 `useSyncAccounts`를 써서 변경 없음. 기본 선택으로 열린 경우 분석 결과로 자동 스크롤하면 탭을 열자마자 화면이 튀어서, 결과 스크롤은 URL로 직접 고른 경우만(`scrollToResult`). "리밸런싱 분석" 버튼이 겸하던 재분석은 segmented 옆 "다시 분석" 아이콘으로. 백테스트 보기는 포트폴리오별로 파생(`backtestFor`)해 포트폴리오를 바꾸면 리밸런싱 분석으로 돌아간다.
- S4 완료. 계획 대비 변경: 전술 국면 알림은 포트폴리오별 설정인데 목록 API가 없어(포트폴리오마다 `GET /tactical/{id}` N회) 알림 설정에는 상태 행 대신 **설정 위치 안내 + 딥링크**만 둠. 진단 인사이트 라벨은 "전체 자산 진단"(진단 탭·홈 공용 `RebalancingStatusCard`) / "이 포트폴리오 진단"(`RebalancingDiagnosisCard`).

**사용자 결정(2026-10-21)**
- 추천과 전술을 하나의 탭으로 합쳐 탭을 4개로 줄인다.
- 백테스트는 분석 모드의 세 번째 항목으로 옮긴다.

**지킬 규칙**
- 탭 위계(계획 50): 1단 pill, 2단 underline, 3단 segmented. 4단은 금지한다.
- 같은 개념은 같은 소스에서 가져온다(계획 63 P1). 그 기준을 바꾸지 않는다.
- 브랜치: `fix/rebalancing-diagnosis-tactical-roles`(f57ae8d)에서 새 브랜치 `refactor/rebalancing-ia-2026-10-21`를 딴다. 착수 전에 `git status`와 `git diff`로 다른 세션의 작업이 있는지 확인한다.
- 실행의 첫 단계로 이 계획을 `docs/plans/64-rebalancing-ia-2026-10-21.md`에 저장하고, `docs/plans/README.md` 인덱스에 추가한다.

---

## 목표 구조
```
리밸런싱 (pill 4개)
├─ 진단        전체 현황: 이탈 행 → 포트폴리오 탭 · 시장신호(배지+1줄) · 위험지표(접힘)
├─ 포트폴리오  목록(선택) → [리밸런싱 분석 | 효율 분석 | 백테스트] segmented → 실행 모달
├─ 목표 조정   대상 포트폴리오 선택기 1개(공용) + [추천 | 전술] underline
│              추천: [전체 | 연령대 | 기간별] segmented — 기간·세제는 select(탭 아님)
│              전술: 국면·제안 비중 · 비중표 편집 · 규칙 백테스트
└─ 이력
```
목표 조정 탭의 단 수: 페이지 pill(1) → 추천/전술 underline(2) → 전체/연령대/기간별 segmented(3). 기간·세제 칩 2줄은 select 1개로 바꿔 탭 단에서 뺀다. 이렇게 해야 4단 금지 규칙을 지킨다.

---

## 배치 S1 — 탭 재편 + 딥링크 호환 (먼저, 한 커밋)
1. **URL 상태를 한 곳으로 모은다(62 E4를 여기서 흡수).** 새 파일 `utils/rebalancingUrl.ts`를 만든다.
   - 내용:
     - `REBALANCING_TABS = ["진단","포트폴리오","목표 조정","이력"]`
     - `GOAL_MODES = ["추천","전술"]`
     - `rebalancingUrl({ tab, mode?, portfolioId?, openAlert?, openExecution?, openRecOptions? })` 빌더
     - `parseRebalancingTab(searchParams)`: 예전 값 `rtab=추천` / `rtab=전술`을 `{tab:"목표 조정", mode}`로 매핑한다. 이미 발송된 이메일·푸시 링크를 살리기 위해서다.
   - 새 훅 `hooks/useRebalancingUrlState.ts`가 `setSearchParams` 복붙 4곳(`RebalancingPage.tsx:57-112`)을 대체한다. 새 쿼리 파라미터는 `gmode=추천|전술`이다.
2. **`RebalancingPage.tsx`를 고친다.**
   - 탭 배열을 위 4개로, 순서를 진단·포트폴리오·목표 조정·이력으로 바꾼다. 스와이프 순서도 따라 바뀐다.
   - 추천과 전술 렌더 분기를 새 `components/rebalancing/GoalAdjustTab.tsx` 하나로 합친다.
   - 진단 탭의 `onOpenTactical`은 `{tab:"목표 조정", mode:"전술"}`로 보낸다.
3. **링크 생성부를 모두 빌더로 바꾼다.**
   - 프론트 약 15곳:
     - `DashboardPage.tsx:70,207`
     - `SetupTargetPortfolioBanner.tsx:33`
     - `AutoInvestStatusBanner.tsx:77`
     - `DividendPlanSection.tsx:338`
     - `GoalTimelineCard.tsx:240`
     - `GoalWizardRecommendationStep.tsx:56`
     - `RebalancingAlertSummaryCard.tsx:39,59`
     - `InvestPlanPage.tsx:172`
     - `SettingsPage.tsx:230`
     - `usePushNotifications.ts:51-82`
     - `RebalancingStatusCard.tsx:331,347`
   - 백엔드에서 새 형식(`rtab=목표 조정&gmode=…`)으로 바꿀 곳: `email_service.py:421,440`.
   - 백엔드 리밸런싱 알림 이메일(`email_service.py:132`): `rtab=포트폴리오&portfolioId=`로 보낸다. portfolio_id를 인자로 받도록 바꾸고 호출부도 맞춘다. 계획 63 P3-4의 미완 항목이다.
   - `insight_service.py:232,244`에 `rtab=포트폴리오`를 추가한다.
   - 예전 값 매핑은 계속 둔다(이미 발송된 링크용).
4. 이력 탭 문구 "진단 탭에서 다시 분석"을 "포트폴리오 탭에서 다시 분석"으로 고친다(`RebalancingHistoryTab.tsx:356`).

## 배치 S2 — 목표 조정 탭 (추천과 전술 통합)
1. **`GoalAdjustTab.tsx`(신규)의 구성**
   - 맨 위에 TabIntro 한 줄: "목표 비중 자체를 바꿀지 제안해요. 적용 후 실행은 포트폴리오 탭에서."
   - 그 아래 공용 **대상 포트폴리오 선택기** 1개.
   - 그 아래 `Tabs variant="underline"`로 [추천 | 전술]을 둔다. 값은 URL `gmode`와 묶는다.
   - 모드별 한 줄 설명은 기존 전술 TabIntro 문구를 재사용한다.
2. **공용 선택 훅 `hooks/useSelectedPortfolio.ts`(신규)**
   - 반환값: `{ portfolios, selectedId, select }`
   - 선택 규칙: URL `portfolioId` → 첫 기준 포트폴리오(`getPortfolioTargetState`) → 첫 포트폴리오.
   - 적용 위치:
     - `RecommendationCard.tsx:200-216`의 `effectiveOverallTargetId` 계산
     - `TacticalAllocationTab.tsx:378-384`의 선택값 계산
     - 포트폴리오 탭의 기본 선택(아래 S3-1)
   - 기본값 하나로 세 탭의 선택이 어긋나는 문제를 없앤다.
3. **선택기를 위로 올린다.**
   - `RecommendationApplySection.tsx:43-57`의 `<select>`와 `TacticalAllocationTab.tsx:407-420`의 `<select>`를 제거한다. 두 컴포넌트는 `selectedPortfolioId` prop만 받는다.
   - 기간별 추천은 대상이 태그로 고정이다(`horizonTargetPortfolio`). 이때 상단 선택기 아래에 "기간별 추천은 ○○(태그 일치) 포트폴리오에 적용돼요" 안내를 띄운다.
4. **추천 내부의 단 수를 줄인다(계획 53 Phase C 항목 포함).**
   - `RecommendationCard.tsx:322-356`의 칩 2줄을 바꾼다.
     - 1줄은 segmented [전체 | 연령대 | 기간별]로 한다. `components/portfolio/allocation/SegmentedControl.tsx`를 재사용하거나 `common/`으로 옮긴다.
     - 기간별을 고르면 select 1개에 "단기 · ISA" 식으로 기간×세제 조합을 나열한다.
   - 기존 내부 상태 `activeTab` / `selectedTaxType`는 유지하고, 표현만 바꾼다.
   - 전술 탭의 빈 상태 CTA는 공용 선택기 쪽으로 올린다. 포트폴리오가 0개면 탭 전체를 빈 상태 1개로 보여준다.

## 배치 S3 — 포트폴리오 탭 정리 (중복 진입점 제거)
1. **기본 선택**: URL이 비어 있으면 `useSelectedPortfolio`의 기본값을 쓴다. 지금은 아무것도 선택되지 않아 분석·실행 영역이 숨겨진다. 기본값은 URL에 쓰지 않고 파생만 한다. 자동 스크롤은 사용자가 직접 고른 경우에만 한다.
2. **분석 모드를 segmented로 바꾸고 백테스트를 편입한다.**
   - `AnalysisPanel.tsx:97-140`의 버튼 행을 SegmentedControl [리밸런싱 분석 | 효율 분석 | 백테스트]로 바꾼다.
   - 재분석은 결과 영역의 기존 "다시 분석" 경로로 둔다. 다중선택 잔재를 제거한다: `selectedIds`, "외 N개", "1개만 선택하세요"(62 E3의 일부).
   - 백테스트를 고르면 `BacktestTab`을 렌더한다.
     - 새 prop `defaultPortfolioIds=[portfolioId]`로 체크박스 초기값을 선택 포트폴리오로 둔다.
     - 다른 포트폴리오 비교 체크는 유지한다.
   - `RebalancingPage.tsx:326-338`의 백테스트 CollapsibleCard와 `useCollapsible` 키를 삭제한다.
3. **실행 버튼을 하나로 줄인다.** `RebalancingDiagnosisCard.tsx:117-126`의 "지금 실행하기"를 제거한다. 바로 아래에 같은 모달을 여는 실행 버튼(데스크톱 / 모바일 고정)이 있기 때문이다.
4. **동기화 진입점을 정리한다.** 계획 63 P3-1/P2-3의 "동기화하고 다시 분석" 안내 1곳과 `RebalancingAccountSyncSection`이 같은 `useSyncAccounts`를 쓰는지 확인한다(62 D3).
   - 아직 갈라져 있으면 공용 훅으로 합친다.
   - 결과 화면(`RebalancingResultSection`)은 실행 직후 맥락이라 유지한다.
5. **자동화 상태를 3곳에서 2곳으로 줄인다.** `PortfolioListSection.tsx:359-385` 목록 상단의 "N개 중 자동 실행 X, 알림 Y" 배너는 카드 칩의 합계일 뿐이다. 이를 목록 헤더 부제(1줄 텍스트)로 낮춘다. 카드 칩과 AnalysisPanel 상태바는 유지한다.
6. **잔재를 정리한다.**
   - `PortfolioListSection.tsx:323`의 `md:w-72 lg:w-80`(옛 좌우 배치)
   - `PortfolioManageTab.tsx:187-192`의 무동작 effect
   - 도달 불가 빈 상태: `AnalysisPanel.tsx:223-229`, `PortfolioExecutionTab.tsx:98-105`
   - 62 D2와 겹치는 항목은 이 커밋에서 같이 처리하고, 62 쪽은 "64에서 처리"로 표기한다.

## 배치 S4 — 진단 탭 밀도 + 알림 설정 일원화
1. **진단 탭의 밀도를 낮춘다(계획 53 Phase C에서 이번 범위에 해당하는 항목).**
   - `RiskMetricsCard`: 기본을 접힘으로 하고 `useCollapsible` 키를 단다.
   - `MarketSignalBanner`: 비GREEN일 때 자동으로 펼치는 동작을 없앤다. 배지와 1줄 요약을 기본으로 하고, 상세는 "자세히"로 연다.
2. **진단 인사이트 두 곳의 이름을 구분한다.**
   - 진단 탭의 "진단 결과"(전체 자산, insights API)는 "전체 자산 진단"으로 바꾼다.
   - `RebalancingDiagnosisCard`(선택 포트폴리오, `analysis.diagnosis_context`)는 "이 포트폴리오 진단"으로 바꾼다.
   - 소스가 서로 다르므로 합치지 않고 라벨만 구분한다. 계획 63 P2-1과 같은 방식이다.
3. **알림 설정 페이지를 시장 관련 알림의 단일 목록으로 만든다.**
   - `NotificationSettingsPage.tsx:309-317`의 "시장 모니터링" 섹션에 전술 "국면 전환 알림"을 추가한다. 상태 행과, 포트폴리오별 설정이므로 `rtab=목표 조정&gmode=전술&portfolioId=` 딥링크로 구성한다.
   - 전술 탭 안의 토글은 그대로 둔다.

---

## 이관/보류
- 계획(`/invest-plan`)에서 전체 추천이 4곳에 노출된다: 추천 탭, 위저드 6단계, 배당 계획, 목표 타임라인. 그중 `SuggestedCandidatesBlock`은 배당 계획에서 중복된다. 이는 페이지 간 중복이라 별도 계획에서 다룬다.
- 홈 "추천 변화" 할 일 항목(계획 50 M5의 미구현분)은 백엔드 `action_items_service` 확장이 필요해 보류한다.
- 컴포넌트 이름의 "Tab" 접미사(`PortfolioManageTab`, `PortfolioExecutionTab`, `BacktestTab`)는 실제로 탭이 아니다. 저가치 리네임이라 보류한다.
- 62 C·D(나머지)·E2·E5·E6·E7은 62에서 진행한다.

## 실행 순서·커밋
S1 → S2 → S3 → S4. 커밋은 배치별로 `refactor:` 또는 `fix:`에 `(plans/64 Sx)`를 붙인다. S1은 탭 상수와 링크 전부를 바꾸므로 하나의 커밋으로 묶는다(중간 상태에서 링크가 깨지지 않게).

## 핵심 재사용 대상
- `components/common/Tabs.tsx`(pill / underline)
- `components/portfolio/allocation/SegmentedControl.tsx`
- `useSwipeTabs`(`hooks/useSwipeNavigation.ts:93`)
- `useCollapsible`
- `getPortfolioTargetState`, `utils/portfolio.ts`의 `mergeAlertsByPortfolio`
- `useAutoExecutionNotice`
- `BacktestTab`, `RecommendationResultPanel`, `TacticalStatusView`

## 검증
- 정적 검사와 테스트: `make lint`, `make typecheck`, `make test-frontend`, 그리고 백엔드 변경(S1의 email/insight) 때문에 `make test-backend`.
- **신규·수정 테스트**
  - `parseRebalancingTab`: 예전 `rtab=추천` / `rtab=전술` 매핑, 알 수 없는 값은 진단.
  - `rebalancingUrl` 빌더.
  - `useSelectedPortfolio`: 우선순위 URL → 기준 → 첫 포트폴리오.
  - `usePushNotifications` 경로 기대값.
  - `email_service` 링크 문자열.
  - `RecommendationCard`: segmented와 기간·세제 select.
  - `AnalysisPanel`: 3모드 전환.
  - 기존 `components.rebalancing2.test.tsx` 등의 탭 이름 단언을 갱신한다.
- **수동 확인**(`make dev`, 데스크톱과 모바일 390px)
  - 탭 순서와 스와이프.
  - 예전 링크 `/rebalancing?rtab=추천&openRecOptions=1`, `?rtab=전술`이 목표 조정 탭의 해당 모드로 열리는지.
  - 진단의 "전술 탭" 버튼.
  - 목표 조정에서 고른 포트폴리오가 포트폴리오 탭에 그대로 유지되는지.
  - 포트폴리오 탭에 처음 들어왔을 때 기준 포트폴리오가 자동으로 선택되는지.
  - 백테스트 모드의 기본 체크가 선택 포트폴리오인지.
  - 실행 버튼이 하나인지.
  - 알림 설정에서 전술 알림 딥링크가 동작하는지.
- **문서 갱신**
  - `frontend/CLAUDE.md`: 컴포넌트·훅·유틸 목록과 rtab 설명.
  - `backend/CLAUDE.md`: 해당하는 경우.
  - `docs/plans/README.md`: 64 행 추가, 62 D2·E3·E4 중 64에서 처리한 부분 표기.
  - 메모리: 새 탭 구조를 기록.
