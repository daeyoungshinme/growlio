# 65. 리밸런싱 › 목표 조정 탭 로딩 속도 개선 (2026-10-22)

## 문제

목표 조정 탭(기본 "추천" 모드)을 열면 카드 전체가 스켈레톤으로 오래 멈춰 있었다.

## 원인

1. `RecommendationCard`가 `GET /rebalancing/goal-recommendation` 응답 전까지 카드 전체(기준 segmented·후보/설정 버튼 포함)를 `SkeletonCard`로 대체했다.
2. 콜드 계산이 무거움 — CAGR·배당수익률·시장신호는 캐시가 있었지만 MVO 입력인 1년 일별수익률(`fetch_yf_daily_returns`)은 캐시가 없었다. `yf.download(threads=False)`로 후보를 순차 다운로드한 뒤 SLSQP + 배당 후보 제안을 실행한다. 기간별 추천은 조합(최대 15개)마다 같은 심볼을 반복 조회했다.
3. 결과 캐시(1h)를 sync마다 `positions_changed`와 무관하게 지웠다. 15:30/18:00 정기 sync, 전체 갱신 때마다 지워져 실사용에선 거의 매번 콜드 계산이었다. Render 슬립 복귀 시에도 in-memory 캐시가 사라진다.
4. 엔드포인트가 결과 캐시를 확인하기 전에 `build_portfolio_overview`(non-lite)와 포지션 조회를 먼저 실행했다.
5. 프론트 워터폴: lazy `GoalAdjustTab` → lazy `RecommendationCard` 청크를 받은 뒤에야 쿼리가 시작됐다. `goal-recommendation`은 영속 캐시 대상이었지만 기본 gcTime(30분)이 지나면 저장본에서 빠졌다.

## 조치 (완료)

- **A1** `RecommendationCard`: 조기 return 제거 — "전체" 결과 영역만 로딩 안내+스켈레톤/오류+재시도. 백그라운드 갱신 중 "업데이트 중" 표시.
- **A2** 전체 추천 쿼리 `gcTime: STALE_TIME.DAY`(신규 상수) — 영속 캐시(maxAge 24h)에 남아 재방문 즉시 표시.
- **A3** `RebalancingPage`: 목표 조정 › 추천이면 같은 queryKey로 전체 추천·settings를 미리 발화.
- **B1** `_fetch_candidate_returns(cache=)`: 심볼별 일별수익률 전역 캐시(`daily_returns_key`, 1일). 전체/연령대/기간별 세 경로 모두 적용. 실패 심볼은 미캐싱.
- **B2** `invalidate_asset_account_caches`: 추천 캐시 3종은 `positions_changed=True`일 때만 무효화.
- **B3** `get_cached_goal_recommendation()` — 엔드포인트가 먼저 확인해 히트 시 overview·포지션 조회 생략.

## 남은 항목

- **실측 미수행** — 실제 데이터로 콜드/웜 응답 시간을 측정하지 않았다. 운영 Render에서 콜드 계산 시간이 여전히 길면 B4(단일 호출 경로의 일별수익률 다운로드를 세마포어 아래에서 묶음 병렬화)를 검토한다. `threads=True`는 크래시 이력이 있어 금지.
- Render 슬립으로 in-memory 캐시가 사라지는 문제는 이 계획 범위 밖이다(외부 핑, 계획 59 D1).
