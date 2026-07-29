# Frontend CLAUDE.md

## Commands

### 설치
```bash
cd frontend && npm install
```

### 실행
```bash
# 개발 서버 (localhost:5173, /api/* → localhost:8000 자동 프록시)
cd frontend && npm run dev
```

### 빌드 & 타입 체크
```bash
# 프로덕션 빌드 (tsc -b && vite build)
cd frontend && npm run build

# 타입 체크만 (빌드 산출물 없음)
cd frontend && npm run typecheck   # npx tsc --noEmit 과 동일
```

### API 타입 자동 생성
```bash
# 백엔드 서버(localhost:8000) 실행 중인 상태에서 실행
cd frontend && npm run generate:api-types
# → src/types/api.generated.ts 생성 (gitignore 대상 — CI 빌드에서 자동 생성 안 됨. 백엔드 실행 중일 때 수동 실행 필요)
# 생성된 타입 사용법: import type { paths, components } from "../types/api.generated";
# 예: components["schemas"]["DashboardSummary"]
```

### 린트 & 테스트
```bash
cd frontend && npm run lint    # ESLint (eslint src)
cd frontend && npm run test    # Vitest (vitest run)
cd frontend && npm run test -- src/utils/__tests__/format.test.ts  # 단일 파일
cd frontend && npm run test:watch                                  # 워치 모드
cd frontend && npm run format  # Prettier (prettier --write src)
```

### Android 빌드 (Capacitor)
```bash
cd frontend && npm run cap:sync    # 웹 빌드 → Android 프로젝트 동기화
cd frontend && npm run cap:android # Android Studio로 열기
make build-android-debug           # APK Debug 빌드 (루트 Makefile)
make build-android-release         # APK Release 빌드
```

### Environment
`frontend/.env` (`.env.example` 참고):
- `VITE_SUPABASE_URL` — Supabase Project URL
- `VITE_SUPABASE_ANON_KEY` — Supabase Anon Key (JWT)
- `VITE_REDIRECT_URL` — OAuth/이메일 인증 후 리다이렉트 URL (예: https://yourdomain.com)
- `VITE_API_DOMAIN` — API 서버 도메인 (Vite 프록시 설정에 사용, 예: localhost:8000)
- `VITE_SENTRY_DSN` — Sentry 오류 추적 DSN (선택, 미설정 시 Sentry 비활성)
- `VITE_SENTRY_RELEASE` — Sentry 릴리스 태그

> `src/lib/supabase.ts`에서 import됨. `.env` 없으면 Supabase 클라이언트 초기화 실패.

> **빌드 시 소스맵 업로드용** (CI/배포 환경 전용, `.env` 아님): `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT`, `SENTRY_RELEASE`.

---

## Architecture (`frontend/src/`)

> **Import 규칙:** 새 코드는 `@/` alias 사용 (예: `import { fmtKrw } from "@/utils/format"`). `vite.config.ts`/`tsconfig.app.json`에 `@/* → src/*` 설정됨.

**페이지 구성** (실제 라우트는 `src/App.tsx` 참고 — 인증 필요 라우트는 `/` 하위 `PrivateRoute`로 감싸짐):
- `/login` — 로그인 (LoginPage)
- `/register` — 회원가입 (RegisterPage)
- `/find-account` — 계정 찾기 (FindAccountPage)
- `/forgot-password` — 비밀번호 찾기 (ForgotPasswordPage)
- `/reset-password` — 비밀번호 재설정 (ResetPasswordPage)
- `/auth/callback` — 회원가입 확인 이메일 링크 전용 랜딩 페이지 (AuthCallbackPage, 인증 불필요). Supabase가 이메일 인증 후 리다이렉트하는 목적지 — 세션 확립 대기 → 성공/실패 안내 → `/dashboard`로 이동
- `/rebalancing/plan-confirm?token=` — 리밸런싱 자동화 매수 취소/매도 승인 (RebalancingPlanConfirmPage, 이메일 링크 전용, 인증 불필요)
- `/dashboard` — 전체 자산 집계, 포트폴리오 요약, 연간 입금 달성률, 배당 현황, 월별 추이
- `/assets` — **자산 관리 허브** 단일 라우트. `AssetsPage`가 내부적으로 "투자현황"(조회 전용 PortfolioContent)/"계좌관리"(CRUD AssetManagementContent) 2개 탭으로 분기 (`ASSETS_TOP_TABS`, `?tab=` 쿼리 파라미터)
- `/invest-plan` — DCA(정기투자) 분석 + 목표 타임라인 (InvestPlanPage)
- `/settings` — DART API 키, 계정 정보(비밀번호 변경), 앱 설정(다크모드/생체인증/로그아웃/탈퇴). KIS/키움 계좌 연동(`/assets`)·투자/입금/배당 목표·DCA(`/invest-plan`)·목표 역산 추천 옵션(`/rebalancing`)·알림 설정(`/settings/notifications`)은 실제 편집 UI가 각 페이지에 있고, 설정 탭에는 상태 요약 + 딥링크만 표시됨
- `/settings/notifications` — 알림 설정 상세(`NotificationSettingsPage`, `/settings`에서 딥링크). 공통 수신 이메일(`NotificationEmailSection`) + 카테고리별 `CollapsibleCard` 3개("정기 리포트·요약"/"즉시 알림"/"시장 모니터링") + 환율/주가/발송이력 탭. `SettingsPage.tsx`(2026-07-26 이전)의 3중 중첩(`SectionCard`›`CollapsibleCard`×3›내부 pill탭)을 완화하기 위해 별도 라우트로 분리됨 — `MarketSignalBanner.tsx`/`RebalancingHistoryTab.tsx`의 `?atab=` 딥링크도 이 경로를 가리킴
- `/rebalancing` — 리밸런싱 실행 허브. 포트폴리오별 목표 비중 편집, 드리프트 현황, 주문 실행 (RebalancingPage)
- 미매칭 경로(`*`)는 `/dashboard`로 리다이렉트

> `/market`, `/portfolio`, `/asset-management`, `/trend` 라우트는 존재하지 않음(과거 구조, 제거됨). `BottomNav`(`src/constants/nav.ts`)도 홈/자산/리밸런싱/계획/설정 5탭만 존재.
> 새 페이지 추가 시 `src/App.tsx`에 `<Route>` 등록 필수.

**최상위 컴포넌트 (`src/components/`):**
- `ErrorBoundary.tsx` — React 에러 바운더리 (App.tsx에서 전체를 감쌈)
- `Toaster.tsx` — `growlio:toast` 이벤트 구독 전역 토스트 UI

**컴포넌트 디렉토리 (`src/components/`):**
assets, backtest, common, dashboard, invest, layout, portfolio, portfolio-analysis, rebalancing, settings, tax

**컨텍스트 (`src/context/`):**
- `ExchangeRateContext.tsx` — `ExchangeRateProvider`로 앱 전체에 환율 공유. `useExchangeRateContext()`로 소비. `useExchangeRate.ts` 훅과 별개 — 컨텍스트 방식으로 동일 쿼리 중복 방지.

`components/common/` 주요 파일: `AccountActionsMenu.tsx` (카드 헤더 등에 밀집된 부가 액션을 `⋯` 오버플로우 메뉴로 접는 공용 컴포넌트 — `items: {icon, label, onClick, disabled?, variant?}[]`, 아이콘+라벨 텍스트를 함께 렌더해 모바일 `title` 툴팁 미동작 문제 우회), `AmountUnitButtons.tsx`, `BiometricGuard.tsx`, `Button.tsx`, `CollapsibleCard.tsx` (카드 전체를 감싸는 헤더+접기 토글, `isOpen`/`onToggle` controlled), `CollapsibleSection.tsx` (카드 내부에 삽입하는 경량 접기 토글), `ConfirmModal.tsx`, `EditableNameField.tsx`, `EmptyState.tsx`, `FormInput.tsx` (공통 폼 인풋), `Modal.tsx`, `OfflineBanner.tsx`, `PageLoader.tsx`, `PriceCell.tsx` (가격 표시 셀), `SkeletonCard.tsx`, `SkeletonStatBox.tsx`, `SuggestionDropdown.tsx`, `Tabs.tsx`, `ToggleSwitch.tsx` (`checked`/`onChange`/`disabled?`/`ariaLabel?` props의 스위치 토글), `Tooltip.tsx`, `TopLoadingBar.tsx`, `TreemapCell.tsx`

> 새 공통 컴포넌트 추가/삭제 시 이 목록도 함께 갱신.

- **`BiometricGuard.tsx`** — `App.tsx`에서 `AppLayout` 전체를 감싸는 게이트 컴포넌트. Android 네이티브 빌드에서 생체 인증 미통과 시 하위 라우트 렌더링 차단 (`useBiometric.ts`와 연동).
- **`OfflineBanner.tsx`** — `useOnlineStatus.ts`로 네트워크 상태 감지 + PWA 오프라인 캐싱(`vite.config.ts`의 VitePWA/Workbox `StaleWhileRevalidate`, 대상: dashboard/portfolio-overview/accounts 엔드포인트)과 함께 오프라인 상태를 안내.
- **`components/dashboard/IsaMaturityCard.tsx`** — ISA 계좌 의무가입 3년 만기 현황 카드. `PortfolioPage`(자산탭 투자현황 › 세금 서브탭)의 `TaxLimitsSection`이 `embedded` 모드로 렌더.
- **`components/dashboard/PensionContributionCard.tsx`** — 연금저축/IRP 연간 납입 현황 카드. 마찬가지로 `TaxLimitsSection`이 `embedded` 모드로 렌더.
- **`components/dashboard/HealthInsuranceRiskCard.tsx`** — 배당소득 기준 건강보험 피부양자 자격상실 위험 상시 노출 카드(진행률 바 + 기준 초과 시 예상 월 보험료). `TaxLimitsSection`이 ISA/연금 계좌 유무와 무관하게 항상 렌더 — 배당소득은 계좌 태그가 아닌 전체 배당 수령액 기준이라 두 카드와 게이트 조건이 다름. `TaxOptimizationCard`("세금 추정" 탭)의 조건부 경고 배너와는 별개(상호 보완 — 이 카드가 상시 노출, 배너는 임계값 근접/초과 시 강조).
- **`components/dashboard/TaxLimitsBanner.tsx`** — `InvestmentSnapshotCard`("주식 투자 현황") 안에 4번째 하위 섹션으로 임베드되는 세금 한도 요약 행. ISA 임박 만기/한도초과·연금공제 달성률을 한 줄로 보여주고 `/assets?tab=투자현황&portfolioTab=세금`으로 딥링크(상세 카드 자체는 여전히 홈에 렌더하지 않음). 계산 로직은 `useTaxLimitsSummary` 훅(`hooks/useTaxLimitsSummary.ts`)에 있으며, 같은 훅을 `InvestmentSnapshotCard`가 헤더 경고 배지·collapsedHint 계산에도 재사용한다(React Query 캐시 공유로 요청 중복 없음).
- **`components/portfolio-analysis/TaxTabContainer.tsx`** — 자산탭 세금 서브탭의 진입점(`PortfolioPage`가 lazy-load). "한도 현황"/"세금 추정" 2탭으로 `TaxLimitsSection`(ISA·연금)과 `TaxOptimizationCard`(세금 추정)를 묶는다 — 기존에 두 카드가 각각 접이식으로 나란히 쌓여 3중 중첩이었던 것을 탭 전환 1단계로 단순화(2026-07-25). 탭 상태는 `?taxTab=` 쿼리파라미터로 영속화(`PortfolioPage`의 기존 `portfolioTab` 관리 패턴과 동일한 `useSearchParams` 방식). Home 배너(`TaxLimitsBanner`)의 `?portfolioTab=세금` 딥링크는 `taxTab` 미지정이라 기본값인 "한도 현황" 탭으로 랜딩한다.
- **`components/portfolio-analysis/TaxLimitsSection.tsx`** — `TaxTabContainer`의 "한도 현황" 탭 콘텐츠. `IsaMaturityCard`/`PensionContributionCard`(계좌 유무 조건부)와 `HealthInsuranceRiskCard`(항상 렌더)를 감싸는 순수 프레젠테이션 컴포넌트(자체 접기 카드 없음 — 탭이 이미 그 역할을 함). 계좌 필터와 무관하게 항상 전체 계좌 기준(`TaxOptimizationCard`의 세금 추정과 달리 `accountId` prop 없음). `HealthInsuranceRiskCard`가 항상 렌더되므로 이 탭이 완전히 빈 상태(empty-state 문구)는 없음.
- **`components/rebalancing/RecommendationCard.tsx`** — 목표 역산 추천 카드 (구 `GoalRecommendationCard.tsx` 대체, `RebalancingPage`에서 lazy-load). 전체/연령대/기간별 3개 탭의 결과 렌더(드리프트 배지→비중 목록→안내문구→후보 제안→적용 섹션)는 `RecommendationResultPanel.tsx`로 통합됨(2026-07-26, 그 이전엔 비중 목록·적용 섹션만 `RecommendationWeightList.tsx`/`RecommendationApplySection.tsx`로 부분 추출된 상태였음) — 탭별 설명 문구·`useMutation`·탭 전환 상태머신은 이 파일에 그대로 유지.
- **`components/rebalancing/RecommendationResultPanel.tsx`** — `RecommendationCard.tsx`의 전체/연령대/기간별 3탭이 공유하는 추천 결과 프레젠테이션(드리프트 배지·`RecommendationWeightList`·안내문구+`MarketSignalLevelBadge`·`SuggestedCandidatesBlock`·`RecommendationApplySection`)을 props로 데이터만 받아 렌더. `applySection`이 `null`이면 적용 섹션 자체를 생략(기간별 탭에서 현금성 자산을 자동 연결할 계좌가 없어 적용이 불가능한 경우).
- **`components/invest/GoalSettingWizard.tsx`** — 투자 목표 최초 설정용 6단계 마법사(현재 자산 확인 → 목표 금액/시점 → 월 적립액 → 결과 확인 → 투자성향·배당목표 → 추천 포트폴리오). `GET /invest/goal-feasibility`로 필요 연수익률·가정 수익률 프리셋별 필요 적립액을 역산해 제안. 5단계(출생연도·리스크 성향·배당목표)까지 입력하면 6단계 진입 시 자동 저장 후 `GET /rebalancing/goal-recommendation`(전체 자산 기준 목표 역산 추천)을 조회해 보여주고, "이 추천으로 포트폴리오 만들기"로 그 비중 그대로 신규 `Portfolio`를 생성할 수 있다(계좌 미연결 가상 목표비중). `InvestPlanPage.tsx`의 기존 플랫 편집 모달(재설정 전용)과 별개로 유지되며 대체하지 않음 — 플랫 모달은 5·6단계 UI가 없어 리스크성향 재설정 없이 기존 값을 그대로 유지한다. `useGoalSettings.ts`의 `openWizard()`/`wizardMode`/`wizardStep`이 상태 관리.

**Android 홈 위젯:** `useWidget.ts`(React 훅) ↔ `src/plugins/WidgetPlugin.ts`(Capacitor 플러그인 브리지) ↔ 네이티브 `android/app/src/main/java/com/growlio/app/{GrowlioWidget,WidgetPlugin}.java`. 위젯 UI 변경 시 네이티브 Java 코드도 함께 수정 필요.

**데이터 흐름:**
```
api/client.ts (axios + JWT interceptor + 401 자동 refresh)
  └── api/{alerts,assets,auth,backtest,dashboard,dividends,economicIndicators,
           insights,invest,marketSignals,portfolios,rebalancing,rebalancingPlan,risk,settings,tax,transactions}.ts
        └── React Query useQuery/useMutation   # 자동 refetch (REFETCH_INTERVAL 상수 기준)
              └── Page 컴포넌트
```

> `api/economicIndicators.ts`는 백엔드 `/economic-indicators/inflation-summary`(CPI·Core CPI 요약)만 호출 — `RebalancingPage`의 `InflationSummaryCard`가 소비. 백엔드에는 이 엔드포인트만 존재함(과거 프론트 미연동이던 지표 목록·구독·캘린더 엔드포인트는 제거됨).

**hooks/**
- `useExchangeRate.ts` — 환율 조회
- `useForm.ts` — 폼 상태 관리
- `useStockSearch.ts` — 종목 검색
- `useCurrencyInput.ts` — 통화 입력 처리 (KRW/USD 포맷팅)
- `useTaxSimulation.ts` — 세금 시뮬레이션 로직 (해외 양도세 계획)
- `useTaxLimitsSummary.ts` — ISA 만기·연금 공제한도·세금 추정 현황을 한 줄 요약(`parts`/`warningText`)으로 계산. `TaxLimitsBanner.tsx`(본문)와 `InvestmentSnapshotCard.tsx`(헤더 경고 배지·collapsedHint) 양쪽에서 호출
- `useAssetManagementData.ts` — 자산관리 페이지 전용 데이터 훅 (accounts + portfolio overview + transactions 통합)
- `useAssetModals.ts` — 자산관리 페이지 모달 열기/닫기 상태 통합 관리
- `useDashboardData.ts` — 대시보드 페이지 전용 데이터 훅 (dashboard + overview + dca + exchange-rate 통합)
- `useDividendData.ts` — 배당 요약 데이터 조회
- `useDividendPlanSettings.ts` — 배당 계획(연/월배당) 설정 폼 상태 관리
- `useEditableSettingsForm.ts` — 설정 편집 모달 공용 상태 머신(editing/saving/dirty-check/close-confirm). `useGoalSettings`/`useDividendPlanSettings`가 내부적으로 사용
- `usePositionsEditor.ts` — 포지션(종목) 편집 폼 상태 관리
- `usePortfolioItemsEditor.ts` — 포트폴리오 종목 편집 폼 상태 (종목 검색 연동)
- `useKisCredentialVerify.ts` — KIS 자격증명 검증 상태 머신 (`verifyKisCredentials` 래핑)
- `useRebalancingBalances.ts` — 리밸런싱 잔고 조회
- `useRebalancingExecution.ts` — 리밸런싱 주문 실행 훅의 공개 진입점(barrel re-export). 실제 구현은 `rebalancingExecution/`(`index.ts`/`reducer.ts`/`types.ts`) 패키지에 있지만, 모든 소비 코드는 이 파일을 통해서만 import — 패키지를 직접 import 금지
- `useRebalancingPrices.ts` — 리밸런싱 종목 현재가 조회
- `useAccountMutations.ts` / `useAccountPositions.ts` — 계좌 뮤테이션·포지션 조회
- `useStockAccountStats.ts` — 증권 계좌별 평가금액·투자원금·손익·입금액·배당액 통계 집계 (portfolio overview + 거래내역 조인)
- `useAlertCrud.ts` / `useRebalancingAlertForm.ts` — 알림 CRUD
- `useSettingsToggle.ts` — `["settings"]`의 boolean 필드 하나를 조회 후 PUT으로 토글하는 반복 패턴(조회+뮤테이션+무효화+에러토스트)을 통합한 제네릭 팩토리(`{ field, defaultValue, mutationFn, invalidate }`). 아래 4개 훅(`useGoalAchievementAlertsToggle`/`useMonthlyReportAlertsToggle`/`useYearEndTaxReminderToggle`/`useRecommendationDriftAlertToggle`)이 필드명만 다르게 얹어 씀 — 전용 상태 조회 엔드포인트가 있는 `useCompositeSignalToggle`/`useMarketSignalDigestToggle`(설정 필드는 후자만 해당)은 구조가 달라 이 팩토리를 쓰지 않음
- `useCompositeSignalToggle.ts` — 시장/리스크 복합신호 알림(등급 전환 시 즉시) on/off 조회·토글. `MarketSignalAlertSection`(설정 페이지, 토글 가능한 단일 소스)과 `MarketSignalBanner`(진단 탭, 상태만 읽기 전용 표시 + 설정 페이지 링크)가 공용
- `useMarketSignalDigestToggle.ts` — 시장신호 매일 요약(08:30 KST, 등급 전환 여부 무관) 알림 on/off. `useCompositeSignalToggle`과 별개 설정 — `["settings"]` 쿼리의 `market_signal_daily_digest_enabled` 필드를 직접 읽음 (전용 상태 조회 엔드포인트 없음). `MarketSignalAlertSection`이 두 번째 토글로 사용
- `useYearEndTaxReminderToggle.ts` — 11~12월 매주 월요일 09:00 KST 연말 절세 리마인더(손실수확·공제한도 요약) on/off. `useSettingsToggle` 사용, `year_end_tax_reminder_enabled` 필드 · `PUT /settings/year-end-tax-reminder`. 기본값 `false`(옵트인). `NotificationSettingsPage`의 "정기 리포트·요약" 그룹에 배치
- `useGoalAchievementAlertsToggle.ts` — 자산/입금/배당 목표 달성 알림(이메일·푸시) on/off. `useSettingsToggle` 사용, `goal_achievement_alerts_enabled` 필드 · `PUT /settings/goal-achievement-alerts`. 기본값 `true` (미설정 시 수신)
- `useMonthlyReportAlertsToggle.ts` — 매월 1일 발송 월간 포트폴리오 리포트 이메일 on/off. `useSettingsToggle` 사용, `monthly_report_enabled` 필드 · `PUT /settings/monthly-report-alerts`. 기본값 `true` (미설정 시 수신)
- `useRecommendationDriftAlertToggle.ts` — 매주 월요일 09:15 KST "추천 비중이 달라졌어요" 알림(이메일·푸시) on/off. `useSettingsToggle` 사용, `recommendation_drift_alert_enabled` 필드 · `PUT /settings/recommendation-drift-alert`. 기본값 `false`(옵트인)
- `useCollapsible.ts` — `[isOpen, toggle, setIsOpen]` 반환하는 접기/펼치기 상태 헬퍼. `CollapsibleCard`/`CollapsibleSection`과 함께 사용
- `useModalBehavior.ts` — 모달 공통 동작(body 스크롤 잠금 참조카운트, 포커스 트랩, Escape 닫기, pull-to-refresh 터치 전파 차단) 훅. `common/Modal.tsx`와 독자 레이아웃이 필요한 모달(`RebalancingExecutionModal.tsx` 등)이 공용
- `useAllocationHistory.ts` / `useAnalysisState.ts` / `useOptimizationSuggestions.ts` — 포트폴리오 분석
- `useBacktestDateRange.ts` — 백테스트 날짜 범위 관리
- `useBiometric.ts` — 생체 인증 (Capacitor Android)
- `useInsights.ts` — 인사이트 조회
- `useGoalSettings.ts` — 투자 목표 설정 폼 상태
- `useHaptic.ts` / `usePullToRefresh.ts` / `useSwipeNavigation.ts` — 모바일 UX
- `useLogout.ts` — 로그아웃 로직, `useOnlineStatus.ts` — 온라인/오프라인 감지
- `usePortfolioTabFetching.ts` — 포트폴리오 탭 데이터 프리패치
- `usePushNotifications.ts` / `useRegisterRefresh.ts` / `useWidget.ts` — FCM 푸시·홈 위젯 (Android)
- `useSyncAllWatcher.ts` — "전체 갱신"(계좌 전체 동기화) 백그라운드 진행 상태 폴링. `App.tsx`의 `AppRoutes()` 최상단에서 한 번만 마운트되어 탭 이동과 무관하게 계속 폴링 — 진행 상태는 `stores/syncStore.ts`(Zustand)로 관리
- `useTransactionFormState.ts` — 거래내역 입력 폼 상태
- `useCapsLockWarning.ts` — 비밀번호 입력 시 Caps Lock 켜짐 여부 감지 (로그인/회원가입 폼)

새 커스텀 훅은 이 디렉토리에 추가/삭제 시 위 목록도 갱신.

**기타 상수 (`src/constants/`):**
- `queryKeys.ts` — React Query queryKey 상수 (`QUERY_KEYS` 객체). 모든 queryKey는 여기서 import
- `queryConfig.ts` — `STALE_TIME`, `REFETCH_INTERVAL` 상수. 매직 넘버 대신 이 상수 사용
- `defaults.ts` — 백테스트 기본 날짜 상수 (`BACKTEST_DEFAULT_START_DATE` 등)
- `tabs.ts` — 탭 배열 + 타입: `ASSETS_TOP_TABS`("투자현황"/"계좌관리", AssetsPage 상위 탭), `ASSET_MANAGEMENT_TABS`("은행계좌"/"증권계좌"/"부동산"/"입출금·배당", 계좌관리 내부 탭), `PORTFOLIO_TABS`
- `transaction.ts` — 거래 유형 한국어 레이블 맵 (`TX_LABELS`: DEPOSIT/WITHDRAWAL/DIVIDEND)
- `validation.ts` — 포트폴리오 비중 허용 오차 (`PORTFOLIO_WEIGHT_TOLERANCE`)
- `rebalancingConfig.ts` — 리밸런싱 알림 폼용 상수 (`SCHEDULE_OPTIONS`, `TRIGGER_CONDITION_OPTIONS`, `MODE_OPTIONS`, `STRATEGY_OPTIONS`, `MARKET_CONDITION_OPTIONS`, `TAX_IMPACT_GATE_OPTIONS` — AUTO 모드 세금영향 게이트 on/off, `AlertAutoModeSection.tsx`가 소비)
- `uiSizes.ts` — 모바일 터치 타겟 상수 (`TOUCH_TARGET_MIN`: `min-h-[44px] min-w-[44px]` + 가운데 정렬, `TOUCH_TARGET_MIN_MOBILE_ONLY`: 모바일에서만 44px 적용하고 `sm:` 이상에서 축소하는 변형, `TOUCH_TARGET_ROW`: 아이콘+레이블이 좌측 정렬인 메뉴 로우/링크용 변형(`justify-start`), `TOUCH_TARGET_COMPACT_MOBILE_ONLY`: 배지/탭/필터 칩처럼 조밀하게 나열되는 보조 요소용 절충 터치 타겟(36px, 모바일 전용). 인터랙티브 요소(버튼/입력 등)에 인라인 `min-h-[44px] min-w-[44px]` 재정의 금지, 이 상수들 사용
- `timers.ts` — UI 타이밍 상수 (`SEARCH_DROPDOWN_HIDE_DELAY`: 150ms blur 후 드롭다운 지연, `REDIRECT_DELAY_MS`: 3000ms, `FOCUS_SETTLE_DELAY`: 0ms)
- `assets.ts` — 자산 유형 관련 상수 (`CASH_TICKER`, `REAL_ESTATE_ASSET_TYPE`, `KR_PROPERTY_MARKET`, `BASE_TYPE_STOCK_ONLY`, `BASE_TYPE_TOTAL_ASSETS`)
- `nav.ts` — `BottomNav` 탭 정의 (홈/자산/리밸런싱/계획/설정 5탭)
- `markets.ts` — 해외거래소 판별 상수 (상세는 하단 "마켓 유틸리티" 참고)
- `inputStyles.ts` — 공통 입력 필드 Tailwind 스타일 상수 (상세는 하단 "입력 스타일 상수" 참고)
- `index.ts` — 상수 re-export

**타입 정의:** `src/types/index.ts` — 포트폴리오 포지션, 계좌 등 공통 TypeScript interface 정의.

**Zod 스키마 (`src/schemas/`):**
- `assets.ts`, `auth.ts`, `portfolios.ts`, `transaction.ts` — 폼 입력값 런타임 유효성 검사 (Zod). 새 폼 추가 시 이 디렉토리에 스키마 파일 추가.

**테스트 위치 (Vitest):**
- `src/utils/__tests__/*.test.ts` — 순수 유틸 함수 단위 테스트 (`format.test.ts`, `error.test.ts`, `colors.test.ts`, `chart.test.ts`, `dividendUtils.test.ts`, `portfolio.test.ts`, `queryInvalidation.test.ts`, `accounts.test.ts`, `diagnosisInsights.test.ts`, `platform.test.ts`, `toast.test.ts` 등)
- `src/__tests__/components.*.test.tsx` — 컴포넌트 테스트 (10개)
- `src/__tests__/pages.*.test.tsx` — 페이지 테스트 (9개)
- `src/__tests__/hooks.*.test.ts(x)` — 커스텀 훅 테스트 (7개)
- `src/__tests__/api.*.test.ts` — API 레이어 테스트 (7개)
- 도메인별 개별 위치: 예) `src/components/rebalancing/__tests__/rebalancingTradeMath.test.ts`

> 순수 유틸뿐 아니라 컴포넌트·훅·페이지·API 레이어 모두 테스트 대상. 새 유틸은 동일 디렉토리에 `*.test.ts`, 새 컴포넌트/훅/페이지는 `src/__tests__/`에 대응 파일 작성. `vite.config.ts`에 커버리지 임계값(lines/functions/branches/statements) 설정됨.

**E2E 테스트 (Playwright):**
```bash
# dev 서버(localhost:5173)가 실행 중이어야 함 — package.json에 전용 npm 스크립트 없음
cd frontend && npx playwright test
```
- 설정: `playwright.config.ts`
- 위치: `e2e/` — `auth.setup.ts`(로그인 상태 저장), `auth.spec.ts`, `dashboard.spec.ts`, `asset-management.spec.ts`, `portfolio.spec.ts`, `transactions.spec.ts`

**asset_type_allocation:** 백엔드는 모든 자산 유형을 반환. PortfolioPage에서 STOCK 타입만 프론트엔드 필터링으로 표시 — 포트폴리오 페이지는 주식 계좌 전용 뷰이므로 의도된 동작.

**`src/lib/supabase.ts`** — Supabase 클라이언트 초기화 (env vars 필요). 직접 확장 금지 — 인증 흐름은 백엔드 JWT가 담당하며 이 파일은 초기화 목적으로만 존재.

> **인증 구조:** Supabase는 이메일 인증·OAuth 콜백(리다이렉트 URL) 처리에만 사용됨. 실제 API 인증은 백엔드(`auth.py`)가 발급한 JWT Bearer 토큰 사용. `api/client.ts`의 Axios 인터셉터가 토큰 관리. Supabase Session과 백엔드 JWT는 별개이므로 혼용 금지.

> 타입 체크는 `npm run build` 또는 위 tsc 명령으로 대체.

**상태 관리 원칙:** 서버에서 오는 데이터 → React Query. 순수 클라이언트 전역 상태 → Zustand.
- Zustand (`src/stores/`): `authStore.ts`(인증 토큰·유저 정보), `themeStore.ts`(다크모드 토글), `syncStore.ts`("전체 갱신" 백그라운드 진행 상태 — `useSyncAllWatcher.ts`가 갱신)
- 새 전역 상태 추가 시: 서버 fetch가 필요하면 React Query 훅, 그렇지 않으면 Zustand store.

**포트폴리오와 대시보드의 관계:** `DashboardPage`가 `/portfolio/overview`를 추가 조회해 `PortfolioSummaryCard`에 전달. 양쪽이 같은 queryKey(`"portfolio-overview"`)를 공유하므로 포트폴리오 sync 후 대시보드도 자동 갱신됨.

---

## Absolute Rules

**수익/손실 색상 (한국 주식 관례)**
- 수익(양수) → `text-red-500`, 손실(음수) → `text-blue-500`.
- 대소문자 주의: 전통적인 green/red와 반대. 절대 혼용 금지.

**React Query queryKey 규칙**
| 데이터 | queryKey |
|--------|----------|
| 대시보드 집계 | `["dashboard"]` |
| 포트폴리오 overview (accountId 지정 시 계좌별, 미지정 시 "all") | `["portfolio-overview", accountId]` — `portfolioOverviewBase`(`["portfolio-overview"]`)는 무효화 프리픽스 전용 |
| 포트폴리오 overview (경량) | `["portfolio-overview", "lite"]` |
| 포트폴리오/백테스트/리밸런싱 탭 | `["portfolios"]` |
| 전체 계좌 목록 | `["accounts"]` |
| 계좌별 포지션 | `["account-positions", accountId]` |
| 계좌별 거래내역 | `["transactions", accountId]` |
| 전체 거래내역 (무기간) | `["transactions", "all"]` |
| 연도별 거래내역 | `["transactions", "all", year]` |
| 배당금 티커별 (accountId 지정 시 계좌별) | `["dividend-by-ticker", accountId]` — `dividendByTickerBase` 무효화 전용 |
| 배당금 요약 (accountId 지정 시 계좌별) | `["dividend-summary", accountId]` — `dividendSummaryBase` 무효화 전용 |
| 배당금 포지션 (accountId 지정 시 계좌별) | `["dividend-positions", accountId]` — `dividendPositionsBase` 무효화 전용 |
| DCA 분석 (InvestPlanPage + DashboardPage) | `["dca-analysis"]` |
| 배당 계획 (연/월배당) | `["dividend-plan"]` |
| 배당 월별 균등화 제안 | `["monthly-optimization"]` |
| 설정 | `["settings"]` |
| 현재 환율 | `["exchange-rate"]` |
| 환율 알림 목록 | `["exchange-rate-alerts"]` |
| 주가 알림 목록 | `["stock-price-alerts"]` |
| 리밸런싱 알림 목록 | `["rebalancing-alerts"]` |
| 포트폴리오별 리밸런싱 알림 | `["rebalancing-alert", portfolioId]` |
| 포트폴리오 내 계좌별 알림 목록 | `["rebalancing-alert", portfolioId, "accounts"]` |
| 계좌별 개별 알림 | `["rebalancing-alert", portfolioId, "accounts", accountId]` |
| 리밸런싱 실행 이력 | `["rebalancing-history"]` |
| 리밸런싱 대기 플랜 목록 | `["rebalancing-plans"]` |
| 리밸런싱 전략 | `["rebalancing-strategy", portfolioId]` — `rebalancingStrategyBase`(`["rebalancing-strategy"]`)는 무효화 프리픽스 전용 |
| 드리프트 경량 요약 (대시보드) | `["drift-summary"]` |
| 세금 추정 요약 (accountId 지정 시 계좌별) | `["tax-summary", year, accountId]` — `taxSummaryBase` 무효화 전용 |
| 해외 포지션 양도세 계획 (accountId 지정 시 계좌별) | `["overseas-positions-tax", accountId]` — `overseasPositionsTaxBase` 무효화 전용 |
| ISA 만기 현황 | `["isa-status"]` |
| 연금 납입 현황 | `["pension-contribution", year]` |
| 자산배분 이력 (DashboardPage 전용, accountId 지정 시 계좌별) | `["allocation-history", months, accountId]` — `allocationHistoryBase` 무효화 전용 |
| 알림 발송 이력 | `["alert-history"]` |
| 인사이트/진단 | `["insights"]` |
| 포트폴리오 리스크 지표 | `["portfolio-risk", id]` |
| 시장 위험 신호 | `["market-signal"]` |
| 복합신호 (시장/리스크) 상태 | `["composite-signal-status"]` |
| 목표 역산 추천 (전체 자산) | `["goal-recommendation", "overall"]` |
| 목표 역산 추천 (투자기간별) | `["goal-recommendation", "by-horizon"]` |
| 목표 역산 추천 (연령대별) | `["goal-recommendation", "by-age"]` |
| 포트폴리오 적용 전 비교 미리보기(현재 목표 비중 기대지표) | `["portfolio-expected-metrics", portfolioId]` |
| 목표 설정 마법사 필요수익률·적립액 가이드 프리뷰 | `["goal-feasibility", goalAmount, targetYear, monthlyDepositAmount, initialAmount]` |
| CPI/Core CPI 인플레이션 요약 | `["inflation-summary"]` |

> 모든 키는 `src/constants/queryKeys.ts`의 `QUERY_KEYS` 상수에서 import. 문자열 하드코딩 금지. 새 키 추가 시 이 표도 함께 갱신.

**mutation 후 캐시 무효화**
- 트랜잭션 CUD → `["transactions", "all"]` + `["dashboard"]` 동시 무효화.
- 계좌 sync → `portfolioOverviewBase`(전체 계좌 필터 조합 포함) + `["dashboard"]` + 배당/세금/자산배분이력 Base 키 무효화.
- 계좌 CUD (자산관리에서) → `["accounts"]` + `portfolioOverviewBase` + `["dashboard"]` + 배당/세금/자산배분이력 Base 키 무효화.
- 배당/세금/자산배분이력은 `account_id` 쿼리 파라미터별로 캐시가 분기되므로(투자현황 탭 계좌 필터), 무효화 시 항상 `xxxBase`(prefix) 키를 사용 — 특정 accountId 키만 지우면 다른 계좌 조합의 캐시가 stale로 남음.

> 수동 `invalidateQueries` 호출 금지 — `src/utils/queryInvalidation.ts`의 유틸 함수 사용 (하단 참고).

**포맷팅 유틸리티 (`src/utils/format.ts`)**
- 모든 포맷 함수는 `src/utils/format.ts`에서 import. 로컬 재정의 금지.
  ```ts
  import { fmtKrw, fmtKrwNullable, fmtKrwShort, fmtMonth, fmtPct } from "@/utils/format";
  ```
- `fmtKrw(n)` — 억원/만원/원 (음수 포함). 일반 텍스트 표시용.
- `fmtKrwNullable(n)` — null/undefined이면 "—" 반환. 테이블 셀 등.
- `fmtKrwShort(n)` — "억"/"만" (단위 없음). 차트 레이블용.
- `fmtKrwPrice(n)` — 소수점 없는 원화 가격 표시.
- `fmtMonth(str)` — "YYYY-MM" → "YYYY년 M월".
- `fmtPct(n)` — "+5.23%" 형식. null이면 "—".
- `convertUsdToKrw(usd, rate)` / `formatUsdAsKrw(usd, rate)` — USD → KRW 환산·포맷.
- `relativeTime(date)` — "3분 전" 등 상대 시간 표시.
- 차트 X축은 `"YY.M"` 형식 (`"25.1"` 등) — 직접 문자열 파싱으로 타임존 이슈 방지

**에러 유틸리티 (`src/utils/error.ts`)**
- `extractErrorMessage(error, fallback?)` — Axios 에러에서 `response.data.detail` 추출. API 에러 메시지 수동 파싱 금지.
  ```ts
  import { extractErrorMessage } from "@/utils/error";
  // catch (e) { toast(extractErrorMessage(e)); }
  ```

**토스트 (`src/utils/toast.ts`)**
- `toast(message, type?)` — `window.dispatchEvent("growlio:toast")` 이벤트 발행. `useToast()` 훅 외부(비React 코드)에서도 직접 호출 가능.
  ```ts
  import { toast } from "@/utils/toast";
  toast("저장되었습니다", "success");
  ```

**포트폴리오 유틸리티 (`src/utils/portfolio.ts`)**
- `groupPositionsByTicker(positions)` — 종목 배열을 ticker+market 기준으로 집계. 여러 계좌 보유 종목 합산 표시 시 사용.
- `getPortfolioTargetState(portfolio, stockAccounts)` — 포트폴리오의 연결 계좌가 "목표 포트폴리오"로 전부/일부/전혀 지정 안 됐는지 판별 ("full"/"partial"/"none").
- `getPortfolioHorizon(portfolio, stockAccounts)` / `getPortfolioHorizonTaxType(portfolio, stockAccounts)` — 포트폴리오의 `investment_horizon`(+`tax_type`) 명시값이 없으면 "기준 포트폴리오"로 지정된 계좌들의 태그가 전부 동일할 때만 역으로 추론. 목표 역산 추천(`RecommendationCard`) 적용 시 어느 포트폴리오가 어느 (기간, 세제유형) 카드를 담당하는지 판별.
- `inferHorizonTaxTypeFromAccounts(accounts)` — 계좌 목록의 `investment_horizon`/`tax_type`이 전부 동일하면 반환. 추천 비중 카드에서 계좌가 미리 선택된 채로 새 포트폴리오를 만들 때 두 태그 초기값을 채우는 데 사용.
- `mergeAlertsByPortfolio(alerts)` — PER_ACCOUNT 스코프 포트폴리오의 계좌별 알림을 portfolio_id 기준으로 병합 (하나라도 AUTO면 병합 결과도 AUTO 표시).

**리밸런싱 알림 설명 유틸리티 (`src/utils/rebalancingAlertDescription.ts`)**
- `buildAlertDescription(...)` — 알림 스케줄/트리거 조건/모드 설정을 사람이 읽는 한글 설명 문장으로 조합.

**리밸런싱 임계값 추천 유틸리티 (`src/utils/rebalancingThresholdRecommendation.ts`)**
- 목표 역산 추천 옵션(계좌 투자기간 태그 등) 기반으로 드리프트 임계값을 추천. `useRebalancingAlertForm.ts`에서 사용.

**추천 비중 변화 감지 유틸리티 (`src/utils/recommendationDrift.ts`)**
- `computeRecommendationDrift(recommended, current)` — 추천 비중과 목표 포트폴리오의 현재 비중을 ticker+market 기준 비교해 `{ maxDeltaPct, newCandidateCount }` 반환.
- `hasSignificantDrift(drift)` — `RECOMMENDATION_DRIFT_THRESHOLD_PCT`(3%p) 이상 차이 나거나 신규 후보가 있으면 true. `RecommendationCard.tsx`가 "추천이 달라졌어요" 배지 노출 여부 판단에 사용.
- `buildWeightDiffRows(recommended, current)` — 두 목록을 합쳐 종목별 (현재 비중, 추천 비중) 전체 비교 행을 만든다(추천 비중 내림차순 정렬) — "적용" 확인 모달의 비교 미리보기(`RecommendationComparisonPreview`, `RecommendationCard.tsx`)에서 사용.

**진단 인사이트 유틸리티 (`src/utils/diagnosisInsights.ts`)**
- `buildDiagnosisNotes(ctx)` — `DiagnosisContext`(시장상황/리스크/세금영향)를 화면 표시용 조건부 문구 리스트로 변환.
- `buildCombinedStatusNote(needsCount, marketLevel)` — "이탈 종목 발견 + 시장상황"을 결합한 한 줄 설명 생성.

**시장 위험 신호 표시 유틸리티 (`src/utils/marketSignalRows.ts`)**
- `buildSignalRows(signals)` — `MarketSignalResponse.signals`(8개 매크로 지표)를 고정 순서의 `SignalRowDisplay[]`로 변환. 백엔드 `market_signal_service.py`의 Tier A(VIX/하이일드 스프레드/고용)/B+C(미국 금리 커브·인플레이션·달러 인덱스·환율·유가) 분류를 그대로 재사용해 각 행에 `tier`를 부여 — `MarketSignalBanner.tsx`가 Tier A는 항상 노출, 나머지는 "매크로 지표 더보기" 서브 토글로 묶는 데 사용(2026-07-26, 8개 신호를 각각 하드코딩된 JSX+개별 색상/라벨 맵으로 반복하던 것을 데이터 기반으로 통합).
- `dotColorForSubScore(subScore)` — 모든 신호의 심각도 점 색상을 `sub_score`(0/1/2/3+) 기준 단일 함수로 통일(과거엔 레벨 enum별 개별 맵이 신호마다 따로 있었음).
- 공용 렌더러는 `components/rebalancing/SignalRow.tsx`(`{label, content}` 프레젠테이션 컴포넌트) — `MarketSignalBanner.tsx`가 `buildSignalRows()` 결과를 매핑해 렌더.

**계좌 유틸리티 (`src/utils/accounts.ts`)**
- `isPortfolioAccount(account)` / `isStockAccount(account)` / `isBankAccount(account)` — 계좌 유형 판별. 인라인 `asset_type` 비교 금지.

**색상 유틸리티 (`src/utils/colors.ts`)**
- P&L 색상은 `pnlColor(value)` 함수 사용 — `PROFIT_COLOR`(`text-red-500`) / `LOSS_COLOR`(`text-blue-500`) 상수도 export됨.
  ```ts
  import { pnlColor } from "@/utils/colors";
  // <span className={pnlColor(profit)}>
  ```
- 직접 `text-red-500` / `text-blue-500` 인라인 작성 금지 (색상 관례 변경 시 일괄 교체 불가).

**리스크 유틸리티 (`src/utils/riskLevel.ts`)**
- `buildMetrics(m)` — `PortfolioRiskMetrics`를 `RiskMetricsCard` 표시용 `MetricConfig[]`로 변환.
- `summarizeRiskLevel(...)` — 리스크 레벨(`RiskLevel`: low/medium/high) 판정 + `LEVEL_BADGE` 색상 매핑. `RiskMetricsCard.tsx`/`DiagnosisSummaryHeader.tsx`가 소비.

**배당 유틸리티 (`src/utils/dividendUtils.ts`)**
- `yieldBadgeClass(yield)` — 배당수익률에 따른 Tailwind 뱃지 클래스 반환 (≥7%: 초록, ≥4%: 에메랄드, ≥2%: 황색).
- `dividendFreqInfo(months, isManual)` — 월 배열로 배당 주기 레이블·색상 반환 (월배당/분기배당/반기배당/연배당).
- `weightBarColor(pct)` — 포트폴리오 비중 막대 색상 반환. 인라인 클래스 직접 작성 금지.

**입력 스타일 상수 (`src/constants/inputStyles.ts`)**
- 인라인 Tailwind 입력 스타일 직접 작성 금지. 상수 import해 사용:
  ```ts
  import { INPUT_SM, INPUT_MD, LABEL_SM, LABEL_MD, SELECT_SM, TEXTAREA_SM } from "../constants/inputStyles";
  ```
- `INPUT_SM` / `INPUT_MD` — `text-sm` / `text-base` 입력 필드 (border, bg, focus ring 포함)
- `LABEL_SM` / `LABEL_MD` — `text-xs` / `text-sm font-medium` 레이블
- `SELECT_SM` — INPUT_SM과 동일 (select 요소용), `TEXTAREA_SM` — resize-none 포함

**모바일 UI 최소 크기 규칙**
- 텍스트는 `text-xs`(12px) 미만 임의값(`text-[9px]`, `text-[10px]` 등) 사용 금지 — 모바일 가독성 저하.
- 인터랙티브 요소(버튼/입력 등) 터치 영역은 `src/constants/uiSizes.ts`의 `TOUCH_TARGET_MIN`(`min-h-[44px] min-w-[44px]`) 사용.
- 단, 배지/탭/필터 칩/보조 링크/카드 내부 아이콘 버튼처럼 여러 개가 조밀하게 나열되는 요소는 44px 강제 시 시각적으로 뭉툭해져 오히려 가독성이 떨어질 수 있다 — 이 경우 `TOUCH_TARGET_COMPACT_MOBILE_ONLY`(36px, WCAG AA 24px 이상 충족)를 사용해도 된다.
- 단, `StockAccountCard.tsx`/`BankAccountCard.tsx`/`PortfolioItemRow.tsx`의 삭제 버튼처럼 이미 앱 전역에 44px로 정착된 아이콘 버튼 패턴은 개별 화면에서 임의로 축소하지 말 것 — 화면 간 일관성이 깨짐.

**헤딩 구조 규칙 (접근성)**
- 각 페이지(`src/pages/*.tsx`)의 최상위 return에는 `<h1 className="sr-only">{페이지명}</h1>`을 두어 스크린리더 사용자가 진입 시 현재 위치를 알 수 있게 한다(시각적으로는 숨김 — `BottomNav`/탭 UI가 이미 시각적 내비게이션을 담당).
- 카드/섹션 제목은 `<span>`/`<p>` 대신 `<h2>`/`<h3>`을 사용 — 스크린리더의 헤딩 내비게이션(다음 섹션으로 건너뛰기)이 동작하려면 실제 헤딩 태그가 필요하다. `CollapsibleCard.tsx`/`settings/shared.tsx`(`SectionCard`)/`Modal.tsx` 등 공용 컴포넌트를 거치는 카드 제목은 이미 전부 `h2`이고, 직접 마크업을 그리던 나머지 straggler(`StockAccountSummaryCard`/`RealEstateSection`/`EditableNameField`/`HeroSummaryCard`)도 정리 완료. 단, `RebalancingMobileCard.tsx` 같은 반복되는 리스트 행 아이템은 헤딩으로 승격하지 않음(그리드/리스트에 다수 반복 렌더돼 헤딩 목록이 라벨로 도배되면 오히려 스크린리더 내비게이션을 해침) — 의도된 제외이니 새 컴포넌트를 만들 때도 이 기준을 따를 것.

**콜랩스 기본값 일관성 규칙**
- 정보 밀도가 낮은 헤드라인 카드(`HeroSummaryCard`, `InvestmentGoalCard` 최상위 등)는 콜랩스 불가로 항상 펼침 유지 — 접었다 폈다 할 만큼 내용이 많지 않음.
- 보조/상세 카드(`InvestmentSnapshotCard`, `RebalancingStatusCard`, `TaxLimitsSection` 등)는 `useCollapsible`로 접기 가능하게 하되, 최초 방문 시 기본값은 **열림**(`true`)으로 시작 — 사용자가 직접 접으면 그 상태가 `localStorage`로 유지된다.
- 단, 이미 펼쳐진 부모 카드 내부의 2차 상세 토글(`InflationSummaryCard`, `RebalancingDetailMetrics`, `RebalancingDiagnosisCard` 등 영속화 키 없는 세션 한정 토글)은 이 규칙 대상이 아님 — "최상위 카드"에만 적용되는 규칙이므로 중첩된 하위 토글까지 강제로 펼칠 필요는 없다.
- 새 카드 추가 시 이 규칙을 따를 것.

**마켓 유틸리티 (`src/constants/markets.ts`)**
- `isOverseasMarket(market)` — market 문자열이 해외거래소인지 판별. 인라인 문자열 비교 금지.
  ```ts
  import { isOverseasMarket } from "../constants/markets";
  // isOverseasMarket("NYSE") → true, isOverseasMarket("KOSPI") → false
  ```

**플랫폼 감지 유틸리티 (`src/utils/platform.ts`)**
- `isNativePlatform()` — Capacitor WebView(네이티브 앱) 여부 감지. Android 빌드에서만 `true` 반환.
- `getApiBaseUrl()` — 네이티브: `VITE_API_DOMAIN` 기반 절대 URL, 웹: `""` (상대 경로 유지).
- API 클라이언트나 네이티브 전용 분기 작성 시 인라인 `window.Capacitor` 접근 금지 — 이 함수 사용.

**차트 유틸리티 (`src/utils/chart.ts`)**
- `chartTooltipStyle(isDark)` — Recharts `<Tooltip>` 다크모드 스타일 반환. 인라인 스타일 객체 중복 작성 금지.
  ```ts
  import { chartTooltipStyle } from "../utils/chart";
  const { contentStyle, labelStyle, itemStyle } = chartTooltipStyle(isDark);
  ```

**캐시 무효화 유틸리티 (`src/utils/queryInvalidation.ts`)**
- 계좌 sync 후: `invalidateSyncData(queryClient)` — portfolio-overview + dashboard + dividend 동시 무효화.
- 계좌 CUD 후: `invalidateAccountData(queryClient)` — accounts + portfolio-overview + dashboard 무효화.
- 거래내역 CUD 후: `invalidateTransactionData(queryClient)` — transactions-all + dashboard 무효화.
- 포트폴리오/백테스트/리밸런싱 CUD 후: `invalidatePortfolioData(queryClient)` — portfolios + accounts + drift-summary + rebalancing-strategy(전체 포트폴리오, 프리픽스) 무효화. 목표 비중 저장 직후 이미 열려있는 리밸런싱 분석 화면(`useAnalysisState`)은 이 무효화가 아니라 `AnalysisPanel`이 계산하는 `portfolioItemsSignature`(분석 중인 포트폴리오의 `items` 직렬화 값) 변경 감지로 자동 재분석됨 — `Portfolio.updated_at`은 비중만 바뀐 저장에서는 갱신되지 않으므로 신선도 판단에 쓰지 말 것.
- DCA 목표 변경 후: `invalidateDcaData(queryClient)` — dca-analysis + settings + dashboard 무효화.
- 환율 알림 CUD 후: `invalidateAlertData(queryClient)` — exchange-rate-alerts 무효화.
- 리밸런싱 알림 CUD 후: `invalidateRebalancingAlertData(queryClient, portfolioId)` — rebalancing-alerts + rebalancing-alert(portfolioId) 무효화.
- 배당 계획 변경 후: `invalidateDividendPlanData(queryClient)`.
- 주가 알림 CUD 후: `invalidateStockPriceAlertData(queryClient)`.
- 리밸런싱 주문 실행 후: `invalidateRebalancingHistoryData(queryClient)`.
- 리밸런싱 대기 플랜 취소/승인 후: `invalidateRebalancingPlanData(queryClient)` — 대기 플랜 목록 + 실행 이력 무효화.
- 복합신호(시장/리스크) 알림 설정 변경 후: `invalidateCompositeSignalData(queryClient)`.
- 시장신호 매일 요약 알림 설정 변경 후: `invalidateMarketSignalDigestData(queryClient)`.
- 연말 절세 리마인더 설정 변경 후: `invalidateYearEndTaxReminderData(queryClient)`.
- 목표 달성 알림 설정 변경 후: `invalidateGoalAchievementAlertsData(queryClient)`.
- 월간 리포트 설정 변경 후: `invalidateMonthlyReportAlertsData(queryClient)`.
- 추천 비중 변화 알림 설정 변경 후: `invalidateRecommendationDriftAlertData(queryClient)`.
- 목표 역산 추천 후보 변경 후: `invalidateGoalCandidateData(queryClient)`.
- 수동으로 `invalidateQueries` 여러 번 호출하지 말고 이 함수 사용.

> **새 invalidation 함수 추가 시:** 이 파일에 `invalidate<Domain>Data(queryClient)` 형태로 추가하고, 관련 mutation의 `onSuccess`에서 호출. 컴포넌트·훅 내부에서 직접 `queryClient.invalidateQueries()` 호출 금지.

**쿼리 설정 상수 (`src/constants/queryConfig.ts`)**
- `STALE_TIME.SHORT` (30s, 기본값), `STALE_TIME.MEDIUM` (60s), `STALE_TIME.LONG` (1h), `STALE_TIME.EXCHANGE_RATE` (5m)
- `REFETCH_INTERVAL.DASHBOARD` (5분), `REFETCH_INTERVAL.PORTFOLIO` (1분)
- staleTime/refetchInterval 매직 넘버 직접 작성 금지. 상수 import해 사용.

---

## Tailwind UI 패턴

**카드 컨테이너**
```
bg-white rounded-2xl border border-gray-200 p-5
dark:bg-gray-800 dark:border-gray-700
```

**아이콘 버튼 (hover 효과 포함)**
```
p-1.5 text-gray-400 hover:text-{color}-600 hover:bg-{color}-50 rounded-lg transition-colors
```

**기본 액션 버튼**
```
bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors
```

**위험(삭제) 버튼**
```
px-5 py-2 text-sm border border-red-300 text-red-600 rounded-lg hover:bg-red-50 transition-colors
```

**다크모드**
- `const { isDark } = useThemeStore()` — 컴포넌트에서 다크모드 상태 조회.
- Tailwind `dark:` 클래스는 HTML `class="dark"` 토글 방식. `isDark` 직접 사용보다 `dark:` 접두사 우선.
- 차트(Recharts)는 `dark:` 미지원 → `chartTooltipStyle(isDark)` 사용 (Absolute Rules 참고).
