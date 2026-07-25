# 시장 위험 신호(복합 매크로 리스크 스코어) 방법론 개선

## 배경

리밸런싱 진단 화면의 "위험지수"(예: 26/26)는 `backend/app/services/market_signal_service.py`가 8개 매크로 지표(VIX·장단기금리차·Fear&Greed·하이일드스프레드·달러인덱스·금리인하기대·원달러환율·유가)를 각각 0~4점으로 채점해 단순 합산한 값이다. 이 스코어는 화면 표시뿐 아니라 **AUTO 리밸런싱 실행 게이트**(`order_builder.is_market_signal_blocking_auto_mode`)와 알림 트리거(등급전환 즉시알림, 복합신호 알림, 매일 다이제스트)에 실질적으로 쓰인다.

2026-07-23, 사용자가 "위험지수 26"의 의미를 물은 데서 시작해 "8개 지표로 판단하는 게 맞는지" 방법론 검토를 요청, 아래 6가지 약점을 확인했다:

1. **가중치 근거 부재** — 지표별 상한(3~4점)이 "기존 비율 유지"로만 산정, 실제 하락장 예측력 등 경험적 근거 없음.
2. **지표 간 다중공선성** — 장단기금리차(T10Y2Y)와 금리인하기대(DGS2-FEDFUNDS)가 둘 다 "Fed 정책금리 경로 기대"라는 동일 정보를 반영 → 위기 시 동시 악화로 같은 리스크를 이중 계상.
3. **Fear & Greed Index의 태생적 한계** — alternative.me API는 크립토 시장 지표. 일반 주식시장 심리 프록시로 쓰기엔 근거 약함.
4. **국내 지표 전무** — 한국 투자자 앱인데 8개 중 원/달러 환율 외 전부 미국/범용 지표.
5. **Hysteresis 없음** — 1시간 캐시 갱신마다 그 순간 raw 값만으로 레벨 재계산 → 경계값 부근 flapping 가능(알림 피로·AUTO 게이트 불안정).
6. **이진 레벨 기반 게이트의 정보 손실** — RED가 15점이든 26점이든 AUTO 게이트 판정 동일.

사용자 결정: 금리 커브 신호 **완전 병합**, Fear & Greed **완전 제거**. Phase 1은 이번 세션에 구현.

## Phase 1 (이번 세션 완료 목표)

1. **Fear & Greed Index 완전 제거** — `fetch_fear_greed_signal`/`_call_fng_api`/FNG 상수/`fear_greed_circuit`/`cb_fng_*` config/프론트 `FearGreedSignal` 타입·배너 행·contrarian_buy/extreme_greed 플래그 전부 삭제.
2. **미국 금리 커브 신호 병합** — T10Y2Y + DGS2-FEDFUNDS를 `fetch_us_rate_curve_signal()` 단일 함수로 묶고 `sub_score = max(두 원신호 sub_score)`(worst-case, 이중계상 방지). 프론트 `signals.us_rate_curve` 단일 필드로 통합.
3. **복합점수 상한 재계산** — 6개 신호(VIX 4 + us_rate_curve 3 + 하이일드 4 + 달러인덱스 3 + 환율 3 + 유가 3 = 20). `COMPOSITE_SCORE_MAX=20`, `_GREEN_MAX=5`(0-5 GREEN), `_YELLOW_MAX=11`(6-11 YELLOW), RED 12-20 — 기존 비율(23%/54%) 유지 재계산.
4. **Hysteresis(확정 레벨) 도입** — `get_market_signal()`은 raw 그대로 유지(표시용), 신규 `get_confirmed_composite_level(cache, db)`가 durable_state(`market_signal_last_level_key` 재정의 + 신규 `market_signal_pending_confirmation_key`)로 연속 2회(≈2시간) 관측 후에만 레벨을 승격. **AUTO 게이트 4곳**(`jobs/rebalancing_auto_execution.py`, `plan_service.execute_due_buy_legs`, `api/v1/rebalancing_execution.py`, `alert_check.py`)과 **등급전환 즉시알림**(`market_signal_alert_service.check_market_signal_level_change`)만 confirmed 사용, 배너/진단화면/일일다이제스트/드리프트 복합신호 트리거는 raw 유지.

상세 설계·의사코드·영향 테스트 목록은 세션 대화 로그 참고(이 문서는 로드맵 인덱스 요약).

## Phase 2 (계획만, 별도 세션)

- Fear & Greed는 완전 제거로 확정됐으므로 "처리 방식 옵션 비교"는 불필요해짐(해소됨).
- AUTO 게이트를 이진 레벨이 아닌 raw score 구간 반영(STRICT에서 고득점 구간 추가 보수화) — `RebalancingAlert` 스키마 확장 가능성 있어 중위험, 사용자 확인 후 진행.

## Phase 3 (리서치만, 코드 구현 범위 밖)

국내 고유 리스크 신호 후보 조사:
- V-KOSPI200(KRX 변동성지수) 무료 API/데이터 존재 여부, `pykrx` 지원 여부
- 국내 회사채-국고채 신용스프레드 — 한국은행 ECOS API 시리즈 존재 여부
- 외국인 순매수/순매도 — KRX 정보데이터시스템/네이버 금융(기존 스크래핑 인프라 재사용 가능성)
- 각 후보의 갱신 지연·rate limit·서킷브레이커 적용 가능성

리서치 완료 후 별도 계획 파일로 분리, Phase 1의 정성적 가중치 분류(Tier A/B/C)를 정량화하는 방법도 함께 조사.

## 상태
- Phase 1: **완료** (2026-07-23, 이 세션) — Fear & Greed 완전 제거, 미국 금리 커브 병합(`fetch_us_rate_curve_signal`, worst-case sub_score), 상한 26→20점 재계산(GREEN 0-5/YELLOW 6-11/RED 12-20), hysteresis(`get_confirmed_composite_level`, 연속 2회 관측 후 반영) 도입해 AUTO 게이트 4곳(`jobs/rebalancing_auto_execution.py`/`plan_service.execute_due_buy_legs`/`api/v1/rebalancing_execution.py`/`alert_check.py`)+등급전환 즉시알림(`market_signal_alert_service.check_market_signal_level_change`)을 confirmed level로 전환. 표시용(`get_market_signal`, 배너/진단화면/일일다이제스트)은 raw 유지. 부수 발견: `jobs/rebalancing_auto_execution.py`가 `AsyncSessionLocal()` 블록 밖에서 시장신호를 먼저 조회하던 순서 버그를 함께 수정(hysteresis에 db 필요해지며 노출됨). 프론트 `marketSignals.ts`/`MarketSignalBanner.tsx`도 FNG 제거+`us_rate_curve` 단일 필드로 갱신. 캐시 키 버전 `_MARKET_SIGNAL_VERSION` v5→v6(스키마 변경으로 구버전 캐시 분리). 백엔드 1900 tests/ruff·mypy clean, 프론트 1383 tests/tsc·eslint clean.
- Phase 2/3: 계획만 (미착수) — Phase 2(AUTO 게이트 raw score 반영)는 사용자 확인 후, Phase 3(국내 리스크 지표 리서치)은 별도 세션 권장.
