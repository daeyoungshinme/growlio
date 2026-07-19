# 모바일 UX 감사 — 2026-07

Growlio 모바일 앱의 기능/탭 구조를 전수 조사하고, 불필요한 기능 제거·병합 후보·모바일 UI/UX 개선사항을 정리한 문서. 자산 모니터링 → 투자 목표 설정 → 포트폴리오 구성 → 시장상황 기반 비중 추천 → 리밸런싱 징후 알림 → 수동/자동 실행으로 이어지는 핵심 플로우를 기준으로 감사했다.

## 1. 제거/축소 후보

| 항목 | 위치 | 상태 |
|---|---|---|
| 구 "포트폴리오 분석" 탭 URL 리다이렉트 `useEffect` | `frontend/src/pages/PortfolioPage.tsx:54-61` | ✅ 제거 완료 |
| 생체인증 토글 (웹에서 비노출) | `frontend/src/pages/SettingsPage.tsx` | 보류 — 기능상 정상 동작(네이티브 전용), 우선순위 낮음 |
| 위젯 안내 텍스트만 있는 설정 항목 | `SettingsPage.tsx` 앱 설정 카드 | 보류 — 우선순위 낮음 |

## 2. 병합 후보

| 항목 | 위치 | 상태 |
|---|---|---|
| 진단/신호 카드 과다 분산 (홈/진단탭/포트폴리오탭 3곳, 최대 6개 컴포넌트) | `RebalancingPage.tsx` 진단 탭, `DashboardPage.tsx`, `RebalancingTable.tsx` | ✅ 부분 적용 — 접기 기본값 처리로 스크롤 부담 축소 (구조적 통합은 `DiagnosisSummaryHeader`가 이미 의도적 드릴다운 설계라 보류) |
| 배당(dividend) 기능 4곳 분산 | `DividendSection`(대시보드), `DividendTab`(자산탭), `DividendPlanSection`(계획탭), `RebalancingDividendSection`(리밸런싱탭) | ✅ 구현 중 재확인 결과 `DividendSection`(대시보드)은 실제로는 어디에도 렌더링되지 않는 **죽은 코드**였음(자체 테스트에서만 import) — 삭제. `DividendTab`↔`DividendPlanSection`은 이미 상호 링크가 구현되어 있었음. `RebalancingDividendSection`에만 링크가 없어 "배당 목표 확인" → `/invest-plan?tab=배당 계획` 링크 추가 |
| 목표 설정 ↔ 목표 기반 추천의 탭 분리 | `InvestPlanPage.tsx`(계획) ↔ `RebalancingPage.tsx`(포트폴리오 탭, `RecommendationCard`) | ✅ 딥링크 추가 완료 |
| AGGREGATE/PER_ACCOUNT 알림 이중 엔드포인트 | `backend/app/api/v1/rebalancing_alerts.py`, `frontend/src/utils/portfolio.ts`(`mergeAlertsByPortfolio`) | 보류 — 백엔드 리스크가 커서 이번 라운드 범위 밖. 스코프 파라미터화한 단일 엔드포인트로의 중장기 리팩터링 후보로 기록만 |

## 3. 모바일 탭 구성 / UI·UX 개선

| 항목 | 위치 | 상태 |
|---|---|---|
| 진단 탭 카드 5개 세로 나열로 인한 스크롤 부담 | `RiskMetricsCard.tsx`, `MarketSignalBanner.tsx`, `InflationSummaryCard.tsx` | ✅ `InflationSummaryCard`에 `CollapsibleCard` 적용 완료. `RiskMetricsCard`(기본 접힘)·`MarketSignalBanner`(GREEN일 때만 기본 접힘)는 조사 중 이미 자체 접기 로직이 구현되어 있음을 확인 — 추가 조치 불필요 |
| 이중 스와이프 충돌 가능성 (`AssetsPage` 상위 탭 vs `PortfolioPage`/`AssetManagementPage` 하위 탭) | `useSwipeTabs`(`hooks/useSwipeNavigation.ts`) 중첩 호출 | ✅ 구현 중 재확인 결과 실제로는 문제 없음 — `useSwipeTabs`의 `handleSwipe`가 최상단에서 `e.stopPropagation()`을 이미 호출하고 있어(`useSwipeNavigation.ts:103`) 하위 탭 스와이프가 상위 페이지 전환(`useSwipeNavigation`)으로 전파되지 않음. 회귀 방지용 테스트를 `hooks.extra.test.tsx`에 추가 |
| 하단 네비 5탭("홈/자산/리밸런싱/계획/설정") 구조 재검토 | `constants/nav.ts` | 보류 — 전체 IA에 영향을 주는 큰 변경이라 이번 라운드 제외 (사용자 결정) |
| 터치 타겟/폰트 크기 규칙 | `constants/uiSizes.ts` | 문제 없음 — 2026-07-16 리팩터링으로 이미 반영됨, 추가 조치 불필요 |

## 참고 — 이번 라운드에서 다루지 않은 항목

- **하단 네비게이션 재편**: "계획" 탭을 리밸런싱 허브에 흡수하고 배당을 독립 탭으로 승격하는 안은 리스크가 크고 전체 IA에 영향을 주므로 별도 논의 후 진행.
- **AGGREGATE/PER_ACCOUNT 알림 엔드포인트 통합**: 현재는 의도된 설계(계좌별/전체 스코프 구분)이므로 급하지 않음. 프론트에서 `mergeAlertsByPortfolio`로 병합 표시 중이라 사용자 체감 문제는 없음.
