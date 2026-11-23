# 148. 낙폭 추매 안내 재구성 — 포트폴리오에서 분리, 여윳돈 하나 + 지수별 규칙, 전술 탭과 역할 정리 (2026-11-23)

## Context
사용자 요청: "리밸런싱 > 목표조정 > 전술과 계획탭 낙폭 추매 안내가 겹치는 것 같다, 개선 검토 + QQQ·SPY 중 하나만 설정 가능한데 둘 다 되게." 이어서 "여윳돈 하나에 설정은 여러 개, 월 적립금액처럼 특정 포트폴리오에 종속되지 않게."

## 검토 — 겹침과 충돌
| | 전술 탭 "웅덩이 매수(눌림목)" (`tactical/tactical_dip.py`) | 계획 탭 "낙폭 추매 안내" (plans/147) |
|---|---|---|
| 신호 | QQQ 60·120일선 눌림+RSI, 공격(RISK_ON) 국면만 | QQQ/SPY 52주 고점 대비 구간 |
| 돈 | 포트폴리오 안 현금 비중 → 주식(목표 비중 변경) | 계좌 밖 여윳돈 |
| 결과 | 제안 비중 적용 시 리밸런싱 주문 | 금액·ETF 안내만, 주문 없음 |

1. 둘 다 "떨어지면 더 산다"인데 관계 설명이 없었다.
2. 적립 자동매수 포트폴리오는 전술 탭이 비중 적용 대신 전술 연동을 권해 웅덩이가 실행되지 않는다 → 적립 사용자의 추매는 낙폭 추매 몫.
3. 충돌: 전술 연동(`market_condition_mode=TACTICAL`) 포트폴리오는 방어 국면에 적립 자동매수를 보류하는데, 같은 때(−20% 낙폭은 대개 방어 국면) 낙폭 추매는 "추매하세요"를 보낸다.

통합은 하지 않는다 — 재원(포트폴리오 내 현금 vs 외부 여윳돈)과 실행(주문 vs 안내)이 달라 합치면 147의 "적립금은 줄이지 않는다" 전제가 깨진다.

## 결정(사용자)
- 충돌: 추매는 그대로 안내하고 "적립 자동매수는 전술 방어 국면이라 보류 중"을 카드·알림·홈 할 일에 함께 표시.
- 여윳돈은 사용자당 하나, 포트폴리오와 무관.
- 규칙은 지수(QQQ·SPY)마다 하나, 각 규칙이 여윳돈 배분 %(합 ≤100)를 갖고 구간 비율은 그 몫 안에서.
- 살 종목: 금액 + 목표 조정 › 추천의 등록 후보 ETF 중 그 지수 추종 ETF별 매수 가능 수량(대안 목록).
- 알림 시점은 사용자 선택: 구간 도달 다음 날 아침(ON_REACH) / 매달 정한 날(MONTHLY_DAY, 사전 1~3일 + 당일).

## 구현
- 마이그레이션 `db2_dip_buy_user_level`: `dip_buy_settings`(사용자당 1행)·`dip_buy_rules`(사용자·지수 unique) 생성, `dca_dip_buy_plans`를 이관 후 드롭(여윳돈 = 사용자 플랜 합, 지수별 첫 플랜 → 규칙, 배분 균등, 완료 기록 유지·사이클 기준액은 버림). **운영 수동 적용, 코드 배포 전에**(db1이 운영에 없으면 db1→db2 함께).
- 규칙 몫 = (남은 여윳돈 + 진행 중 사이클 추매액) × 배분% — 한 규칙의 추매로 다른 규칙 몫이 줄지 않는다. 사이클 첫 추매 때 고정. 안내액은 규칙 남은 몫·남은 여윳돈 상한(동시 발동은 생성 순으로 차감). 여윳돈·배분을 고치면 사이클 중 기준액을 새 풀로 재계산.
- ETF 대안: `etf_index_classifier.classify_holding`(네트워크 없음)으로 `US_NASDAQ100`/`US_SP500` INDEX만 — 레버리지·커버드콜 제외. 수량은 내림. 후보 시딩은 하지 않는다.
- 전술 보류 판정: `order_builder.tactical_regime_for_gate` + `is_market_signal_blocking_auto_mode("TACTICAL", …)` 재사용.
- 알림 잡(id 유지): 08:10 ON_REACH 새 구간만 1회(`notified_tiers`, 사이클 초기화 때 비움) + MONTHLY_DAY 당일/취소, 18:40 MONTHLY_DAY 사전. 사용자당 한 건으로 묶음. dedup `dip_buy:{user_id}:{date}:{slot}`.
- API: `GET /invest/dip-buy`, `PUT /invest/dip-buy/settings`, `POST /invest/dip-buy/rules`, `PUT|DELETE /invest/dip-buy/rules/{id}`, `POST /invest/dip-buy/rules/{id}/complete`.
- 프론트: `DipBuyCard`(여윳돈 요약·규칙 카드·ETF 대안·보류 안내), `DipBuySettingsModal`(여윳돈·알림 방식), `DipBuyRuleModal`(지수·배분·구간). 추천 후보 변경(`invalidateGoalRecommendationData`)이 추매 카드도 무효화.
- 전술 탭: 적립 포트폴리오면 웅덩이 요약 아래 "낙폭 추매 안내" 링크, 웅덩이 투입폭 설명에 구분 문구.

## 검증
- 백엔드 `tests/test_dip_buy.py`(규칙 몫·동시 발동 상한·배분 검증·기준액 재계산·회복 초기화·ETF 매칭·수량·알림일 휴장 이월·CRUD/404/409/422·잡 ON_REACH 1회·MONTHLY 사전/당일/취소/dedup·전술 보류·메일), `test_action_items_service.py` DIP_BUY. 전체 4228 passed, 커버리지 93.8%.
- 프론트 `components.dipBuyCard.test.tsx`, `TacticalAllocationTab.test.tsx`(링크), `queryInvalidation.test.ts`.
- 로컬 DB가 없어 `alembic check`는 못 했다. `alembic upgrade db1:db2 --sql`로 DDL·이관 SQL만 확인.
- 실데이터·실기기 확인 안 함.
