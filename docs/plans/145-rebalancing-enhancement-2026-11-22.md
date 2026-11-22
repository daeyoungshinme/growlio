# 계획 145 — 리밸런싱 탭 개선·고도화 (2026-11-22)

## Context

리밸런싱 탭은 62(코드)·63(흐름)·64(IA)·136(시점 진단)을 거쳐 기능은 풍부하지만, 이번 분석에서 다음이 남아 있었다.
- **실버그 2건**
  - AUTO 세금 게이트가 BUY_ONLY·정액 적립 알림까지 막는다.
  - 자동화 "꺼짐" 칩이 표시되지 않는다.
- **조회 실패가 빈 상태로 보이는 화면**이 여러 곳 있다.
- **같은 정보가 반복 노출**된다: 자동화 상태 3중, 시장 종합 판단 3중.
- **고도화 미구현** — 사용자가 고른 3가지:
  1. 입금액 우선 배분
  2. 밴드 경계까지만 거래 + 최소 거래액
  3. 목표 비중 출처 기록·홈 연동

4개 PR로 나눈다. 실행 시작 시 이 내용을 이 문서와 `docs/plans/README.md` 인덱스가 기준이다.

---

## PR1 — 실버그·상태 처리 (fix/rebalancing-145-bugs) — 구현 완료(미커밋)

> A2는 "꺼짐"뿐 아니라 "적립매수" 칩도 같은 원인(카드가 `mode`만 넘김)으로 안 보였다 — 카드에 알림 객체를 통째로 넘긴다. A1의 기존 테스트는 BUY_ONLY가 막히는 동작을 정상으로 고정하고 있어 FULL로 바꿨다. A4는 rollback이 알림 ORM 행을 expire시키므로 기준을 루프 전에 float로 뽑는다.

**A1. AUTO 세금 게이트 범위 (백엔드, 확인됨)**
- 현재 동작: `plan_gates._check_tax_gate`(`backend/app/services/rebalancing/plan_gates.py:89`)가 `_build_tax_preview(analysis, overview)`를 부른다. 이 함수는 `analysis.items` 중 diff<0인 **전 항목**을 매도한다고 가정하고 세금을 계산한다.
- 그래서 매도가 없는 BUY_ONLY·정액 적립(`is_dca_amount_mode`)도 해외 이익 종목만 있으면 `TaxGateBlocked`로 막힌다. 이탈 안 한 항목의 매도분도 합산된다.
- 수정:
  - `_check_tax_gate`에 `strategy`와 `drifting`을 넘긴다.
  - 매도 주문이 없는 전략(BUY_ONLY, DCA 모드)은 게이트를 건너뛴다.
  - 그 외 전략은 이탈 항목만으로 `estimate_sell_costs`를 계산한다. 계획 138이 `drift_summary_service.py:154`에서 쓴 방식과 같다.
  - 호출부는 `plan_generation.py:483`. strategy는 `strategy_override or alert.strategy`를 게이트 앞으로 끌어올린다.
- 테스트: BUY_ONLY·DCA는 게이트를 통과하고, FULL은 이탈 항목만 합산하는지 확인한다. patch 경로는 `plan_generation.X`.

**A2. 자동화 "꺼짐" 칩 (프론트)**
- 문제: `PortfolioCard.tsx:194`가 `existingAlert={{ mode }}`만 넘겨 `AutomationStatusBar.tsx:67`의 `isOff`가 항상 거짓이다.
- 수정: `is_active`를 함께 넘긴다.
- 테스트: `AutomationStatusBar`에 테스트 파일을 신설한다. 지금은 직접 테스트가 없다.

**A3. 조회 실패 ≠ 빈 상태**
- `PortfolioManageTab`이 `isError`를 `PortfolioListSection`으로 넘긴다. 실패하면 `PageLoadError`와 다시 시도를 보여 준다.
- `PortfolioListSection.tsx:250`의 인라인 `Loader2`를 `SkeletonCard`로 바꾼다.
- `RebalancingStatusCard`: drift-summary나 insights 조회가 실패하면 해당 영역에 실패 안내와 재시도를 보여 준다.
- `RiskMetricsCard`(`RebalancingPage.tsx:262`): 실패해도 카드를 유지하고 실패 상태를 표시한다.
- `RebalancingHistoryTab` 정리:
  - plans 쿼리 로딩을 포함한다(:216).
  - 빈 상태를 `EmptyState`로 바꾼다(:248).
  - 상세 조회 실패 시 재시도 버튼을 둔다(:109).
  - `PendingPlanRow`의 처리 중 상태를 행별로 나눈다(`mutation.variables`로 비교, :273).
- `RebalancingAlertModal.tsx:73`의 인라인 스피너를 Skeleton으로 바꾼다.
- 기존 `components.loadFailureNotShownAsEmpty.test.tsx`에 케이스를 추가하고, `PendingPlanRow` 테스트를 신설한다.

**A4. 이탈 임계값 드리프트 (백엔드)**
- `insight_service.py:228-246`의 `REBALANCING_OPPORTUNITY`가 5/10을 하드코딩하고 있다.
  - `_portfolio_queries.alert_drift_thresholds`와 `drift_rule.is_drifting`을 쓰도록 바꾼다.
  - 상대 밴드를 포함해 화면·알림·자동 실행과 같은 판정이 되게 한다.
- 기본값 5.0이 `service.py:424`와 `_portfolio_queries.py:63` 두 곳에 있다. `drift_rule.py`에 `DEFAULT_DRIFT_THRESHOLD_PCT` 상수 하나로 모은다.

---

## PR2 — 화면 정리 (refactor/rebalancing-145-ui)

동작 변경 없이 중복과 규칙 위반만 정리한다.
- **자동화 상태 3중 노출 해소** (포트폴리오 탭):
  - `PortfolioListSection` 헤더의 자동화 합계를 제거한다.
  - 카드 칩(요약)과 `AnalysisPanel` 바(상세)만 남긴다.
- **`MarketSignalBanner`**:
  - 확정 등급 설명이 `gateLagging`(:115)과 상세(:127)에 중복돼 있다. 상세 쪽 하나로 합친다.
  - "종합"이 헤더 배지(:86), 요약 칩, 차트 추이 아래(:171) 세 곳에 있다. 차트 추이 아래 반복을 제거한다.
- **`UnifiedPortfolioEditor`**:
  - 중복 힌트(:252·:281)를 하나로 줄인다.
  - `title` 속성(:301·:314)을 `InfoTip`으로 바꾼다. 터치에서 보이지 않기 때문이다.
- **`RebalancingOrderTable.tsx:71`**: `useMediaQuery("(min-width: 768px)")`를 `useIsSmUp`으로 바꿔 모바일 카드 판정을 다른 화면과 통일한다.
- **400줄 초과 파일 분할**: `RecommendationCard.tsx`(445)의 적용 영역을 `RecommendationApplySection`으로 분리한다. 이미 테스트 파일명이 존재하는 이름이다.
- 기존 테스트 통과 + 바뀐 렌더 단언을 갱신한다.

---

## PR3 — 거래 방식 고도화 (feat/rebalancing-145-trade)

**마이그레이션 1개** (`rb2`, `rebalancing_alerts` 컬럼 추가)
- `trade_to_band: bool = False`
- `min_trade_krw: Numeric(18,2) | None`
- `dca_allocation_mode: String(16) = "TARGET"`
- 모델은 `backend/app/models/alert.py:72`. 스키마는 `schemas/alert.py`. 운영 적용은 수동이며 **코드 배포 전**에 해야 한다.

**B1. 예산 부족 시 비례 배분 (입금액 우선 배분 ①)**
- 현재: `_order_quantity_guard.clamp_buy_orders_to_budget`(:113)는 **목록 순서대로** 예산을 소진한다. 앞 종목만 사고 뒤의 더 부족한 종목은 SKIPPED될 수 있다.
- 변경:
  - 총액이 예산을 넘으면 비율 `factor = budget/total`로 각 수량을 `floor`한다.
  - 남은 돈은 "덜 산 금액이 큰 종목부터 1주씩" 채운다.
- 보충 루프는 `dca_allocation.allocate_dca_amount`(:69-81)의 루프와 같은 로직이다. `_order_quantity_guard.fill_leftover_shares(budgets, prices, qtys, leftover)`로 추출해 양쪽이 공유한다.
- FULL 국내 매수, TWO_PHASE `_execute_buys_within_budget`, BUY_ONLY 모두 이 함수를 거친다.

**B2. 정액 적립 "부족분 우선" 모드 (입금액 우선 배분 ②)**
- 알림에서 `dca_allocation_mode="GAP_FIRST"`이면, 금액을 투입한 뒤의 총액을 기준으로 목표 미달 종목의 부족액에 비례해 먼저 배분한다. 남는 금액은 기존처럼 목표 비중으로 나눈다.
- 순수 함수 `allocate_dca_gap_first(rows, amount_krw)`를 `dca_allocation.py`에 둔다.
  - 행에 `current_value_krw`와 그룹 합산값이 필요하다. `dca_buy_rows`가 이미 그룹을 대표 멤버로 펼치므로, 그룹 현재가치는 원 그룹 행 값을 함께 넘긴다.
  - 기존 규칙 "시세 갱신 뒤 분할"을 지킨다.
- 프론트 `utils/dcaAutoBuy`는 백엔드와 같은 규칙이어야 한다. 미리보기도 모드를 반영한다.

**B3. 밴드 경계까지만 거래 + 최소 거래액**
- `drift_rule.py`에 순수 함수 `shrink_to_band(item, threshold_pct, relative_pct, base_value_krw)`를 추가한다.
  - 경계는 `target ± min(abs_thr, target×rel/100)`로, `is_drifting`과 같은 규칙을 쓴다.
  - diff_krw를 경계까지로 줄이고 `shares_to_trade`를 같은 비율로 `floor`한다.
  - 그룹 행은 diff만 줄인다. 먼저 `group_expansion.expand_group_items`가 diff 기준으로 펼치는지 확인한다. 아니면 멤버 diff도 같은 비율로 줄인다.
- 적용 위치:
  - AUTO·quick-execute: `plan_generation._drifting_items_for_alert` 뒤, `alert.trade_to_band`일 때.
  - 수동 분석: `GET /rebalancing/portfolios/{id}/analyze?band_edge=true`. `portfolio_analysis_service` 캐시 키에 포함한다.
- `min_trade_krw`: `build_rebalancing_orders`에서 `qty × reference_price < min_trade_krw`인 주문을 건너뛴다. 로그 reason은 `below_min_trade`.
- 프론트:
  - 알림 모달 `alertModal/AlertAutoModeSection`(또는 Trigger)에 "목표까지 / 허용 범위 경계까지" `SegmentedControl`과 최소 거래액 입력을 추가한다. 적립식 섹션에는 "목표 비중대로 / 부족한 종목 먼저"를 추가한다.
  - `AnalysisPanel`에 "경계까지만" 토글을 두고 `useAnalysisState`에 파라미터를 추가한다.
  - `utils/rebalancingAlertDescription` 요약 문구에 반영한다.
- 테스트:
  - 순수 함수: `shrink_to_band`, `allocate_dca_gap_first`, `fill_leftover_shares`, 비례 clamp.
  - `build_rebalancing_orders` 최소액.
  - 프론트 모달·설명 유틸.

---

## PR4 — 목표 비중 출처·홈 연동 (feat/rebalancing-145-source)

**C1. 목표 비중 출처 기록**
- `Portfolio`에 `target_source: String(16) | None`(MANUAL/RECOMMENDATION/TACTICAL)과 `target_source_at: DateTime | None`을 추가한다. 마이그레이션은 PR3의 `rb2`에 합치거나 `rb3`로 만든다.
- 기록 시점:
  - `portfolio_crud_service` 업데이트에서 항목이 바뀌면 기록한다. 요청 스키마에 `target_source`를 선택 필드로 두고, 기본값은 MANUAL이다.
  - `RecommendationCard`의 적용 경로는 `RECOMMENDATION`을 보낸다.
  - `tactical_apply`는 `TACTICAL`로 기록한다.
- 표시: `PortfolioCard`, `AnalysisPanel` 헤더에 "목표: 추천 적용 · 11/20".
- 주의: `Portfolio.updated_at`은 비중만 바뀐 저장에서는 갱신되지 않는다. 그래서 `target_source_at`을 별도로 둔다.

**C2. 홈 "지금 할 일"에 시점 판정**
- `action_items_service.py:169-196` REBALANCE 행 detail에 `s.timing` 라벨을 앞에 붙인다(지금 / 나눠서 / 보류 / …).
- HOLD만 남은 경우 우선순위를 낮춘다(`utils/actionPriority`와 맞춘다).
- 그룹 행은 NOW 개수를 표시한다.
- 라벨 텍스트는 프론트 `utils/rebalancingTiming.TIMING_LABEL`과 같게 둔다. 백엔드에 상수를 두고 주석으로 연결한다.

**C3. 홈 "추천이 바뀜" 항목**
- 새 kind `RECOMMENDATION_DRIFT`를 추가한다. 링크는 `rebalancingUrl` 목표 조정 › 추천과 같은 문자열이다.
- 콜드 계산이 수십 초라 홈에서는 계산하지 않는다. `goal_recommendation_service`에 **캐시 조회 전용** 함수(`peek_goal_recommendation` — 1h·stale 키만 읽고, 없으면 None)를 추가한다.
  - `recommendation_drift.compute_recommendation_drift`를 재사용한다. 임계값 3%p는 프론트와 동일하다.
- 대상은 `target_source`가 RECOMMENDATION인 포트폴리오로 한정한다(C1 의존). 사용자가 추천을 따르기로 한 포트폴리오만 알린다.
- 프론트: `api/dashboard.ts` kind 유니온, `ActionItemsCard` 아이콘·라벨.

---

## 재사용할 기존 코드
| 용도 | 위치 |
|---|---|
| 이탈 판정 단일 규칙 | `drift_rule.is_drifting`, `alert_relative_threshold` (`services/rebalancing/drift_rule.py`) |
| 매도 비용 추정 | `diagnosis_service.estimate_sell_costs` |
| 1주씩 보충 로직 | `dca_allocation.allocate_dca_amount` → 공용화 |
| 시점 판정 | `drift_summary_service.get_drift_summaries`, `timing_verdict.decide_timing` |
| 추천 변화 판정 | `goal/recommendation_drift.compute_recommendation_drift` |
| 프론트 탭 링크 | `utils/rebalancingUrl.rebalancingUrl` |
| 캐시 무효화 | `invalidateRebalancingAlertData` / `invalidatePortfolioData` |

## 문서 갱신
- `backend/CLAUDE.md` 리밸런싱 항목: drift_rule `shrink_to_band`, dca GAP_FIRST, clamp 비례 배분.
- `frontend/CLAUDE.md` `dcaAutoBuy` 동일 규칙.
- `docs/plans/README.md`. 한 줄 요약과 함정만 적는다.

## 검증
- 백엔드: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pytest`, 이후 `pytest --cov` 91% 게이트. PR3·PR4는 `uv run alembic check`(로컬 DB).
- 프론트: `D:\project\growlio\frontend`(대문자 드라이브)에서 `npm run lint -- --max-warnings 0 && npm run format:check && npm run typecheck && npm run test`.
- 수동 확인 (`bash dev.sh`):
  - 진단·포트폴리오·이력 탭에서 네트워크 오프라인/500을 주입해 실패 UI를 확인한다.
  - 알림 모달 새 옵션 저장 → 다시 열어 값이 유지되는지 본다.
  - "경계까지만" 토글 시 분석 수량이 줄어드는지 본다.
  - 홈 지금 할 일에 시점 라벨이 붙는지 본다.
- 운영: `rb2`(·`rb3`) 마이그레이션은 코드 배포 전 수동 적용. 실계좌 AUTO 동작(비례 clamp·GAP_FIRST)은 실기기 확인 대기로 기록한다.
