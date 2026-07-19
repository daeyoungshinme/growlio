# 계획 5: RebalancingPage "백테스팅" 최상위 탭 → 하위 진입점으로 격하

**리스크: 낮음 (탭 배열 수정 + 컴포넌트 진입 경로 변경, 외부 딥링크 없음 확인됨)**

## 배경 (Why)

`RebalancingPage`의 최상위 탭은 4개(`진단/포트폴리오/백테스팅/이력`, `frontend/src/pages/RebalancingPage.tsx:31`)이며, 이 중 "백테스팅"은 핵심 워크플로우(목표설정→포트폴리오 구성→진단→알림→리밸런싱 실행)와 결이 다른 부가 분석 기능이다. 모바일 화면에서 최상위 탭 슬롯은 한정된 자원인데, 실사용 빈도가 상대적으로 낮을 가능성이 큰 기능이 그 슬롯 하나를 차지하고 있다.

`git grep`으로 확인한 결과 `rtab=백테스팅`을 참조하는 외부 딥링크는 없다(`RebalancingPage.tsx` 자기 자신의 탭 정의/렌더 분기 외에 이 문자열을 쓰는 곳 없음) — 즉 탭 이동이 다른 화면의 네비게이션을 깨뜨리지 않는다.

## 현재 코드 상태 (2026-07-19 기준 — 실행 전 재확인 필수)

- `frontend/src/pages/RebalancingPage.tsx:29` — `const BacktestTab = lazy(() => import("../components/rebalancing/BacktestTab"));`
- `frontend/src/pages/RebalancingPage.tsx:31` — `const REBALANCING_PAGE_TABS = ["진단", "포트폴리오", "백테스팅", "이력"] as const;`
- `frontend/src/pages/RebalancingPage.tsx:97` — `useSwipeTabs(tabContentRef, REBALANCING_PAGE_TABS, localTab, handleTabChange)` — 탭 배열이 스와이프 네비게이션과 직결되므로 배열에서 빼면 스와이프 순서도 자동으로 3개로 줄어듦(별도 처리 불필요).
- `frontend/src/pages/RebalancingPage.tsx:206-250` 부근 — `localTab === "포트폴리오"` 블록: `RecommendationCard` → `PortfolioManageTab` → (portfolioId 선택 시) `PortfolioExecutionTab`이 순서대로 렌더됨. 새 진입점을 추가할 자연스러운 위치.
- `frontend/src/pages/RebalancingPage.tsx:251` 부근 — `localTab === "백테스팅"` 블록, `<BacktestTab />` 렌더 — 제거 대상.

## 구현 단계

1. **탭 배열 축소**: `REBALANCING_PAGE_TABS`에서 `"백테스팅"` 제거 → `["진단", "포트폴리오", "이력"]`. `RebalancingPageTab` 타입은 자동으로 갱신됨(배열 기반 타입이므로).
2. **진입 경로 추가**: "포트폴리오" 탭 하단(`PortfolioManageTab`/`PortfolioExecutionTab` 다음)에 백테스트 진입 UI 추가. 두 가지 방식 중 택1(구현 세션이 실제 화면 보고 결정):
   - (a) `CollapsibleCard`/`CollapsibleSection`(공용 컴포넌트, 기본 접힘)로 "백테스트" 섹션을 포트폴리오 탭 최하단에 인라인 — 별도 화면 전환 없이 스크롤로 접근.
   - (b) "백테스트 실행" 버튼 → `BacktestTab`을 `Modal.tsx`(공용) 안에 렌더 — 포트폴리오 탭 화면을 가리지 않음.
   - 기존 프로젝트가 "포트폴리오 탭 내부에 분석/실행을 조건부 인라인"하는 패턴을 이미 쓰고 있으므로(`PortfolioExecutionTab`이 `portfolioId` 선택 시 조건부 렌더), (a)가 기존 관례와 더 일관됨 — 특별한 이유 없으면 (a) 권장.
3. **`localTab === "백테스팅"` 블록 제거**, `BacktestTab` import는 새 위치에서 계속 lazy-load.
4. **테스트**: `frontend/src/__tests__/pages.*.test.tsx` 중 RebalancingPage 테스트에서 탭 개수/이름을 하드코딩해서 검증하는 부분이 있다면 갱신(예: `REBALANCING_PAGE_TABS.length === 4` 같은 assertion). `BacktestTab` 자체 테스트는 렌더 위치만 바뀌었으므로 기존 테스트 대부분 유지 가능 — import 경로가 그대로면 컴포넌트 자체 테스트는 영향 없음.
5. **검증**: `cd frontend && npm run test && npm run typecheck && npm run lint && npm run build`. 실제 브라우저(`npm run dev`)에서 포트폴리오 탭 진입 후 백테스트 섹션이 정상 동작하는지 수동 확인 권장(백테스트는 별도 API 호출을 하므로 단위테스트만으론 실사용 흐름 검증이 부족할 수 있음).

## 주의사항

- 이 변경은 순수 프론트 UI 리팩터링이며 백엔드/API 변경이 전혀 없다 — 가장 독립적으로 진행 가능한 계획.
- 만약 실사용 데이터(예: 애널리틱스, 사용자 피드백)로 "백테스팅을 자주 쓴다"는 근거가 확인되면 이 계획은 진행하지 말고 README에 "보류"로 기록할 것 — 이 계획은 추정("결이 다른 부가기능")에 근거한 제안이지 확정된 사용자 요청이 아니다.
