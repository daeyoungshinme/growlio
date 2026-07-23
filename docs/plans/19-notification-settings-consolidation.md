# 계획 19: 알림 설정 코드 중복 제거 + 설정 화면 인지부하 완화

**리스크: 낮음(1번 훅 통합은 순수 리팩터) ~ 중간(2번 UI 재배치는 레이아웃 변경, 기존 로직/쿼리는 재사용).**

## 배경 (Why)

2026-07-23 "전반적 성능개선" 감사에서 프론트엔드 성능 조사와 기능구조 조사 양쪽이 독립적으로 동일한 지점을 지적함: `UserSettings`에 옵트인 알림 토글이 계속 추가되면서(목표달성/월간리포트/연말절세리마인더/추천비중변화/복합신호/시장신호일일요약 6종) (a) 프론트 훅과 백엔드 엔드포인트가 매번 동일한 보일러플레이트를 복붙하고 있고, (b) `SettingsPage.tsx`의 "알림 설정" 카드 하나 안에 개별 토글 4개 + 4탭 서브탭바(그 안에 토글 2개 추가) 3단 중첩 구조가 형성돼 모바일 화면에서 스크롤이 길고 어떤 알림이 켜져 있는지 파악하기 어려움.

`docs/plans/04-notification-center-unification.md`(진짜 통합 알림 센터 신규 화면)는 여전히 유효하지만 "하단 네비 구조 변경이 필요해 범위 밖"으로 스코프 아웃된 상태 — 이번 계획은 그보다 훨씬 작은 범위(기존 화면 안에서 그룹핑 + 코드 중복 제거)로 실익을 얻는 것이 목표.

## 1. 프론트 훅 통합 (코드 중복 제거)

**현재 상태:** `src/hooks/useGoalAchievementAlertsToggle.ts`, `useMonthlyReportAlertsToggle.ts`, `useYearEndTaxReminderToggle.ts`, `useRecommendationDriftAlertToggle.ts` 4개(각 ~31줄)가 `useQuery(["settings"]) + useMutation(PUT .../toggle-field) + invalidate + toast` 구조로 필드명만 다를 뿐 100% 동일. `useCompositeSignalToggle.ts`/`useMarketSignalDigestToggle.ts` 2개도 유사(단, 전용 상태 조회 방식이 달라 완전 동일하진 않음 — 우선 확실히 동일한 4개부터 통합).

**구현:**
1. `src/hooks/useSettingsToggle.ts` 신규: `useSettingsToggle({ field, endpoint, invalidate })` 형태의 제네릭 팩토리. `["settings"]` 쿼리에서 `field` 값을 읽고, `endpoint`로 PUT 호출, 성공 시 `invalidate(queryClient)` 호출 + 토스트.
2. 기존 4개 훅 파일의 내부 구현을 이 팩토리 호출 한 줄로 교체(파일 자체는 유지 — 소비하는 컴포넌트의 import 경로가 바뀌지 않도록). 예: `useGoalAchievementAlertsToggle.ts`는 `export const useGoalAchievementAlertsToggle = () => useSettingsToggle({ field: "goal_achievement_alerts_enabled", endpoint: "/settings/goal-achievement-alerts", invalidate: invalidateGoalAchievementAlertsData })`.
3. 소비 컴포넌트(`SettingsPage.tsx`, `MarketSignalAlertSection.tsx` 등)는 변경 없음 — 훅의 반환 타입(`{ enabled, toggle, isLoading }` 등 기존 시그니처)을 그대로 유지해야 함.
4. 관련 훅 테스트(`src/__tests__/hooks.*.test.ts`) 4개 파일이 리팩터 후에도 통과하는지 확인. `useCompositeSignalToggle`/`useMarketSignalDigestToggle`은 이번엔 건드리지 않음(구조가 달라 별도 검토 필요).

**백엔드는 이번 범위에서 변경하지 않음** — 엔드포인트 6개(`PUT /settings/goal-achievement-alerts` 등)를 단일 엔드포인트로 통합하는 것은 API 계약 변경이라 리스크가 더 크고, 프론트 훅 통합만으로 대부분의 유지보수 비용(신규 알림 추가 시 복붙)은 해소됨. 백엔드 통합은 필요성이 재확인되면 별도 계획으로 분리.

## 2. `SettingsPage.tsx` 알림 섹션 그룹화 (인지부하 완화)

**현재 상태:** `frontend/src/pages/SettingsPage.tsx:355-443` 부근 "알림 설정" 카드 하나에 독립 토글 4개(목표달성/월간리포트/연말절세리마인더/추천비중변화)가 세로 나열된 뒤, 그 아래 4탭 서브탭바(환율/주가/시장신호/발송이력) — 시장신호 탭 안에 다시 토글 2개(`MarketSignalAlertSection`)가 중첩. 별도로 `RebalancingAlertSummaryCard`가 리밸런싱 알림을 요약 카드로 보여줌(계획4번에서 이미 구현).

**구현:**
1. 현재 나열형 4개 토글을 목적별로 3개 카테고리 요약 카드로 그룹핑 — 각 카드는 `CollapsibleCard`(기본 접힘)로 감싸 첫 화면 스크롤 길이를 줄임:
   - **"정기 리포트·리마인더"**: 월간 리포트, 연말 절세 리마인더 (발송 빈도가 낮고 정보성인 것들 묶음)
   - **"목표·추천 변화 감지"**: 목표 달성 알림, 추천 비중 변화 알림
   - **"시장 모니터링"**: 기존 `MarketSignalAlertSection`(복합신호+일일요약) 그대로 유지, 탭 밖으로 꺼내 동일 위계로 배치
2. 환율/주가/발송이력 3탭은 그대로 유지(이건 CRUD가 필요한 알림이라 토글 나열과 성격이 다름 — 무리하게 합치지 않음).
3. `RebalancingAlertSummaryCard`와 동일한 시각적 패턴(요약 텍스트 + 펼치면 상세) 재사용해 화면 전체의 일관성 유지.
4. 접근성: 각 그룹 카드 제목은 `frontend/CLAUDE.md`의 헤딩 규칙(`h2`)을 따를 것.
5. `npx playwright test`(settings 관련 E2E가 있다면) 또는 최소한 수동으로 `/settings` 화면에서 각 토글이 정상 동작하는지 확인.

## 검증

```bash
cd frontend && npm run test && npm run typecheck && npm run lint
```

1번과 2번은 독립적으로 진행 가능(1번 먼저 착수 권장 — 리스크 낮고 2번의 전제 조건은 아님).

## 참고

- `docs/plans/04-notification-center-unification.md` — 더 큰 범위의 통합 알림 센터(신규 화면)는 이 계획과 별개로 여전히 로드맵에 남아있음. 이번 계획으로 상당 부분 완화되면 04번의 우선순위는 더 낮아질 수 있음.
