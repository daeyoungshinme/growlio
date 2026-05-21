# Frontend CLAUDE.md

## Commands

> **Claude Code Bash 환경**: `node`/`npm`/`npx`가 PATH에 없음.
> 실행 시 앞에 `PATH="/opt/homebrew/Cellar/node@20/20.20.2/bin:$PATH"` 추가 필요.
> 타입 체크: `PATH="/opt/homebrew/Cellar/node@20/20.20.2/bin:$PATH" node frontend/node_modules/.bin/tsc --noEmit`

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
```

---

## Architecture (`frontend/src/`)

**페이지 구성:**
- `/login` — 로그인 (LoginPage)
- `/dashboard` — 전체 자산 집계, 포트폴리오 요약, 연간 입금 달성률, 배당 현황, 월별 추이
- `/portfolio` — 주식 계좌 **조회 전용** (읽기 전용). 계좌별 sync, 차트, 종목 현황. 계좌 추가/삭제/종목관리/입출금은 여기서 하지 않음
- `/asset-management` — **모든 계좌 관리 허브**. 은행계좌/증권계좌 추가·삭제, 종목관리(StockPositionsModal), 입출금(TransactionModal), 입출금·배당 내역 탭
- `/invest-plan` — DCA(정기투자) 분석 + 목표 타임라인 (InvestPlanPage)
- `/settings` — KIS/LS 자격증명, 오픈뱅킹 연결, 투자/입금 목표 설정

> 구 URL 리다이렉트: `/assets` → `/portfolio`, `/trend` → `/dashboard`

**컴포넌트 디렉토리 (`src/components/`):**
assets, backtest, common, dashboard, invest, layout, portfolio-analysis, portfolios, rebalancing, transactions, trend

**데이터 흐름:**
```
api/client.ts (axios + JWT interceptor + 401 자동 refresh)
  └── api/{alerts,assets,backtest,dashboard,invest,portfolios,rebalancing,transactions}.ts
        └── React Query useQuery/useMutation   # 60초 자동 refetch
              └── Page 컴포넌트
```

**hooks/** — 커스텀 React 훅 디렉토리. API 로직이 아닌 UI 동작 추상화용.

> 린트/테스트 스크립트 없음 (`package.json`에 `lint`, `test` 명령 미설정). 타입 체크는 `npm run build` 또는 위 tsc 명령으로 대체.

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
| 계좌별 포지션 | `["account-positions", accountId]` |
| 전체 거래내역 | `["transactions", "all", selectedYear]` |
| 배당금 티커별 | `["dividend-by-ticker"]` |

**mutation 후 캐시 무효화**
- 트랜잭션 CUD → `["transactions", accountId]` + `["dashboard"]` 동시 무효화.
- 계좌 sync → `["portfolio-overview"]` + `["dashboard"]` 무효화.
- 계좌 CUD (자산관리에서) → `["accounts"]` + `["portfolio-overview"]` + `["dashboard"]` 동시 무효화.

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

**차트 유틸리티 (`src/utils/chart.ts`)**
- `chartTooltipStyle(isDark)` — Recharts `<Tooltip>` 다크모드 스타일 반환. 인라인 스타일 객체 중복 작성 금지.
  ```ts
  import { chartTooltipStyle } from "../utils/chart";
  const { contentStyle, labelStyle, itemStyle } = chartTooltipStyle(isDark);
  ```

**캐시 무효화 유틸리티 (`src/utils/queryInvalidation.ts`)**
- 계좌 sync 후: `invalidateSyncData(queryClient)` — portfolio-overview + dashboard + dividend 동시 무효화.
- 계좌 CUD 후: `invalidateAccountData(queryClient)` — accounts + portfolio-overview + dashboard 무효화.
- 수동으로 `invalidateQueries` 여러 번 호출하지 말고 이 함수 사용.

**커스텀 훅 (`src/hooks/`)**
- `useToast()` — toast 알림. 성공/에러 메시지 표시. 인라인 에러 state 대신 사용.
- `useAsyncAction()` — 비동기 작업 로딩/에러 처리 래퍼.

---

## Tailwind UI 패턴

**카드 컨테이너**
```
bg-white rounded-2xl border border-gray-200 p-5
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
