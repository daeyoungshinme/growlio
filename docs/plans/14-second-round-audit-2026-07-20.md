# 계획 14: 2차 재감사 — 요구사항 완결성 + UX 흐름 관점 (2026-07-20 밤)

## 배경 (Why)

2026-07-20 하루 동안 이미 3~4차례 "불필요 기능 제거·병합 + 탭 UX 개선 + 고도화 로드맵" 감사가 반복되어 `docs/plans/01~13`이 대부분 완료 처리됐다(README 상태표 참고). 사용자가 같은 취지를 다시 요청해, 이번엔 **기존 결론을 신뢰하지 않고 "코드 존재 여부"가 아닌 "실제 비즈니스 로직이 요구사항을 충족하는가" / "사용자 여정 관점의 UX"** 두 축으로 독립 재조사했다(서브에이전트 2개 병렬, 과거 산출물 미참조 지시).

과거 감사들은 주로 dead code·중복 함수·탭 배치 관점이었고, 이번엔 다음 결과가 새로 나왔다.

## 신규 발견

### A. 백엔드 — 요구사항 완결성

| # | 발견 | 근거 | 심각도 |
|---|---|---|---|
| A1 | **배당 목표가 포트폴리오 최적화에 반영 안 됨** | `goal_recommendation_service.py:264-268`에서 `required_dividend_yield_pct` 계산은 하지만, `goal_portfolio_optimizer.py`의 SLSQP 목적함수/제약(`L75, 134, 147-158`)엔 dividend 관련 파라미터가 0건. `expected_dividend_yield_pct`(`L362-366`)는 자산목표만으로 뽑힌 비중에 배당수익률을 사후 대입한 표시값일 뿐 | 중간 — 사용자가 요청한 "배당 목표 달성을 위한 포트폴리오 구성"이 절반만 구현됨 |
| A2 | **AUTO 자동매매에 거래 금액 상한 없음** | `order_builder.py`/`rebalancing_auto_execution.py`/`execution_service.py` 전체에서 "1회 최대 거래액" 류 상한 코드 0건(grep). 중복실행 방지·재시도 격리 등 다른 안전장치는 견고하나 금액 캡은 없어 계좌 잔고만큼 자동 매매될 수 있음 | 높음 — 실자금 안전장치 공백 |
| A3 | 연금저축/IRP/ISA 절세 로직이 **상태 표시에 그침, 실행 타이밍 추천 없음** | `pension_contribution_service.py:17-21`이 "세액공제율은 이 화면에서는 계산하지 않습니다"라 명시. 한도 잔여액만 보여주고 "언제·얼마"를 제안하지 않음(단, Tax-Loss Harvesting은 `tax_service.py:270-302`에서 예외적으로 구체적 실행 추천 있음) | 낮음~중간 — 기능 확장 아이디어 |
| A4 | 시장신호 8개 지표의 개별 임계값이 **백테스트 근거 없는 수동 상수** | `market_signal_service.py` 예: VIX 20/25/30(`L72-83`), DXY 이격도 1/3/5%(`L194-205`); `compute_composite_signal`(`L469-543`)은 단순 동일가중 합산(`L494`) | 낮음 — 기존에도 알려진 설계 한계, 정밀 검증은 별도 리서치 프로젝트 규모 |

### B. 프론트엔드 — UX 흐름

| # | 발견 | 근거 | 심각도 |
|---|---|---|---|
| B1 | **목표 달성 알림(GOAL_ASSET/GOAL_DEPOSIT/GOAL_DIVIDEND) 끄는 UI가 없음** | `usePushNotifications.ts:63-67`, `SettingsPage.tsx` 라벨 매핑엔 존재하나 on/off 토글이 어디에도 없음 — 사용자가 이 알림을 원치 않아도 끌 방법이 없음 | 높음 — 실제 버그(설정 불가능한 알림) |
| B2 | 진단탭에서 `DiagnosisSummaryHeader`(요약)와 `RebalancingStatusCard`(상세, `showAllInsights=true`)가 **같은 드리프트 정보를 연속 두 번** 표시 | `RebalancingPage.tsx:170-186` | 중간 — 카드 인플레이션의 실제 원인 |
| B3 | 대시보드 카드 7개 중 `InvestmentSnapshotCard`/`AllocationHistoryChart` 2개만 접힘 미지원, 나머지는 지원 — **접힘 처리 일관성 부재** | `DashboardPage.tsx:150-202`, grep `CollapsibleCard` 미사용 확인 | 낮음 |
| B4 | 기간×계좌유형 추천 카드(`RecommendationCard.tsx`)가 **리밸런싱탭의 비기본 하위탭("포트폴리오")에 숨어있어 발견성 낮음** | `RebalancingPage.tsx:217-226`, 기본 하위탭은 "진단" | 중간 — 핵심 기능인데 첫 방문자가 못 찾음 |
| B5 | 알림 관리가 설정탭(요약+딥링크, 의도된 설계)과 `PortfolioManageTab.tsx`(`?openAlert=1`, 실제 편집기) 2곳으로 분산 — 기존에도 알려졌으나 실제 편집 진입점이 리밸런싱탭에만 있다는 점이 이번에 명확해짐 | `MarketSignalBanner.tsx:454` 주석, `PortfolioManageTab.tsx` | 낮음 — 의도된 설계, 개선 여지만 있음 |

각 발견 심각도는 예상과 다르게 나왔다: **A2·B1이 가장 실질적** — A2는 사용자가 명시적으로 요청한 "자동 매수/매도" 기능의 안전 공백이고, B1은 이미 존재하는 기능(알림)을 사용자가 제어할 수 없는 명백한 UI 누락이다. 나머지는 개선하면 좋지만 급하지 않음.

## 권장 우선순위 → 구현 결과 (2026-07-20 같은 세션에서 1~6번 전부 완료)

1. **B1 (알림 on/off 토글 추가) — 완료.** `UserSettings.goal_achievement_alerts_enabled`(기본 True, 마이그레이션 `314d148b8f35`) 신규 컬럼 + `PUT /settings/goal-achievement-alerts` + `goal_achievement.py` job 쿼리에 필터 추가. 프론트 `useGoalAchievementAlertsToggle.ts` 신규, `SettingsPage.tsx` "다른 설정" 카드에 토글 추가.
2. **A2 (AUTO 거래 금액 상한) — 완료.** `Settings.auto_rebalancing_max_order_value_krw`(기본 5천만원, env로 조정 가능) + `order_builder.clamp_orders_to_max_value()` 신규 — `plan_service.generate_pending_plan_for_alert()`(AUTO 스케줄러·quick-execute 공용 대기 플랜 생성 경로)에서 주문 생성 직후 적용. 상한 초과 시 수량 축소, 1주도 못 사면 스킵.
3. **B2 (진단탭 중복 카드 통합) — 완료.** `RebalancingStatusCard`에 `showCombinedNote` prop 추가(기본 true) — 진단탭에서만 `false`로 낮춰 `DiagnosisSummaryHeader`와 같은 문구가 두 번 뜨는 것 방지.
4. **B4 (추천 카드 발견성) — 완료.** `InvestmentGoalCard.tsx` 하단에 "목표에 맞는 포트폴리오 추천 보기 →"(`/rebalancing?rtab=포트폴리오`) 딥링크 추가.
5. **A1 (배당목표 최적화 반영) — 완료.** `_optimize_goal_portfolio()`에 `dividend_yields`/`required_dividend_yield_pct` 파라미터 추가, 달성 가능하면 SLSQP 부등식 제약으로 반영, 불가능하면 fail-soft(제약 무시+note 안내). `goal_recommendation_service._compute_goal_recommendation()`(전체 자산 기준 경로만)이 연동. by-horizon 경로는 범위 밖 유지(목표금액 역산을 안 하는 별도 경로).
6. **B3 (접힘 일관성) — 완료.** `InvestmentSnapshotCard`를 `CollapsibleCard`로 전환(신규 접힘 지원), `AllocationHistoryChart`의 독자 `useState` 토글을 공용 `useCollapsible`(localStorage 영속화)로 교체.
7. **A3 (절세 타이밍 추천)** — 미착수, 기능 확장급이라 별도 계획 필요.
8. **A4 (임계값 검증)** — 미착수, 리서치 프로젝트 규모, 로드맵 참고용으로만 유지.

검증: 백엔드 1721 tests 86.52%(ruff/mypy clean), 프론트 1318 tests(tsc/eslint clean).

## 동시 세션 주의사항

이 조사 시점 워킹트리에 계획 13번(시장신호 매일 다이제스트) 구현이 미커밋 상태로 존재했음 — 이 문서가 언급하는 파일들과 겹치지 않아 충돌 없음.
