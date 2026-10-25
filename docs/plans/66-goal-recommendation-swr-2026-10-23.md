# 66. 목표 조정 › 추천 로딩 2차 — 계측·배당 캐시 1일·stale-while-revalidate (2026-10-23)

## 문제

plans/65 이후에도 리밸런싱 › 목표 조정 탭(기본 "추천")이 느렸다. 65는 실측 없이 끝나서 어느 구간이 지연의 주원인인지 알 수 없었다.

## 원인 (65 이후 남은 것)

결과 캐시(`goal_recommendation_key`, 1h)가 미스나면 `_compute_goal_recommendation`이 아래를 순서대로 실행한다.

| 단계 | 캐시 TTL(이전) | 콜드 비용 |
|---|---|---|
| CAGR 10년 `get_historical_returns` | 1d | yf 배치 다운로드. 실패한 국내 종목은 pykrx |
| 후보 배당수익률 `_fetch_dividend_yields` | **1h** | 종목마다 Naver/Yahoo 스크래핑 |
| 시장신호 `get_market_signal` | 1h | FRED 등 |
| 일별수익률 `_fetch_candidate_returns` | 1d | yf 순차 다운로드 |
| SLSQP | – | CPU |
| 배당목표 제안 `_suggest_for_dividend_goal` | **1h** | 배당목표가 있으면 `RECOMMENDATION_UNIVERSE` 전체 배당 스크래핑 |

1. 결과 캐시와 배당 캐시가 둘 다 1h라 함께 만료된다. 1시간 넘게 지나 다시 열면 결과를 재계산하면서 스크래핑도 다시 한다.
2. 만료되면 그냥 미스다. 그 시점의 사용자는 전체 계산이 끝날 때까지 기다린다. 프론트 영속 캐시는 같은 기기에서만 도움이 된다.
3. 캐시가 인메모리라 Render 슬립이나 재배포 뒤에는 전부 콜드다(이 계획 범위 밖, 계획 59 D1).

## 조치 (완료)

- **P0 계측**: `goal_recommendation_timing` 로그를 남긴다. 키는 `candidates_ms`, `cagr_dividend_signal_ms`, `daily_returns_ms`, `optimizer_ms`, `dividend_suggest_ms`, `total_ms`, 후보 수다. 일별수익률 캐시 적중 여부는 `goal_daily_returns_cache`(hit/miss)로 남긴다. 캐시가 모두 미스인 요청의 전체 시간은 `goal_recommendation_cold_request`로 남긴다.
- **P1** `TTL_GOAL_CANDIDATE_DIVIDEND_YIELD` 1h → 1d(`TTL_DIVIDEND_INFO`와 같음). 이제 1h 뒤 재계산할 때 남는 비용은 시장신호와 SLSQP 정도다.
- **P2 stale-while-revalidate**:
  - 정상 결과를 저장할 때 `goal_recommendation_stale_key`(1d)에도 쓴다.
  - 엔드포인트 동작: 1h 키를 먼저 본다. 미스이고 stale이 있으면 stale을 즉시 반환하고, FastAPI `BackgroundTasks`로 `refresh_goal_recommendation_in_background`를 예약한다. 이 갱신은 자기 `AsyncSessionLocal`을 쓰고, `inproc_lock`으로 유저당 1건만 돌며, 실패하면 로그만 남긴다. 둘 다 없으면 기존처럼 계산한다.
  - 입력 변경 시에는 stale도 지운다. 대상: `invalidate_goal_recommendation_caches`(목표·후보·옵션)와 `invalidate_asset_account_caches(positions_changed=True)`. 평가액만 바뀐 sync는 stale을 남긴다(1h 키와 같은 트레이드오프).
- 정리: overview·포지션으로 `(base_krw, existing_items)`를 만드는 코드가 엔드포인트와 추천 변화 알림 job에 중복돼 있었다. 이를 `build_overall_recommendation_inputs()`로 합쳤고, 계산까지 묶은 `get_overall_goal_recommendation_for_user()`도 추가했다.

## 남은 항목

- **운영 실측**: 배포 후 Render 로그의 `goal_recommendation_timing`으로 재기동 직후(전부 콜드), 1h 경과(SWR), 웜 세 경우를 확인한다.
- **P3 공유 캐시 예열**(실측 후 결정): 기동 시나 정기 sync 뒤에 유니버스와 등록 후보 합집합의 CAGR·일별수익률·배당을 미리 채운다.
- by-horizon·by-age 경로의 SWR — 기본 진입인 "전체"부터 적용했다.
