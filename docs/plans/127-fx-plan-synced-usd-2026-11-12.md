# 계획 127 — 달러 환전 계획: 보유 달러를 계좌관리 동기화 값으로 (2026-11-12)

## 배경

계획 124(경량 예수금·계좌별 병렬·환율 병렬)와 #260(커넥션 반납) 뒤에도 "달러 환전 계획" 카드는 느렸다.
남은 가장 큰 대기는 **카드를 열 때마다 하는 증권사 실시간 달러 조회**였다. 2분 캐시라 대부분 미스였고, 한 번에
KIS 토큰 + 해외잔고 최대 3회(달러 0원이면 3거래소 모두. 환전이 필요한 사용자가 바로 이 경우)와 키움 ust21110을 기다렸다.
또 `get_fx_plan`은 환율 컨텍스트(Yahoo)를 다 기다린 뒤에야 DB·증권사 조회를 시작해 두 대기가 더해졌다.

사용자 제안: 포트폴리오 연결 계좌 필터를 없애고, 보유 달러는 계좌관리에 저장된 `deposit_usd`를 쓴다.

## 검토

| 항목 | 판단 |
|---|---|
| 속도 | 로딩 경로에서 증권사 HTTP가 사라진다. DB 몇 쿼리와 환율(실시간 캐시, 1년 일봉 6h 캐시·기동 예열)만 남는다 |
| 일관성 | 계좌관리 화면 숫자와 같다. 동기화와 실시간 경량 조회가 같은 필드(KIS `frcr_dncl_amt_2`, 키움 `fc_entra`)를 쓰므로 시점만 다르다 |
| 환전 직후 옛 값 | 동기화(15:30·18:00·수동) 전에는 이미 환전한 달러를 모른다(plans/121 B가 실시간을 넣은 이유). 그래서 기준 시각을 보여 주고 "달러 예수금 새로 받기"(증권 계좌 동기화) 버튼을 둔다 |
| 연결 필터 제거 | 활성 증권 계좌 전체의 달러를 센다(연결 계좌가 없는 포트폴리오는 원래 이렇게 동작했다). 포트폴리오 계획이 여럿이면 같은 달러가 각 계획에서 차감되지만, 계좌별 내역이 보이므로 받아들인다 |
| WAITING_FX | 카드의 상쇄 계산만 동기화 값을 쓴다. 실제 재매수 판정(`plan_execution`, `dca_fx_wait_retry`)은 여전히 실시간 `fetch_usd_buying_power`를 쓴다 |

## 변경

- **백엔드** — `fx_plan_service._held_usd(db, user_id)`: 활성 `POSITION_STOCK_ASSET_TYPES` 계좌의 `deposit_usd`(브로커 `SYNCED`, 수기 `MANUAL`)에서 추가 환전 보관 달러를 뺀다. 실시간 조회와 관련 코드(`_account_usd`·`_fetch_live_usd`·실패 캐시·`_held_is_live`)를 지웠다. `usd_buying_power_key`·`TTL_USD_BUYING_POWER`·동기화 무효화 SCAN·`fetch_usd_buying_power(release_db=)`도 지웠다.
- `get_fx_plan`: 환율 컨텍스트를 `create_task`로 먼저 시작해 DB 읽기와 겹친다. DB 읽기를 끝내면 `release_read_connection` 뒤에 기다리고, 예외가 나면 task를 cancel한다. 응답에서 `held_usd_is_live`를 빼고 `held_usd_synced_at`(달러가 있는 브로커 계좌 중 가장 오래된 동기화)과 계좌별 `synced_at`을 넣었다. `fx_plan_timing`은 `status`·`accounts`·`ms`만 남긴다.
- **프론트** — 산식 라벨을 "(동기화 기준 · N시간 전)"으로 바꿨다. "달러 예수금 새로 받기"는 `accountsQuery` 중 동기화 가능한 증권 계좌를 `useSyncAccounts`로 동기화한다(0달러 계좌는 계획 응답에 없어서 계좌 목록에서 고른다). `invalidateSyncData`가 `fxPlanBase`를 지운다. `fxPlanQuery`·`FX_PLAN_DEFAULT_MONTHS`는 `api/queryOptions.ts`로 옮겼고, `InvestPlanPage`가 카드가 펼쳐지는 순간 기본 계획을 프리페치해 lazy 청크 로드와 요청이 함께 출발한다.

## 하지 않은 것

- 재방문 시 이전 계획 먼저 표시(SWR)와 환율 위치 블록 분리 — 증권사 조회가 빠져 응답이 짧아지므로 불필요하다.
- KIS 예수금 0원일 때 3거래소 → 1회 단축 — 로딩 경로에서 빠졌다. WAITING_FX 실행 경로는 그대로 둔다.

## 확인 대기

- 운영 로그 `fx_plan_timing ms`로 개선 전후를 비교한다.
- 실기기에서 새로 받기 → 동기화 → 카드 갱신과 기준 시각 변경을 확인한다.
