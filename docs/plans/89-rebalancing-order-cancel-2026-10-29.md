# 89. 리밸런싱 실행 주문 — 미체결분 취소 (2026-10-29)

> 상태: **구현 완료(미커밋)**. 실계좌·모의투자 실기기 확인은 아직 하지 않았다.

## Context

리밸런싱 실행(수동·원클릭·AUTO 플랜 leg)으로 증권사에 접수된 주문은 앱에서 되돌릴 수 없었다. 기존 "취소"(`cancel_buy_leg`)는 **실행 전 대기 플랜 leg**만 취소한다.

범위는 사용자가 정했다: **미체결 수량만 취소**한다. 체결된 주문을 반대 주문으로 되돌리는 기능은 하지 않는다(가격차·수수료·세금 손실 위험).

취소가 실제로 쓸모 있는 경우:
- 해외 지정가 주문. AUTO는 해외 시장가를 지정가로 바꾸므로 미체결로 오래 남는다.
- 국내 지정가 주문. 국내 시장가는 거의 즉시 체결된다.

## 설계

- **미체결 조회 없이 취소를 바로 요청한다.** KIS 미체결 조회(TTTC8036R·TTTS3018R)는 모의투자를 지원하지 않는다. 또 조회와 취소 사이에 체결될 수 있다. 이미 체결됐으면 증권사가 거부하고, 그 사유를 `CANCEL_FAILED`로 기록해 보여준다. 부분체결이면 잔량 전부를 취소한다.
- **증권사 거부는 `KisApiError`/`KiwoomApiError`로 온다.** `kis_request`/`kiwoom_request`가 rt_cd·return_code≠0이면 `BrokerOrderRejectedError`보다 먼저 이 예외를 던진다. 세 예외 모두 거부로 처리한다. 그 밖의 예외(타임아웃 등)는 기록하지 않고 502를 돌려준다. 응답이 유실된 경우 실제로는 취소됐을 수 있기 때문이다.
- **KIS 국내 취소에는 `KRX_FWDG_ORD_ORGNO`(주문 조직번호)가 필요하다.** 주문 응답에서 꺼내 `rebalancing_execution_results.order_org_no`에 저장한다(마이그레이션 `oc1_rebalancing_result_cancel`). 배포 전 기록은 조직번호가 없어 취소할 수 없다. 국내 주문은 당일 소멸하므로 실질적인 손실은 없다.
- 취소 가능 판정은 `order_cancel_service.cancel_block_reason`이다. 이력 상세의 `cancelable`과 취소 API가 이 함수를 같이 쓴다. 조건: SUCCESS + 주문번호 + 미취소 + KIS/키움 계좌. 국내는 KST 당일 주문만, 해외는 24시간 이내 주문만이다(미국 장이 KST 자정을 넘김). `CANCEL_FAILED`는 다시 시도할 수 있다.
- 동시 클릭은 `SELECT … FOR UPDATE`(결과 행)로 막는다.

| 증권사 | 국내 | 해외 |
|---|---|---|
| KIS | `TTTC0803U`/`VTTC0803U` `order-rvsecncl`, `RVSE_CNCL_DVSN_CD=02`, `QTY_ALL_ORD_YN=Y` | `TTTT1004U`/`VTTT1004U` `order-rvsecncl`, 거래소는 저장된(AMEX 보정된) market |
| 키움 | `kt10003` `/api/dostk/ordr`, `cncl_qty=0`(잔량 전부) | `ust20003` `/api/us/ordr`, `orig_ord_no`·`stex_tp`·`stk_cd` — 기존 주문과 같은 오픈소스 .NET 클라이언트(`CancelOrderAsync`)로 교차검증 |

## 변경 파일

- 백엔드:
  - `kis/order.py`·`kiwoom/order.py`: 취소 래퍼 추가. KIS 국내 주문은 `order_org_no`도 반환한다.
  - 상수 파일.
  - `models/asset.py`: 컬럼 4개 추가.
  - `schemas/rebalancing/execution.py`: `OrderResult`에 `result_id`·`cancel_*`·`cancelable` 추가(`order_org_no`는 응답에서 제외), `OrderCancelResponse` 추가.
  - `_order_executor_common.py`·`execution_service._save_execution_history`: 조직번호를 저장하고, 실행 직후 응답에도 result_id를 붙인다.
  - `order_cancel_service.py`(신규).
  - `rebalancing_execution.py`: `POST /rebalancing/history/results/{id}/cancel` 추가, 이력 상세에 취소 필드 추가.
- 프론트:
  - `api/rebalancing.ts`.
  - `OrderCancelAction.tsx`(신규): 확인 모달, 결과 표시, 이력 쿼리 무효화.
  - `OrderResultList.tsx`: 실행 직후 결과와 이력 상세 양쪽에 연결.

## 검증

- 백엔드 3091 passed, 커버리지 91.88%. ruff·mypy 클린.
- 신규 `tests/test_rebalancing_order_cancel.py`. `test_broker_order_requests.py`에 취소 요청 형태 테스트를 추가했다.
- 프론트 1869 passed. eslint·prettier·tsc 클린. 신규 `components.orderCancelAction.test.tsx`.
- 마이그레이션은 `alembic upgrade/downgrade --sql`(오프라인)로만 확인했다. 로컬 `.env`가 공유 Supabase를 가리켜 실제 적용은 하지 않았다. Render preDeploy가 적용한다. **코드보다 마이그레이션이 먼저 적용돼야 한다**(새 컬럼을 SELECT한다).

## 남은 일

- KIS 모의투자로 실기기 확인: 국내 지정가 저가 매수 → 이력에서 미체결 취소 → 증권사 앱에서 취소 확인. 시장가로 체결된 주문을 취소하면 거부 메시지가 뜨는지 확인.
- 키움 해외 취소(`ust20003`)는 실호출로 확인한 적이 없다(교차검증만 했다).
