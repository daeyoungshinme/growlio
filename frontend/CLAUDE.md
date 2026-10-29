# Frontend CLAUDE.md

> 파일 목록은 **한 줄 요약 + 코드만 봐선 모르는 함정**만 적는다. 설계 경위·변경 이력은 `docs/plans/`와 git log에 있다 — 여기에 다시 쓰지 말 것.

## Commands

```bash
cd frontend && npm install
cd frontend && npm run dev            # localhost:5173, /api/* → localhost:8000 프록시
cd frontend && npm run build          # tsc -b && vite build
cd frontend && npm run typecheck      # tsc --noEmit(앱) + -p tsconfig.test.json(테스트 포함, 같은 엄격도·noUncheckedIndexedAccess on) — build의 tsc -b는 앱만 본다
cd frontend && npm run lint           # eslint src
cd frontend && npm run format         # prettier --write src  (검사만: format:check — CI·make lint와 동일)
cd frontend && npm run test           # vitest run
cd frontend && npm run test -- src/utils/__tests__/format.test.ts
cd frontend && npm run test:watch
cd frontend && npm run generate:icons # public/favicon*.svg → 웹 아이콘·Android 런처/스플래시 PNG 재생성 (sharp)

# API 타입 생성 — 백엔드(localhost:8000) 실행 중일 때 수동. 결과 src/types/api.generated.ts는 gitignore, CI에서 생성 안 됨
cd frontend && npm run generate:api-types   # 사용: import type { components } from "@/types/api.generated"

# Android (Capacitor)
cd frontend && npm run cap:sync       # 웹 빌드 → Android 동기화
cd frontend && npm run cap:android    # Android Studio 열기
make build-android-debug / build-android-release
```

### Environment (`frontend/.env`, `.env.example` 참고)

- `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` — 없으면 Supabase 클라이언트 초기화 실패
- `VITE_REDIRECT_URL` — OAuth/이메일 인증 후 리다이렉트
- `VITE_API_DOMAIN` — API 도메인 (Vite 프록시·네이티브 절대 URL)
- `VITE_SENTRY_DSN`(선택), `VITE_SENTRY_RELEASE`
- 소스맵 업로드(CI/배포 전용, `.env` 아님): `SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT`, `SENTRY_RELEASE`

---

## Architecture (`frontend/src/`)

- **Import**: 새 코드는 `@/` alias (`@/* → src/*`).
- **상태 관리**: 서버 데이터 → React Query, 순수 클라이언트 전역 상태 → Zustand(`stores/`: `authStore`, `themeStore`, `syncStore`, `pushNotificationStore`).

### 라우트 (`src/App.tsx`, 인증 필요 라우트는 `PrivateRoute` 하위)

- 인증: `/login`, `/register`, `/find-account`, `/forgot-password`, `/reset-password`, `/auth/callback`(이메일 인증 랜딩, 인증 불필요)
- `/rebalancing/plan-confirm?token=` — 이메일 링크 전용 매수 취소/매도 승인(인증 불필요)
- `/dashboard` — 홈
- `/assets` — 단일 라우트, `?tab=` 투자현황/계좌관리 (`ASSETS_TOP_TABS`)
- `/invest-plan` — 적립 계획/배당 계획/절세/챌린지
- `/settings`, `/settings/notifications` — 각 기능의 편집 UI는 해당 페이지에 있고 설정 탭엔 요약 + 딥링크만
- `/rebalancing` — `?rtab=` 진단/포트폴리오/목표 조정/이력, 목표 조정 안 `?gmode=` 추천/전술. **링크는 반드시 `utils/rebalancingUrl.ts`의 `rebalancingUrl()`로**, 페이지 내부 URL 상태는 `hooks/useRebalancingUrlState.ts`
- `*` → `/dashboard`. `/market`·`/portfolio`·`/asset-management`·`/trend`는 없음(제거됨). `BottomNav`(`constants/nav.ts`)는 5탭
- 새 페이지는 `App.tsx`에 `<Route>` 등록 필수

### 데이터 흐름

```
api/client.ts (axios + Supabase access token 첨부 + 401 시 refreshSession 후 재시도)
  └── api/{도메인}.ts → React Query useQuery/useMutation → Page
```

- **인증**: 로그인·가입·갱신은 전부 Supabase Auth. 백엔드는 JWKS 검증만 — 별도 "백엔드 JWT" 없음.
- `lib/supabase.ts` — `await getSupabase()`로 지연 로드(supabase-js ~200KB가 부팅 경로를 막던 문제). **동기 `supabase` export 없음.** 토큰 첨부·갱신은 `api/client.ts` 소관. 세션은 localStorage 평문 — 쿠키 전환 보류 결정은 `docs/plans/28-localstorage-token-decision.md`.
- `lib/storedSession.ts` — 저장된 `sb-*-auth-token`을 SDK 없이 동기로 읽어 부팅 시 토큰 시드.
- `lib/sentry.ts` — 지연 초기화. **앱 코드는 `@sentry/react`를 직접 import 금지**(엔트리 청크로 다시 끌려옴).
- `lib/serviceWorker.ts` — 웹에서만 SW 등록, Capacitor에선 해제.
- `context/ExchangeRateContext.tsx` — 환율을 컨텍스트로 공유(`useExchangeRateContext()`).
- `asset_type_allocation`은 백엔드가 전 유형을 주고 PortfolioPage가 STOCK만 필터 — 의도된 동작.
- 대시보드와 자산탭이 `portfolio-overview` queryKey를 공유 — sync 후 양쪽 자동 갱신.

### 컴포넌트

디렉토리: assets, backtest, common, dashboard, invest, layout, portfolio, portfolio-analysis, rebalancing, settings, tax. 최상위 `ErrorBoundary.tsx`, `Toaster.tsx`(`growlio:toast` 이벤트 구독).

**`common/`** (추가/삭제 시 갱신): `AccountActionsMenu`(⋯ 오버플로우 메뉴 — 아이콘+라벨 함께 렌더, 모바일 `title` 미동작 우회), `AmountUnitButtons`, `BiometricGuard`, `Button`, `CollapsibleCard`(카드 전체, controlled), `CollapsibleSection`(카드 내부 경량), `ConfirmModal`, `EditableNameField`, `EmptyState`, `FormInput`, `Modal`(+`ModalFooter` — **입력 폼 모달의 저장 버튼은 여기에**, 본문 끝이면 모바일 키보드에 가려짐), `OfflineBanner`, `PageLoader`, `PriceCell`, `SkeletonCard`, `SkeletonStatBox`, `SuggestionDropdown`, `MiniDonut`(의존성 없는 SVG 도넛 — 홈이 recharts 청크 없이 그림), `Tabs`, `ToggleSwitch`(+`ToggleRow` — 행 전체가 label, 설정 목록은 이것), `Tooltip`, `TopLoadingBar`, `TreemapCell`

- `BiometricGuard` — Android 생체 인증 게이트. **UI 게이트일 뿐 보안 경계 아님**(캐시된 JWT로 API 호출은 막히지 않음).
- `OfflineBanner` — PWA Workbox `StaleWhileRevalidate`(dashboard/portfolio-overview/accounts)와 함께 오프라인 안내.

**주요 화면 컴포넌트 — 진입 지점과 함정만**

- `dashboard/ActionItemsCard` — 홈 "지금 할 일"(`GET /dashboard/action-items`). **홈에서 리밸런싱을 다루는 유일한 카드**(REBALANCE 행 + 시장 신호 배지). 배지 상수 `utils/marketSignalBadge.ts`, 우선순위·마감 라벨 `utils/actionPriority.ts`(둘 다 공용).
- `dashboard/{IsaMaturityCard,PensionContributionCard,HealthInsuranceRiskCard}` — 계획탭 › 절세의 `TaxLimitsSection`이 렌더(건보 카드는 항상).
- `portfolio-analysis/TaxTabContainer` — 계획탭 "절세"(`?taxTab=`, `?taxAccount=`). 옛 `/assets?portfolioTab=세금` 링크는 `utils/legacyTabRedirect.ts`가 옮김.
- `portfolio/AllocationCard` — 자산탭 비중 분석(국내/해외·종목·지수). 하위 뷰 `portfolio/allocation/`. "종목" 보기는 상위 5 + 기타만.
- `assets/AccountHistoryTab` — 계좌관리 "내역"(`?history=` 현금 흐름/매수 내역).
- `rebalancing/GoalAdjustTab` — 목표 조정(추천·전술 서브탭). 상단 포트폴리오 선택기는 **전술 모드만**, 추천은 `RecommendationCard` 적용 영역 select에서 고름 — 선택은 둘 다 URL `portfolioId` 공유. 콘텐츠 ErrorBoundary/Suspense는 **`key={mode}`로 모드마다 새 경계** — React Router v7이 URL 변경을 `startTransition`으로 감싸 공유 경계면 이전 모드 화면이 남는다.
- `rebalancing/TacticalAllocationTab` — 전술 배분(국면·제안 비중·적용). 적용은 `POST /tactical/{id}/apply`(**주문 없음**) 후 포트폴리오 탭 실행 흐름으로 넘김. 표시 조각 `TacticalStatusParts.tsx`, 확인창 `TacticalApplyConfirmModal.tsx`, 백테스트 `TacticalBacktestSection.tsx`, 비중표 편집 `TacticalWeightsEditor.tsx`, 문구·색상 `tacticalLabels.ts`. 차트 지표는 이 탭이 아니라 진단 탭 `MarketSignalBanner` + `ChartTrendList`. **설정 upsert는 항상 현재 `tilt_shift_pct`·`dip_shift_pct`·`use_macro`를 함께 보낸다**(생략 시 서버 기본값으로 덮임).
- `rebalancing/RecommendationCard` — 목표 역산 추천(목표 조정 › 추천 전용). 결과 렌더는 `RecommendationResultPanel.tsx`. 전체 추천은 콜드 계산이 수십 초라 **카드 전체를 막지 않고 결과 영역만 로딩**. `gcTime: STALE_TIME.DAY`, `RebalancingPage`가 같은 queryKey로 미리 발화.
- **자동화 설정 모달(`RebalancingAlertModalRouter`)의 호스트는 `PortfolioManageTab` 하나뿐** — 다른 진입점은 `portfolioId=<id>&openAlert=1`(`openAlert=dca`는 적립식 자동매수 프리셋) URL 파라미터로 요청. 모달을 직접 마운트하지 말 것.
- `invest/ChallengeSection` — 챌린지 탭. 홈 요약 `dashboard/ChallengeProgressCard`, 네비 빨간 점 `useChallengeNudge`.
- `invest/GoalSettingWizard` — 목표 최초 설정 6단계 마법사(`InvestPlanPage`의 재설정 모달과 별개).

**Android 홈 위젯**: `useWidget.ts` ↔ `plugins/WidgetPlugin.ts` ↔ 네이티브 `android/app/src/main/java/com/growlio/app/{GrowlioWidget,WidgetPlugin}.java` — 위젯 UI 변경 시 Java도 함께.

### hooks/ (추가/삭제 시 해당 그룹 갱신)

_공통/입력_
- `useExchangeRate` · `useForm` · `useStockSearch` · `useCurrencyInput` · `useCapsLockWarning` · `useTransactionFormState`
- `useCollapsible` — `[isOpen, toggle, setIsOpen]`(setter 참조 고정)
- `useLatestRef` — 한 번 등록하는 네이티브 리스너에서 최신 값 읽기. `useNavigate()`는 경로마다 새 함수라 effect deps에 넣으면 이동마다 재등록됨
- `useTimeout` — 언마운트 시 해제되는 setTimeout. 상태를 바꾸는 지연 콜백은 맨 `setTimeout` 대신 이것
- `useModalBehavior` — 스크롤 잠금·포커스 트랩·Escape. Escape·트랩은 **맨 위 모달만**(Android 뒤로가기가 Escape를 보내므로)
- `useEditableSettingsForm` — 설정 편집 모달 상태 머신. `numberFieldPayload()`로 부분 갱신 payload를 만든다(빈 칸 → 키 생략, 지움 → null) — `PUT /settings/goal`이 보낸 키만 바꾸기 때문
- `useMediaQuery`(`useIsSmUp`) — 모바일 카드/데스크톱 표 중 보이는 쪽만 렌더

_자산관리/대시보드_
- `useAssetManagementData` · `useAssetModals` · `useDashboardData` · `useAccountMutations` · `useAccountPositions` · `useStockAccountStats` · `usePositionsEditor` · `usePortfolioItemsEditor`
- `createCredentialVerify` — 자격증명 확인 상태 머신 팩토리. `useKisCredentialVerify`/`useKiwoomCredentialVerify`/`useTossCredentialVerify`는 얇은 래퍼, `useBrokerCredentialVerify`가 브로커별로 묶음(필드 정의 `constants/brokerCredentials.ts`)

_세금·배당_
- `useTaxSimulation` · `useDividendData` · `useDividendPlanSettings`

_리밸런싱/추천_
- `useSelectedPortfolio` — "지금 보는 포트폴리오"(URL → 기준 → 첫 번째). `{ preferTactical: true }`면 전술 켠 포트폴리오 우선. 기본값은 URL에 쓰지 않고 파생만
- `useRebalancingUrlState` — rtab·gmode·portfolioId. 탭은 state로 복사하지 않고 URL에서 파생
- `useRebalancingExecution` — **공개 진입점(barrel)**. 구현은 `rebalancingExecution/` 패키지지만 직접 import 금지
- `useAnalysisState` — 분석(기본은 동기화 기준 예수금, 결과 5분 재사용). 실시간 예수금은 "실시간 잔고로 다시 분석"(`live: true`)에서만
- `useRebalancingBalances` · `useRebalancingPrices` · `useAllocationHistory` · `useOptimizationSuggestions` · `useBacktestDateRange` · `useGoalSettings`
- `useAlertCrud` · `useRebalancingAlertForm`(`useRebalancingAlertQueries`·`useRebalancingAlertFormState`)
- `useSyncAccounts` — 여러 계좌 동기화 + 무효화(`run`이 전부 성공 여부 반환)
- `useDcaTacticalLink` — 적립식 자동매수의 전술 연동 여부 `{dcaAuto, linked}`. 계좌별 알림이 여럿일 수 있어 `mergeAlertsByPortfolio` 대신 행 단위 판정
- `useAutoExecutionNotice` — 켜진 AUTO가 있으면 "다음 자동 실행부터 새 목표로 주문" 문구
- `useAddSuggestedCandidates` · `useCandidateOverlap`(디바운스 포함)
- `useTacticalAllocation` — `useTacticalStatus`/`useTacticalBacktest`/`useTacticalMutations`(적용은 `invalidateTacticalData(qc, { portfolioChanged: true })`)
- `useChallenges` · `useChallengeMutations` · `useChallengeNudge`
- `usePortfolioTabFetching`(`useMainPageFetching`) — 새로고침 인디케이터용

_알림 토글_ (`["settings"]` boolean 필드 조회/PUT)
- `useSettingsToggle` — 제네릭 팩토리(`{ field, defaultValue, mutationFn, invalidate? }`). 아래 토글 대부분이 이것 위에 얹힘
- `useCompositeSignalToggle`(전용 상태 엔드포인트라 팩토리 미사용) · `useMarketSignalDigestToggle` · `useYearEndTaxReminderToggle`(기본 off) · `useGoalAchievementAlertsToggle`(on) · `useMonthlyReportAlertsToggle`(on) · `useRecommendationDriftAlertToggle`(off) · `useChallengeRemindersToggle`(off)
- `useAutoRebalancingDailyCap` — 금액 입력이지만 같은 패턴(null=무제한)

_모바일/네이티브_
- `useBiometric` · `useHaptic` · `usePullToRefresh` · `useSwipeNavigation` · `usePushNotifications` · `useRegisterRefresh` · `useWidget`
- `useSyncAllWatcher` — "전체 갱신" 폴링. `App.tsx` `AppRoutes()`에서 **한 번만** 마운트(상태는 `stores/syncStore.ts`)

_기타_
- `useInsights` · `useLogout` · `useOnlineStatus`

### constants/

- `queryKeys.ts` — **모든 queryKey는 `QUERY_KEYS`에서 import**
- `queryConfig.ts` — `STALE_TIME`/`REFETCH_INTERVAL` + persist(24h localStorage) 설정. **persist 대상 응답 형태를 호환되지 않게 바꾸면 `PERSIST_CACHE_BUSTER`를 날짜로 올린다**
- `tabs.ts` — `ASSETS_TOP_TABS`, `ASSET_MANAGEMENT_TABS`, `PORTFOLIO_TABS`
- `rebalancingConfig.ts` — 알림 폼 옵션 상수 + `PLAN_LEG_STATUS_LABEL`
- `uiSizes.ts` — 터치 타겟 상수 (아래 모바일 규칙)
- `markets.ts` · `inputStyles.ts` — 아래 Absolute Rules
- `transaction.ts`(`TX_TYPES`/`TX_LABELS`/`TX_COLORS`) · `validation.ts`(`PORTFOLIO_WEIGHT_TOLERANCE`) · `timers.ts` · `assets.ts` · `defaults.ts` · `goalRiskTolerance.ts` · `savingsPresets.ts` · `nav.ts` · `index.ts`(re-export)
- `brokerCredentials.ts` — 자격증명 폼 테이블. **새 브로커는 여기 추가**

**타입**: `src/types/index.ts`. **Zod(`src/schemas/`)**: `challenge`, `trade`, `transaction` — 실제 폼이 쓰는 스키마만, 새 폼 추가 시 여기에.

### 테스트 (Vitest)

- `src/utils/__tests__/*.test.ts` — 순수 유틸 (새 유틸도 여기)
- `src/__tests__/{components,pages,hooks,api}.*.test.ts(x)` — 새 컴포넌트·훅·페이지·API는 여기에 대응 파일
- 도메인별 개별 위치도 있음 (예: `components/rebalancing/__tests__/`)
- 커버리지 임계값은 `vite.config.ts`

---

## Absolute Rules

**수익/손실 색상 (한국 관례 — green/red와 반대)**: 수익 → `text-red-500`, 손실 → `text-blue-500`. 직접 쓰지 말고 `utils/colors.ts`의 `pnlColor(value)`(또는 `PROFIT_COLOR`/`LOSS_COLOR`).

**React Query queryKey**

| 데이터 | queryKey |
| --- | --- |
| 대시보드 집계 | `["dashboard"]` |
| 포트폴리오 overview | `["portfolio-overview", accountId]` (미지정 "all") · 경량 `["portfolio-overview", "lite"]` |
| 추종 지수별 비중 | `["index-exposure", accountId]` · 지수 그룹 제안 `["index-exposure", "group-suggestions", accountIds]` |
| 포트폴리오/백테스트/리밸런싱 탭 | `["portfolios"]` |
| 계좌 목록 / 계좌별 포지션 | `["accounts"]` / `["account-positions", accountId]` |
| 거래내역 | 계좌별 `["transactions", accountId]` · 전체 `["transactions", "all"]` · 연도별 `["transactions", "all", year]` |
| 기간별 매수 | `["period-purchases", period, year, month, accountId]` |
| 수기 매매 기록 | `["trades", accountId, ticker, market]` |
| 배당 | `["dividend-by-ticker", accountId]` · `["dividend-summary", accountId]` · `["dividend-positions", accountId]` · `["dividend-plan"]` · `["monthly-optimization"]` |
| DCA 분석 | `["dca-analysis"]` |
| 챌린지 | `["challenges"]` · 넛지 `["challenges", "summary"]` |
| 설정 / 환율 | `["settings"]` / `["exchange-rate"]` |
| 환율·주가 알림 | `["exchange-rate-alerts"]` · `["stock-price-alerts"]` |
| 리밸런싱 알림 | 목록 `["rebalancing-alerts"]` · 포트폴리오별 `["rebalancing-alert", portfolioId]` · 계좌 목록 `[..., "accounts"]` · 계좌별 `[..., "accounts", accountId]` |
| 리밸런싱 실행 이력 | `["rebalancing-history"]` · 상세 `["rebalancing-history", executionId]` |
| 대기 플랜 | `["rebalancing-plans"]` · 승인 페이지 미리보기 `["rebalancing-plan-preview", token]` |
| 리밸런싱 전략 | `["rebalancing-strategy", portfolioId]` |
| 드리프트 요약 / 지금 할 일 | `["drift-summary"]` / `["action-items"]` |
| 세금 | `["tax-summary", year, accountId]` · `["overseas-positions-tax", accountId]` · `["isa-status"]` · `["pension-contribution", year]` · `["overseas-realized", year, accountId]` · `["tax-action-plan"]` |
| 자산배분 이력 | `["allocation-history", months, accountId]` |
| 알림 발송 이력(무한 스크롤은 `alertHistoryPages`) / 인사이트 | `["alert-history"]` / `["insights"]` |
| 리스크 / 시장 신호 / 복합신호 | `["portfolio-risk"]` / `["market-signal"]` / `["composite-signal-status"]` |
| 목표 역산 추천 | `["goal-recommendation", "overall" \| "by-horizon" \| "by-age"]` · 후보 중복 `["goal-recommendation", "candidate-overlap", signature]` |
| 적용 전 비교 | `["portfolio-expected-metrics", portfolioId]` |
| 마법사 프리뷰 | `["goal-feasibility", goalAmount, targetYear, monthlyDepositAmount, initialAmount]` |
| 인플레이션 요약 | `["inflation-summary"]` |
| 전술 배분 | 상태 `["tactical-status", portfolioId]` · 켠 목록 `["tactical-status", "list"]` · 시장 입력 `["tactical-market"]`(무효화 없음) · 백테스트 `["tactical-backtest", portfolioId, years]` |

- 문자열 하드코딩 금지 — `QUERY_KEYS`에서 import. 새 키 추가 시 이 표도 갱신.
- 계좌·연도별로 분기되는 키는 무효화 전용 `xxxBase` 프리픽스 키(`portfolioOverviewBase`, `transactionsBase`, `taxSummaryBase` 등)가 따로 있다 — **무효화는 항상 Base 키로**(특정 accountId 키만 지우면 다른 조합이 stale).
- 여러 화면이 같은 키로 조회하는 쿼리(portfolios·settings·market-signal·drift-summary·composite-signal-status·accounts·portfolio-overview lite·rebalancing-alerts·goal-recommendation overall)는 `src/api/queryOptions.ts` 공용 정의 사용 — `useQuery(portfoliosQuery)`, 조건부는 `{ ...portfoliosQuery, enabled }`. 화면마다 queryFn·staleTime을 다시 적지 말 것(덮어쓰기는 이유가 있을 때만, 예: 위저드 `staleTime: NONE`, 대시보드 폴링). 새 공용 쿼리도 여기에. 부팅·로그인 프리페치 목록은 `src/api/prefetch.ts` 하나.

**캐시 무효화 (`src/utils/queryInvalidation.ts`)** — 컴포넌트·훅에서 `queryClient.invalidateQueries()` 직접 호출 금지. 새 함수는 `invalidate<Domain>Data(queryClient)` 형태로 여기에 추가. 각 함수의 정확한 대상은 소스 확인.

| 상황 | 함수 |
| --- | --- |
| 계좌 sync | `invalidateSyncData` |
| 계좌 CUD | `invalidateAccountData` |
| 브로커 연동 해제 | `invalidateBrokerCredentialData` |
| 거래내역 CUD | `invalidateTransactionData` |
| 수기 매매 기록 CUD | `invalidateTradeData` (해외 SELL이 양도세 실현손익이 되므로 세금·지금 할 일 포함) |
| 포트폴리오/리밸런싱 CUD | `invalidatePortfolioData` |
| 전술 설정 / 제안 비중 적용 / 전술 연동 자동매수 해제 | `invalidateTacticalData` / `{ portfolioChanged: true }` / `{ dcaLinked: true }` |
| DCA·배당 목표 변경 | `invalidateDcaData` (목표 금액·연도 변경은 `{ goalRecommendation: true }`, 배당 목표는 + `invalidateGoalRecommendationData`) |
| 소득 구간 변경 | `invalidateIncomeBracketData` |
| 챌린지 CUD | `invalidateChallengeData` |
| 환율 / 주가 / 리밸런싱 알림 CUD | `invalidateAlertData` / `invalidateStockPriceAlertData` / `invalidateRebalancingAlertData(qc, portfolioId)` |
| 주문 실행 | `invalidateRebalancingHistoryData` |
| 대기 플랜 취소/승인 | `invalidateRebalancingPlanData(qc, { executed })` — 응답 `EXECUTED`면 `executed: true` |
| 복합신호 설정 / 추천 후보 변경 | `invalidateCompositeSignalData` / `invalidateGoalRecommendationData` |
| 다른 화면 영향 없는 설정 | `invalidateSettingsData` (옵트인 토글 기본값) |

- 당겨서 새로고침처럼 자기 쿼리 하나만 다시 받을 땐 그 `useQuery`의 `refetch`.
- 목표 비중 저장 후 열린 분석 화면은 `portfolioItemsSignature` 변경으로 자동 재분석된다 — **`Portfolio.updated_at`은 비중만 바뀐 저장에선 갱신되지 않으니 신선도 판단에 쓰지 말 것.**

**쿼리 설정 상수 (`constants/queryConfig.ts`)** — staleTime/refetchInterval 매직 넘버 금지.
- `STALE_TIME`: `NONE`(0) · `VERY_SHORT`(15s) · `SHORT`(30s, 기본) · `MEDIUM`(60s) · `FIVE_MINUTES`/`EXCHANGE_RATE`(5m) · `LONG`(1h) · `DAY`(24h, 무거운 계산의 `gcTime`)
- `REFETCH_INTERVAL.DASHBOARD` / `.PORTFOLIO` (5분)

**포맷 (`utils/format.ts`)** — 로컬 재정의 금지.
- `fmtKrw`(억/만/원) · `fmtKrwPreview`(입력 중 "5,000,000원 (500만원)") · `fmtKrwShort`(차트 레이블) · `fmtKrwPrice` · `fmtMonth` · `fmtPct`(null → "—") · `fmtDateTime` · `relativeTime` · `convertUsdToKrw`/`formatUsdAsKrw`
- `pctOf(part, total)` — 인라인 `total > 0 ? v / total * 100 : 0` 대신. `clampPct(pct)` — 진행률 바 width에 그대로 넣지 말 것
- **날짜**: `localToday()`/`localMonth()` 사용 — `new Date().toISOString().slice(...)`는 UTC라 KST 09시 전엔 전날/전월. 모듈 최상위 상수로 고정하지 말고 폼을 열 때 호출. `parseYmd`/`daysUntilYmd`
- 차트 X축은 `"YY.M"` — 직접 문자열 파싱(타임존 이슈 방지)

**에러·토스트·스토리지**
- `utils/error.ts` `extractErrorMessage(e, fallback?)` — API 에러 수동 파싱 금지
- `utils/toast.ts` `toast(message, type?)` — 훅 아님, 어디서든 호출
- `utils/safeStorage.ts` — **`localStorage`/`sessionStorage` 직접 접근 금지**(차단 환경에선 접근만으로 throw해 부팅 실패)
- `utils/cacheOwner.ts` — 사용자 전환 시 persist 캐시 폐기(쿼리키에 user id가 없음)

**도메인 유틸 (`utils/`)** — 인라인 재구현 금지, 백엔드 공식 포팅본은 **양쪽을 함께 수정**
- `accounts.ts` — `isPortfolioAccount`/`isStockAccount`/`isBankAccount`(**`account.asset_type` 문자열을 전달**, 인라인 비교 금지), `isSyncableAccount`, `isBrokerBalanceAccount`(3사), `isOrderExecutableAccount`(KIS·키움만 — 백엔드 `ORDER_EXECUTABLE_ASSET_TYPES`와 같은 집합), `horizonTaggedAccounts`(기간별 합산은 `invested_krw + unrealized_pnl` — `amount_krw`는 예수금 포함이라 주식 총액보다 커짐)
- `portfolio.ts` — `groupPositionsByTicker`, `getPortfolioTargetState`, `getPortfolioHorizon(TaxType)`, `inferHorizonTaxTypeFromAccounts`, `mergeAlertsByPortfolio`
- `portfolioGroups.ts` — 지수 그룹 편집 순수 함수. 레버리지 멤버는 대표·국내 대체 후보에서 제외(백엔드 검증과 같은 규칙)
- `components/rebalancing/rebalancingTradeMath.ts` — **분석 결과 그룹 행은 `shares_to_trade`가 null** — 주문·거래 요약은 `flattenTradeItems()`로 펼친 목록 사용
- `rebalancingUrl.ts` — `REBALANCING_TABS`·`GOAL_MODES`가 탭 이름 단일 정의(**백엔드 `email_service`·`insight_service`·`action_items_service`의 탭 문자열과 같아야 함**), `parseRebalancingTab`(옛 `rtab=추천/전술` 호환), `rebalancingUrl()`
- `recommendationDrift.ts` — `RECOMMENDATION_DRIFT_THRESHOLD_PCT`(3%p) — 백엔드 `compute_recommendation_drift`와 동일 로직. `foldIntoPortfolioGroups`는 백엔드 `fold_into_portfolio_groups`와 같은 규칙
- `marketSignalRows.ts` — 매크로 8지표 행 변환(Tier 분류는 백엔드 `market_signal_service` 재사용)
- `dcaScenarioProjection.ts` — 백엔드 `dca_service._build_projection_curve()` 포팅
- `legacyTabRedirect.ts` — 이메일·푸시에 저장된 옛 딥링크 호환 — **지우지 말 것**
- 그 외: `rebalancingAlertDescription`, `rebalancingThresholdRecommendation`, `etfOverlap`, `diagnosisInsights`, `riskLevel`, `dividendUtils`(`weightBarColor` — 비중 막대 색 인라인 금지), `savingsProjection`, `goalFeasibility`, `dcaAutoBuy`, `actionPriority`, `marketSignalBadge`, `notificationAlertGroups`

**마켓 (`constants/markets.ts`)** — 인라인 문자열 비교 금지.
- `isOverseasMarket(market)`, `marketLabel(market)`(화면엔 원시 코드 대신), `POSITION_MARKETS`
- **토스 해외 포지션 market은 `"US"`라 `isOverseasMarket`이 못 잡는다** — 국내/해외 이분은 `DOMESTIC_MARKETS.includes(m.toUpperCase())`

**플랫폼 (`utils/platform.ts`)**: `isNativePlatform()`, `getApiBaseUrl()`(네이티브는 `VITE_API_DOMAIN` 절대 URL, 웹은 `""`) — 인라인 `window.Capacitor` 접근 금지.

**차트 (`utils/chart.ts`)**: `chartTooltipStyle(isDark)`, `chartTickStyle(isDark)`/`CHART_TICK_FONT_SIZE`(12) — 인라인 스타일·`fontSize: 11` 금지. Recharts는 `dark:` 미지원이라 `isDark`로.

**입력 스타일 (`constants/inputStyles.ts`)**: `INPUT_SM`/`INPUT_MD`, `LABEL_SM`/`LABEL_MD`, `SELECT_SM`, `TEXTAREA_SM` — 인라인 Tailwind 입력 스타일 금지.

**모바일 UI**
- `text-xs`(12px) 미만 임의값(`text-[10px]` 등) 금지. 차트 축·범례도 12px 이상.
- 터치 타겟은 `constants/uiSizes.ts` 상수 — 인라인 `min-h-[44px] min-w-[44px]` 금지. `TOUCH_TARGET_MIN`(44px) 기본, `TOUCH_TARGET_MIN_MOBILE_ONLY`(sm 이상 축소), `TOUCH_TARGET_ROW`(좌측 정렬 행), `TOUCH_TARGET_COMPACT_MOBILE_ONLY`(36px — 배지·탭·칩처럼 조밀한 보조 요소).
- 이미 44px로 정착된 삭제 아이콘 버튼(`StockAccountCard`·`BankAccountCard`·`PortfolioItemRow`)은 개별 화면에서 축소 금지.
- 금융 기록 삭제·실주문/실계획 생성 등 되돌릴 수 없는 동작은 `ConfirmModal`(무엇이 일어나는지 문구 포함)을 거친다.
- 하단 고정 요소는 `index.css`의 `--bottom-nav-h` 변수 사용(`bottom-[calc(var(--bottom-nav-h)+env(safe-area-inset-bottom))]`) — rem 하드코딩 금지.
- `title` 속성은 터치에서 안 보인다 — 사용자가 알아야 할 정보는 화면 표시 또는 탭→토스트.
- 페이지 스크롤 안 `max-h-* overflow-y-auto` 중첩 스크롤 금지 → "N개 더 보기".
- 음수 가능한 숫자 입력은 모바일 키패드에 마이너스가 없으므로 이익/손실 `SegmentedControl` + 절댓값 입력(`TaxPlannerSection` 참고).

**지연 로딩**: 페이지 내부의 무거운 탭·서브패널도 `React.lazy()`로 분리(최상위 라우트만이 아님). 로딩 표시는 `SkeletonCard`/`SkeletonStatBox` — 인라인 플레이스홀더 새로 작성 금지.

**헤딩 (접근성)**
- 각 페이지 최상위에 `<h1 className="sr-only">{페이지명}</h1>`.
- 카드/섹션 제목은 `<h2>`/`<h3>`(공용 `CollapsibleCard`·`SectionCard`·`Modal`은 이미 h2). 단 반복 리스트 행(`RebalancingMobileCard` 등)은 헤딩으로 올리지 않는다.

**콜랩스 기본값**
- 헤드라인 카드(`HeroSummaryCard`, `InvestmentGoalCard`)는 접기 불가. 단 `HeroSummaryCard`의 총액·범례 금액은 **기본 숨김**(탭하면 표시, 저장 안 함).
- 보조/상세 최상위 카드는 `useCollapsible`로 접기 가능, 첫 방문은 **열림**, 접은 상태는 localStorage 유지. 이미 펼친 카드 안의 2차 토글은 대상 아님.
- **기본 접힘 예외**(보조 도구·상세): 진단 `RiskMetricsCard`, `MarketSignalBanner` 상세("자세히"), 전술 백테스트·판정 근거·비중표 편집, 절약 복리 시뮬레이터, `RebalancingDiagnosisCard`, 분석 "상세 정보", "더 빨리 달성하려면?", 절세 플래너, `AllocationCard`(모바일만). localStorage 키는 `growlio:<영역>:<이름>` 형식.
- 홈에는 `RebalancingStatusCard`가 없다(진단탭 전용, 항상 펼침) — 홈 리밸런싱은 `ActionItemsCard`만.

---

## Tailwind UI 패턴

```
카드       bg-white rounded-2xl border border-gray-200 p-5 dark:bg-gray-800 dark:border-gray-700
아이콘버튼 p-1.5 text-gray-400 hover:text-{color}-600 hover:bg-{color}-50 rounded-lg transition-colors
기본 액션  bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50 transition-colors
위험(삭제) px-5 py-2 text-sm border border-red-300 text-red-600 rounded-lg hover:bg-red-50 transition-colors
```

- 다크모드: `const { isDark } = useThemeStore()`. Tailwind `dark:`(HTML `class="dark"` 토글)를 `isDark`보다 우선.
