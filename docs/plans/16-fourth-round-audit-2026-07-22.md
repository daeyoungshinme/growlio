# 계획 16: 4차 재감사 — 잔여 백로그 실행 + 신규 관점(성능/접근성/경쟁기능격차) (2026-07-22)

## 배경 (Why)

같은 취지("불필요 기능 제거·병합 + 모바일 탭 UX 개선 + 고도화 로드맵")의 전체 감사가 이미 4차례(07-06, 07-19, 07-20×2, 07-21) 수행되어 `docs/plans/01~15`가 대부분 완료 처리됐다. 사용자가 2026-07-22에 5번째로 동일 요청을 해, `AskUserQuestion`으로 방향을 확인한 결과 "계획 15 잔여 백로그 실행" + "지금까지 안 쓴 3개 새 축(성능/로딩, 접근성, 경쟁앱 대비 기능격차)으로 재조사" 둘 다 진행하기로 확정했다.

## A. 계획 15 잔여 백로그 (구현 완료)

코드 재검증 결과 5·6번(월간리포트 옵트아웃 토글, MONTHLY_REPORT 라벨)은 이미 동시 세션이 완료해뒀음을 확인(`useMonthlyReportAlertsToggle.ts`, `SettingsPage.tsx:89`). 8~12번 중 11번을 제외한 4건을 이번 세션에서 구현했다.

- **A5(8)**: `StockAccountModal.tsx` — 세제유형/투자기간 필드를 `CollapsibleSection`(신규 계좌는 기본 접힘, 수정 모드는 기본 펼침)으로 이동.
- **A7(9)**: `UnifiedPortfolioEditor.tsx` — 투자기간/세제유형 태그 선택을 `CollapsibleSection`으로 이동(수정 모드거나 `initialAccountIds`로 프리필된 경우엔 기본 펼침, 완전 신규 생성은 기본 접힘).
- **A6(10)**: `DashboardPage.tsx` — 목표(자산/입금/배당) 미설정 + 포트폴리오 0개인 "완전 신규" 유저는 `AllocationHistoryChart`(자산 추이, 데이터 없어 의미 없음)를 렌더하지 않도록 조건 추가. 목표나 포트폴리오를 하나라도 설정하면 다음 방문부터 노출.
- **B5(12)**: `TaxOptimizationCard.tsx` — 해외 미실현 손실(`overseas_unrealized_gain_krw < 0`)이 있으면 절세 플래너를 기본 펼침 + "손실수확 가능" 배지 노출. 사용자가 명시적으로 토글하면 그 이후엔 사용자 선택이 우선.
- **B4(11)**: `market_signal_alert_service.py`의 구독조건(활성 RebalancingAlert 필요)은 **범위 밖 유지** — 신규 구독 모델 도입은 스키마 변경이 필요한 중간 리스크 항목이라 별도 논의 필요, 여전히 유효한 발견으로 기록.

## B. 성능/로딩 축 (신규 조사, Explore 에이전트)

프론트+백엔드 전체를 조사한 결과, 라우트 단위 lazy-load, 차트별 lazy-load, `vite.config.ts`의 `manualChunks`, 모바일 리스트 가상화(`@tanstack/react-virtual`), 배치 가격조회, 네이티브 폴링 차단이 이미 잘 되어 있어 실질적 이슈는 1건뿐이었다.

- **실행 완료**: `TransactionList.tsx`(계좌관리 › 입출금·배당 모달의 거래내역 리스트)가 형제 컴포넌트 `TransactionHistoryTab.tsx`와 달리 무제한/미가상화 렌더였음 — 동일한 `useVirtualizer` 패딩-행 패턴을 데스크탑 테이블에 적용(`maxHeight: 480px` + `overscan: 10`). 모바일 카드뷰는 sibling 컴포넌트와 동일하게 미가상화 유지(계좌당 거래 건수가 보통 적어 낮은 우선순위).
- **조치 없음(이미 양호)**: 나머지 15건 — 라우트 lazy-load 전부 정상, 대시보드/자산관리 훅의 쿼리가 진짜 병렬(waterfall 없음), 5분/1분 refetch 간격이 배터리 친화적이고 네이티브에선 폴링 비활성화됨, `StockHoldingsTable`/`RebalancingHistoryTab`은 이미 가상화 또는 백엔드 페이지네이션으로 바운드됨, lucide-react 아이콘 import 전부 tree-shakeable, 백엔드 `/dashboard`·`/portfolio/overview` 응답 페이로드 적정 크기, N+1 없음. `useRealtimePrice.ts`(WebSocket)는 구현은 완비되어 있으나 현재 호출부가 전혀 없는 미사용 인프라(정보성, 조치 불필요 — 향후 실시간 가격 화면을 추가할 때 참고).

## C. 접근성 축 (신규 조사, Explore 에이전트)

터치타겟(기존에 이미 처리됨)과는 별개로 6건의 실질적 갭을 발견, 5건을 구현했다.

- **실행 완료 — 토스트 `aria-live`**: `Toaster.tsx` — 에러 토스트는 `role="alert" aria-live="assertive"`, 나머지는 `role="status" aria-live="polite"`.
- **실행 완료 — 스켈레톤 `aria-busy`**: `SkeletonCard.tsx`/`SkeletonTable.tsx`에 `role="status" aria-label="로딩 중" aria-busy="true"` 추가(`PageLoader.tsx`와 동일 패턴). `SkeletonStatBox`는 같은 그리드에 4개가 반복 렌더되므로 컴포넌트 자체가 아니라 감싸는 그리드(`HeroSummaryCard.tsx`, `PortfolioPage.tsx`)에 단일 `role="status"`를 부여해 중복 안내를 피함.
- **실행 완료 — 모달 접근성 버그**: `UnifiedPortfolioEditor.tsx`가 다른 17개 모달과 달리 `useModalBehavior`를 쓰지 않아 포커스트랩·Escape·복귀포커스·`role="dialog"`가 전혀 없던 실제 버그를 수정 — 훅 배선 + `role="dialog" aria-modal="true" aria-labelledby`.
- **실행 완료 — 폼 에러 연결**: `FormInput.tsx`의 `error`/`hint` 텍스트에 `id` 부여 후 인풋에 `aria-describedby`로 연결, `error` 존재 시 `aria-invalid="true"`. 공용 컴포넌트라 전 앱 폼에 일괄 적용됨.
- **실행 완료 — 다크모드 저대비 배지**: `dividendUtils.ts`의 `yieldBadgeClass`/`dividendFreqInfo` 최하위 티어 다크모드 텍스트를 `dark:text-gray-400`/`dark:text-gray-500` → `dark:text-gray-300`로 한 단계 밝게(라이트모드는 변경 없음).
- **범위 조정 — 헤딩 구조**: 인증 후 화면에 `<h1>`이 전무했던 문제. 전체 카드 제목(`<span>/<p>` → `<h2>/<h3>`) 일괄 교정은 수십 개 컴포넌트에 걸쳐 범위가 커 이번엔 보류하고, 대신 (a) 5개 메인 페이지(`DashboardPage`/`AssetsPage`/`RebalancingPage`/`InvestPlanPage`/`SettingsPage`) 최상단에 `<h1 className="sr-only">{페이지명}</h1>` 추가, (b) `frontend/CLAUDE.md`에 헤딩 규칙 신규 추가해 향후 신규/수정 컴포넌트부터 점진적으로 `<h2>/<h3>` 사용을 유도.
- **확인 결과 문제 없음**: P&L 색상은 항상 `+`/`-` 기호·%·₩ 텍스트와 함께 쓰여 색상 단독 의존 없음. 샘플 확인한 아이콘 전용 버튼은 전부 `aria-label` 보유. `useModalBehavior` 자체(초기 포커스, 복귀 포커스)는 정확히 동작 확인.

## D. 경쟁앱 대비 기능격차 (로드맵 전용, 이번 세션 미구현)

코드 조사가 아니라 도메인 지식 + 웹검색(로보어드바이저 비교, 토스증권 자동매수 기능) 기반. `docs/plans/README.md`에 로드맵으로만 기록.

| 항목 | 근거 | 왜 지금 안 하는가 |
|---|---|---|
| 정기 자동매수("주식 모으기"류) — 드리프트 무관, 스케줄+금액 고정 자동매수 | 토스증권 대표 기능. Growlio는 DCA *분석*(`dca_service.py`)만 있고 AUTO 실행은 전부 리밸런싱 드리프트 트리거(`order_builder.py`/`plan_service.py`) | 실제 자금 이동 신규 기능(기존 AUTO 파이프라인과 다른 트리거 모델 신설) — [[project_feature_audit_2026-07-06]]의 AUTO 게이트 신중론과 동일한 이유로 별도 논의 필요 |
| ETF 총비용(TER: 운용보수+환전+출금 수수료) 투명성 | 핀트/에임 등 로보어드바이저가 차별점으로 강조. Growlio 데이터 모델엔 expense ratio 필드 자체가 없음 | 데이터 소스 확보(ETF 운용보수 공시 연동)부터 필요한 리서치성 과제 |

## 검증

- 프론트: `npm run typecheck && npm run lint && npm run test` 전체 통과
- 백엔드: 코드 변경 없음(11번 보류) — 회귀 확인용으로 `uv run pytest` 1회 실행
- 수동 확인(자동테스트 미커버): `UnifiedPortfolioEditor` 모달 Tab/Escape/포커스 복귀 — 브라우저 실사용 검증은 로그인 세션 제약으로 제한적일 수 있음
