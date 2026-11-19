# 138. 136·137 신규 코드 첫 감사 (2026-11-19)

## Context

136(상대 이탈 밴드·진단 시점 판정)과 137(위험 지표 재계산·시장 종합 판단·진단 요약 칩)이 같은 날 머지됐다(#285·#286). 관례대로 새 코드의 첫 감사를 했다. 백엔드와 프론트엔드를 나눠 감사했고, 핵심 항목은 코드에서 직접 재확인했다.

## A. 실버그 — 완료

- **A1 S&P500 −10% 손실액이 현금을 두 번 줄임** (`risk_service.compute_risk_result`)
  - 베타는 예수금 비중이 든 일별 포트폴리오 수익률로 구한다. 여기에 주식 평가액을 곱해 현금 비중만큼 한 번 더 줄었다. 예수금 50%면 손실액이 절반으로 표시됐다.
  - 수정: `var_95_krw`와 같은 전체 평가액(`total_for_weights`)을 곱한다.
  - 테스트: 예수금이 있는 케이스.
- **A2 종목 최대 비중이 같은 종목을 시장 코드별로 쪼갬** (`risk_service._concentration`)
  - 토스 `US`와 KIS `NASDAQ`의 AAPL이 30%·30%로 따로 집계돼 복합 위험 기준(40%)이 발동하지 않았다.
  - 수정: yf 심볼로 합친 뒤 최댓값을 구한다.
- **A3 시점 판정의 예상 매도 비용에 이탈하지 않은 초과분까지 포함** (`drift_summary_service`)
  - 자동 실행(`plan_generation`)은 이탈 항목만 맞춘다.
  - 수정: `estimate_sell_costs(items, overview)`로 받는 인자를 항목 목록으로 바꾸고, drift-summary는 `filter_drifting_items` 결과만 넘긴다. 진단 카드 세금 미리보기는 지금처럼 전체 항목을 넘긴다.
- **A5 상대 이탈 기준이 선택지 밖 값이면 "끔"으로 표시** (`AlertTriggerSection`)
  - API로 30을 저장하면 화면은 "끔"인데 저장할 때 30이 다시 전송됐다.
  - 수정: `rebalancingConfig.relativeThresholdOptions`가 저장값을 선택지에 보탠다.
- ~~A4 DRIFT_ONLY 다음 예정일~~ — 136 B2가 의도적으로 null("이탈 시" 표기)로 둔 설계라 제외했다.

## B. 안정성·일관성 — 완료

- B1: drift-summary가 시장 신호를 외부 조회하기 전에 `release_read_connection`을 부른다. 복합 신호 알림을 끈 사용자가 캐시 미스를 겪는 경로다.
- B2: 리밸런싱 푸시와 지금 할 일 문구에 상대 기준을 병기한다. 이메일은 136에서 이미 반영했다.
- B3: `RebalancingAlertCreate`에서 SCHEDULE_ONLY이면 `relative_threshold_pct`를 None으로 정규화한다. 이 값이 남아 있으면 `alert_drift_thresholds` 최솟값이 오염된다. 경계값 테스트를 추가했다.
- B4: `pct_change`의 기본 pad(폐기 예정)에 기대지 않도록 `ffill()` + `fill_method=None`으로 바꿨다. 결과값은 같다.
- B5·B6: 진단 요약 칩을 `ErrorBoundary`로 감쌌다. 시장 칩은 이동할 시장 배너(signal)가 있을 때만 만든다.
- B7: 위험 카드 "쏠림" 값이 긴 ETF 이름으로 390px 화면을 넘쳤다. 값만 말줄임하고, 전체 이름은 펼친 설명에 나온다.
- B8: `AutomationStatusBar`와 진단 카드의 안정 문구에 상대 기준을 병기한다.
- B9: 시장 판단 근거 `key` 중복을 막았다. 이탈 칩 문구는 "이탈 포트폴리오 N개"로 바꿨다.

## 이관 (`remaining-tasks.md`)

- 비USD 해외시장(TSE·HKEX·SSE·SGX·LSE) 수익률이 현지 통화 그대로다(`risk_service._USD_MARKETS`). 보유 사례를 확인한 뒤 결정한다.
- 현금성 non-tradable 포지션이 위험 계산에서 현금으로도 종목으로도 잡히지 않는다. 정의를 바꿔야 한다.
- 진단 카드 상태(로컬 분석)와 서버 시점 판정(동기화 스냅샷)이 어긋날 수 있다. 데이터 출처가 달라서이며 UX 결정이 필요하다.
- 위험 계산마다 `get_index_exposure`를 조회한다(콜드 캐시면 최대 20초). 운영에서 실측한 뒤 판단한다.

## 검증

- backend: ruff·format·mypy 통과, pytest 4041 passed.
- frontend: lint·format·typecheck 통과, vitest 2167 passed.
