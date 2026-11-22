# 계획 143 — 계획탭(/invest-plan) 전체 감사·고도화 (2026-11-22)

> 상태: PR1(A·E4)·PR2(B·C·D) 구현 완료, PR3(E1~E3) 남음. 착수 전 `git status`로 다른 세션 변경을 확인하고, 아래 파일:라인이 현재 코드와 다르면 코드를 우선한다.

## Context
계획탭(적립 계획·배당 계획·절세·챌린지)은 계획 8(2026-07) 이후로 탭 단위 감사를 받은 적이 없다. 그사이 50·67·106·110·113·139에서 부분 수정만 쌓였다. 이번 조사에서 확인한 문제는 세 종류다.
1. 계산이 틀리는 실버그: 배당수익률 단위, 해외 매도 마감일, ISA 절세액, 챌린지 마감월
2. 같은 탭 안에서 같은 정보가 여러 번 나오고, 오류·로딩 처리가 화면마다 다름
3. 계획 8에서 남은 고도화 아이디어(시나리오 비교, 배당 세후 표시 등)

**다시 손대지 않을 것**(사용자 결정):
- 세금은 계획 › 절세에 둔다.
- 챌린지는 생성할 때 기본값만 채운다(실시간 연동 안 함).
- 배당 계획의 추천은 이름 요약과 링크만 둔다.
- 대주주 50억, 금투세 삭제.
- 삭제한 계좌의 연금·실현손익은 세금 집계에 포함한다(110 B3).
- 스트릭·연도별 배당 목록·건보 카드는 한도 현황에 그대로 둔다(67).

---

## A. 실버그 (먼저, 테스트 동반)

**A1 yfinance forward 배당수익률 단위** — `backend/app/services/dividend/sync_sources.py:83-91`
- 문제: 최신 yfinance는 `dividendYield`(forward)를 퍼센트로 주는데 `trailingAnnualDividendYield`는 소수다. 지금 코드는 `>0.3`일 때만 100으로 나누므로, TTM이 없고 수익률이 0.3% 미만인 종목은 25배 이상 부풀려진다.
- 수정: forward 값은 항상 `/100`으로 정규화한다. trailing 값에만 기존 0.3 휴리스틱을 남긴다.
- 테스트: `test_dividend_sync_sources.py`에 forward 0.25(=0.25%) 사례를 추가한다. 착수 전에 `uv.lock`의 yfinance 버전에서 실제 단위를 확인한다.

**A2 해외 매도 마감일** — `backend/app/services/tax/tax_action_builders.py:165`
- 문제: 12/31이 월요일인 해(2029)에는 마감일이 12/31로 나와 다음 해 귀속이 된다. 연말 휴장도 무시한다.
- 수정: 12/31에서 거꾸로 세어 KR·US 공통 영업일 기준 "마지막 거래일 − 결제일수(T+1, 보수적으로 −2영업일)"로 계산한다. 계획 122에서 도입한 `holidays` 기반 휴장일 유틸을 재사용한다(`grep -rn "holidays" backend/app/core`로 위치 확인).
- 테스트: 2026·2029·2035 경계 케이스.

**A3 ISA 절세액: 국내 상장 해외 ETF** — `backend/app/services/tax/isa_service.py:110, 181-184`
- 문제: KOSPI 시장 코드의 해외지수 ETF 평가이익을 "국내 = 일반계좌 비과세"로 처리해 절세액을 과소 추정한다. 실제로는 매도 시 배당소득 15.4% 과세 대상이다.
- 수정: ETF 판별과 기초자산 해외 여부 판별에 기존 `etf/etf_profile_service`와 지수 그룹 매핑(계획 74·76)을 재사용한다. 해외 ETF 평가이익은 `rates["dividend"]`로 과세한다.
- 문제: 해외 250만 공제를 계좌마다 빼고 있다. 수정: 인당 1회 공제로 바꾸고, 표시 문구로 근사치임을 밝힌다.

**A4 챌린지 `deadline_month` 미사용** — `backend/app/services/challenge_service.py`
- 문제: 마감월이 저장만 되고 진행률·실패 판정에 쓰이지 않는다.
- 수정: 마감월이 지나면 스트릭 계산을 거기서 멈추고, 미달이면 `FAILED`(또는 만료) 상태를 낸다.
- 프론트: `ChallengeCard`에 남은 개월 수와 만료 배지를 표시한다. 상태 enum이 바뀌면 마이그레이션이 필요한지 확인한다. 가능하면 응답 필드 계산만으로 처리해 스키마는 바꾸지 않는다.

**A5 캐시 연도 경계**
- `dividend_summary` 캐시 키에 연도를 추가한다(`backend/app/core/` 또는 `app/services/cache_keys` 위치 확인). 거래 변경 시 올해만 무효화하던 것을 영향받는 거래 연도로 바꾼다(`api/v1/transactions.py:160` 부근).
- 챌린지 캐시 키에 현재 KST 월을 포함한다.

**A6 DCA 실적 0원 달성률 None** — `backend/app/services/dca_service.py:225`
- 문제: `if actual and` 조건이라 실적 0원이 None이 된다. 수정: `is not None`으로 바꾼다.
- 시작 금액이 "첫 스냅샷 날짜의 일부 계좌 합"으로 과소 추정되는 문제: 계좌별로 시작일 이후 첫 스냅샷을 합산하도록 바꾼다(월별 집계 :169-205와 같은 방식).

**A7 (확인 후 처리)**
- 세금 소득 집계에 모의투자 계좌의 배당·이자가 섞이는지 `tax_service.py:238, 349`에서 확인한다.
- 배당 계획 필요 수익률 분모(`dividend/plan_service.py:51-55`의 `build_portfolio_overview`)에 부동산이 들어가는지 확인한다.
- 실버그로 확인되면 수정하고, 아니면 계획서에 근거를 기록한다.

## B. 중복 정보·UX 정리 (프론트)

- **B1** 건보 피부양자 경고 중복을 정리한다. 세금 추정의 `FinancialIncomeThresholdNotice`(`components/portfolio-analysis/TaxOptimizationCard.tsx:214-269`)는 한 줄 + "한도 현황에서 보기" 링크로 줄인다. 카드 본체는 한도 현황에 그대로 둔다.
- **B2** 적립 계획 탭에 WAITING_FX 안내가 두 번 나온다. `AutoInvestStatusBanner.tsx:144-151`을 남기고, `FxPlanCard.tsx:390-403`은 개수 배지만 둔다.
- **B3** "더 빨리 달성하려면?" 블록(`GoalTimelineCard.tsx:135-243`, `DividendPlanSection.tsx:261-314`)을 공용 컴포넌트 `FasterGoalHint`로 뽑는다. 배당 탭에서 두 번 나오는 필요 배당수익률은 한 번만 보여 준다.
- **B4** `FxPlanCard.tsx:336` 1/3/6개월 선택의 pill `Tabs`를 `SegmentedControl`로 바꾼다(탭 계층 규칙).
- **B5** 목표 마법사 자동 오픈(`hooks/useGoalSettings.ts:139-154`)을 `적립 계획` 탭에서만 띄운다. 훅에 `activeTab` 인자 또는 `autoOpen` 플래그를 넘긴다. 다른 탭으로 딥링크해 들어왔을 때 `dca-analysis` 조회도 지연시킬 수 있는지 검토한다(`pages/InvestPlanPage.tsx:110-129`).
- **B6** 환전 계획 카드의 텍스트를 줄인다(`FxPlanCard.tsx:346-386`). 산식과 계좌별 보유 달러 목록을 "계산 근거" 접힘으로 옮긴다.

## C. 로딩·오류·요청 효율

- **C1** 재시도 버튼이 없는 세 곳(`DividendPlanSection.tsx:59-65`, `ChallengeSection.tsx:68-75`, `FxPlanCard.tsx:244-250`)에 `PageLoadError`(또는 EmptyState+refetch)를 통일해 적용한다.
- **C2** 인라인 로딩 표시를 `SkeletonCard`로 바꾼다: `TaxOptimizationCard.tsx:100,186`, `TaxActionPlanCard.tsx:146-155`. `TaxLimitsSection`의 ISA·연금 카드에 스켈레톤을 넣어 레이아웃 밀림을 막는다.
- **C3** 설정 편집 모달을 열 때 `fetchSettings()`를 다시 부르지 않게 한다(`useGoalSettings.ts:84,202`, `useDividendPlanSettings.ts:36`). `queryClient.ensureQueryData(settingsQuery)`로 캐시를 우선 쓴다.
- **C4** 연금 카드의 직렬 조회(`PensionContributionCard.tsx:29-34`)를 없앤다. 백엔드 `/tax/pension-contribution`이 overview 값을 직접 계산할 수 있으면 프론트 의존을 제거한다. 그렇지 않으면 overview-lite를 페이지 레벨에서 prefetch한다.
- **C5** 인라인 쿼리 정의를 `queryOptions.ts`로 옮긴다(TaxOptimizationCard·PensionContributionCard·TaxActionPlanCard).
- **C6** `DCAProjectionChart.tsx:31-34`의 직접 `matchMedia` 호출을 `useIsSmUp`으로 바꾼다.

## D. 구조 정리

- **D1** 배당 설정 모달 인라인 JSX(`InvestPlanPage.tsx:376-412`)를 `DividendSettingsModal`로 분리한다. `<form id>`+`form=` 패턴을 적용한다(`FxExtraNeedModal` 참고). 결과적으로 InvestPlanPage가 400줄 아래로 내려간다.
- **D2** 탭 본문을 `InvestPlanDcaTab` 등 탭별 컴포넌트로 분리한다(D1과 함께, 필요할 때만).
- **D3** 홈의 `to="/invest-plan"` 하드코딩 4곳(`InvestmentGoalCard.tsx:28`, `DcaOutlook.tsx:124`, `goalChips.tsx:162,232`)을 `investPlanUrl()` 빌더로 바꾼다.
- **D4** `tax_action_builders.py`(501줄)는 A2 수정 때 마감일·영업일 헬퍼를 분리해 500줄 아래로 낮춘다.
- **D5** `list_challenges_with_progress`의 챌린지별 SQL(N+1)을 입금 챌린지끼리 계좌별 월 순입금 1회 조회로 묶는다(`challenge_service.py:241`).

## E. 고도화 (계획 8 확장 아이디어, 사용자가 E1~E3 전부 선택)

- **E1** 적립 계획 시나리오 비교: 보수·중립·공격 수익률(예: 기대수익률 −2%p / 기준 / +2%p) 토글을 둔다. `DCAProjectionChart`에 3선 또는 SegmentedControl을 쓴다. 계산은 이미 통합된 미래가치 공식(계획 113 C4, `goal_return_solver.py:32-50`)을 재사용한다.
- **E2** 배당 계획 세후 표시: 예상 연·월배당을 세전과 세후로 나눠 보여 준다(국내 15.4%, 해외 15% 원천징수, ISA·연금 계좌는 과세이연·비과세). 계좌 유형은 기존 tax 계좌 분류를 재사용한다. 스키마 변경은 없다.
- **E3** 배당 목표 달성 예상 시점 타임라인(계획 8): 적립 계획의 `GoalTimelineCard` 패턴을 따른다. 월 적립 + 현재 수익률 + 배당 재투자 가정으로 연배당 목표 도달 시점을 계산한다.
- **E4** 문서: `docs/remaining-tasks.md:59` P4 "대주주 50억·금투세" 줄을 삭제한다(110에서 이미 완료).

(보류 유지: 기간별 목표 금액(50 E4, 스키마 변경), 2027 세율 표 추가(입법 확인 대기). 대신 A2와 함께 `pick_year_rule` 폴백이 일어나면 경고 로그를 남기는 정도만 한다.)

---

## 배치·PR
- PR1: A1~A7 + E4 (백엔드 실버그, 테스트)
- PR2: B·C·D (프론트 정리, D4·D5 포함)
- PR3: E1~E3 (고도화)

각 PR마다 계획서 상태와 README 행을 갱신하고, 파일을 추가하거나 옮기면 backend·frontend CLAUDE.md 목록도 갱신한다.

## 검증
- 백엔드: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pytest`. 최종 확인은 커버리지 91% 게이트(`pytest --cov`). 신규 테스트는 A1 단위, A2 연도 경계, A3 ISA 해외 ETF, A4 마감월, A5 캐시 키 연도, A6 0원.
- 프론트: `D:\project\growlio\frontend`(대문자 드라이브)에서 `npm run lint -- --max-warnings 0 && npm run format:check && npm run typecheck && npm run test`. B5 마법사 탭 조건, C1 재시도, B3 공용 컴포넌트 테스트를 추가한다.
- 수동: `bash dev.sh`로 띄운 뒤 390px 뷰포트에서 4개 탭, `?tab=절세` 딥링크(미설정 계정에서 마법사가 뜨지 않는지), 환전 계획 펼침, 챌린지 마감월을 확인한다.
- 스키마를 바꾸지 않는 것이 목표다. 바뀌면 `uv run alembic check`를 돌리고, 운영 DB 마이그레이션을 수동으로 적용해야 한다고 명시한다.

---

## PR1 결과 (2026-11-22)

- **A1** forward `dividendYield`는 항상 /100, 0.3 휴리스틱은 trailing에만. yfinance 0.2.66.
- **A2** 마감일 = 12월 마지막 NYSE 거래일에서 2거래일 전(`market_hours.us_year_end_trade_deadline`). 2024·2025 증권사 공지일(12/27·12/29)과 일치, 2029·2035(12/31 월요일)도 연내. 액션 문구에 실제 날짜 표시.
- **A3** 국내상장 해외지수·채권·원자재 ETF 평가이익을 일반계좌 세금(배당소득 15.4%)에 넣음(`isa_service.is_taxable_domestic_listed_etf` — `etf_index_classifier` 재사용, 판별 불가는 기존처럼 비과세). 250만 공제 인당 1회 항목은 **하지 않음** — ISA는 1인 1계좌라 계좌별 차감이 곧 인당 차감.
- **A4** `deadline_month`: 스트릭·월 그리드를 마감월까지만, 응답에 `is_expired`·`months_left`(표시 전용, status·스키마 불변). 마감 지난 챌린지는 독려·결산·네비 배지에서 제외(`challenge_service.not_expired_clause`). 카드에 "N개월 남음"/"기한 종료".
- **A5** `dividend_summary_key`에 연도, `challenge_progress_key`에 KST 월. 거래 CUD는 올해 + 거래 연도(수정은 옛·새) 배당 캐시 무효화.
- **A6** 실적 0원 → 달성률 0%. 시작 금액은 계좌별(시작 후 31일 내 첫 스냅샷, 없으면 시작 전 마지막) 합산, 없으면 기존 방식. 실 DB 테스트(`TestDcaInitialValue`)는 CI에서만 돈다.
- **A7** 배당 계획 필요 배당수익률 분모에 부동산이 들어가던 실버그 → 추천과 같은 `investable_assets_krw`. 모의 계좌 배당·이자: 브로커 동기화가 거래내역을 만들지 않아 사용자가 직접 넣은 경우만 해당 → 변경 안 함.
- **E4** remaining-tasks P4 "대주주 50억·금투세" 줄 삭제.
- 미반영: D4 `tax_action_builders.py` 504줄(PR2에서 분리).

## PR2 결과 (2026-11-22)

- **B1** 세금 추정의 금융소득 경고에서 건보 상세(예상 보험료·안내)를 빼고 한 줄 + "한도 현황에서 보기" 링크.
- **B4** 환전 계획 1/3/6개월을 pill `Tabs` → `SegmentedControl`(탭 계층 규칙).
- **B5** 목표 마법사 자동 오픈은 적립 계획 탭에서만(`useGoalSettings({ autoOpenWizard })`) — 다른 탭으로 딥링크하면 본 것으로 기록하지도 않는다.
- **B6** 환전 계획: "N개월 적립에 $X 필요 · 보유 $Y (기준 시각)" 한 줄만 보이고 산식·계좌별 보유 달러는 "계산 근거" 접힘(`growlio:fxPlan:basisOpen`).
- **C1** 배당 계획·챌린지·환전 계획 조회 실패에 "다시 시도".
- **C2** 세금 추정 "계산 중..."·플래너 "불러오는 중..." → `SkeletonCard`, 한도 현황 ISA·연금 자리 스켈레톤.
- **C3** 목표·배당 설정 모달은 `queryClient.fetchQuery(settingsQuery)`(캐시 우선). 마법사 저장 직전 최신값 조회(`fetchSettings`)는 의도라 유지.
- **C6** `DCAProjectionChart` 직접 `matchMedia` → `useIsSmUp`.
- **D1** 배당 설정 모달을 `DividendSettingsModal`로 분리(`<form id>` + `form=`, Enter 저장). `InvestPlanPage` 429 → 399줄.
- **D3** 홈 `/invest-plan` 하드코딩 5곳 → `investPlanUrl("적립 계획")`.
- **D4** `tax_action_builders.py` 504 → 362줄, 해외 이익실현·손실수확·마감일은 `tax_action_overseas.py`.
- **D5** 챌린지 목록: 입금 챌린지를 계좌별로 가장 이른 시작월부터 한 번만 조회(`compute_progress(monthly_net=)`).
- **하지 않음**
  - B2: 배너(항상 보임, 알림)와 접힌 환전 카드(환전할 금액 제공)는 역할이 달라 유지.
  - B3: 두 "더 빨리 달성하려면?"은 비교 지표(수익률/배당수익률)가 달라 공용화 이득이 작다. 배당 쪽은 67 P1-13에서 이미 한 줄 비교.
  - C4: 연금 카드가 기다리는 overview-lite는 홈·부팅 프리페치로 대부분 캐시됨.
  - C5: 인라인 쿼리 3곳은 한 화면 전용이라 CLAUDE.md 규칙(공용 쿼리만 `queryOptions`) 대상 아님.
  - D2: D1로 400줄 아래가 돼 탭 본문 분리는 보류.
  - `TaxActionPlanCard` 로딩 pulse는 헤더가 있는 섹션 안이라 `SkeletonCard`(카드 안 카드) 대신 유지.
- PR3 참고: `DCAProjectionChart`에 이미 보수/공격 수익률 시나리오 토글(`showScenarios`, `SAVINGS_RETURN_PRESETS`)이 있다 — E1은 새로 만들기보다 이것을 기준으로 확인할 것.
