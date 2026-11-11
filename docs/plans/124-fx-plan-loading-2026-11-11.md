# 계획 124 — 달러 환전 계획 카드 로딩 개선 (2026-11-11)

## 배경

계획 › 적립 계획 › "달러 환전 계획" 카드(`FxPlanCard`, `GET /invest/fx-plan`)를 펼치면 오래 걸린다는 사용자 보고.
실측 없이 코드 추적으로 원인을 좁혔다. 느린 곳은 대부분 **캐시 미스 때 순차로 쌓이는 외부 호출**과 **프론트 요청 폭포**였다.

| # | 원인 | 위치 |
|---|---|---|
| 1 | 실시간 달러 예수금을 얻으려고 **해외 잔고 전체**를 조회 — KIS는 NYSE·AMEX·NASDAQ 3거래소 × 연속조회, 키움은 보유종목(ust21070) 연속조회 + 예수금. 필요한 건 예수금 한 값 | `rebalancing/usd_buying_power.fetch_usd_buying_power` |
| 2 | 계좌별 실시간 달러 조회가 for 루프로 **순차**. 2분 캐시라 대부분 미스 | `fx_plan_service._held_usd` |
| 3 | 실시간 환율과 Yahoo `USDKRW=X` 1년 일봉을 **순차**로 기다림. 1년 일봉은 기동 예열 대상이 아니라 Render 슬립 후 첫 진입마다 다운로드(`yf_download` 전역 락 대기 포함) | `fx_plan_service.load_fx_rate_context`, `jobs/startup_warmup.py` |
| 4 | `FxExtraNeedsSection`이 카드 본문 로딩이 끝난 뒤에야 마운트 → `/invest/fx-extra-needs`가 fx-plan 응답 뒤에 시작 | `FxPlanCard.tsx` |
| 5 | 월 탭(1/3/6개월)이 queryKey라 탭마다 새 요청 | `FxPlanCard.tsx` |

## 변경

- **A. 예수금 경량 조회** — `kis/balance.get_overseas_deposit_usd`(거래소당 첫 페이지 1회, 값이 나오면 중단. 0이면 다음 거래소도 봐서 `get_overseas_balance`의 `deposit_usd`와 같은 값), `kiwoom/balance.get_overseas_deposit_usd`(ust21110 1회). `fetch_usd_buying_power`가 이것을 쓴다 → WAITING_FX 판정·`dca_fx_wait_retry` 잡도 같이 가벼워짐. 동기화는 포지션이 필요하므로 `get_overseas_balance` 그대로.
- **B. 병렬 조회** — `_held_usd`가 계좌들을 `asyncio.gather`(세마포어 3)로. 증권사 조회는 계좌별 짧은 `AsyncSessionLocal()`로(요청 세션은 동시 사용 불가, 토큰 발급이 commit) — `sync_all_service.sync_accounts`와 같은 패턴. `_account_usd`는 더 이상 요청 세션을 받지 않는다.
- **C. 환율 컨텍스트** — 실시간 환율·1년 일봉을 `gather`. `startup_warmup`에 `usd_krw_history`(1년 일봉) 추가.
- **D. 프론트** — `FxPlanCard`를 바깥 래퍼(`FxPlanBody` + `FxExtraNeedsSection` 동시 마운트)로 분리. 계획이 나온 상태(OK·SUFFICIENT)면 나머지 기간을 `prefetchQuery` — 서버 2분 캐시에 맞아 증권사 재호출 없음.
- **E. 계측** — `fx_plan_timing` 로그(`rate_ctx_ms`·`held_usd_ms`·`accounts`·`ms`). 계획이 계산된 경로에서만 남긴다.

## 하지 않은 것

- 실시간 달러 TTL(2분) 연장·stale 우선 반환 — 환전 직후 다시 열면 바로 반영(plans/121 B)과 충돌.
- Render 무료 플랜 슬립 자체(재기동 수십 초) — 외부 핑(plans/121 D) 소관.

## 확인 대기

- **KIS·키움 실계좌에서 경량 조회 예수금이 동기화(`get_overseas_balance`) 값과 같은지** — 목 테스트로만 확인. KIS는 "외화예수금은 거래소별 응답에 동일" 전제(기존 코드 주석)에 의존.
- 운영 로그 `fx_plan_timing`으로 전후 소요 비교.
