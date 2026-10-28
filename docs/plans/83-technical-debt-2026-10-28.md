# 83. 기술부채 감사 (2026-10-28)

> 상태: **A·B·C 완료**. D는 사용자 확인 후 진행한다. 이관 항목은 계획 80과 같다.

## Context

계획 80 이후 들어온 코드를 감사했다.
- plans/82 진단 "시장 상황" 통합(PR #165)
- 목표 조정 선택기 정리(PR #166, plans/81)
- 홈 금액 숨김(PR #168)
- dnspython CVE 패치

정적 검사는 전부 0건이다: ruff check/format, mypy, tsc, eslint, prettier, npm audit. 프론트 vitest(1856건)와 백엔드 `test_tactical_allocation`(93건)도 모두 통과했다. 그래서 계획 80의 교훈대로 최근 기능끼리 만나는 경로를 손으로 추적했다.

## A. 회귀: 전술 기본 선택이 다른 탭과 어긋남 (plans/64 S2 불변식)

- `GoalAdjustTab`(전술)은 `useSelectedPortfolio(id, { preferTactical: true })`로 URL이 비어 있으면 **전술 켠 포트폴리오 X**를 고른다.
- `RebalancingPage`는 `useSelectedPortfolio(portfolioId)`로 **기준 포트폴리오 Y**를 기본값으로 쓴다.
- 결과: 전술에서 X를 보다가 포트폴리오 탭으로 옮기면(탭이나 스와이프) Y가 보였다. plans/64 S2가 고친 "탭마다 다른 포트폴리오" 문제가 다시 생긴 것이다. "분석·실행으로 이동" 버튼은 id를 명시적으로 넘기므로 정상이었다.

**수정**: `RebalancingPage`가 전술 모드에서 떠날 때(URL 선택 없음) 보이던 id를 `tacticalDefaultId` state에 기억한다. 이후에는 `portfolioId ?? tacticalDefaultId`를 요청값으로 쓰고 `GoalAdjustTab`에도 넘긴다. 페이지의 `useSelectedPortfolio`에도 전술 모드일 때 `preferTactical`을 넘긴다(같은 queryKey라 추가 요청 없음).
- URL에는 쓰지 않는다. URL `portfolioId`는 "직접 고름"을 뜻하고, 포트폴리오 탭에서 분석 결과로 자동 스크롤하는 신호다.
- 테스트: `pages.rebalancing.test.tsx`에 두 케이스를 추가했다. 첫째, 전술(p2)에서 포트폴리오 탭으로 가면 p2가 유지된다(수정 전 코드에서는 실패). 둘째, 전술을 거치지 않으면 기본값은 기준 포트폴리오(p1)다.

## B. 문서 드리프트
1. 코드 3곳이 `plans/81`을 인용하지만 계획서와 README 행이 없었다(PR #166이 계획서 없이 머지됨). 81 문서와 README 행을 사후 작성했다.
2. README 82 행이 "완료(미커밋)"이었지만 PR #165로 머지됐다. 상태를 갱신했다.
3. `MiniDonut` 주석은 "가운데에 이름·비중·금액"이라고 했지만 실제 가운데에는 이름·비중만 나온다. 금액은 조각 `<title>`에만 있다. 주석을 실제에 맞췄다.

## C. 사소한 정리 (동작 변화 없음)
- `useSelectedPortfolio` 반환값에서 쓰는 곳이 없는 `anchoredIds`를 제거하고, 테스트 mock에서도 뺐다.
- `TacticalStatusParts`의 파일 내부 전용 `SummaryLine`·`ReasonList`에서 `export`를 제거했다.

## D. 브랜치·worktree 정리 (사용자 확인 필요)
- worktree `D:/project/growlio-pr82`([feat/market-status-consolidation], #165로 머지됨) 제거
- 원격 `feat/market-status-tactical-picker-2026-10-27`(da931a63, #165·#166을 하나로 합친 버려진 변형) 삭제
- 이미 main에 반영된 dependabot 브랜치 정리
  - `vite-8.2.2`: main은 ^8.3.5
  - `vite-plugin-pwa-2.0.0`: main은 ^2.0.0
- `frontend-dependencies-6f8c7c1c92`(10-20)는 남은 범프가 있는지 확인한다.

## 이관 (계획 80과 같음)
- pandas 3: pyproject가 `<3.0.0`으로 의도적으로 고정했다. 메이저 업그레이드는 별도 계획으로 한다.
- untracked_holdings 제거(APK 재빌드 필요)
- 65 B4·66 P3 실측, 실기기 확인, 대형 함수 분해

## 검증
- `make lint`, `make typecheck`, `make test-frontend`
- 수동 확인: URL 없이 목표 조정 › 전술로 들어가 전술 켠 포트폴리오가 선택되는지 본다. 그다음 포트폴리오 탭으로 옮겨 같은 포트폴리오가 보이고 자동 스크롤은 없는지 확인한다.
