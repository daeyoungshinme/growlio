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

> **Import 규칙:** 새 코드는 `@/` alias 사용 (예: `import { fmtKrw } from "@/utils/format"`). `vite.config.ts`/`tsconfig.app.json`에 `@/* → src/*` 설정됨 — 현재 221개 파일이 `@/`, 9개만 상대경로 사용 중. 이 문서의 예시 코드 중 일부는 과거 상대경로(`"../utils/..."`) 스타일로 남아있을 수 있음.

**페이지 구성** (실제 라우트는 `src/App.tsx` 참고 — 인증 필요 라우트는 `/` 하위 `PrivateRoute`로 감싸짐):
- `/login` — 로그인 (LoginPage)
- `/register` — 회원가입 (RegisterPage)
- `/find-account` — 계정 찾기 (FindAccountPage)
- `/forgot-password` — 비밀번호 찾기 (ForgotPasswordPage)
- `/reset-password` — 비밀번호 재설정 (ResetPasswordPage)
- `/dashboard` — 전체 자산 집계, 포트폴리오 요약, 연간 입금 달성률, 배당 현황, 월별 추이
- `/assets` — **자산 관리 허브** 단일 라우트. `AssetsPage`가 내부적으로 "투자현황"(조회 전용 PortfolioContent)/"계좌관리"(CRUD AssetManagementContent) 2개 탭으로 분기 (`ASSETS_TOP_TABS`, `?tab=` 쿼리 파라미터)
- `/invest-plan` — DCA(정기투자) 분석 + 목표 타임라인 (InvestPlanPage)
- `/settings` — KIS/키움 자격증명, 투자/입금 목표 설정
- `/rebalancing` — 리밸런싱 실행 허브. 포트폴리오별 목표 비중 편집, 드리프트 현황, 주문 실행 (RebalancingPage)
- 미매칭 경로(`*`)는 `/dashboard`로 리다이렉트

> `/market`, `/portfolio`, `/asset-management`, `/trend` 라우트는 존재하지 않음(과거 구조, 제거됨). `BottomNav`(`src/constants/nav.ts`)도 홈/자산/리밸런싱/계획/설정 5탭만 존재.
> 새 페이지 추가 시 `src/App.tsx`에 `<Route>` 등록 필수.

**최상위 컴포넌트 (`src/components/`):**
- `ErrorBoundary.tsx` — React 에러 바운더리 (App.tsx에서 전체를 감쌈)
- `Toaster.tsx` — `growlio:toast` 이벤트 구독 전역 토스트 UI

**컴포넌트 디렉토리 (`src/components/`):**
assets, backtest, common, dashboard, invest, layout, portfolio, portfolio-analysis, rebalancing, settings

**컨텍스트 (`src/context/`):**
- `ExchangeRateContext.tsx` — `ExchangeRateProvider`로 앱 전체에 환율 공유. `useExchangeRateContext()`로 소비. `useExchangeRate.ts` 훅과 별개 — 컨텍스트 방식으로 동일 쿼리 중복 방지.

`components/common/` 주요 파일: `AmountUnitButtons.tsx`, `BiometricGuard.tsx`, `Button.tsx`, `ConfirmModal.tsx`, `EditableNameField.tsx`, `EmptyState.tsx`, `FormInput.tsx` (공통 폼 인풋), `Modal.tsx`, `OfflineBanner.tsx`, `PageLoader.tsx`, `PriceCell.tsx` (가격 표시 셀), `SkeletonCard.tsx`, `SkeletonStatBox.tsx`, `SkeletonTable.tsx`, `StatCard.tsx`, `SuggestionDropdown.tsx`, `Tabs.tsx`, `Tooltip.tsx`, `TopLoadingBar.tsx`, `TreemapCell.tsx`

> 새 공통 컴포넌트 추가/삭제 시 이 목록도 함께 갱신.

- **`BiometricGuard.tsx`** — `App.tsx`에서 `AppLayout` 전체를 감싸는 게이트 컴포넌트. Android 네이티브 빌드에서 생체 인증 미통과 시 하위 라우트 렌더링 차단 (`useBiometric.ts`와 연동).
- **`OfflineBanner.tsx`** — `useOnlineStatus.ts`로 네트워크 상태 감지 + PWA 오프라인 캐싱(`vite.config.ts`의 VitePWA/Workbox `StaleWhileRevalidate`, 대상: dashboard/portfolio-overview/accounts 엔드포인트)과 함께 오프라인 상태를 안내.

**Android 홈 위젯:** `useWidget.ts`(React 훅) ↔ `src/plugins/WidgetPlugin.ts`(Capacitor 플러그인 브리지) ↔ 네이티브 `android/app/src/main/java/com/growlio/app/{GrowlioWidget,WidgetPlugin}.java`. 위젯 UI 변경 시 네이티브 Java 코드도 함께 수정 필요.

**데이터 흐름:**
```
api/client.ts (axios + JWT interceptor + 401 자동 refresh)
  └── api/{alerts,assets,backtest,dashboard,dividends,
           insights,invest,marketSignals,portfolios,rebalancing,risk,settings,tax,transactions}.ts
        └── React Query useQuery/useMutation   # 자동 refetch (REFETCH_INTERVAL 상수 기준)
              └── Page 컴포넌트
```

> 백엔드 `/economic-indicators` 라우터는 존재하지만 이를 호출하는 프론트 API 모듈이 없음(프론트 미연동).

**hooks/**
- `useExchangeRate.ts` — 환율 조회
- `useForm.ts` — 폼 상태 관리
- `useStockSearch.ts` — 종목 검색
- `useCurrencyInput.ts` — 통화 입력 처리 (KRW/USD 포맷팅)
- `useTaxSimulation.ts` — 세금 시뮬레이션 로직 (해외 양도세 계획)
- `useAssetManagementData.ts` — 자산관리 페이지 전용 데이터 훅 (accounts + portfolio overview + transactions 통합)
- `useAssetModals.ts` — 자산관리 페이지 모달 열기/닫기 상태 통합 관리
- `useDashboardData.ts` — 대시보드 페이지 전용 데이터 훅 (dashboard + overview + dca + exchange-rate 통합)
- `useDividendData.ts` — 배당 요약 데이터 조회
- `usePositionsEditor.ts` — 포지션(종목) 편집 폼 상태 관리
- `usePortfolioItemsEditor.ts` — 포트폴리오 종목 편집 폼 상태 (종목 검색 연동)
- `useKisCredentialVerify.ts` — KIS 자격증명 검증 상태 머신 (`verifyKisCredentials` 래핑)
- `useRebalancingBalances.ts` — 리밸런싱 잔고 조회
- `useRebalancingExecution.ts` — 리밸런싱 주문 실행 훅의 공개 진입점(barrel re-export). 실제 구현은 `rebalancingExecution/`(`index.ts`/`reducer.ts`/`types.ts`) 패키지에 있지만, 모든 소비 코드는 이 파일을 통해서만 import — 패키지를 직접 import 금지
- `useRebalancingPrices.ts` — 리밸런싱 종목 현재가 조회
- `useRealtimePrice.ts` — WebSocket 실시간 가격 구독 (`/api/v1/ws/prices`). 연결 끊김 시 최대 3회 지수 백오프(1s/3s/10s) 재연결.
- `useAccountMutations.ts` / `useAccountPositions.ts` — 계좌 뮤테이션·포지션 조회
- `useAlertCrud.ts` / `useRebalancingAlertForm.ts` — 알림 CRUD
- `useAllocationHistory.ts` / `useAnalysisState.ts` / `useOptimizationSuggestions.ts` — 포트폴리오 분석
- `useBacktestDateRange.ts` — 백테스트 날짜 범위 관리
- `useBiometric.ts` — 생체 인증 (Capacitor Android)
- `useInsights.ts` — 인사이트 조회
- `useGoalSettings.ts` — 투자 목표 설정 폼 상태
- `useHaptic.ts` / `usePullToRefresh.ts` / `useSwipeNavigation.ts` — 모바일 UX
- `useLogout.ts` — 로그아웃 로직, `useOnlineStatus.ts` — 온라인/오프라인 감지
- `usePortfolioTabFetching.ts` — 포트폴리오 탭 데이터 프리패치
- `usePushNotifications.ts` / `useRegisterRefresh.ts` / `useWidget.ts` — FCM 푸시·홈 위젯 (Android)
- `useTransactionFormState.ts` — 거래내역 입력 폼 상태

새 커스텀 훅은 이 디렉토리에 추가/삭제 시 위 목록도 갱신.

**기타 상수 (`src/constants/`):**
- `queryKeys.ts` — React Query queryKey 상수 (`QUERY_KEYS` 객체). 모든 queryKey는 여기서 import
- `queryConfig.ts` — `STALE_TIME`, `REFETCH_INTERVAL` 상수. 매직 넘버 대신 이 상수 사용
- `defaults.ts` — 백테스트 기본 날짜 상수 (`BACKTEST_DEFAULT_START_DATE` 등)
- `tabs.ts` — 탭 배열 + 타입: `ASSETS_TOP_TABS`("투자현황"/"계좌관리", AssetsPage 상위 탭), `ASSET_MANAGEMENT_TABS`("은행계좌"/"증권계좌"/"부동산"/"입출금·배당", 계좌관리 내부 탭), `PORTFOLIO_TABS`
- `transaction.ts` — 거래 유형 한국어 레이블 맵 (`TX_LABELS`: DEPOSIT/WITHDRAWAL/DIVIDEND)
- `validation.ts` — 포트폴리오 비중 허용 오차 (`PORTFOLIO_WEIGHT_TOLERANCE`)
- `rebalancingConfig.ts` — 리밸런싱 알림 폼용 상수 (`SCHEDULE_OPTIONS`, `TRIGGER_CONDITION_OPTIONS`, `MODE_OPTIONS`, `STRATEGY_OPTIONS`, `MARKET_CONDITION_OPTIONS`)
- `uiSizes.ts` — 모바일 터치 타겟 상수 (`TOUCH_TARGET_MIN`: `min-h-[44px] min-w-[44px]`, `TOUCH_TARGET_MIN_MOBILE_ONLY`: 모바일에서만 44px 적용하고 `sm:` 이상에서 축소하는 변형). 인터랙티브 요소(버튼/입력 등)에 인라인 `min-h-[44px] min-w-[44px]` 재정의 금지, 이 상수 사용
- `timers.ts` — UI 타이밍 상수 (`SEARCH_DROPDOWN_HIDE_DELAY`: 150ms blur 후 드롭다운 지연, `REDIRECT_DELAY_MS`: 3000ms, `FOCUS_SETTLE_DELAY`: 0ms)
- `assets.ts` — 자산 유형 관련 상수 (`CASH_TICKER`, `REAL_ESTATE_ASSET_TYPE`, `KR_PROPERTY_MARKET`, `BASE_TYPE_STOCK_ONLY`, `BASE_TYPE_TOTAL_ASSETS`)
- `nav.ts` — `BottomNav` 탭 정의 (홈/자산/리밸런싱/계획/설정 5탭)
- `index.ts` — 상수 re-export

**타입 정의:** `src/types/index.ts` — 포트폴리오 포지션, 계좌 등 공통 TypeScript interface 정의.

**Zod 스키마 (`src/schemas/`):**
- `assets.ts`, `auth.ts`, `portfolios.ts`, `settings.ts`, `transaction.ts` — 폼 입력값 런타임 유효성 검사 (Zod). 새 폼 추가 시 이 디렉토리에 스키마 파일 추가.

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

**WebSocket 패턴**
- 새 WebSocket 훅은 `useRealtimePrice.ts` 패턴 참고.

> **인증 구조:** Supabase는 이메일 인증·OAuth 콜백(리다이렉트 URL) 처리에만 사용됨. 실제 API 인증은 백엔드(`auth.py`)가 발급한 JWT Bearer 토큰 사용. `api/client.ts`의 Axios 인터셉터가 토큰 관리. Supabase Session과 백엔드 JWT는 별개이므로 혼용 금지.

> 타입 체크는 `npm run build` 또는 위 tsc 명령으로 대체.

**상태 관리 원칙:** 서버에서 오는 데이터 → React Query. 순수 클라이언트 전역 상태 → Zustand.
- Zustand (`src/stores/`): `authStore.ts`(인증 토큰·유저 정보), `themeStore.ts`(다크모드 토글)
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
| 포트폴리오 overview | `["portfolio-overview"]` |
| 포트폴리오/백테스트/리밸런싱 탭 | `["portfolios"]` |
| 전체 계좌 목록 | `["accounts"]` |
| 계좌별 포지션 | `["account-positions", accountId]` |
| 전체 거래내역 (무기간) | `["transactions", "all"]` |
| 연도별 거래내역 | `["transactions", "all", year]` |
| 배당금 티커별 | `["dividend-by-ticker"]` |
| 배당금 요약 | `["dividend-summary"]` |
| 배당금 포지션 | `["dividend-positions"]` |
| DCA 분석 (InvestPlanPage + DashboardPage) | `["dca-analysis"]` |
| 설정 | `["settings"]` |
| 현재 환율 | `["exchange-rate"]` |
| 환율 알림 목록 | `["exchange-rate-alerts"]` |
| 주가 알림 목록 | `["stock-price-alerts"]` |
| 리밸런싱 알림 목록 | `["rebalancing-alerts"]` |
| 포트폴리오별 리밸런싱 알림 | `["rebalancing-alert", portfolioId]` |
| 세금 추정 요약 | `["tax-summary", year]` |

> 모든 키는 `src/constants/queryKeys.ts`의 `QUERY_KEYS` 상수에서 import. 문자열 하드코딩 금지.

**mutation 후 캐시 무효화**
- 트랜잭션 CUD → `["transactions", "all"]` + `["dashboard"]` 동시 무효화.
- 계좌 sync → `["portfolio-overview"]` + `["dashboard"]` 무효화.
- 계좌 CUD (자산관리에서) → `["accounts"]` + `["portfolio-overview"]` + `["dashboard"]` 동시 무효화.

> 수동 `invalidateQueries` 호출 금지 — `src/utils/queryInvalidation.ts`의 유틸 함수 사용 (하단 참고).

**포맷팅 유틸리티 (`src/utils/format.ts`)**
- 모든 포맷 함수는 `src/utils/format.ts`에서 import. 로컬 재정의 금지.
  ```ts
  import { fmtKrw, fmtKrwNullable, fmtKrwShort, fmtMonth, fmtPct } from "../utils/format";
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
  import { extractErrorMessage } from "../utils/error";
  // catch (e) { toast(extractErrorMessage(e)); }
  ```

**토스트 (`src/utils/toast.ts`)**
- `toast(message, type?)` — `window.dispatchEvent("growlio:toast")` 이벤트 발행. `useToast()` 훅 외부(비React 코드)에서도 직접 호출 가능.
  ```ts
  import { toast } from "../utils/toast";
  toast("저장되었습니다", "success");
  ```

**포트폴리오 유틸리티 (`src/utils/portfolio.ts`)**
- `groupPositionsByTicker(positions)` — 종목 배열을 ticker+market 기준으로 집계. 여러 계좌 보유 종목 합산 표시 시 사용.

**계좌 유틸리티 (`src/utils/accounts.ts`)**
- `isPortfolioAccount(account)` / `isStockAccount(account)` / `isBankAccount(account)` — 계좌 유형 판별. 인라인 `asset_type` 비교 금지.

**색상 유틸리티 (`src/utils/colors.ts`)**
- P&L 색상은 `pnlColor(value)` 함수 사용 — `PROFIT_COLOR`(`text-red-500`) / `LOSS_COLOR`(`text-blue-500`) 상수도 export됨.
  ```ts
  import { pnlColor } from "../utils/colors";
  // <span className={pnlColor(profit)}>
  ```
- 직접 `text-red-500` / `text-blue-500` 인라인 작성 금지 (색상 관례 변경 시 일괄 교체 불가).

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
- 포트폴리오/백테스트/리밸런싱 CUD 후: `invalidatePortfolioData(queryClient)` — portfolios 무효화.
- DCA 목표 변경 후: `invalidateDcaData(queryClient)` — dca-analysis + settings + dashboard 무효화.
- 환율 알림 CUD 후: `invalidateAlertData(queryClient)` — exchange-rate-alerts 무효화.
- 리밸런싱 알림 CUD 후: `invalidateRebalancingAlertData(queryClient, portfolioId)` — rebalancing-alerts + rebalancing-alert(portfolioId) 무효화.
- 배당 계획 변경 후: `invalidateDividendPlanData(queryClient)`.
- 주가 알림 CUD 후: `invalidateStockPriceAlertData(queryClient)`.
- 리밸런싱 주문 실행 후: `invalidateRebalancingHistoryData(queryClient)`.
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
