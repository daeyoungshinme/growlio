# 계획 130 — 대형 파일 분할 (2026-11-14)

## Context

계획 122부터 매번 이관되던 "550줄↑ 백엔드 11개·500줄↑ 프론트 4개 분할"을 처리했다(사용자 요청: 계획 129 남은 항목 처리). 동작 변경은 없다 — 함수·상수를 옮기고 import·테스트 patch 경로만 바꿨다.

분할 경계는 **테스트 patch가 깨지지 않는 곳**으로 골랐다. 옮긴 함수가 patch 대상 이름을 부르면 patch가 새 모듈에 닿지 않으므로 둘 중 하나로 처리했다.

- 원래 모듈이 옮긴 이름을 import해 쓰면(`plan_generation` ← `plan_gates`) 원래 경로 patch가 그대로 유효하다.
- 새 모듈이 원래 모듈의 헬퍼를 부르면 모듈 속성(`plan_execution as _pe`, `_goal_recommendation_common as _grc`)으로 불러 patch 경로를 하나로 유지한다(`_grc` 선례).

## 백엔드

| 파일 | 전 → 후 | 새 모듈 |
|---|---|---|
| `services/fx_plan_service.py` | 753 → 548 | `fx_plan_alerts.py` — 계획 구간 알림 맞추기(`sync_fx_plan_alerts`) |
| `rebalancing/plan_execution.py` | 743 → 545 | `plan_fx_wait.py`(환전 대기 재매수·자동 재확인), `plan_sweeps.py`(실행 결과 유실 leg 마감·매도 승인 만료) |
| `rebalancing/plan_generation.py` | 667 → 523 | `plan_gates.py` — 생성 안 함 sentinel·세금영향·스냅샷 신선도 게이트(하루 한도 게이트는 오늘 누적 조회와 함께 남김) |
| `rebalancing/service.py` | 649 → 469 | `analysis_items.py` — 항목 접근·그룹 행 조립·현재 보유 맵·배당 정보 |
| `goal/goal_portfolio_optimizer.py` | 678 → 518 | `goal_portfolio_weights.py` — 공분산·비중 반올림·기대 지표 |
| `goal/_goal_recommendation_common.py` | 614 → 441 | `_goal_dividend_suggestions.py`(`_gds`) — 배당 목표 후보 제안·가중평균 |
| `goal/goal_recommendation_service.py` | 598 → 553 | `recommendation_drift.py` — 추천 변화 판정(프론트 `recommendationDrift.ts` 짝) |
| `goal/goal_horizon_recommendation_service.py` | 592 → 477 | `goal_horizon_policy.py` — 조합 정책(자산군·시장 필터·단기 주식 하한·IRP 안전자산) |
| `tax/tax_action_service.py` | 609 → 136 | `tax_action_builders.py` — 세법 테이블·우선순위·액션 빌더(순수) |
| `notifications/email_templates/rebalancing.py` | 581 → 375 | `rebalancing_blocked.py` — AUTO 게이트 차단·적립 자금 부족 메일 |

남긴 것:

- `notifications/email_service.py`(575) — 템플릿마다 `send_*` 하나인 평면 API. 호출부 약 30곳이 이름으로 import하고 테스트 patch 약 100곳이 이 경로다. 나누면 재노출 shim이 필요해 실익이 없다.
- `goal_recommendation_service.py`의 필요수익률 역산(`_resolve_*`) — 스냅샷 테스트가 `months_until_year_end`를 진입점 경로로 patch해 옮기지 않았다(553줄).

## 프론트

| 파일 | 전 → 후 | 새 파일 |
|---|---|---|
| `pages/InvestPlanPage.tsx` | 618 → 429 | `invest/DcaSettingsSummaryCard.tsx`(적립 계획 설정 요약), `invest/GoalSettingsEditModal.tsx`(플랫 편집 모달) |
| `rebalancing/RebalancingHistoryTab.tsx` | 576 → 316 | `rebalancing/PendingPlanRow.tsx` — 대기 플랜 leg 행(카운트다운·승인·환전 대기 재매수) |
| `hooks/rebalancingExecution/index.ts` | 552 → 497 | `rebalancingExecution/initialSelection.ts` — 모달 기본 매수 계좌·선택(순수) |
| `portfolio-analysis/PortfolioListSection.tsx` | 538 → 336 | `portfolio-analysis/PortfolioCard.tsx` |

## 검증

- 백엔드: ruff·format·mypy 0건, pytest 3975 passed / 6 skipped(분할 전과 같음), 커버리지 93.67%(게이트 91%). 목표 추천 스냅샷(`test_goal_recommendation_snapshots.py`) 변경 없이 통과.
- 프론트: eslint `--max-warnings 0`·prettier·typecheck(앱·테스트) 통과, vitest 200 files / 2136 passed, `--coverage` 임계값 통과.

## 이관

- drift N+1(의도적 순차), 해외 주가 알림 `target_price_usd`(제품 결정), 129 B1 실행 간 차감(실계좌 확인 대기) — 계획 129 그대로.
- 사용자 작업: 키움 REST 주문의 원화주문 설정 실계좌 1회, 외부 핑 등록 후 `keep-alive.yml` 제거, 2028학년도 수능일 발표 후 `_KRX_CSAT_DAYS` 추가.
