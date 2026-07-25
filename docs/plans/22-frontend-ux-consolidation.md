# 프론트엔드 UX 통합 과제 (2026-07-25 전면 재감사)

## 배경

2026-07-25, 사용자가 "모바일 자산관리 앱 핵심 요구사항 대비 구현 검토 + 탭별 UI/UX 문제 + 불필요/중복 기능 정리 + 고도화 계획"을 요청하며 기존 `docs/plans/README.md`(21개 항목, 대부분 완료)를 참조하지 않고 처음부터 전면 재감사를 선택했다. 프론트엔드 UX·백엔드 기능완결성·죽은코드/중복 3개 관점의 독립 조사 결과, 요청한 핵심 기능(모니터링/목표설정/기간·계좌특성별 추천/절세계획/시장모니터링+드리프트신호/알림/수동·자동실행)은 전부 구현되어 있었다. 그중 안전한 죽은 코드 5건과 버그·일관성 문제 6건은 같은 세션에 즉시 정리했다(`docs/plans/README.md` 상태표 참고). 아래 항목들은 설계 판단이 필요해 코드는 건드리지 않고 문서로만 남긴다.

## 항목

### 1. 세금정보 3곳 분산
- **현재 상태**: Home(`InvestmentSnapshotCard`의 4번째 서브섹션 `TaxLimitsBanner`) / 자산탭→투자현황→세금 서브탭(`TaxLimitsSection`이 `IsaMaturityCard`+`PensionContributionCard`를 기본 접힘으로 감쌈, 그 옆에 `TaxOptimizationCard`가 내부에 "절세 플래너"·"금투세 시뮬레이션" 2개 접힘 패널을 또 가짐) / 자산탭→계좌관리 "전체 자산 구성" 카드(주식/현금/부동산 비중 — 위 두 곳과는 다른 분류체계).
- **문제**: 코드 레벨 중복은 없음(`useTaxLimitsSummary` 훅을 여러 곳이 공유해 API 콜 중복 없이 구현됨) — 문제는 UX 레벨: 사용자가 "내 세금 현황이 정확히 어디에 있는지" 헷갈릴 수 있는 3중 진입점.
- **제안**: Home 배너는 유지(딥링크 진입점으로서 역할 명확), 자산탭 세금 서브탭 내부의 `TaxLimitsSection`과 `TaxOptimizationCard`를 하나의 상위 컨테이너로 묶어 "한도 현황"/"세금 추정" 2탭 정도로 재편하면 3곳→2곳으로 줄어들고 내부 이중 접힘도 해소됨. 계좌관리의 "전체 자산 구성"은 세금과 무관한 자산배분 요약이므로 그대로 유지.

### 2. 설정탭 알림토글 9개 난립
- **현재 상태**: `SettingsPage.tsx`에 `useGoalAchievementAlertsToggle`/`useMonthlyReportAlertsToggle`/`useYearEndTaxReminderToggle`/`useRecommendationDriftAlertToggle`/`useCompositeSignalToggle`/`useMarketSignalDigestToggle` 등 6개 토글 훅 + 환율/주가/리밸런싱 알림 CRUD 3종이 3개의 `CollapsibleCard`("정기 리포트·리마인더"/"목표·추천 변화 감지"/"시장 모니터링")로 그룹핑되어 있음(`useSettingsToggle` 팩토리로 훅 자체는 이미 통합됨).
- **문제**: 전부 정상 연결되어 있어 죽은 기능은 없지만, 한 페이지에 3중 중첩 콜랩스+9개 토글이 몰려 있어 이 페이지가 앱에서 가장 밀도 높은 화면.
- **제안**: 별도 하위 라우트(`/settings/notifications`)로 분리하거나, 최소한 카테고리를 사용자가 실제로 신경 쓰는 빈도 기준(예: "즉시 알림" vs "정기 요약")으로 재편.

### 3. `RecommendationCard.tsx` 984줄 — 3중 중복 JSX
- **현재 상태**: 전체/연령대/기간별 3개 탭 각각에서 목표 비중 리스트+드리프트 배지+후보 제안+적용/생성 버튼을 그리는 ~120줄 JSX 블록이 거의 그대로 3번 반복(대략 456-595행/596-748행/749-885행).
- **제안**: 공용 서브컴포넌트(`RecommendationResultBlock` 등)로 추출해 props로 데이터만 주입. 비중 표시가 현재 순수 `<ul>` 텍스트 목록인데, 서브컴포넌트 추출 시 막대 그래프 등 시각화를 곁들이면 가독성도 함께 개선 가능(모바일 카드인데 텍스트 밀도가 가장 높은 화면).

### 4. `StockAccountCard.tsx` 아이콘 전용 액션 5개 클러스터
- **현재 상태**: 수정/동기화/종목관리/입출금/삭제 5개 아이콘 버튼이 카드 헤더에 `flex flex-wrap`으로 배치, 각각 44px 터치타겟 + `title`/`aria-label`만 있고 시각적 텍스트 라벨 없음.
- **문제**: 모바일에서는 `title` 툴팁이 뜨지 않아 아이콘 모양만으로 기능을 구분해야 함 — 앱에서 가장 밀집된 아이콘 클러스터.
- **제안**: 3개 이하 주요 액션만 아이콘으로 노출하고 나머지는 `⋯` 오버플로우 메뉴로 이동, 또는 좁은 화면에서 2줄로 자연스럽게 wrap되도록 유지하되 라벨을 아이콘 아래 6px 텍스트로 보강.

### 5. 콜랩스 기본 열림/닫힘 상태 일관성 없음
- **현재 상태**: `RebalancingStatusCard`/`InvestmentSnapshotCard`는 `useCollapsible`로 localStorage 영속화되며 기본 열림, `TaxLimitsSection`은 기본 닫힘(영속화 있음), `HeroSummaryCard`/`InvestmentGoalCard`는 아예 콜랩스 불가.
- **제안**: "정보 밀도가 낮은 카드는 항상 펼침, 밀도가 높은 카드는 접기 가능 + 기본값은 최초 방문 시 열림"처럼 명시적 규칙을 `frontend/CLAUDE.md`에 문서화하고 신규/기존 카드에 일괄 적용.

### 6. AUTO 실행 집계 한도 부재 (백엔드)
- **현재 상태**: 주문 1건당 상한(`auto_rebalancing_max_order_value_krw`, 기본 5천만원)과 알림 1개당 하루 1회 트리거 제한은 있음(`order_builder.py`/`plan_service.py`).
- **문제**: PER_ACCOUNT 스코프로 여러 알림이 동시에 AUTO 설정된 경우, 포트폴리오·계좌 전체를 합산한 하루 총 거래대금 상한이 없음 — 여러 계좌가 같은 날 동시에 최대치로 트리거되면 개별 한도는 지켜지지만 합산 금액은 예측 밖으로 커질 수 있음.
- **제안**: 의도된 설계인지(사용자가 계좌별로 독립 설정했으니 합산 제한이 오히려 의도를 왜곡한다는 관점도 가능) 먼저 확인 후, 필요하면 유저 단위 일일 합산 한도를 `UserSettings`에 추가.

### 7. `quick_execute_rebalancing` 네이밍 오해 소지 (백엔드)
- **현재 상태**: `api/v1/rebalancing_execution.py`의 `quick_execute_rebalancing`은 이름과 달리 즉시 실행이 아니라 AUTO와 동일한 대기 플랜을 생성함(매수는 대기 후 자동 실행, 매도는 이메일 승인).
- **제안**: 함수/엔드포인트명을 `create_execution_plan` 등으로 변경하거나, 최소한 docstring/OpenAPI summary에 "즉시 체결 아님"을 명확히 표기.

### 8. 경쟁앱 대비 기능격차 (기존 로드맵, 재확인만)
- 정기 자동매수(DCA 실매매), ETF TER(총보수) 투명성 — `docs/plans/16-fourth-round-audit-2026-07-22.md` D절에서 이미 로드맵으로 기록됨, 이번 재감사에서도 여전히 코드 미착수 확인.

### 9. 시장신호 방법론 Phase 2/3 (기존 `docs/plans/21`, 재확인만)
- AUTO 게이트 raw score 반영(Phase 2), 국내 리스크 지표 리서치(Phase 3, V-KOSPI200/신용스프레드/외국인 순매수) — 여전히 계획만 존재, 이번 세션에서 인플레이션·고용 신호가 추가되며 8종·상한 27점으로 바뀐 것과는 별개(그건 이미 반영됨).

## 상태
- **1~7번 구현 완료 (2026-07-25, 별도 세션)** — 상세 구현 내역은 `docs/plans/README.md`의 22번 행 참고. 8·9번(경쟁앱 기능격차, 시장신호 방법론 Phase 2/3)은 로드맵으로 계속 유지, 착수 없음.
