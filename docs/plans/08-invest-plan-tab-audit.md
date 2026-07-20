# 계획 8: 계획탭(`/invest-plan`) 개선 — 기능 감사 + UX + 신규기능

**리스크: 낮음~중간 (2번 항목만 데이터 정합성 확인이 필요해 중간, 나머지는 낮음)**

## 배경 (Why)

2026-07-20 사용자 요청으로 계획탭(`InvestPlanPage.tsx` — "적립 계획"/"배당 계획")을 전수 점검했다. **주의: "계획" 탭은 `/invest-plan`이며, "리밸런싱" 탭(`/rebalancing`)과는 완전히 다른 화면이다** — nav 레이블이 비슷해 보여도 혼동하지 말 것 (`frontend/src/constants/nav.ts:10-16` 참고).

## ⚠️ 실행 전 필수 확인사항

이 프로젝트는 여러 세션에서 동시에 작업되는 경우가 잦다. `git status`/`git diff`로 대상 파일이 이미 다른 세션에 의해 수정 중이 아닌지 확인하고, 파일:라인이 실제 코드와 다르면 코드 현재 상태를 우선한다.

## 현재 코드 상태 (2026-07-20 기준)

- `frontend/src/pages/InvestPlanPage.tsx` — `TABS = ["적립 계획", "배당 계획"]`(28행), `useGoalSettings`/`useDividendPlanSettings` 훅 사용
- `frontend/src/components/invest/GoalTimelineCard.tsx`, `DCAProjectionChart.tsx`, `MonthlyAchievementTable.tsx`, `YearlyAchievementTable.tsx`, `DividendPlanSection.tsx`
- 백엔드: `backend/app/api/v1/invest.py` (`GET /dca-analysis`, `GET /dividend-plan`), `backend/app/services/dca_service.py`

## 구현 단계 (항목별 독립 실행 가능)

### 1. [UX/신규기능] 목표 역산 추천 미리보기 부재

`InvestPlanPage.tsx:137-144` — "목표 기반 포트폴리오 추천 보기 →" 가 `/rebalancing?rtab=포트폴리오`로 이동하는 텍스트 링크 하나뿐이다. 계획탭에서 목표를 확인하는 김에 추천 현황(예: 추천 비중과 현재 비중의 괴리, AUTO 여부)을 미리 볼 수 있으면 탭 전환 없이 파악 가능하다.

- `api/settings.ts`의 `goal-recommendation` 관련 조회 함수 또는 `QUERY_KEYS`의 `["goal-recommendation", "overall"]` 쿼리 재사용(신규 fetch 추가 불필요, 기존 캐시 공유)
- 신규 컴포넌트 `frontend/src/components/invest/GoalRecommendationPreviewCard.tsx` — 요약 1~2줄 + "자세히 보기" 링크(기존 딥링크 유지)
- **주의**: `docs/plans/04-notification-center-unification.md`(설정탭 알림 요약 카드, 미착수)와 패턴은 비슷하지만 대상 화면·데이터가 다르므로 별도 컴포넌트로 작성 — 04번 파일과 코드 충돌 없음

### 2. [기능감사, 중간 리스크] 목표 변경 시 과거 달성률 이력 왜곡 가능성

목표 금액/연수익률/시작일 등을 수정(`InvestPlanPage.tsx:310-390` 편집 모달, `useGoalSettings.ts`)했을 때, `MonthlyAchievementTable`/`YearlyAchievementTable`가 보여주는 과거 달성률이 수정 시점 이전 데이터에도 새 목표값 기준으로 재계산되어 표시되는지 확인 필요.

- `backend/app/services/dca_service.py`의 달성률 계산 로직에서 "목표값"을 항상 최신값 하나만 참조하는지, 시점별 스냅샷을 쓰는지 확인
- 만약 항상 최신 목표값 기준이라면 "목표를 상향 조정했더니 과거 달성률이 갑자기 낮아 보이는" 혼란이 생길 수 있음 — 의도된 동작인지(목표는 현재 시점 기준 하나만 존재) 사용자와 확인 후 필요 시 "목표 변경 이력" 배지나 안내 문구 추가 검토
- **이 항목은 먼저 현재 동작을 확인하는 조사부터 시작** — 실제 왜곡이 없다면 코드 변경 불필요

### 3. [구조 정리, 낮은 우선순위] Tax* 컴포넌트 폴더 위치

`frontend/src/components/invest/{GeumtSimulationSection,TaxPlannerSection,TaxRecommendationList,TaxSimulationCard,TaxPositionTable}.tsx` — grep 확인 결과 이 5개 파일은 계획탭이 아니라 **자산탭 세금 탭**(`components/portfolio-analysis/TaxOptimizationCard.tsx`)에서만 import된다(`frontend/src/__tests__/pages.invest.test.tsx`, `components.invest.test.tsx`에도 걸려 있어 이름은 invest 테스트지만 실제 소비처는 다름).

- `components/invest/` → `components/tax/`로 이동(순수 파일 이동 + import 경로 수정)
- `frontend/CLAUDE.md`의 "컴포넌트 디렉토리" 목록에 `tax` 추가
- 테스트 파일(`pages.invest.test.tsx`, `components.invest.test.tsx`)의 import 경로도 함께 수정
- **기능 변경 없는 순수 리팩터링 — 우선순위 낮음, 다른 항목들과 파일이 겹치지 않아 아무 때나 진행 가능**

## 확장 아이디어 (이번 계획 범위 밖, 참고용)

- 배당 계획 탭에도 적립 계획처럼 "타임라인 카드"(목표 달성 예상 시점) 추가
- DCA 프로젝션에 시나리오 비교(보수적/중립/공격적 수익률 가정) 토글 추가
