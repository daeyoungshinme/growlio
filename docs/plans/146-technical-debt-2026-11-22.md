# 146. 기술부채 — 143·144·145 첫 감사 (2026-11-22)

상태: **완료**(배치 A #302 · B #303 · C, 스택 PR). 열린 PR 0건, ruff·mypy·pip-audit·npm audit(운영·개발)·TODO 모두 0건. 범위는 아직 감사하지 않은 143(#292~#294)·144(#295~#297)·145(#298~#301) 신규 코드. `docs/remaining-tasks.md` P1~P4는 확인·결정 대기라 제외. ✔ 표시는 코드를 직접 읽어 재현 경로를 확인한 항목.

## 배치 A — 리밸런싱(145) 실버그·정합 (PR 1, 백엔드 위주)

**A1 ✔ 편집기 저장만 해도 목표 출처가 MANUAL로 덮어써짐**
- 위치: `backend/app/services/portfolio/portfolio_crud_service.py:180-184`
- 현재 동작: `body.items`가 있으면 무조건 `target_source`와 `target_source_at`을 기록한다. 편집기는 이름이나 계좌만 바꿔도 `items`를 보낸다. 그 결과 RECOMMENDATION이나 TACTICAL이 MANUAL로 바뀌고, 홈의 "추천이 바뀜"이 영영 뜨지 않는다.
- 수정:
  - 기존 항목과 새 항목의 (ticker/market/group, weight) 시그니처를 비교해 바뀐 경우에만 기록한다.
  - `target_source`가 요청에 없으면(`model_fields_set`) 기존 값을 유지한다. 스키마 기본값 MANUAL에 의존하지 않는다.
  - 프론트 `PortfolioManageTab.tsx:220-227`의 수정 저장은 `target_source`를 생략한다.
- 테스트: 이름만 바꾼 저장 → 출처 유지 / 비중 변경 → MANUAL.

**A2 ✔ 예산 비례 배분이 비싼 1주 주문을 통째로 빼고 예수금을 남김**
- 위치: `backend/app/services/rebalancing/_order_quantity_guard.py:139-192` (`clamp_buy_orders_to_budget`)
- 예: 예산 95만, A 90만×1과 B 1만×10 → A가 SKIPPED되고 85만이 남는다.
- 수정: 비례 배분과 보충을 끝낸 뒤 "수량 0이고 단가 ≤ 예산"인 주문이 있으면 그 주문을 먼저 1주 확보한 배분안을 하나 더 만든다. 나머지는 비례·보충으로 채운다. 두 배분안 중 쓰는 금액이 더 큰 쪽을 고르고, 같으면 비례안을 고른다. `fill_leftover_shares`를 재사용한다.
- 테스트: 위 예시, 그리고 기존 비례 테스트 회귀.

**A3 ✔ trade_to_band 매수가 내림 때문에 경계 밖에 남아 다음 실행에 또 걸림**
- 위치: `drift_rule.py:96-106` (`shrink_to_band`)
- 수정: 매수(`diff_w > 0`)는 수량을 올림한다. 대신 목표 비중(`target_value_krw`) 기준 수량을 넘지 않게 상한을 둔다. 매도는 지금처럼 둔다.
- 테스트: 1주 단가가 큰 소액 포트폴리오에서 매수 후 `is_drifting`이 False인지 확인한다.

**A4 목표 0% 종목은 trade_to_band에서도 끝까지 정리**
- 위치: `drift_rule.py:92-96`
- 현재 동작: 목표 0% 종목이 기준값(예: 5%p)에서 멈추고 더 이상 팔리지 않는다.
- 수정: `target_w == 0`이면 경계 축소를 건너뛴다(전량 매도 유지). `test_untargeted_holding_keeps_band_weight`를 반대 기대값으로 바꾼다.
- 결정 근거: 목표 0%는 "보유하지 않음"이라는 뜻이다.

**A5 최소 거래액이 정액 적립 매수를 소리 없이 지움**
- 위치: `plan_generation.py:186`
- 수정: 정액 적립 모드(`is_dca_amount_mode`)에는 `drop_orders_below_min_value`를 적용하지 않는다. 폼(`useRebalancingAlertForm.ts:226`)은 정액 프리셋이면 `min_trade_krw`를 숨기고 null로 보낸다.

**A6 GAP_FIRST를 사전 부족 판정과 환전 계획이 모름**
- 위치: `dca_cash_shortfall_service.fixed_amount_needs` (92-115)
- 수정: 알림의 `dca_allocation_mode == GAP_FIRST`이면 `dca_allocation`의 같은 분할 함수(현재 보유값 기준)로 원화·달러 몫을 나눈다. 보유값을 조회하지 못하면 목표 비중으로 폴백한다. `fx_plan_service`는 이 함수를 그대로 쓰므로 함께 맞춰진다.
- 프론트 `utils/dcaAutoBuy`는 미리보기 전용이라 GAP_FIRST를 포팅하지 않는다. 대신 `frontend/CLAUDE.md` 문구를 "목표 비중 분할만 같음"으로 고친다.

**A7 홈 "추천이 바뀜" 거짓 알림과 묶음 링크**
- 위치: `recommendation_drift_alert_service.find_drifted_targets`, `action_items_service.py:447`
- 수정 1: 비교 대상 추천의 종류를 기록한다. `target_source=RECOMMENDATION`과 함께 `target_source_detail`(overall/horizon/age)을 쓰면 마이그레이션이 필요하다. 그래서 마이그레이션 없이, 적용 당시 추천과 같은 종류를 판별할 수 없는 경우(연령대 추천, 또는 기간 태그 포트폴리오에 전체 추천 적용)는 drift 비교에서 제외하는 보수적 방식으로 처리한다.
- 수정 2: 묶음 링크는 목표 조정 탭으로 보내고 포트폴리오는 지정하지 않는다.

**A8 정리(같은 PR)**
- `peek_drifted_portfolios`: RECOMMENDATION 포트폴리오가 없으면 계좌 조회 전에 바로 반환한다.
- 리밸런싱 알림 저장·삭제 시 `insights_key`를 무효화한다(`rebalancing_alerts.py`, `cache_invalidation`).
- `group_expansion._base_krw`: 축소 전 목표 총액을 쓴다(멤버 `target_weight_pct` 표시 오류).
- 알림 메일 수량 미리보기(`build_alert_order_preview`)에 `shrink_to_band`와 최소 거래액을 같은 순서로 적용한다.
- `backend/CLAUDE.md` `order_builder` 항목에 `drop_orders_below_min_value`를 한 줄 추가한다.

## 배치 B — 계획탭(143) 실버그 (PR 2)

**B1 ✔ 홈 챌린지 카드에 마감 지난 챌린지가 나옴**
- 위치: `frontend/src/components/dashboard/ChallengeProgressCard.tsx:14`
- 수정: 필터에 `&& !c.is_expired`를 추가한다.

**B2 ✔ 시나리오 수익률에 부동소수점 오차가 표시됨** (예: 연 5.300000000000001%)
- 위치: `utils/dcaScenarioProjection.ts:55-57`
- 수정: 결과를 소수 2자리로 반올림하고, 8.3·6.6·5.1 테스트를 추가한다.

**B3 ✔ 국내 레버리지·인버스 ETF를 ISA 절세액 계산에서 비과세로 봄**
- 위치: `backend/app/services/tax/isa_service.py:40-59`
- 수정: `cls.kind == "LEVERAGED"`(또는 정규식 `레버리지|인버스|2X|선물`)이면 과세로 본다. 국내주식형이어도 파생형은 배당소득과세 대상이다.
- 테스트: KODEX 레버리지, KODEX 인버스.

**B4 해외 절세 마감일 KST/ET 비교**
- 위치: `tax_action_overseas.py:66,121`
- 수정: `today`를 ET 날짜로 바꿔 비교하거나, 마감일 판정을 "ET 기준 오늘"로 한다. 12/30 KST 새벽 테스트를 추가한다.

**B5 만료 RETURN_PCT·TARGET_VALUE 진행률**
- 위치: `challenge_service.compute_progress`
- 수정: `is_expired`이면 진행률을 계산하지 않고 null로 둔다. 화면은 "기한 종료"만 보인다. 마감 당시 스냅샷은 저장하지 않는 설계라서 이렇게 처리한다.

**B6 `pick_year_rule` 폴백 경고 로그**
- 계획 143 문서에 적었지만 실제로는 넣지 않았다.
- 위치: `tax_service.py:57-61`

**B7 정리**
- 배당 목표 달성 문구에 "세전 재투자 가정"을 명시한다(`dividendGoalTimeline`).
- E3 테스트: `useRealTimers`를 `afterEach`로 옮기고 날짜 값을 검증한다.
- `transactions.py:174` 연도 루프에서 무효화를 1회로 줄인다.
- `InvestPlanPage` 401줄은 2줄만 줄여 400 이하로 맞춘다.

## 배치 C — 자산탭(144) (PR 3, 프론트 위주)

**C1 평가액 미수신 시 합계 카드에 "입금 대비 −100%"가 뜸**
- 위치: `StockAccountSummaryCard.tsx:16-38,68-80`
- 수정: `statsStatus`를 내려 받고 `"ready"`일 때만 `vsDeposit`을 표시한다. 금액순 정렬도 ready가 아니면 기본 정렬로 대체한다(`AssetManagementPage.tsx:181`).

**C2 은행·증권 합계 카드가 합산 제외 계좌까지 더함**
- 위치: `BankAccountSummaryCard`, `sumDepositReturn`
- 수정: 계획 144의 "합산 제외는 전부 제외" 원칙에 맞춰 `include_in_total !== false`만 합산한다. 제외된 계좌가 있으면 "합산 제외 N개 빠짐" 한 줄을 표시한다(투자현황과 같은 문구).

**C3 계좌를 직접 골랐을 때 투자기간 카드가 사라짐**
- 위치: `HorizonSummaryCard.tsx:33-35`, `PortfolioPage.tsx:215`
- 수정: 합산 제외 필터는 `!selectedAccountId`일 때만 적용한다.

**C4 계좌별 추이 조회 실패가 빈 상태로 보임**
- 위치: `useAllocationHistory`, `AllocationHistoryChart.tsx:85-94`
- 수정: `isError`를 내보내고 실패 문구와 다시 시도 버튼을 둔다.

**C5 정리**
- `_ALLOC_HISTORY_VERSION`을 v4로 올린다.
- 계획 144 문서의 "미푸시" 문구를 고친다.
- `test_real_db_upserts.py`에서 `date.today()`를 `today_kst()`로 바꾼다.

## 범위 밖(계획서 이관 표에 기록)
- 145: 수동 분석 `band_edge` 토글
- 이력 탭 행별 pending 표시(서버 FOR UPDATE가 중복을 막으므로 영향 낮음)
- quick-execute NOTIFY 모드의 경계·최소액 미적용(계획서 문구만 수정)
- 143: 설정 모달 1h stale prefill
- A6 시작 금액 오래된 스냅샷
- 배당 캐시 버전
- 144: 계획서의 기존 이관 3건
- remaining-tasks P1~P4는 그대로 둔다.

## 문서 갱신
- `docs/plans/146-…md` 신설, README 146행 추가
- `docs/remaining-tasks.md`의 "완료"와 이관 갱신
- `backend/CLAUDE.md`: `order_builder`, `drift_rule`의 0% 예외, `portfolio_crud_service` 출처 유지 규칙
- `frontend/CLAUDE.md`: `dcaAutoBuy` 문구

## 검증
- 백엔드: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pytest --cov=app` (91% 게이트, Windows 종료 코드 -1073741819는 무시)
- 프론트: `D:\project\growlio\frontend`(대문자 드라이브)에서 `npm run lint -- --max-warnings 0 && npm run format:check && npm run typecheck && npm run test`
- 마이그레이션은 없다(A7을 보수적 방식으로 처리해서). 그래서 `alembic check` 변화가 없다.
- 회귀 확인용 새 테스트:
  - `test_portfolio_crud`(출처 유지)
  - `test_order_quantity_guard`(95만 예시)
  - `test_drift_rule`(경계 올림·0% 전량)
  - `test_plan_generation`(정액 + 최소액)
  - `test_dca_cash_shortfall`(GAP_FIRST)
  - `test_isa_service`(레버리지)
  - 프론트 `ChallengeProgressCard`·`dcaScenarioProjection`·`StockAccountSummaryCard`·`HorizonSummaryCard`
- 각 PR은 커밋 전에 `git status`로 다른 세션의 변경이 섞였는지 확인한다.

---

## 결과

### 배치 A (PR 1)
- A1~A5·A8 계획대로.
  - A2는 0주가 된 주문을 큰 계획 금액부터 1주 확보해 보고, 쓰는 금액이 늘면 채택한다(`_fit_proportional`).
  - A3 매수 목표 금액은 `(경계 안쪽 정수 주 + 0.5) × 가격`이며 원래 목표 금액이 상한이다. 반 주 여유는 `refresh_live_prices`가 실시간가로 다시 내림할 때를 위한 것이다.
- **A6 범위 축소**: GAP_FIRST 분할은 사전 부족 판정(`find_dca_cash_shortfalls`)에만 반영했다. 보유 평가액은 포트폴리오 연결 계좌, 없으면 실행 계좌의 현재 포지션을 쓴다. 환전 계획은 여러 달 평균 필요 달러라서 목표 비중 분할을 유지한다(`fixed_amount_needs`의 `held_values` 미지정).
- **A7 방식 변경**: 마이그레이션 없이 적용한 추천의 종류를 알 방법이 없다. 그래서 홈 `peek_drifted_portfolios`는 RECOMMENDATION 포트폴리오가 캐시된 전체·기간별·연령대 추천 **모두와** 3%p 넘게 다를 때만 띄운다. 적용 시점에는 그중 하나와 같았기 때문이다. 주간 알림(`find_drifted_targets`)의 짝짓기 규칙은 그대로다. 묶음 항목 링크에서는 `portfolioId`를 뺐다.
  - 남은 한계: 적용한 추천 종류의 캐시가 만료되고(1h+stale 1d) 다른 종류만 남으면 거짓으로 뜰 수 있다.
- 검증: 백엔드 4137 passed·커버리지 93.78%, 프론트 2258 passed, lint·typecheck 통과.

### 배치 B (PR 2)
- B1~B6 계획대로.
  - B3는 `cls.kind == "LEVERAGED"` 또는 이름의 `레버리지|인버스|선물|2X`를 과세로 본다.
  - B4는 `deadline_passed(today, deadline, now)`로 처리한다. KST 마감 다음 날만 실제 ET 시각(16시 마감)으로 판정한다.
  - B5는 마감이 지난 RETURN_PCT·TARGET_VALUE 챌린지의 진행률을 null로 두고 자산 조회도 건너뛴다.
  - B6 경고는 프로세스당 표·연도별 1회만 남긴다.
- B7:
  - 문구는 "세전 배당 재투자"로 바꿨다.
  - E3 테스트는 `afterEach`에서 실제 타이머로 되돌리고 날짜 값을 검증한다.
  - `InvestPlanPage`는 399줄이다.
  - **`transactions.py` 연도별 무효화는 남겼다** — 연도 수(보통 1~2개)만큼 인메모리 SCAN이 한 번 더 도는 정도라서 고쳐도 얻는 게 없다.
- 검증: 백엔드 4144 passed·93.78%, 프론트 2260 passed.

### 배치 C (PR 3)
- C1:
  - 증권 합계 카드는 `statsStatus === "ready"`일 때만 입금 대비 수익을 보여 준다.
  - 금액순 정렬은 ready가 아니면 기본 순서로 둔다.
- C2: 은행·증권 합계 카드에서 합산 제외 계좌를 빼고, 빠진 계좌가 있으면 "합산 제외 계좌 N개는 빠짐"을 표시한다(투자현황과 같은 문구).
- C3: `HorizonSummaryCard`에 `accountSelected`를 추가했다. 계좌를 직접 고르면 합산 제외 계좌도 포함한다.
- C4:
  - `useAllocationHistory`가 `isError`·`refetch`를 내보낸다.
  - 차트는 데이터 없이 실패하면 실패 문구와 다시 시도 버튼을 보여 준다. 홈 카드도 같다.
- C5:
  - `_ALLOC_HISTORY_VERSION`을 v4로 올렸다.
  - 계획서 144 문구를 고쳤다.
  - 실 DB 테스트의 `date.today()`를 `today_kst()`로 바꿨다.
- 검증: 백엔드 4144 passed·93.78%, 프론트 2266 passed.
