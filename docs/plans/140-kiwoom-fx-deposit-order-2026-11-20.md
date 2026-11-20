# 140. 키움 리밸런싱: 외화 예수금 표시 + 외화 우선·원화 대체 주문 (2026-11-20)

## 요청

"키움증권 리밸런싱에 예수금이 원화만 표시되는데 외화도 표시되도록 하고, 외화로 주문 가능하면 외화로 주문하고 외화로 주문이 되지 않을 때 원화로 주문하도록."

## 원인

- 실행 확인 화면(`RebalancingConfirmStep`·`CashSummaryBar`)은 `GET /rebalancing/broker-balance` 응답의 원화만 보였다. provider `sync()`는
  `BalanceResult.deposit_foreign`(키움 `fc_entra`)을 받는데 `broker_balance_service`가 응답에 싣지 않았다. 그래서 해외 매수 비용(원화 환산)이
  원화 예수금과만 비교돼 "부족"이 거짓으로 떴다.
- 수동 실행의 키움 해외 매수(`_broker_order_flow.execute_buys_with_cash_check`)는 해외가 섞이면 확인 없이 발주했다. 달러 확인은 AUTO 정액 적립
  leg(`usd_buying_power.check_usd_shortfall`)에만 있었다.

## 제약

키움 REST 해외 주문(ust20000)에는 **결제통화 필드가 없다**. 원화 결제는 계좌의 원화주문 서비스 신청으로만 되고, 신청 계좌는 증권사가 **보유 외화를
먼저 쓰고 부족분만 원화**로 채운다(키움 미국주식 원화주문 거래설명서). 앱은 이 신청을 `AssetAccount.krw_overseas_order`로 표시받는다(PR #266).
→ "외화 우선, 안 되면 원화"는 증권사 동작이고, 앱은 주문마다 결과를 **판정**만 한다.

결정(사용자): 원화주문 표시가 **없는** 키움 계좌에서 달러가 부족한 해외 매수는 주문하지 않고 SKIPPED + 안내.

## 수정

### 백엔드

- `KisBalanceResponse`에 `deposit_usd`(해외 조회 실패면 None)·`krw_overseas_order` 추가 — `broker_balance_service`가 3사 모두 채운다
  (원화주문 플래그는 `uses_krw_overseas_order`라 키움만 참).
- `_broker_order_flow`: `BrokerOrderOps.overseas_buy_funding`(선택, 키움만) + `OverseasFunding(usd, krw_order, krw_as_usd)`.
  funding op가 있으면 매수를 국내/해외로 나눠 국내는 원화 매수여력 clamp(예전엔 해외가 섞이면 clamp를 건너뜀), 해외는 국내 발주 **뒤**
  여력을 조회해 주문 순서대로 판정(`execute_overseas_buys_with_funding`):
  - 필요 달러 = 수량 × (지정가 | 참고 시세 × 1.02) × `FX_FEE_BUFFER`
  - 남은 달러로 충분 → 발주, `settlement_currency="USD"`
  - 부족 + 원화주문 → 남은 달러 + 원화 환산 여력(`krw_order_usd_capacity` — 실환율 × `KRW_ORDER_FX_MARGIN`)으로 충분하면 발주(`KRW`), 아니면 SKIPPED
  - 부족 + 일반 계좌 → SKIPPED("환전하거나 원화주문을 신청·표시하세요")
  - 가격 모름·여력 조회 실패·실환율 없음 → 판정 없이 발주(증권사가 최종 판정 — 기존 원칙)
  - 여력은 성공한 주문 몫만 뺀다
- `OrderResult.settlement_currency`(응답 전용 — **이력에는 저장하지 않는다**, 이력 상세엔 안 보임).
- `usd_buying_power._krw_order_usd`의 환산식을 `krw_order_usd_capacity`로 빼 실행기와 공유.
- AUTO 플랜: 정액 적립 leg는 기존 `check_usd_shortfall`(WAITING_FX)이 먼저 거른다. 그 외 해외 매수가 전부 SKIPPED면 leg는 FAILED + 사유 알림
  (`_fail_leg_without_fills`).

### 프론트엔드

- 잔고 상태 `depositUsd`(해외 조회 실패면 비움).
- `getCashAnalysis`: 키움 계좌이고 달러·환율·시세를 다 알면 원화/달러를 따로 본다 — `usd {available, required, shortfall, krwForUsdShortfall}`.
  해외 매도 예상 대금은 달러 쪽, 원화 매수필요는 국내 몫 + (원화주문이면) 달러 부족분 × 환율 × 1.03. 하나라도 모르면 예전처럼 원화 환산 합계.
- 전체 예수금 배너는 달러 예수금 × 환율을 더하고 "(달러 환산 포함)" 표시.
- 계좌 헤더 "주문가능 ₩X · $Y" + "원화주문" 배지, `CashSummaryBar` 달러 줄(부족 시 원화 결제 / 건너뜀 안내), 결과 행 "원화 결제" 배지.

## 남은 일 / 사용자 확인

- 원화주문 신청 계좌에서 달러가 모자란 해외 매수가 실제로 원화로 체결되는지 실계좌 1회(계획 129부터 미검증).
- KIS·토스 계좌도 헤더에 달러 예수금은 보이지만 통화별 판정은 키움만이다(KIS는 통합증거금 등 결제 규칙이 달라 이번 범위 밖).
