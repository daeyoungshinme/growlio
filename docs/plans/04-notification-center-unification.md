# 계획 4: 알림 관리 화면 분산 완화 — "리밸런싱 알림 현황" 요약 카드

**리스크: 중간 (신규 UI 컴포넌트 + 기존 쿼리 재사용, 라우팅/nav 변경 없음)**

## 배경 (Why)

알림 관련 UI가 두 곳에 나뉘어 있다:
- **SettingsPage 알림 탭** (`/settings`, `ALERT_TABS`: 환율/주가/시장신호/발송이력) — 4번째 리밸런싱 알림만 빠져 있음.
- **RebalancingPage Bell 모달** (`/rebalancing`) — 리밸런싱 드리프트 알림(AGGREGATE/PER_ACCOUNT) CRUD 전용.

SettingsPage는 이미 이 분리를 인지하고 있다 — `SettingsPage.tsx:280-289`에 "리밸런싱 비중 이탈 알림 및 자동 실행 설정은 [리밸런싱 탭]에서 설정합니다"라는 **텍스트 링크만** 있고, 실제 알림이 몇 개 있는지, AUTO가 켜져 있는지 등 상태는 전혀 보여주지 않는다. 2026-07-05 감사에서 "알림 3계열 통합"이 검토됐으나 보류된 바 있다.

**이번 계획의 범위는 "통합"이 아니라 "가시성 보완"이다** — 하단 네비게이션에 새 탭을 만들거나 화면을 합치는 큰 IA 변경(`docs/mobile-ux-audit-2026-07.md`에서 이미 "보류, 사용자 결정 필요"로 명시된 영역)은 건드리지 않는다. 대신 SettingsPage의 저 텍스트 한 줄을, 실제 상태를 보여주는 요약 카드로 바꾼다.

## 현재 코드 상태 (2026-07-19 기준 — 실행 전 재확인 필수)

- `frontend/src/pages/SettingsPage.tsx:277-321` — `alertSectionRef`로 감싼 "알림 설정" `SectionCard`. 280-289줄이 교체 대상.
- 리밸런싱 알림 목록 조회: 기존 훅/쿼리 확인 필요 — `useAlertCrud.ts`(`frontend/CLAUDE.md` hooks 목록) 또는 `QUERY_KEYS.rebalancingAlerts`(`["rebalancing-alerts"]`, `frontend/CLAUDE.md` "React Query queryKey 규칙" 표 참고). `PortfolioManageTab.tsx`/`RebalancingAlertModal.tsx`가 이미 이 데이터를 쓰고 있으므로 같은 쿼리를 SettingsPage에서도 재사용(중복 fetch 아님, React Query 캐시 공유).
- `mergeAlertsByPortfolio(alerts)`(`frontend/src/utils/portfolio.ts`, `frontend/CLAUDE.md`에 문서화됨) — PER_ACCOUNT 스코프 알림을 포트폴리오 기준으로 병합해 "하나라도 AUTO면 병합 결과도 AUTO 표시" — 요약 카드에서 그대로 재사용 가능.

## 구현 단계

1. **신규 컴포넌트** `frontend/src/components/settings/RebalancingAlertSummaryCard.tsx` — 리밸런싱 알림 목록을 조회해 `mergeAlertsByPortfolio()`로 병합 후:
   - 활성 알림 개수, 그중 AUTO 모드 개수를 한 줄 요약(예: "포트폴리오 3개 중 2개에 알림 설정됨 (AUTO 1개)").
   - 알림이 하나도 없으면 "아직 설정된 리밸런싱 알림이 없어요" + CTA.
   - 클릭 시 기존과 동일하게 `/rebalancing?rtab=포트폴리오`로 이동(딥링크 그대로 유지).
2. `SettingsPage.tsx:280-289`의 정적 문구를 이 컴포넌트로 교체.
3. 로딩 상태(스켈레톤)는 `SkeletonCard`(공용 컴포넌트) 재사용.
4. **테스트**: `frontend/src/__tests__/components.settings2.test.tsx`(기존 SettingsPage 테스트 파일 — git status상 최근 다른 세션이 이미 수정 중이었으니 최신 내용 확인 후 추가)에 요약 카드 렌더 케이스 추가. 신규 컴포넌트 자체 테스트도 `src/__tests__/components.*.test.tsx`에 추가.
5. **검증**: `cd frontend && npm run test && npm run typecheck && npm run lint`.

## 확장 아이디어 (이번 계획 범위 밖, 참고용)

- 환율/주가/시장신호 알림도 같은 패턴으로 개수 요약을 SettingsPage 알림 탭 상단에 공통 헤더로 얹으면 "알림 설정 현황을 한눈에" 보는 효과가 더 커진다 — 이번엔 리밸런싱 알림 하나만 먼저 시범 적용하고, 반응 보고 나머지 3종에도 확장할지 판단.
- 진짜 "통합 알림 센터" 화면(전용 라우트)이 필요하다고 판단되면 하단 네비게이션 구조 변경이 불가피하므로, 그건 별도로 사용자와 먼저 논의할 것 — 이 계획에서 임의로 진행하지 말 것.
