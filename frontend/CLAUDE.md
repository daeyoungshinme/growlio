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
cd frontend && npx tsc --noEmit
```

### API 타입 자동 생성
```bash
# 백엔드 서버(localhost:8000) 실행 중인 상태에서 실행
cd frontend && npm run generate:api-types
# → src/types/api.generated.ts 생성 (gitignore 대상 — 빌드 시 재생성)
# 생성된 타입 사용법: import type { paths, components } from "../types/api.generated";
# 예: components["schemas"]["DashboardSummary"]
```

### 린트 & 테스트
```bash
cd frontend && npm run lint    # ESLint (eslint src)
cd frontend && npm run test    # Vitest (vitest run)
cd frontend && npm run test -- src/utils/__tests__/format.test.ts  # 단일 파일
cd frontend && npm run test -- --watch                             # 워치 모드
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

> `src/lib/supabase.ts`에서 import됨. `.env` 없으면 Supabase 클라이언트 초기화 실패.

---

## Architecture (`frontend/src/`)

**페이지 구성:**
- `/login` — 로그인 (LoginPage)
- `/dashboard` — 전체 자산 집계, 포트폴리오 요약, 연간 입금 달성률, 배당 현황, 월별 추이
- `/portfolio` — 주식 계좌 **조회 전용** (읽기 전용). 계좌별 sync, 차트, 종목 현황. 계좌 추가/삭제/종목관리/입출금은 여기서 하지 않음
- `/asset-management` — **모든 계좌 관리 허브**. 은행계좌/증권계좌 추가·삭제, 종목관리(StockPositionsModal), 입출금(TransactionModal), 입출금·배당 내역 탭
- `/invest-plan` — DCA(정기투자) 분석 + 목표 타임라인 (InvestPlanPage)
- `/settings` — KIS/키움 자격증명, 오픈뱅킹 연결, 투자/입금 목표 설정
- `/register` — 회원가입 (RegisterPage)
- `/forgot-password` — 비밀번호 찾기 (ForgotPasswordPage)
- `/reset-password` — 비밀번호 재설정 (ResetPasswordPage)
- `/find-account` — 계정 찾기 (FindAccountPage)
- `/trend` — `/dashboard`로 리다이렉트 (TrendPage 제거됨)

> 구 URL 리다이렉트: `/assets` → `/portfolio`
> 새 페이지 추가 시 `src/App.tsx`에 `<Route>` 등록 필수.

**최상위 컴포넌트 (`src/`):**
- `ErrorBoundary.tsx` — React 에러 바운더리 (App.tsx에서 전체를 감쌈)
- `Toaster.tsx` — `growlio:toast` 이벤트 구독 전역 토스트 UI

**컴포넌트 디렉토리 (`src/components/`):**
assets, backtest, common, dashboard, invest, layout, portfolio, portfolio-analysis, rebalancing, settings, trend

`components/common/` 주요 파일: `ConfirmModal.tsx`, `FormInput.tsx` (공통 폼 인풋), `Modal.tsx`, `PageLoader.tsx`, `PriceCell.tsx` (가격 표시 셀), `SkeletonCard.tsx`, `SkeletonStatBox.tsx`, `SkeletonTable.tsx`, `StatCard.tsx`, `TreemapCell.tsx`

**데이터 흐름:**
```
api/client.ts (axios + JWT interceptor + 401 자동 refresh)
  └── api/{alerts,assets,backtest,dashboard,dart,invest,portfolios,rebalancing,tax,transactions}.ts
        └── React Query useQuery/useMutation   # 자동 refetch (REFETCH_INTERVAL 상수 기준)
              └── Page 컴포넌트
```

**hooks/**
- `useExchangeRate.ts` — 환율 조회
- `useForm.ts` — 폼 상태 관리
- `useStockSearch.ts` — 종목 검색
- `useCurrencyInput.ts` — 통화 입력 처리 (KRW/USD 포맷팅)
- `useTaxSimulation.ts` — 세금 시뮬레이션 로직 (해외 양도세 계획)
- `useAssetManagementData.ts` — 자산관리 페이지 전용 데이터 훅 (accounts + portfolio overview + transactions 통합)
- `useAssetModals.ts` — 자산관리 페이지 모달 열기/닫기 상태 통합 관리
- `useDashboardData.ts` — 대시보드 페이지 전용 데이터 훅 (dashboard + overview + dca + exchange-rate 통합)
- `usePositionsEditor.ts` — 포지션(종목) 편집 폼 상태 관리
- `useRebalancingBalances.ts` — 리밸런싱 잔고 조회
- `useRebalancingExecution.ts` — 리밸런싱 주문 실행 뮤테이션
- `useRebalancingPrices.ts` — 리밸런싱 종목 현재가 조회

새 커스텀 훅은 이 디렉토리에 추가.

**기타 상수 (`src/constants/`):**
- `queryKeys.ts` — React Query queryKey 상수 (`QUERY_KEYS` 객체). 모든 queryKey는 여기서 import
- `queryConfig.ts` — `STALE_TIME`, `REFETCH_INTERVAL` 상수. 매직 넘버 대신 이 상수 사용
- `defaults.ts` — 백테스트 기본 날짜 상수 (`BACKTEST_DEFAULT_START_DATE` 등)
- `tabs.ts` — 자산관리·포트폴리오 탭 배열 + 타입 (`ASSET_MANAGEMENT_TABS`, `PORTFOLIO_TABS`)
- `transaction.ts` — 거래 유형 한국어 레이블 맵 (`TX_LABELS`: DEPOSIT/WITHDRAWAL/DIVIDEND)
- `validation.ts` — 포트폴리오 비중 허용 오차 (`PORTFOLIO_WEIGHT_TOLERANCE`)
- `index.ts` — 상수 re-export

**타입 정의:** `src/types/index.ts` — 포트폴리오 포지션, 계좌 등 공통 TypeScript interface 정의.

**테스트 위치:** `src/utils/__tests__/*.test.ts` (Vitest). 유틸 함수 단위 테스트만 존재: `format.test.ts`, `error.test.ts`, `colors.test.ts`.

**asset_type_allocation:** 백엔드는 모든 자산 유형을 반환. PortfolioPage에서 STOCK 타입만 프론트엔드 필터링으로 표시.

**`src/lib/supabase.ts`** — Supabase 클라이언트 초기화 (env vars 필요). 직접 확장 금지 — 인증 흐름은 백엔드 JWT가 담당하며 이 파일은 초기화 목적으로만 존재.

> 타입 체크는 `npm run build` 또는 위 tsc 명령으로 대체.

**상태 관리:** Zustand — `authStore.ts`(인증), `themeStore.ts`(다크모드). 서버 상태는 React Query 전담.

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
- `fmtMonth(str)` — "YYYY-MM" → "YYYY년 M월".
- `fmtPct(n)` — "+5.23%" 형식. null이면 "—".
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

**마켓 유틸리티 (`src/constants/markets.ts`)**
- `isOverseasMarket(market)` — market 문자열이 해외거래소인지 판별. 인라인 문자열 비교 금지.
  ```ts
  import { isOverseasMarket } from "../constants/markets";
  // isOverseasMarket("NYSE") → true, isOverseasMarket("KOSPI") → false
  ```

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
- 수동으로 `invalidateQueries` 여러 번 호출하지 말고 이 함수 사용.
> **⚠️ 예외 — stock-price-alerts:** `queryInvalidation.ts` 유틸 미존재. CUD 후 직접 호출 필수:
> `qc.invalidateQueries({ queryKey: QUERY_KEYS.stockPriceAlerts })`

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
