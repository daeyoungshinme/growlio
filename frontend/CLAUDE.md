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
# 생성된 타입 사용법: import type { paths, components } from "@/types/api.generated";
# 예: components["schemas"]["DashboardSummary"]
```

### 린트 & 테스트

```bash
cd frontend && npm run lint    # ESLint (eslint src)
cd frontend && npm run test    # Vitest (vitest run)
cd frontend && npm run test -- src/utils/__tests__/format.test.ts  # 단일 파일
cd frontend && npm run test:watch                                  # 워치 모드
cd frontend && npm run format  # Prettier (prettier --write src)
cd frontend && npm run format:check  # Prettier 검사만 (CI·make lint와 동일)
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

> **Import 규칙:** 새 코드는 `@/` alias 사용 (예: `import { fmtKrw } from "@/utils/format"`). `vite.config.ts`/`tsconfig.json`에 `@/* → src/*` 설정됨.

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
- `/invest-plan` — DCA(정기투자) 분석 + 목표 타임라인 + 절세 + 적립 챌린지 (InvestPlanPage, 상단 탭: 적립 계획/배당 계획/절세/챌린지)
- `/settings` — DART API 키, 계정 정보(비밀번호 변경), 앱 설정(다크모드/생체인증/로그아웃/탈퇴). 계좌 연동·목표·DCA·추천 옵션·알림 설정은 각 페이지에 실제 편집 UI가 있고 설정 탭엔 상태 요약 + 딥링크만
- `/settings/notifications` — 알림 설정 상세(`NotificationSettingsPage`, `/settings`에서 딥링크). 공통 수신 이메일(`NotificationEmailSection`) + `CollapsibleCard` 3개("정기 리포트·요약"/"즉시 알림"/"시장 모니터링") + 환율/주가/발송이력 탭. `MarketSignalBanner.tsx`/`RebalancingHistoryTab.tsx`의 `?atab=` 딥링크가 이 경로를 가리킴
- `/rebalancing` — 리밸런싱 실행 허브. 포트폴리오별 목표 비중 편집, 드리프트 현황, 주문 실행 (RebalancingPage, `?rtab=` 진단/포트폴리오/목표 조정/이력 + 목표 조정 안 `?gmode=` 추천/전술 — 예전 `rtab=추천`/`rtab=전술` 링크는 해당 모드로 매핑. 링크는 반드시 `utils/rebalancingUrl.ts`의 `rebalancingUrl()`로 만들고, 페이지 내부 URL 상태는 `hooks/useRebalancingUrlState.ts`)
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

`components/common/` 주요 파일: `AccountActionsMenu.tsx` (카드 헤더 등에 밀집된 부가 액션을 `⋯` 오버플로우 메뉴로 접는 공용 컴포넌트 — `items: {icon, label, onClick, disabled?, variant?}[]`, 아이콘+라벨 텍스트를 함께 렌더해 모바일 `title` 툴팁 미동작 문제 우회), `AmountUnitButtons.tsx`, `BiometricGuard.tsx`, `Button.tsx`, `CollapsibleCard.tsx` (카드 전체를 감싸는 헤더+접기 토글, `isOpen`/`onToggle` controlled), `CollapsibleSection.tsx` (카드 내부에 삽입하는 경량 접기 토글), `ConfirmModal.tsx`, `EditableNameField.tsx`, `EmptyState.tsx`, `FormInput.tsx` (공통 폼 인풋), `Modal.tsx` (+ `ModalFooter` — 스크롤 본문 다음 형제로 두는 하단 고정 버튼 영역. 입력 폼 모달의 저장/다음 버튼은 여기에 둔다 — 본문 끝에 두면 모바일 키보드에 가려짐), `OfflineBanner.tsx`, `PageLoader.tsx`, `PriceCell.tsx` (가격 표시 셀), `SkeletonCard.tsx`, `SkeletonStatBox.tsx`, `SuggestionDropdown.tsx`, `MiniDonut.tsx` (의존성 없는 SVG 도넛 — 홈 히어로가 recharts 청크 없이 자산 구성을 그림, 조각 탭 시 가운데 라벨), `Tabs.tsx`, `ToggleSwitch.tsx` (`checked`/`onChange`/`disabled?`/`ariaLabel?` props의 스위치 토글 + `ToggleRow` — 제목·설명·스위치 한 행 전체가 label이라 어디를 눌러도 토글, 설정 목록은 이걸 쓴다), `Tooltip.tsx`, `TopLoadingBar.tsx`, `TreemapCell.tsx`

> 새 공통 컴포넌트 추가/삭제 시 이 목록도 함께 갱신.

- **`BiometricGuard.tsx`** — `App.tsx`에서 `AppLayout` 전체를 감싸는 게이트 컴포넌트. Android 네이티브 빌드에서 생체 인증 미통과 시 하위 라우트 렌더링 차단 (`useBiometric.ts`와 연동). **UI 레벨 게이트일 뿐** — 통과 못 해도 캐시된 JWT로 API 호출 자체는 막히지 않는다. 실제 접근 통제는 백엔드 JWT 인증이 담당하며, 이 컴포넌트를 보안 경계로 의존하는 설계는 하지 말 것.
- **`OfflineBanner.tsx`** — `useOnlineStatus.ts`로 네트워크 상태 감지 + PWA 오프라인 캐싱(`vite.config.ts`의 VitePWA/Workbox `StaleWhileRevalidate`, 대상: dashboard/portfolio-overview/accounts 엔드포인트)과 함께 오프라인 상태를 안내.
- **`components/dashboard/IsaMaturityCard.tsx`** — ISA 계좌 의무가입 3년 만기 현황 카드. 계획탭 › 절세(`TaxTabContainer`)의 `TaxLimitsSection`이 `embedded` 모드로 렌더.
- **`components/dashboard/PensionContributionCard.tsx`** — 연금저축/IRP 연간 납입 현황 카드. 마찬가지로 `TaxLimitsSection`이 `embedded` 모드로 렌더.
- **`components/dashboard/HealthInsuranceRiskCard.tsx`** — 배당소득 기준 건보 피부양자 자격상실 위험 상시 카드(진행률 바 + 초과 시 예상 월 보험료). `TaxLimitsSection`이 계좌 유무와 무관하게 항상 렌더(배당소득은 전체 수령액 기준). `TaxOptimizationCard`의 조건부 경고 배너와 상호 보완.
- **`components/dashboard/ActionItemsCard.tsx`** — 홈 "지금 할 일"(Hero 바로 아래, lazy). `GET /dashboard/action-items`(백엔드 `action_items_service`가 전술 제안 비중 적용(TACTICAL, 목표 조정 › 전술 링크 — plans/75)·리밸런싱 필요·자동매수 예수금 부족·세금 경고·절세 1순위·챌린지 미입금을 우선순위·마감 순 최대 5건으로 집계)를 행 단위 링크로 렌더. 0건이면 한 줄 안내, 조회 실패 시 "다시 시도" 한 줄. 홈에서 리밸런싱을 다루는 유일한 카드 — REBALANCE 행 제목 옆에 시장 신호 배지(`marketSignal` prop, "시장 안정/주의/위험")를 붙인다. 리밸런싱 행이 없으면 홈에 시장 신호가 없다(등급 전환은 즉시 알림·진단 탭이 담당). 예전 별도 "리밸런싱 점검" 카드와 카드 하단 상태 줄은 삭제(plans/73). 배지 상수는 `utils/marketSignalBadge.ts`(진단탭 `RebalancingStatusCard`와 공용). 세금 한도 요약/경고는 예전엔 `InvestmentSnapshotCard`의 `TaxLimitsBanner`였음(2026-10-08 삭제 — 스냅샷 카드는 주식 3수치만). 우선순위 배지·마감 라벨은 `utils/actionPriority.ts`(`TaxActionPlanCard`와 공용).
- **`components/portfolio-analysis/TaxTabContainer.tsx`** — 계획탭 "절세" 서브탭 진입점(lazy, `InvestPlanPage`). "한도 현황"/"세금 추정" 2탭으로 `TaxLimitsSection`·`TaxOptimizationCard`를 묶음. 탭 상태 `?taxTab=`, 세금 추정 계좌 `?taxAccount=` 영속화. `taxTab` 미지정 딥링크는 "한도 현황" 랜딩. 옛 `/assets?portfolioTab=세금` 링크는 `utils/legacyTabRedirect.ts`가 이쪽으로 옮김.
- **`components/portfolio/AllocationCard.tsx`** — 자산탭 투자현황의 비중 분석 카드(lazy). 국내/해외(상장시장 ↔ 실제 투자지역 토글)·종목·지수별 비중을 탭 1개 카드로 통합. 하위 뷰는 `components/portfolio/allocation/`(`RegionAllocationView`/`StockAllocationView`/`IndexAllocationView` + 공용 `WeightBarRow`·`ListingBadge`·`SegmentedControl`). "종목" 보기는 아래 보유 종목 목록(`StockHoldingsTable`)과 겹치지 않게 상위 5 + "기타 N종목"만 그리고, "보유 종목 전체 비중순 보기"가 `PortfolioPage`를 거쳐 목록의 `sortRequest` prop으로 비중순 정렬 + 스크롤한다. 모바일 기본 접힘(아래 콜랩스 규칙 예외).
- **`components/assets/AccountHistoryTab.tsx`** — 계좌관리 "내역" 탭. 세그먼트 "현금 흐름"(입출금·배당 `TransactionHistoryTab`) / "매수 내역"(`PeriodPurchasesTab` — 월/연 매수 종목·수익률, 스냅샷 추정 `추정`/수기 `기록` 배지 + `TradeFormModal`로 매수/매도 기록, 해외 USD→KRW 환산). 세그먼트는 `?history=` 영속. 옛 `atab=입출금·배당`/`기간별 매수`는 `legacyHistorySegment()`로 변환.
- **`components/rebalancing/GoalAdjustTab.tsx`** — 리밸런싱 "목표 조정" 탭(lazy, plans/64). 추천·전술(둘 다 목표 비중 자체를 바꾸는 제안)을 underline 서브탭(`gmode`)으로 묶고 `RecommendationCard`/`TacticalAllocationTab`을 lazy 렌더. 대상 포트폴리오 선택기는 이 탭에 하나만(`useSelectedPortfolio`) — 두 자식은 `showTargetPicker`/`showPortfolioPicker={false}`로 자체 select를 숨긴다. 콘텐츠 ErrorBoundary/Suspense는 `key={mode}`로 모드마다 새 경계 — React Router v7이 URL 변경을 `startTransition`으로 감싸서, 공유 경계면 lazy 청크 로딩 동안 이전 모드 화면(탭 하이라이트 포함)이 그대로 남는다. 마운트 시 반대쪽 모드 청크도 미리 받는다.
- **`components/rebalancing/TacticalAllocationTab.tsx`** — 리밸런싱 "목표 조정 › 전술" 모드(lazy). 포트폴리오 선택 → `useTacticalStatus`로 나스닥100/S&P500 전술 배분 국면(QQQ·SPY·DIA 키는 지수 그룹 비중 — 비교표 행 아래 `GroupNote`가 서버 `current_groups`로 "대표 VOO · N종목 합산"/"적용하면 같은 지수 보유 종목을 묶어요" 표시, plans/76)(매크로 확정등급 × 차트 추세, 2일 확정)·지표·현재/제안 비중 표시, 켜기/알림 토글/끄기, "제안 비중 적용"(`ConfirmModal` 경유 → `POST /tactical/{id}/apply`, **주문 없음**) 후 "리밸런싱 분석·실행으로 이동"으로 포트폴리오 탭의 기존 실행 흐름에 넘긴다. 카드 상단은 국면 배지(전략 켠 경우 "N일째", 끈 경우 "(오늘 관측)") + "지금 할 일" 한 줄(`tacticalNextAction` — 미사용/판정 불가/전환 확인 중/나머지 적용/적용/할 일 없음) + 다음 전환 조건 최대 2줄(서버 `transition_hints`) + 틸트·웅덩이 한 줄 요약(웅덩이는 서버 `dip_deployed_pct` — 현금 한도 반영)만 두고, 매크로 확정 등급·근거·지표 행·틸트/웅덩이 근거는 "판정 근거·차트 지표" 접힘(`growlio:rebalancing:tactical-details-open`, 기본 접힘 — plans/69). 지표 행은 이평선 절대가 대신 종가의 20·60·120·200일선 대비 이격 + 웅덩이 단계 배지(`PULLBACK_LABEL`, 투입 기준인 QQQ 행에만). DIA(다우) 지표는 비중표 어느 국면에든 DIA가 있을 때만 "참고 · 국면 판단 미반영"으로 표시하고, 비중 비교 표의 선택 자산(DIA·QLD·SSO, `OPTIONAL_ASSETS`) 행은 현재·제안 모두 0%면 숨긴다. 적용 확인창은 `Modal` 2버튼("절반 먼저 적용"=`fraction 0.5`, 전술 자산만 있는 포트폴리오만 / "한 번에 적용") — 서버 `partial_regime`이 확정 국면과 같으면(절반 적용함) 버튼·확인창이 "나머지 적용"(fraction 1) 하나로 바뀌고 실행 화면 이동 버튼도 함께 보인다. 하위 `TacticalBacktestSection.tsx`(규칙 백테스트, 기본 접힘 `growlio:rebalancing:tactical-backtest-open` — 지표표에 "평균 비중 고정" 비교선·연 회전율, `BacktestResultChart`를 lazy 재사용(어댑터 `tacticalLabels.toChartSeries`), 최근 국면 전환 목록 5건+더 보기), `TacticalWeightsEditor.tsx`(전략 켠 경우 맨 위 프리셋 2×2 카드(`TACTICAL_PRESETS` 안정·균형·성장·레버리지 — 20년 실측 CAGR·MDD 표시, 누르면 초안만 채우고 저장은 별도, 초안과 일치하면 aria-pressed) + "매크로 신호 반영" 토글(`use_macro`) + 국면별 비중표 3국면×6자산(QQQ/SPY/DIA/QLD/SSO/현금 — DIA·QLD·SSO는 선택 자산, 응답에 없으면 0, 레버리지 비중 있으면 복리 감쇠 경고) + 틸트 이동폭 0~20%p + 웅덩이 투입폭 0~30%p 편집, 기본 접힘 `growlio:rebalancing:tactical-weights-open`, 서버 값 변경 시 `key`로 재마운트해 초안 초기화), 문구·색상 `tacticalLabels.ts`. 진단 탭과의 역할 구분(진단=목표 대비 이탈 점검, 전술=목표 자체 변경 제안)은 `RebalancingPage`의 진단 `TabIntro`와 `GoalAdjustTab`의 모드 소개 줄이 담당하고, "매크로(확정)" 배지 옆에 진단 탭 즉시 등급보다 늦게 바뀔 수 있다는 안내를 툴팁이 아닌 화면 문구로 둔다(모바일은 툴팁 미동작). 진단 탭 `MarketSignalBanner`는 `onOpenTactical` prop을 받으면 상세 영역 하단에 "목표 조정 › 전술" 이동 버튼을 그린다. 설정 upsert는 항상 현재 `tilt_shift_pct`·`dip_shift_pct`·`use_macro`를 함께 보낸다(생략 시 서버 기본값 0·0·true로 덮임). `use_macro=false`면 상세 접힘의 매크로 배지 대신 "매크로 반영 안 함".
- **`components/portfolio-analysis/TaxLimitsSection.tsx`** — "한도 현황" 탭 콘텐츠. `IsaMaturityCard`/`PensionContributionCard`(계좌 조건부) + `HealthInsuranceRiskCard`(항상)를 감싸는 순수 프레젠테이션. 항상 전체 계좌 기준(`accountId` prop 없음). 항상 렌더 카드가 있어 empty-state 없음.
- **`components/rebalancing/RecommendationCard.tsx`** — 목표 역산 추천 카드(lazy). 리밸런싱 페이지 **"목표 조정 › 추천" 모드**(`rtab=목표 조정&gmode=추천`) 전용 — 링크는 `rebalancingUrl({ tab: "목표 조정", mode: "추천" })`, 포트폴리오 생성·관리·실행은 `rtab=포트폴리오`. `openRecOptions=1`이면 옵션 모달을 연 채 마운트. 전체/연령대/단기·중기·장기는 `SegmentedControl`(탭 위계 3단), 같은 기간 안의 세제유형은 4단 탭이 되지 않게 "계좌 유형" select. 적용 대상은 모든 포트폴리오(기준 포트폴리오 우선 선택). 결과 렌더는 `RecommendationResultPanel.tsx`로 통합, 탭별 문구·`useMutation`·전환 상태머신은 이 파일. 전체 추천(`goalRecommendationOverall`)은 백엔드 콜드 계산이 수십 초 걸릴 수 있어 **카드 전체를 막지 않는다** — 기준 segmented·후보/설정 버튼은 먼저 그리고 "전체" 결과 영역만 로딩/오류/재시도(plans/65). `gcTime: STALE_TIME.DAY`로 영속 캐시에 남기고, `RebalancingPage`가 목표 조정 › 추천일 때 같은 queryKey로 미리 발화한다(lazy 청크 2단계와 병렬).
- **자동화 설정 모달(`RebalancingAlertModalRouter`)의 호스트는 `PortfolioManageTab` 하나뿐** — 다른 곳(분석/실행 패널, 진단탭 CTA, 계획탭 배너)은 `portfolioId=<id>&openAlert=1` URL 파라미터로 요청한다(`openAlert=dca`는 신규 알림일 때 정기 적립식 자동매수 프리셋 화면으로 바로 연다 — 계획탭 `AutoInvestStatusBanner`의 "자동매수 설정"). 새 진입점도 모달을 직접 마운트하지 말고 이 파라미터를 쓸 것.
- **`components/rebalancing/RecommendationResultPanel.tsx`** — 3탭 공유 추천 결과 프레젠테이션(드리프트 배지·`RecommendationWeightList`·`MarketSignalLevelBadge`·`SuggestedCandidatesBlock`·`RecommendationApplySection`). `applySection===null`이면 적용 섹션 생략(현금성 자동 연결 계좌 없을 때).
- **`components/invest/ChallengeSection.tsx`** — 계획 탭 "챌린지" 서브탭(lazy). `useChallenges`+`useChallengeMutations`, `ChallengeCard` 리스트, `ChallengeFormModal`(생성/편집), `ChallengeMonthGrid`(적립 습관 캘린더). 스트릭 기준은 백엔드가 "월 순입금>0"으로 계산 — 목표액 수정해도 과거 스트릭 불변. `components/dashboard/ChallengeProgressCard.tsx`가 홈에서 진행 중 챌린지 요약(입금 스트릭 우선), `BottomNav`가 `useChallengeNudge`로 계획 탭 아이콘에 빨간 점.
- **`components/invest/GoalSettingWizard.tsx`** — 투자 목표 최초 설정 6단계 마법사(자산 확인→금액/시점→월 적립액→결과→투자성향·배당목표→추천 포트폴리오). `GET /invest/goal-feasibility`로 프리셋별 필요 적립액 역산, 6단계에서 `GET /rebalancing/goal-recommendation` → "이 추천으로 포트폴리오 만들기"로 신규 `Portfolio` 생성(계좌 미연결). `InvestPlanPage.tsx`의 플랫 편집 모달(재설정 전용)과 별개. 상태: `useGoalSettings.ts`.

**Android 홈 위젯:** `useWidget.ts`(React 훅) ↔ `src/plugins/WidgetPlugin.ts`(Capacitor 플러그인 브리지) ↔ 네이티브 `android/app/src/main/java/com/growlio/app/{GrowlioWidget,WidgetPlugin}.java`. 위젯 UI 변경 시 네이티브 Java 코드도 함께 수정 필요.

**데이터 흐름:**

```
api/client.ts (axios + Supabase access token 첨부 + 401 시 Supabase refreshSession 재시도)
  └── api/{alerts,assets,auth,backtest,challenges,dashboard,dividends,economicIndicators,
           insights,invest,marketSignals,portfolios,rebalancing,rebalancingPlan,risk,settings,tax,trades,transactions}.ts
        └── React Query useQuery/useMutation   # 자동 refetch (REFETCH_INTERVAL 상수 기준)
              └── Page 컴포넌트
```

> `api/economicIndicators.ts`는 백엔드 `/economic-indicators/inflation-summary`(CPI·Core CPI 요약)만 호출 — `RebalancingPage` 진단탭 `MarketSignalBanner`의 상세 영역(`InflationIndicatorList`)이 소비. 백엔드에는 이 엔드포인트만 존재함.

**hooks/** (도메인별로 그룹핑 — 새 훅 추가/삭제 시 해당 그룹에 함께 갱신)

_공통/입력_

- `useExchangeRate.ts` — 환율 조회
- `useForm.ts` — 폼 상태 관리
- `useStockSearch.ts` — 종목 검색
- `useCurrencyInput.ts` — 통화 입력 처리 (KRW/USD 포맷팅)
- `useCollapsible.ts` — `[isOpen, toggle, setIsOpen]` 반환하는 접기/펼치기 상태 헬퍼(setter 참조 고정 — effect 의존성에 넣어도 됨). `CollapsibleCard`/`CollapsibleSection`과 함께 사용
- `useTimeout.ts` — 언마운트 시 자동 해제·재예약 시 이전 예약 취소되는 setTimeout(`scheduleTimeout(fn, ms)`). "3초 뒤 확인 해제"·blur 후 드롭다운 닫기처럼 상태를 바꾸는 지연 콜백은 맨 `setTimeout` 대신 이것을 쓴다
- `useModalBehavior.ts` — 모달 공통 동작(body 스크롤 잠금 참조카운트, 포커스 트랩, Escape 닫기, pull-to-refresh 터치 전파 차단) 훅. `common/Modal.tsx`·`common/ConfirmModal.tsx`와 독자 레이아웃이 필요한 모달(`RebalancingExecutionModal.tsx` 등)이 공용. Escape·포커스 트랩은 **맨 위 모달만** 처리(DOM상 다른 열린 모달을 품은 쪽은 아래층, 형제끼리는 나중에 열린 쪽이 위) — Android 뒤로가기가 Escape를 dispatch하므로 확인창 위에서 한 번 눌러 아래 모달까지 닫히지 않게 함
- `useEditableSettingsForm.ts` — 설정 편집 모달 공용 상태 머신(editing/saving/dirty-check/close-confirm). `useGoalSettings`/`useDividendPlanSettings`가 내부적으로 사용. `numberFieldPayload(value, initial)` — 부분 갱신 payload 값(값 있음→숫자, 원래 값을 지움→null, 처음부터 빈 칸→undefined로 키 생략). `PUT /settings/goal`은 보낸 키만 바꾸고 null은 비우므로, 초기 폼이 비어 있어도 기존 목표를 지우지 않으려면 이 헬퍼를 쓴다

_세금_

- `useTaxSimulation.ts` — 세금 시뮬레이션 로직 (해외 양도세 계획)

_자산관리/대시보드_

- `useAssetManagementData.ts` — 자산관리 페이지 전용 데이터 훅 (accounts + portfolio overview + transactions 통합)
- `useAssetModals.ts` — 자산관리 페이지 모달 열기/닫기 상태 통합 관리
- `useDashboardData.ts` — 대시보드 페이지 전용 데이터 훅 (dashboard + overview + dca + exchange-rate 통합)
- `useAccountMutations.ts` / `useAccountPositions.ts` — 계좌 뮤테이션·포지션 조회
- `useStockAccountStats.ts` — 증권 계좌별 평가금액·투자원금·손익·입금액·배당액 통계 집계 (portfolio overview + 거래내역 조인)
- `usePositionsEditor.ts` — 포지션(종목) 편집 폼 상태 관리
- `usePortfolioItemsEditor.ts` — 포트폴리오 종목 편집 폼 상태 (종목 검색 연동)
- `createCredentialVerify.ts` — 브로커 자격증명 "확인" 버튼용 상태 머신(idle→loading→ok/error) 제네릭 팩토리. `useKisCredentialVerify.ts`/`useKiwoomCredentialVerify.ts`/`useTossCredentialVerify.ts`는 검증 API 호출부만 클로저로 넘겨 얹은 얇은 래퍼 (`components/assets/CredentialVerifyButton.tsx`가 결과 UI 공용). `useBrokerCredentialVerify.ts`는 이 3개를 브로커(`BrokerDataSource`)별 핸들로 묶어 폼에 제공 — 입력 필드 정의는 `constants/brokerCredentials.ts`

_배당_

- `useDividendData.ts` — 배당 요약 데이터 조회
- `useDividendPlanSettings.ts` — 배당 계획(연/월배당) 설정 폼 상태 관리

_리밸런싱/추천_

- `useSelectedPortfolio.ts` — 리밸런싱 페이지의 "지금 보는 포트폴리오"(URL `portfolioId` → 첫 기준 포트폴리오 → 첫 포트폴리오, `resolveSelectedPortfolioId`). 목표 조정(추천·전술)과 포트폴리오 탭이 같은 기본값을 쓴다. 기본값은 URL에 쓰지 않고 파생만
- `useAnalysisState.ts`는 `AnalysisPanel`(포트폴리오 1개 전용 — 다중선택 잔재 제거, plans/64 S3)이 사용. 포트폴리오 탭 분석 영역은 기본 선택으로 열려도 결과로 자동 스크롤하지 않고(`scrollToResult`), URL로 직접 고른 경우만 스크롤
- `useRebalancingUrlState.ts` — 리밸런싱 페이지 URL 상태(rtab·gmode·portfolioId 읽기, `navigateTo`/`clearParam` 쓰기). 탭은 state로 복사하지 않고 URL에서 파생
- `useRebalancingBalances.ts` — 리밸런싱 잔고 조회
- `useDcaTacticalLink.ts` — 포트폴리오 자동매수가 적립식(활성 AUTO + BUY_ONLY)인지·전술 연동(`market_condition_mode="TACTICAL"`)인지 `{dcaAuto, linked}`. 전술 탭이 "비중 적용 대신 전술 연동 권장" 안내·적립 보조 모드 "지금 할 일"(`tacticalNextAction(..., {dcaLinked})`)·끄기 토스트에 사용(plans/71)
- `useAutoExecutionNotice.ts` — 포트폴리오에 켜진 AUTO 알림이 있으면 "다음 자동 실행부터 새 목표로 주문" 안내 문구(없으면 null). 목표 비중을 바꾸는 확인창(추천 적용·전술 적용)에서 사용
- `useSyncAccounts.ts` — 여러 계좌 동기화 + 동기화 쿼리 무효화(`run`이 전부 성공 여부 반환). 리밸런싱 실행 결과·분석 하단 "계좌 데이터 갱신"·실행 후 "실행 전 기준" 배너가 공유하며, 성공 시 호출부가 바로 재분석
- `useRebalancingExecution.ts` — 리밸런싱 주문 실행 훅의 공개 진입점(barrel re-export). 실제 구현은 `rebalancingExecution/`(`index.ts`/`reducer.ts`/`types.ts`) 패키지에 있지만, 모든 소비 코드는 이 파일을 통해서만 import — 패키지를 직접 import 금지
- `useRebalancingPrices.ts` — 리밸런싱 종목 현재가 조회
- `useAlertCrud.ts` / `useRebalancingAlertForm.ts`(`useRebalancingAlertQueries`·`useRebalancingAlertFormState`) — 알림 CRUD
- `useAllocationHistory.ts` / `useAnalysisState.ts` / `useOptimizationSuggestions.ts` — 포트폴리오 분석 (`useAnalysisState`는 기본적으로 동기화 기준 예수금으로 분석하고 결과를 5분 재사용 — 계좌·overview·portfolios 쿼리가 무효화되면 폐기. 증권사 실시간 예수금(`fetchLiveDepositKrw`)은 `triggerRebalancingAnalysis(id, { live: true })`, 즉 "실시간 잔고로 다시 분석" 버튼에서만. 계좌 로딩 전 자동 분석 보류, plans/72)
- `useMediaQuery.ts` — `useMediaQuery(query)`/`useIsSmUp()`. 모바일 카드 뷰·데스크톱 표 중 보이는 쪽만 렌더할 때 사용(matchMedia 없는 환경은 null → 둘 다 렌더하고 CSS에 맡김)
- `useBacktestDateRange.ts` — 백테스트 날짜 범위 관리
- `useGoalSettings.ts` — 투자 목표 설정 폼 상태
- `useChallenges.ts` / `useChallengeMutations.ts` / `useChallengeNudge.ts` — 적립 챌린지 목록 조회 / 생성·수정·삭제 뮤테이션 / 하단 네비 배지용 넛지 요약
- `useAddSuggestedCandidates.ts` — 목표 역산 추천의 `suggested_candidates`(고배당 미등록 후보 제안)를 "후보에 추가" 클릭으로 승인하는 뮤테이션. `RecommendationCard.tsx`/`DividendPlanSection.tsx` 공용
- `useCandidateOverlap.ts` — 추천 후보 ETF 중복·총보수 분석(`POST /rebalancing/candidates/overlap`) 조회. 후보 편집 연타 시 요청 폭주를 막는 디바운스(`CANDIDATE_OVERLAP_DEBOUNCE_MS`) 포함. 표시 헬퍼는 `utils/etfOverlap.ts`
- `usePortfolioTabFetching.ts`(`useMainPageFetching`) — 홈·포트폴리오 탭 주요 쿼리 중 하나라도 fetch 중인지(새로고침 인디케이터용)
- `useTacticalAllocation.ts` — QQQ/SPY 전술 배분: `useTacticalStatus`(국면·지표·제안 비중) / `useTacticalBacktest`(카드 펼칠 때만) / `useTacticalMutations`(켜기·설정 `upsert`, 끄기 `disable`, 제안 비중 적용 `apply` — 적용은 포트폴리오 목표가 바뀌므로 `invalidateTacticalData(qc, { portfolioChanged: true })`)

_알림 토글_ (설정 페이지, `["settings"]` boolean 필드 조회/PUT 패턴)

- `useSettingsToggle.ts` — 조회+뮤테이션+무효화+에러토스트 패턴을 통합한 제네릭 팩토리(`{ field, defaultValue, mutationFn, invalidate }`). 아래 토글 훅 대부분이 필드명만 바꿔 얹어 씀. `useCompositeSignalToggle`/`useMarketSignalDigestToggle`은 전용 상태 조회 엔드포인트가 있어 이 팩토리 미사용
- `useCompositeSignalToggle.ts` — 복합신호(시장/리스크) 등급 전환 시 즉시 알림 on/off. `MarketSignalAlertSection`(설정, 토글) + `MarketSignalBanner`(진단 탭, 읽기 전용) 공용
- `useMarketSignalDigestToggle.ts` — 시장신호 매일 요약(08:30 KST) on/off. `["settings"]` 쿼리의 `market_signal_daily_digest_enabled` 직접 읽음. `MarketSignalAlertSection` 두 번째 토글
- `useYearEndTaxReminderToggle.ts` — 연말 절세 리마인더 on/off. `year_end_tax_reminder_enabled` · `PUT /settings/year-end-tax-reminder`. 기본 `false`(옵트인)
- `useGoalAchievementAlertsToggle.ts` — 목표 달성 알림 on/off. `goal_achievement_alerts_enabled` · `PUT /settings/goal-achievement-alerts`. 기본 `true`
- `useMonthlyReportAlertsToggle.ts` — 월간 리포트 이메일 on/off. `monthly_report_enabled` · `PUT /settings/monthly-report-alerts`. 기본 `true`
- `useRecommendationDriftAlertToggle.ts` — "추천 비중이 달라졌어요" 알림 on/off. `recommendation_drift_alert_enabled` · `PUT /settings/recommendation-drift-alert`. 기본 `false`(옵트인)
- `useChallengeRemindersToggle.ts` — 적립 챌린지 독려(매월 25일)·월간 결산(매월 1일) 알림 on/off. `challenge_reminders_enabled` · `PUT /settings/challenge-reminders`. 기본 `false`(옵트인)
- `useAutoRebalancingDailyCap.ts` — AUTO 리밸런싱 하루 거래대금 상한 조회/저장(`auto_rebalancing_daily_value_cap_krw` · `PUT /settings/auto-rebalancing-daily-cap`, null=무제한). 토글이 아닌 금액 입력이지만 같은 `["settings"]` 패턴

_모바일/네이티브 (Capacitor)_

- `useBiometric.ts` — 생체 인증 (Capacitor Android)
- `useHaptic.ts` / `usePullToRefresh.ts` / `useSwipeNavigation.ts` — 모바일 UX
- `usePushNotifications.ts` / `useRegisterRefresh.ts` / `useWidget.ts` — FCM 푸시·홈 위젯 (Android)
- `useSyncAllWatcher.ts` — "전체 갱신"(계좌 전체 동기화) 백그라운드 진행 상태 폴링. `App.tsx`의 `AppRoutes()` 최상단에서 한 번만 마운트되어 탭 이동과 무관하게 계속 폴링 — 진행 상태는 `stores/syncStore.ts`(Zustand)로 관리

_기타_

- `useInsights.ts` — 인사이트 조회
- `useLogout.ts` — 로그아웃 로직, `useOnlineStatus.ts` — 온라인/오프라인 감지
- `useTransactionFormState.ts` — 거래내역 입력 폼 상태
- `useCapsLockWarning.ts` — 비밀번호 입력 시 Caps Lock 켜짐 여부 감지 (로그인/회원가입 폼)

**기타 상수 (`src/constants/`):**

- `queryKeys.ts` — React Query queryKey 상수 (`QUERY_KEYS` 객체). 모든 queryKey는 여기서 import
- `queryConfig.ts` — `STALE_TIME`, `REFETCH_INTERVAL` 상수. 매직 넘버 대신 이 상수 사용
- `defaults.ts` — 백테스트 기본 날짜 상수 (`BACKTEST_DEFAULT_START_DATE` 등)
- `tabs.ts` — 탭 배열 + 타입: `ASSETS_TOP_TABS`("투자현황"/"계좌관리", AssetsPage 상위 탭), `ASSET_MANAGEMENT_TABS`("은행계좌"/"증권계좌"/"부동산"/"내역", 계좌관리 내부 탭 — "내역"은 `AccountHistoryTab`), `PORTFOLIO_TABS`("종목 현황"/"배당", 세금은 계획탭 › 절세로 이동)
- `transaction.ts` — 거래 유형 상수 (`TX_TYPES`, `TX_LABELS`/`TX_COLORS`: DEPOSIT/WITHDRAWAL/DIVIDEND/INTEREST) + `txDeleteConfirmMessage()`(입출금 기록 삭제 확인 문구)
- `validation.ts` — 포트폴리오 비중 허용 오차 (`PORTFOLIO_WEIGHT_TOLERANCE`)
- `rebalancingConfig.ts` — 리밸런싱 알림 폼용 상수 (`SCHEDULE_OPTIONS`, `TRIGGER_CONDITION_OPTIONS`, `MODE_OPTIONS`, `STRATEGY_OPTIONS`, `MARKET_CONDITION_OPTIONS`, `TAX_IMPACT_GATE_OPTIONS` — AUTO 모드 세금영향 게이트 on/off, `AlertAutoModeSection.tsx`가 소비) + `PLAN_LEG_STATUS_LABEL`(대기 플랜 leg 상태 6종 한글 라벨 — 이력 탭·승인 페이지 공용)
- `uiSizes.ts` — 모바일 터치 타겟 상수 (`TOUCH_TARGET_MIN`: `min-h-[44px] min-w-[44px]` + 가운데 정렬, `TOUCH_TARGET_MIN_MOBILE_ONLY`: 모바일에서만 44px 적용하고 `sm:` 이상에서 축소하는 변형, `TOUCH_TARGET_ROW`: 아이콘+레이블이 좌측 정렬인 메뉴 로우/링크용 변형(`justify-start`), `TOUCH_TARGET_COMPACT_MOBILE_ONLY`: 배지/탭/필터 칩처럼 조밀하게 나열되는 보조 요소용 절충 터치 타겟(36px, 모바일 전용). 인터랙티브 요소(버튼/입력 등)에 인라인 `min-h-[44px] min-w-[44px]` 재정의 금지, 이 상수들 사용
- `timers.ts` — UI 타이밍 상수 (`SEARCH_DROPDOWN_HIDE_DELAY`: 150ms blur 후 드롭다운 지연, `REDIRECT_DELAY_MS`: 3000ms, `FOCUS_SETTLE_DELAY`: 0ms)
- `assets.ts` — 자산 유형 관련 상수 (`CASH_TICKER`, `REAL_ESTATE_ASSET_TYPE`, `KR_PROPERTY_MARKET`, `BASE_TYPE_STOCK_ONLY`, `BASE_TYPE_TOTAL_ASSETS`, `CASH_EQUIVALENT_TICKER`/`CASH_EQUIVALENT_MARKET`/`CASH_EQUIVALENT_NAME`)
- `goalRiskTolerance.ts` — 목표 설정 마법사/옵션 모달 공용 리스크 성향 옵션 레이블 (`GoalSettingWizard`, `GoalRecommendationOptionsModal`)
- `savingsPresets.ts` — 계획탭 저축 시뮬레이터 가정 수익률 프리셋
- `brokerCredentials.ts` — KIS/키움/토스 자격증명 입력 폼 설정 테이블(`BrokerDataSource`) — `BrokerCredentialFields`가 이 테이블만 보고 렌더. 새 브로커는 여기 추가
- `nav.ts` — `BottomNav` 탭 정의 (홈/자산/리밸런싱/계획/설정 5탭)
- `markets.ts` — 해외거래소 판별 상수 (상세는 하단 "마켓 유틸리티" 참고)
- `inputStyles.ts` — 공통 입력 필드 Tailwind 스타일 상수 (상세는 하단 "입력 스타일 상수" 참고)
- `index.ts` — 상수 re-export

**타입 정의:** `src/types/index.ts` — 포트폴리오 포지션, 계좌 등 공통 TypeScript interface 정의.

**Zod 스키마 (`src/schemas/`):**

- `challenge.ts`, `trade.ts`, `transaction.ts` — 폼 입력값 런타임 유효성 검사 (Zod). 실제 폼이 쓰는 스키마만 둔다(폼 없이 테스트만 쓰던 auth·assets·portfolios는 plans/54에서 삭제). 새 폼 추가 시 이 디렉토리에 스키마 파일 추가.

**테스트 위치 (Vitest):**

- `src/utils/__tests__/*.test.ts` — 순수 유틸 함수 단위 테스트 (`format.test.ts`, `error.test.ts`, `colors.test.ts`, `chart.test.ts`, `dividendUtils.test.ts`, `portfolio.test.ts`, `queryInvalidation.test.ts`, `accounts.test.ts`, `diagnosisInsights.test.ts`, `platform.test.ts`, `toast.test.ts`, `actionPriority.test.ts`, `legacyTabRedirect.test.ts` 등)
- `src/__tests__/components.*.test.tsx` — 컴포넌트 테스트
- `src/__tests__/pages.*.test.tsx` — 페이지 테스트
- `src/__tests__/hooks.*.test.ts(x)` — 커스텀 훅 테스트
- `src/__tests__/api.*.test.ts` — API 레이어 테스트

> 각 카테고리 파일 개수는 계속 늘어남 — 현재 목록은 `ls src/__tests__/` 확인.

- 도메인별 개별 위치: 예) `src/components/rebalancing/__tests__/rebalancingTradeMath.test.ts`

> 순수 유틸뿐 아니라 컴포넌트·훅·페이지·API 레이어 모두 테스트 대상. 새 유틸은 동일 디렉토리에 `*.test.ts`, 새 컴포넌트/훅/페이지는 `src/__tests__/`에 대응 파일 작성. `vite.config.ts`에 커버리지 임계값(lines/functions/branches/statements) 설정됨.

**asset_type_allocation:** 백엔드는 모든 자산 유형을 반환. PortfolioPage에서 STOCK 타입만 프론트엔드 필터링으로 표시 — 포트폴리오 페이지는 주식 계좌 전용 뷰이므로 의도된 동작.

**`src/lib/storedSession.ts`** — supabase-js가 저장한 `sb-*-auth-token`을 SDK 없이 동기로 읽음(`readValidStoredToken`/`hasStoredSession`/`readStoredSession`). `api/client.ts`가 부팅 시 토큰을 시드해 401→refresh 왕복을 없애고, `authStore`의 낙관적 로그인(7일, `/auth/me` 검증은 백그라운드)이 사용자 일치 확인에 씀. 형식 해석 실패 시 null(기존 경로로 폴백). **`src/lib/serviceWorker.ts`** — 웹에서만 SW 등록(`vite.config.ts`의 `injectRegister: null`), Capacitor에서는 기존 등록·캐시 해제. **`src/lib/sentry.ts`** — Sentry 지연 초기화(`initSentryDeferred`, 유휴 시간 동적 import) + `captureException` 래퍼. 앱 코드는 `@sentry/react`를 직접 import하지 말 것(엔트리 청크로 다시 끌려옴). 라우트 패턴 트랜잭션은 쓰지 않음(plans/72).

**`src/lib/supabase.ts`** — `getSupabase()`(async 함수)를 통해 Supabase 클라이언트를 지연 초기화한다(env vars 필요). `@supabase/supabase-js`(약 200KB)를 top-level import하면 이 파일을 참조하는 모든 부팅 경로(authStore/api client)가 실제 렌더 전에 파싱·실행을 먼저 기다려야 해 모바일 저사양 기기에서 체감 로딩 지연을 유발했다 — 그래서 `await import("@supabase/supabase-js")`로 동적 로드하고 클라이언트를 메모이즈한다. 모든 소비 코드(`authStore.ts`, `api/client.ts`, `AuthCallbackPage.tsx` 등)는 `const supabase = await getSupabase();` 형태로 사용 — 동기 `supabase` export는 없음. 직접 확장 금지 — 토큰 첨부·갱신은 `api/client.ts` 인터셉터 소관. `persistSession: true`로 세션 JWT가 localStorage(`sb-*-auth-token`)에 평문 저장됨 — httpOnly 쿠키 전환은 Capacitor WebView SameSite 제약으로 보류, CSP + 로그아웃 시 `queryClient.clear()`+`PERSIST_CACHE_KEY` 삭제로 경계강화만 적용(결정기록: `docs/plans/28-localstorage-token-decision.md`).

> **인증 구조:** 로그인·회원가입·토큰 갱신은 전부 Supabase Auth가 담당하고, 백엔드는 토큰을 발급하지 않는다. `api/client.ts`의 Axios 인터셉터가 Supabase 세션의 `access_token`을 `Authorization: Bearer`로 첨부하고(모듈 레벨 캐시), 401이면 `supabase.auth.refreshSession()` 후 대기 큐의 요청을 재시도, 갱신 실패 시 로그아웃. 백엔드는 이 토큰을 Supabase JWKS로 검증만 한다(`backend/app/services/auth_service.py`). 별도의 "백엔드 JWT"는 없다.

**상태 관리 원칙:** 서버에서 오는 데이터 → React Query. 순수 클라이언트 전역 상태 → Zustand.

- Zustand (`src/stores/`): `authStore.ts`(인증 토큰·유저 정보), `themeStore.ts`(다크모드 토글), `syncStore.ts`("전체 갱신" 백그라운드 진행 상태 — `useSyncAllWatcher.ts`가 갱신), `pushNotificationStore.ts`(FCM 푸시 등록 상태 — `SettingsPage`가 읽음)
- 새 전역 상태 추가 시: 서버 fetch가 필요하면 React Query 훅, 그렇지 않으면 Zustand store.

**포트폴리오와 대시보드의 관계:** `DashboardPage`가 `/portfolio/overview`를 추가 조회해 `PortfolioSummaryCard`에 전달. 양쪽이 같은 queryKey(`"portfolio-overview"`)를 공유하므로 포트폴리오 sync 후 대시보드도 자동 갱신됨.

---

## Absolute Rules

**수익/손실 색상 (한국 주식 관례)**

- 수익(양수) → `text-red-500`, 손실(음수) → `text-blue-500`.
- 대소문자 주의: 전통적인 green/red와 반대. 절대 혼용 금지.

**React Query queryKey 규칙**

| 데이터                                                             | queryKey                                                                                                                    |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- |
| 대시보드 집계                                                      | `["dashboard"]`                                                                                                             |
| 포트폴리오 overview (accountId 지정 시 계좌별, 미지정 시 "all")    | `["portfolio-overview", accountId]` — `portfolioOverviewBase`(`["portfolio-overview"]`)는 무효화 프리픽스 전용              |
| 포트폴리오 overview (경량)                                         | `["portfolio-overview", "lite"]`                                                                                            |
| 추종 지수별 비중 (자산탭 비중 분석 카드, accountId 지정 시 계좌별) | `["index-exposure", accountId]` — `indexExposureBase`(`["index-exposure"]`)는 무효화 프리픽스 전용(sync·계좌 CUD 시 무효화) |
| 지수 그룹 제안 (포트폴리오 편집기 "지수로 묶기") | `["index-exposure", "group-suggestions", accountIds]` — `indexExposureBase` 하위라 같은 무효화를 공유 |
| 포트폴리오/백테스트/리밸런싱 탭                                    | `["portfolios"]`                                                                                                            |
| 전체 계좌 목록                                                     | `["accounts"]`                                                                                                              |
| 계좌별 포지션                                                      | `["account-positions", accountId]`                                                                                          |
| 계좌별 거래내역                                                    | `["transactions", accountId]` — `transactionsBase`(`["transactions"]`)는 무효화 프리픽스 전용(전체·연도별·계좌별 함께)      |
| 전체 거래내역 (무기간)                                             | `["transactions", "all"]`                                                                                                   |
| 연도별 거래내역                                                    | `["transactions", "all", year]`                                                                                             |
| 기간별 매수 (계좌관리 › 내역 › 매수 내역)                          | `["period-purchases", period, year, month, accountId]` — `periodPurchasesBase` 무효화 전용(sync·계좌 CUD·매매기록 CUD 시)    |
| 수기 매매 기록 (종목별)                                            | `["trades", accountId, ticker, market]` — `trades` 프리픽스로 무효화                                                        |
| 배당금 티커별 (accountId 지정 시 계좌별)                           | `["dividend-by-ticker", accountId]` — `dividendByTickerBase` 무효화 전용                                                    |
| 배당금 요약 (accountId 지정 시 계좌별)                             | `["dividend-summary", accountId]` — `dividendSummaryBase` 무효화 전용                                                       |
| 배당금 포지션 (accountId 지정 시 계좌별)                           | `["dividend-positions", accountId]` — `dividendPositionsBase` 무효화 전용                                                   |
| DCA 분석 (InvestPlanPage + DashboardPage)                          | `["dca-analysis"]`                                                                                                          |
| 적립 챌린지 목록 + 진행률 (계획 탭 · 대시보드)                     | `["challenges"]`                                                                                                            |
| 적립 챌린지 넛지 요약 (하단 네비 배지)                             | `["challenges", "summary"]`                                                                                                 |
| 배당 계획 (연/월배당)                                              | `["dividend-plan"]`                                                                                                         |
| 배당 월별 균등화 제안                                              | `["monthly-optimization"]`                                                                                                  |
| 설정                                                               | `["settings"]`                                                                                                              |
| 현재 환율                                                          | `["exchange-rate"]`                                                                                                         |
| 환율 알림 목록                                                     | `["exchange-rate-alerts"]`                                                                                                  |
| 주가 알림 목록                                                     | `["stock-price-alerts"]`                                                                                                    |
| 리밸런싱 알림 목록                                                 | `["rebalancing-alerts"]`                                                                                                    |
| 포트폴리오별 리밸런싱 알림                                         | `["rebalancing-alert", portfolioId]` — `rebalancingAlertBase`(`["rebalancing-alert"]`)는 무효화 프리픽스 전용               |
| 포트폴리오 내 계좌별 알림 목록                                     | `["rebalancing-alert", portfolioId, "accounts"]`                                                                            |
| 계좌별 개별 알림                                                   | `["rebalancing-alert", portfolioId, "accounts", accountId]`                                                                 |
| 리밸런싱 실행 이력                                                 | `["rebalancing-history"]`                                                                                                   |
| 리밸런싱 대기 플랜 목록                                            | `["rebalancing-plans"]`                                                                                                     |
| 이메일·푸시 승인 페이지 플랜 미리보기                              | `["rebalancing-plan-preview", token]`                                                                                       |
| 리밸런싱 전략                                                      | `["rebalancing-strategy", portfolioId]` — `rebalancingStrategyBase`(`["rebalancing-strategy"]`)는 무효화 프리픽스 전용      |
| 드리프트 경량 요약 (대시보드)                                      | `["drift-summary"]`                                                                                                         |
| 홈 "지금 할 일" (행동 신호 집계)                                  | `["action-items"]`                                                                                                          |
| 세금 추정 요약 (accountId 지정 시 계좌별)                          | `["tax-summary", year, accountId]` — `taxSummaryBase` 무효화 전용                                                           |
| 해외 포지션 양도세 계획 (accountId 지정 시 계좌별)                 | `["overseas-positions-tax", accountId]` — `overseasPositionsTaxBase` 무효화 전용                                            |
| ISA 만기 현황                                                      | `["isa-status"]`                                                                                                            |
| 연금 납입 현황                                                     | `["pension-contribution", year]` — `pensionContributionBase` 무효화 전용                                                    |
| 해외 실현손익 (KIS 기간손익, accountId 지정 시 계좌별)             | `["overseas-realized", year, accountId]` — `overseasRealizedBase` 무효화 전용                                               |
| 절세 액션 플랜                                                     | `["tax-action-plan"]`                                                                                                       |
| 자산배분 이력 (DashboardPage 전용, accountId 지정 시 계좌별)       | `["allocation-history", months, accountId]` — `allocationHistoryBase` 무효화 전용                                           |
| 알림 발송 이력                                                     | `["alert-history"]`                                                                                                         |
| 인사이트/진단                                                      | `["insights"]`                                                                                                              |
| 포트폴리오 리스크 지표                                             | `["portfolio-risk", id]` — `portfolioRiskBase` 무효화 전용                                                                  |
| 시장 위험 신호                                                     | `["market-signal"]`                                                                                                         |
| 복합신호 (시장/리스크) 상태                                        | `["composite-signal-status"]`                                                                                               |
| 목표 역산 추천 (전체 자산)                                         | `["goal-recommendation", "overall"]` — `goalRecommendationBase`(`["goal-recommendation"]`)는 무효화 프리픽스 전용           |
| 목표 역산 추천 (투자기간별)                                        | `["goal-recommendation", "by-horizon"]`                                                                                     |
| 목표 역산 추천 (연령대별)                                          | `["goal-recommendation", "by-age"]`                                                                                         |
| 추천 후보 ETF 중복·유사 점검                                       | `["goal-recommendation", "candidate-overlap", signature]` — goal-recommendation 프리픽스로 함께 무효화                      |
| 포트폴리오 적용 전 비교 미리보기(현재 목표 비중 기대지표)          | `["portfolio-expected-metrics", portfolioId]`                                                                               |
| 목표 설정 마법사 필요수익률·적립액 가이드 프리뷰                   | `["goal-feasibility", goalAmount, targetYear, monthlyDepositAmount, initialAmount]`                                         |
| CPI/Core CPI 인플레이션 요약                                       | `["inflation-summary"]`                                                                                                     |
| QQQ/SPY 전술 배분 국면·제안 비중 (포트폴리오별)                    | `["tactical-status", portfolioId]` — `tacticalStatusBase` 무효화 전용                                                       |
| 전술 배분 규칙 백테스트                                            | `["tactical-backtest", portfolioId, years]` — `tacticalBacktestBase` 무효화 전용(비중표 변경 시)                            |

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
  import { fmtKrw, fmtKrwShort, fmtMonth, fmtPct } from "@/utils/format";
  ```
- `fmtKrw(n)` — 억원/만원/원 (음수 포함). 일반 텍스트 표시용.
- `fmtKrwPreview(n)` — 입력 중 금액 확인용 "5,000,000원 (500만원)" (콤마 + 억/만원 병기).
- `fmtKrwShort(n)` — "억"/"만" (단위 없음). 차트 레이블용.
- `fmtKrwPrice(n)` — 소수점 없는 원화 가격 표시.
- `fmtMonth(str)` — "YYYY-MM" → "YYYY년 M월".
- `fmtPct(n)` — "+5.23%" 형식. null이면 "—".
- `pctOf(part, total)` — 합계 대비 비중(%), 합계 0 이하면 0. 인라인 `total > 0 ? (v / total) * 100 : 0` 대신 사용.
- `clampPct(pct)` — 진행률 바 렌더링용 0~100 클램프. 프로그레스 바 `style={{ width }}`에 값 그대로 넣지 말 것.
- `localToday()` — 사용자 로컬(KST) 기준 오늘 "YYYY-MM-DD". 날짜 입력 기본값에 `new Date().toISOString().slice(0, 10)`를 쓰지 말 것 — UTC라 KST 오전 9시 전엔 전날이 된다. 모듈 최상위 상수로 고정하지 말고 폼을 열 때 호출(자정을 넘긴 세션 대응).
- `localMonth()` — 같은 기준의 이번 달 "YYYY-MM". `new Date().toISOString().slice(0, 7)` 금지(매월 1일 오전 9시 전엔 전월).
- `parseYmd(str)` / `daysUntilYmd(str)` — "YYYY-MM-DD" 분해 / 로컬 자정 기준 남은 일수(지났으면 음수).
- `fmtDateTime(iso)` — ISO 시각 → `toLocaleString("ko-KR")` 날짜·시각 표기. 옵션이 다른 표기(시각 생략 등)는 인라인 유지.
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

- `toast(message, type?)` — `window.dispatchEvent("growlio:toast")` 이벤트 발행. React 훅이 아니라 일반 함수라 컴포넌트·비React 코드 어디서든 직접 호출(`components/Toaster.tsx`가 구독해 표시).
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

**지수 그룹 편집 유틸리티 (`src/utils/portfolioGroups.ts`, plans/74)**

- 포트폴리오 항목의 지수 그룹(`PortfolioItem.group` — ticker/market은 대표 매수 종목, `members`는 함께 합산할 종목, `domestic_alt`는 ISA·연금 계좌용 국내 대체 매수 종목) 편집 순수 함수: `applyIndexGroup(items, suggestion)`(같은 지수 단독 행을 그룹 한 행으로 합치고 비중 합산), `setGroupPrimary`·`setGroupDomesticAlt`(이전 대표·대체 종목은 멤버로 남김), `removeGroupMember`, `ungroupItem`. 멤버 `leverage`(정방향 레버리지 배수, QLD=2)는 노출 기준 합산용 — `isLeveraged`·`memberLabel`("QLD ×2"), 레버리지 멤버는 대표·국내 대체 후보에서 제외(백엔드 검증과 같은 규칙). UI는 `UnifiedPortfolioEditor`의 "지수로 묶기"(`IndexGroupPicker`) + `PortfolioGroupItemRow`.
- 분석 결과의 그룹 행은 `shares_to_trade`가 null이고 종목별 매매는 `members`에 있다 — 주문·거래 요약은 `components/rebalancing/rebalancingTradeMath.ts`의 `flattenTradeItems()`로 펼친 목록을 쓴다(`calcTradeSummary`·`getActionableItems`가 이미 사용).

**리밸런싱 URL 유틸리티 (`src/utils/rebalancingUrl.ts`)**
- `REBALANCING_TABS`(진단/포트폴리오/목표 조정/이력)·`GOAL_MODES`(추천/전술) — 탭 이름의 단일 정의. 백엔드 `email_service._rebalancing_link`·`insight_service`·`action_items_service`의 탭 문자열과 같아야 함
- `parseRebalancingTab(params)` — 예전 `rtab=추천`/`rtab=전술`(이미 발송된 이메일·푸시)을 목표 조정 탭의 해당 모드로 매핑, 알 수 없는 값은 진단
- `rebalancingUrl(options)` — `/rebalancing` 링크 빌더(공백은 `%20`). 링크 문자열을 직접 조립하지 말 것

**리밸런싱 알림 설명 유틸리티 (`src/utils/rebalancingAlertDescription.ts`)**

- `buildAlertDescription(...)` — 알림 스케줄/트리거 조건/모드 설정을 사람이 읽는 한글 설명 문장으로 조합.

**리밸런싱 임계값 추천 유틸리티 (`src/utils/rebalancingThresholdRecommendation.ts`)**

- 목표 역산 추천 옵션(계좌 투자기간 태그 등) 기반으로 드리프트 임계값을 추천. `useRebalancingAlertForm.ts`에서 사용.

**추천 비중 변화 감지 유틸리티 (`src/utils/recommendationDrift.ts`)**

- `computeRecommendationDrift(recommended, current)` — 추천 비중과 목표 포트폴리오의 현재 비중을 ticker+market 기준 비교해 `{ maxDeltaPct, newCandidateCount }` 반환.
- `hasSignificantDrift(drift)` — `RECOMMENDATION_DRIFT_THRESHOLD_PCT`(3%p) 이상 차이 나거나 신규 후보가 있으면 true. `RecommendationCard.tsx`가 "추천이 달라졌어요" 배지 노출 여부 판단에 사용.
- `foldIntoPortfolioGroups(recommended, current)` — 추천 종목 중 현재 포트폴리오 지수 그룹 멤버는 그룹(대표 종목 키)으로 합산(백엔드 `fold_into_portfolio_groups`와 같은 규칙). `computeRecommendationDrift`·`buildWeightDiffRows`가 내부에서 먼저 적용. `toPortfolioItemsPreservingGroups(recommended, current)` — 추천 적용 저장용(합산 + 그룹 정보 유지), `RecommendationCard` 적용 뮤테이션이 사용.
- `buildWeightDiffRows(recommended, current)` — 두 목록을 합쳐 종목별 (현재 비중, 추천 비중) 전체 비교 행을 만든다(추천 비중 내림차순 정렬) — "적용" 확인 모달의 비교 미리보기(`RecommendationComparisonPreview`, `RecommendationCard.tsx`)에서 사용.

**ETF 중복 표시 유틸리티 (`src/utils/etfOverlap.ts`)**

- `formatTerPct(pct)` — 총보수(%)를 유효숫자 3자리로 표시(0.0068% 같은 초저보수도 뭉개지지 않게). `annualCostGapPer10M(gapPct)` — 보수 차이 → 1,000만원 보유 시 연간 비용 차이(원). `useCandidateOverlap` 결과 렌더용.

**진단 인사이트 유틸리티 (`src/utils/diagnosisInsights.ts`)**

- `buildDiagnosisNotes(ctx)` — `DiagnosisContext`(시장상황/리스크/세금영향)를 화면 표시용 조건부 문구 리스트로 변환.
- `buildCombinedStatusNote(needsCount, marketLevel)` — "이탈 종목 발견 + 시장상황"을 결합한 한 줄 설명 생성.

**시장 위험 신호 표시 유틸리티 (`src/utils/marketSignalRows.ts`)**

- `buildSignalRows(signals)` — `MarketSignalResponse.signals`(8개 매크로 지표)를 고정 순서 `SignalRowDisplay[]`로 변환. 백엔드 `market_signal_service.py`의 Tier A(VIX/하이일드/고용)/B+C(금리 커브·인플레이션·달러·환율·유가) 분류를 재사용해 각 행에 `tier` 부여 — `MarketSignalBanner.tsx`가 Tier A는 항상, 나머지는 "매크로 지표 더보기" 토글로 묶음.
- `dotColorForSubScore(subScore)` — 심각도 점 색상을 `sub_score`(0/1/2/3+) 기준 단일 함수로 통일.
- 공용 렌더러: `components/rebalancing/SignalRow.tsx`(`{label, content}` 프레젠테이션).

**계좌 유틸리티 (`src/utils/accounts.ts`)**

- `isPortfolioAccount(assetType)` / `isStockAccount(assetType)` / `isBankAccount(assetType)` — `asset_type` 문자열을 받아 계좌 유형 판별(계좌 객체가 아닌 `account.asset_type` 전달). 인라인 `asset_type` 비교 금지.
- `isSyncableAccount(dataSource)` — KIS/키움/토스 API 연동 계좌(`data_source`)라 브로커 동기화 가능한지.
- `isBrokerBalanceAccount(assetType)` — 실시간 잔고·리밸런싱 진단 대상 브로커 계좌(KIS·키움·토스, `BROKER_BALANCE_ASSET_TYPES`).
- `isOrderExecutableAccount(assetType)` — 주문 실행 가능 계좌(KIS·키움, `ORDER_EXECUTABLE_ASSET_TYPES` — 토스는 주문 API 미구현). 백엔드 `order_builder.ORDER_EXECUTABLE_ASSET_TYPES`와 같은 집합.
- `horizonTaggedAccounts(accounts)` — 투자기간 태그가 있는 증권 계좌(`isPortfolioAccount`)만. 자산탭 투자현황 "투자기간별 자산현황"(`HorizonSummaryCard`)은 이 계좌들의 `invested_krw + unrealized_pnl`(= `total_stock_krw`와 같은 공식, 예수금 제외)로 합산한다 — `amount_krw`(예수금 포함)나 은행 계좌를 쓰면 기간별 합이 주식 총평가액보다 커진다.

**색상 유틸리티 (`src/utils/colors.ts`)**

- P&L 색상은 `pnlColor(value)` 함수 사용 — `PROFIT_COLOR`(`text-red-500`) / `LOSS_COLOR`(`text-blue-500`) 상수도 export됨.
  ```ts
  import { pnlColor } from "@/utils/colors";
  // <span className={pnlColor(profit)}>
  ```
- 직접 `text-red-500` / `text-blue-500` 인라인 작성 금지 (색상 관례 변경 시 일괄 교체 불가).

**리스크 유틸리티 (`src/utils/riskLevel.ts`)**

- `buildMetrics(m)` — `PortfolioRiskMetrics`를 `RiskMetricsCard` 표시용 `MetricConfig[]`로 변환.
- `summarizeRiskLevel(...)` — 리스크 레벨(`RiskLevel`: low/medium/high) 판정 + `LEVEL_BADGE` 색상 매핑. `RiskMetricsCard.tsx`가 소비.

**기타 계산 유틸 (`src/utils/`)** — 백엔드 공식을 포팅한 것은 양쪽을 함께 수정할 것

- `dcaScenarioProjection.ts` — DCA 시나리오 비교 곡선. 백엔드 `dca_service.py`의 `_build_projection_curve()` 공식 포팅.
- `savingsProjection.ts` — 계획탭 절약 복리 시뮬레이터(월복리 연금 미래가치).
- `goalFeasibility.ts` — `classifyGoalFeasibility(requiredReturnPct)`: 필요 수익률을 달성 가능성 구간(밴드)으로 분류. `GoalSettingWizard` 사용.
- `dcaAutoBuy.ts` — `isDcaAutoBuyPreset(alert)`: AUTO·매월·SCHEDULE_ONLY·BUY_ONLY 조합이면 "정기 적립식 자동매수"로 표시 판정.
- `actionPriority.ts` — 행동 항목 우선순위 배지 스타일(`ACTION_PRIORITY_STYLE`: HIGH 우선/MEDIUM 권장/LOW 참고)·마감 라벨(`deadlineLabel`). `TaxActionPlanCard`·`ActionItemsCard` 공용
- `legacyTabRedirect.ts` — 탭 재편(plans/50)으로 옮겨진 옛 딥링크 변환: `legacyAssetsTaxRedirect()`(자산 세금 → 계획 › 절세), `legacyHistorySegment()`(계좌관리 옛 하위탭 → 내역 세그먼트). 이메일·푸시에 저장된 링크 호환용이라 지우지 말 것
- `safeStorage.ts` — `storageGet`/`storageSet`/`storageRemove`(localStorage), `sessionGet`/`sessionSet`(sessionStorage), `getLocalStorageOrUndefined`(객체 자체가 필요한 persister용). 저장소가 막힌 환경(사생활 보호 모드·사이트 데이터 차단)에서 예외를 삼키는 래퍼 — `localStorage`/`sessionStorage` 직접 접근 금지(차단 시 `window.localStorage` 접근만으로 throw해 부팅 실패).
- `notificationAlertGroups.ts` — 알림 설정 페이지의 필드 그룹(`REPORT_ALERT_FIELDS`/`INSTANT_ALERT_FIELDS`).

**배당 유틸리티 (`src/utils/dividendUtils.ts`)**

- `yieldBadgeClass(yield)` — 배당수익률에 따른 Tailwind 뱃지 클래스 반환 (≥7%: 초록, ≥4%: 에메랄드, ≥2%: 황색).
- `dividendFreqInfo(months)` — 월 배열로 배당 주기 레이블·색상 반환 (월배당/분기배당/반기배당/연배당).
- `weightBarColor(pct)` — 포트폴리오 비중 막대 색상 반환. 인라인 클래스 직접 작성 금지.

**입력 스타일 상수 (`src/constants/inputStyles.ts`)**

- 인라인 Tailwind 입력 스타일 직접 작성 금지. 상수 import해 사용:
  ```ts
  import {
    INPUT_SM,
    INPUT_MD,
    LABEL_SM,
    LABEL_MD,
    SELECT_SM,
    TEXTAREA_SM,
  } from "@/constants/inputStyles";
  ```
- `INPUT_SM` / `INPUT_MD` — `text-sm` / `text-base` 입력 필드 (border, bg, focus ring 포함)
- `LABEL_SM` / `LABEL_MD` — `text-xs` / `text-sm font-medium` 레이블
- `SELECT_SM` — INPUT_SM과 동일 (select 요소용), `TEXTAREA_SM` — resize-none 포함

**모바일 UI 최소 크기 규칙**

- 텍스트는 `text-xs`(12px) 미만 임의값(`text-[9px]`, `text-[10px]` 등) 사용 금지 — 모바일 가독성 저하.
- 인터랙티브 요소(버튼/입력 등) 터치 영역은 `src/constants/uiSizes.ts`의 `TOUCH_TARGET_MIN`(`min-h-[44px] min-w-[44px]`) 사용.
- 단, 배지/탭/필터 칩/보조 링크/카드 내부 아이콘 버튼처럼 여러 개가 조밀하게 나열되는 요소는 44px 강제 시 시각적으로 뭉툭해져 오히려 가독성이 떨어질 수 있다 — 이 경우 `TOUCH_TARGET_COMPACT_MOBILE_ONLY`(36px, WCAG AA 24px 이상 충족)를 사용해도 된다.
- 단, `StockAccountCard.tsx`/`BankAccountCard.tsx`/`PortfolioItemRow.tsx`의 삭제 버튼처럼 이미 앱 전역에 44px로 정착된 아이콘 버튼 패턴은 개별 화면에서 임의로 축소하지 말 것 — 화면 간 일관성이 깨짐.
- 금융 기록 삭제·실주문/실계획 생성처럼 되돌릴 수 없는 동작은 한 번 탭으로 실행하지 말고 `ConfirmModal`(무엇이 지워지는지/실행되는지 문구 포함)을 거친다 — 휴지통이 수정 아이콘 바로 옆이라 모바일 오탭이 잦다.
- 차트 축·범례 글자도 12px 이상 — Recharts tick은 `chartTickStyle(isDark)`(`utils/chart.ts`, `CHART_TICK_FONT_SIZE`)를 쓴다.
- 모바일 하단 네비 높이는 `index.css`의 `--bottom-nav-h` 하나가 기준 — 하단에 붙는 고정 요소(모달 `avoidBottomNav`·Toaster·고정 실행 바·본문 하단 여백)는 `bottom-[calc(var(--bottom-nav-h)+env(safe-area-inset-bottom))]`처럼 이 변수를 쓰고 rem 값을 하드코딩하지 말 것.
- `title` 속성은 터치에서 보이지 않는다 — 실패 사유·용어 설명·비활성 사유처럼 사용자가 알아야 하는 정보는 화면에 표시하거나 탭→토스트로 보여준다.
- 페이지 스크롤 안에 `max-h-* overflow-y-auto` 중첩 스크롤을 두지 말고 "N개 더 보기"로 개수를 제한한다.
- 음수가 가능한 숫자 입력(실현 손익·누적손익 등)은 `inputMode="numeric"/"decimal"` 키패드에 마이너스 키가 없으므로 이익/손실 `SegmentedControl` 토글 + 절댓값 입력으로 받는다(`TaxPlannerSection`·`IsaMaturityCard` 참고).

**탭/서브패널 지연 로딩 규칙**

- 페이지 내부 무거운 탭·서브패널 콘텐츠는 `React.lazy()`로 분리 — 최상위 라우트뿐 아니라 페이지 안에서 탭 전환으로 진입하는 콘텐츠도 대상(예: `AssetsPage`가 `AssetManagementPage`/`PortfolioPage`를, `PortfolioPage`/`InvestPlanPage`/`RebalancingPage`/`DashboardPage`가 각각 하위 탭 컴포넌트를 lazy-load). 새 탭 콘텐츠 추가 시 이 패턴을 따를 것.
- 로딩 중 표시는 `common/SkeletonCard.tsx`/`SkeletonStatBox.tsx`를 사용 — 카드/통계 박스 형태의 로딩 플레이스홀더를 인라인으로 새로 작성하지 말 것.

**헤딩 구조 규칙 (접근성)**

- 각 페이지(`src/pages/*.tsx`)의 최상위 return에는 `<h1 className="sr-only">{페이지명}</h1>`을 두어 스크린리더 사용자가 진입 시 현재 위치를 알 수 있게 한다(시각적으로는 숨김 — `BottomNav`/탭 UI가 이미 시각적 내비게이션을 담당).
- 카드/섹션 제목은 `<span>`/`<p>` 대신 `<h2>`/`<h3>`을 사용 — 스크린리더의 헤딩 내비게이션(다음 섹션으로 건너뛰기)이 동작하려면 실제 헤딩 태그가 필요하다. `CollapsibleCard.tsx`/`settings/shared.tsx`(`SectionCard`)/`Modal.tsx` 등 공용 컴포넌트를 거치는 카드 제목은 이미 전부 `h2`이고, 직접 마크업을 그리던 나머지 straggler(`StockAccountSummaryCard`/`RealEstateSection`/`EditableNameField`/`HeroSummaryCard`)도 정리 완료. 단, `RebalancingMobileCard.tsx` 같은 반복되는 리스트 행 아이템은 헤딩으로 승격하지 않음(그리드/리스트에 다수 반복 렌더돼 헤딩 목록이 라벨로 도배되면 오히려 스크린리더 내비게이션을 해침) — 의도된 제외이니 새 컴포넌트를 만들 때도 이 기준을 따를 것.

**콜랩스 기본값 일관성 규칙**

- 정보 밀도가 낮은 헤드라인 카드(`HeroSummaryCard`, `InvestmentGoalCard` 최상위 등)는 콜랩스 불가로 항상 펼침 유지 — 접었다 폈다 할 만큼 내용이 많지 않음.
- 보조/상세 카드(`InvestmentSnapshotCard`, `RebalancingStatusCard`, `TaxLimitsSection` 등)는 `useCollapsible`로 접기 가능하게 하되, 최초 방문 시 기본값은 **열림**(`true`)으로 시작 — 사용자가 직접 접으면 그 상태가 `localStorage`로 유지된다.
- 단, 이미 펼쳐진 부모 카드 내부의 2차 상세 토글(`MarketSignalBanner` 매크로·물가 지표 확장, `RebalancingDetailMetrics` 등 영속화 키 없는 세션 한정 토글)은 이 규칙 대상이 아님 — "최상위 카드"에만 적용되는 규칙이므로 중첩된 하위 토글까지 강제로 펼칠 필요는 없다.
- 새 카드 추가 시 이 규칙을 따를 것.
- 예외: 리밸런싱 진단 탭의 `RiskMetricsCard`는 **기본 접힘**(`growlio:rebalancing:risk-metrics-open`), `MarketSignalBanner`는 등급과 무관하게 배지+한 줄 요약이 기본이고 상세는 "자세히"로 연다(plans/64 S4 — 예전엔 비GREEN이면 자동 펼침).
- 예외: 리밸런싱 "목표 조정 › 전술"의 규칙 백테스트 카드와 계획탭 "절약 복리 시뮬레이터" 카드는
  보조 도구라 **기본 접힘**(`growlio:rebalancing:tactical-backtest-open`, `growlio:invest:savingsSimulatorOpen`). 포트폴리오 백테스트는 카드가 아니라 분석 패널(`AnalysisPanel`)의 세 번째 보기(리밸런싱 분석 / 효율 분석 / 백테스트 segmented)로 옮겼다(plans/64 S3).
- 예외: 자산탭 투자현황의 `AllocationCard`(비중 분석)는 **모바일(<640px)만 기본 접힘**(`growlio:portfolio:allocationOpen`, 사용자가 펼치면 유지) —
  바로 아래 보유 종목 목록이 첫 화면 가까이 오도록(plans/58). 접힘 힌트로 최대 종목·해외상장 비중을 보여준다.
- 홈에는 `RebalancingStatusCard`가 없다 — 리밸런싱은 `ActionItemsCard`의 REBALANCE 행(+시장 신호 배지)만 다룬다(같은 drift-summary가 홈에 여러 번
  노출되지 않게, plans/67 P1-3 → plans/73). `RebalancingStatusCard`는 진단탭 전용이며 항상 펼침.
  예외: 홈의 `ChallengeProgressCard`는 접는 카드가 아니라 한 줄 행.
- 예외(plans/67): 리밸런싱 포트폴리오 탭의 `RebalancingDiagnosisCard`(`growlio:rebalancing:diagnosisCardOpen`)와 분석 결과 아래
  "상세 정보"(지표·배당·미포함 종목·분석 시점, `growlio:rebalancing:analysisDetailsOpen`), 계획탭의 "더 빨리 달성하려면?"
  (`growlio:goalTimeline:fasterOpen`, `growlio:dividendPlan:fasterOpen`), 절세 플래너는 **기본 접힘** — 보조 제안·상세라 화면 길이만 늘림.

**마켓 유틸리티 (`src/constants/markets.ts`)**

- `DOMESTIC_MARKETS` — 국내 시장 코드(KOSPI·KOSDAQ·KRX). 비교 전 `.toUpperCase()`. 토스 해외 포지션은 `"US"`라 `isOverseasMarket`이 해외로 못 잡으므로, 국내/해외 이분은 `DOMESTIC_MARKETS.includes`로 한다.
- `POSITION_MARKETS` — 포지션 편집 드롭다운용 시장 목록.
- `marketLabel(market)` — 화면 표시용 라벨(`NASDAQ_US`→NASDAQ, `US`→미국, `KRX`→국내, `CASH`→현금). 시장 코드를 화면에 그릴 땐 원시값 대신 이것을 쓴다.
- `isOverseasMarket(market)` — market 문자열이 해외거래소인지 판별. 인라인 문자열 비교 금지.
  ```ts
  import { isOverseasMarket } from "@/constants/markets";
  // isOverseasMarket("NYSE") → true, isOverseasMarket("KOSPI") → false
  ```

**플랫폼 감지 유틸리티 (`src/utils/platform.ts`)**

- `isNativePlatform()` — Capacitor WebView(네이티브 앱) 여부 감지. Android 빌드에서만 `true` 반환.
- `getApiBaseUrl()` — 네이티브: `VITE_API_DOMAIN` 기반 절대 URL, 웹: `""` (상대 경로 유지).
- API 클라이언트나 네이티브 전용 분기 작성 시 인라인 `window.Capacitor` 접근 금지 — 이 함수 사용.

**차트 유틸리티 (`src/utils/chart.ts`)**

- `chartTooltipStyle(isDark)` — Recharts `<Tooltip>` 다크모드 스타일 반환. 인라인 스타일 객체 중복 작성 금지.
- `chartTickStyle(isDark)` / `CHART_TICK_FONT_SIZE`(12) — 축 tick 스타일. `fontSize: 11` 같은 인라인 값 금지.
  ```ts
  import { chartTooltipStyle } from "@/utils/chart";
  const { contentStyle, labelStyle, itemStyle } = chartTooltipStyle(isDark);
  ```

**캐시 무효화 유틸리티 (`src/utils/queryInvalidation.ts`)** — 아래 괄호 설명은 대표 항목만 나열(각 함수는 세금/자산배분이력 등 파생 Base 키도 함께 무효화하는 경우가 많음) — 정확한 전체 목록은 소스 확인.

- 계좌 sync 후: `invalidateSyncData(queryClient)` — portfolio-overview + dashboard + dividend 등 무효화.
- 계좌 CUD 후: `invalidateAccountData(queryClient)` — accounts + portfolio-overview + dashboard 등 무효화.
- 브로커 API 키 삭제(연동 해제) 후: `invalidateBrokerCredentialData(queryClient)` — 계좌 데이터 + 리밸런싱 알림·대기 플랜 무효화.
- 거래내역 CUD 후: `invalidateTransactionData(queryClient)` — transactions(전체·계좌별 프리픽스) + dashboard + 챌린지·연금/ISA·세금·지금 할 일 + 배당 요약·배당 계획(DIVIDEND 거래) 무효화.
- 수기 매매 기록 CUD 후: `invalidateTradeData(queryClient)` — trades + period-purchases + overseas-realized·tax-summary·tax-action-plan·action-items 무효화(해외 SELL 기록이 미지원 계좌 양도세 실현손익이 됨).
- 전술 배분 설정 변경 후: `invalidateTacticalData(queryClient)` — tactical-status + tactical-backtest. 제안 비중 적용(포트폴리오 목표 교체) 후엔 `{ portfolioChanged: true }`로 `invalidatePortfolioData`까지.
- 포트폴리오/백테스트/리밸런싱 CUD 후: `invalidatePortfolioData(queryClient)` — portfolios + accounts + drift-summary + rebalancing-strategy(전체 포트폴리오, 프리픽스) 무효화. 목표 비중 저장 직후 이미 열려있는 리밸런싱 분석 화면(`useAnalysisState`)은 이 무효화가 아니라 `AnalysisPanel`이 계산하는 `portfolioItemsSignature`(분석 중인 포트폴리오의 `items` 직렬화 값) 변경 감지로 자동 재분석됨 — `Portfolio.updated_at`은 비중만 바뀐 저장에서는 갱신되지 않으므로 신선도 판단에 쓰지 말 것.
- DCA 목표 변경 후: `invalidateDcaData(queryClient)` — dca-analysis + settings + dashboard + dividend-plan + challenges + action-items 무효화.
- 소득 구간 변경 후: `invalidateIncomeBracketData(queryClient)` — tax-action-plan + settings + action-items 무효화.
- 적립 챌린지 CUD 후: `invalidateChallengeData(queryClient)` — challenges(+summary 프리픽스) + dashboard 무효화.
- 적립 챌린지 알림 설정 변경 후: `invalidateChallengeRemindersData(queryClient)` — settings 무효화.
- 환율 알림 CUD 후: `invalidateAlertData(queryClient)` — exchange-rate-alerts 무효화.
- 리밸런싱 알림 CUD 후: `invalidateRebalancingAlertData(queryClient, portfolioId)` — rebalancing-alerts + rebalancing-alert(portfolioId) 무효화.
- 배당 목표 변경 후: `invalidateDcaData` + `invalidateGoalRecommendationData` — `PUT /settings/goal`은 대시보드·DCA·챌린지·추천 캐시를 함께 지운다(배당 계획만 무효화하면 홈 목표 카드가 stale).
- 주가 알림 CUD 후: `invalidateStockPriceAlertData(queryClient)`.
- 리밸런싱 주문 실행 후: `invalidateRebalancingHistoryData(queryClient)`.
- 리밸런싱 대기 플랜 취소/승인 후: `invalidateRebalancingPlanData(queryClient, { executed })` — 대기 플랜 목록 + 실행 이력 무효화. 승인은 즉시 체결하므로 응답 `status === "EXECUTED"`면 `executed: true`로 넘겨 `invalidateSyncData`(보유·드리프트·지금 할 일)까지 갱신.
- 복합신호(시장/리스크) 알림 설정 변경 후: `invalidateCompositeSignalData(queryClient)`.
- 시장신호 매일 요약 알림 설정 변경 후: `invalidateMarketSignalDigestData(queryClient)`.
- 연말 절세 리마인더 설정 변경 후: `invalidateYearEndTaxReminderData(queryClient)`.
- 목표 달성 알림 설정 변경 후: `invalidateGoalAchievementAlertsData(queryClient)`.
- 월간 리포트 설정 변경 후: `invalidateMonthlyReportAlertsData(queryClient)`.
- 추천 비중 변화 알림 설정 변경 후: `invalidateRecommendationDriftAlertData(queryClient)`.
- 목표 역산 추천 후보 변경 후: `invalidateGoalRecommendationData(queryClient)`.
- 다른 화면에 영향 없는 설정 저장 후(또는 백엔드가 설정을 바꿨을 수 있을 때): `invalidateSettingsData(queryClient)` — settings만 재조회. 위의 알림 토글별 함수들(몸체 동일)은 plans/52 D(`PATCH /settings`)에서 이것으로 합친다.
- 당겨서 새로고침처럼 화면 자신의 쿼리 하나만 다시 받을 때는 그 `useQuery`의 `refetch`를 쓴다.
- 수동으로 `invalidateQueries` 여러 번 호출하지 말고 이 함수 사용.

> **새 invalidation 함수 추가 시:** 이 파일에 `invalidate<Domain>Data(queryClient)` 형태로 추가하고, 관련 mutation의 `onSuccess`에서 호출. 컴포넌트·훅 내부에서 직접 `queryClient.invalidateQueries()` 호출 금지.

**쿼리 설정 상수 (`src/constants/queryConfig.ts`)**

- `STALE_TIME.NONE` (0, 열 때마다 최신), `STALE_TIME.VERY_SHORT` (15s), `STALE_TIME.SHORT` (30s, 기본값), `STALE_TIME.MEDIUM` (60s), `STALE_TIME.FIVE_MINUTES`·`STALE_TIME.EXCHANGE_RATE` (5m), `STALE_TIME.LONG` (1h), `STALE_TIME.DAY` (24h — 영속 캐시 maxAge와 같음, 무거운 계산 결과의 `gcTime`용: 목표 역산 전체 추천)
- `REFETCH_INTERVAL.DASHBOARD` (5분), `REFETCH_INTERVAL.PORTFOLIO` (5분)
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
