# 77. 기술부채 감사 (2026-10-27)

## Context

계획 61(10-20) 이후 계획 62~76이 들어왔다. 정적 검사(ruff·ruff format·mypy·tsc·eslint·prettier)는 0건이고 main CI(3ea45f25)도 녹색이었다. 그래서 이번 감사는 세 축을 봤다.

1. **브랜치 상태**: 61의 실버그 5커밋이 `fix/tech-debt-2026-10-20`에만 있고 main에 병합된 적이 없었다.
   - `YEAR_END_TAX_REMINDER`(21자) → `alert_history.alert_type` `String(20)`. 이력 저장이 실패하고 같은 날 중복 판정도 무력화된다.
   - **11-02(월) 09:00 KST 첫 발송** 전에 배포가 필요하다.
   - 61의 `at1` 마이그레이션은 `ix1`을 이었는데 main의 `ta1`도 `ix1`을 이어서, 그대로 병합하면 head가 2개가 된다.
2. **지수 그룹(74/76) 일관성**: 그룹을 모르는 드리프트 계산이 두 곳 남아 있었다.
3. **62 잔여(C·F) 중 실버그 성격**.

상태: **A~D 완료**. 브랜치 `fix/tech-debt-2026-10-27`, 배치별 커밋.

## 배치 A — 계획 61 병합 (P0)

- `fix/tech-debt-2026-10-20`을 merge(커밋 bda2146b).
- `at1` down_revision `ix1` → `ig2_portfolio_item_member_leverage`. `alembic heads` 단일 확인.
- 충돌 해결:
  - AUTO job: 61의 항목별 격리(`_process_one_alert`)에 71의 TACTICAL 게이트(`tactical_regime_for_gate`)를 이식.
  - FRED: 61의 `_fred_today()`와 main의 `observation_start` 인자를 병행.
  - `useWidget`: 72의 캐시 구독 방식을 유지(조회가 없어 61의 인증 `enabled` 가드 불필요).
  - `App.tsx`: 72가 제거한 `SentryRoutes`는 되살리지 않고 cacheOwner 이벤트만 반영.
- 62 A8(AUTO 알림별 격리)도 이 병합으로 해소.

## 배치 B — 지수 그룹 일관성

- **B1 실버그** `insight_service._check_rebalancing_opportunity`: 드리프트를 티커 단위로 따로 계산해서, 그룹(대표 VOO + 멤버 SPY)을 목표대로 보유해도 "리밸런싱 필요 70%p"가 떴다.
  - 단일 판정 `compute_portfolio_drift_summary`(63 P1-3)로 교체했다. 기준 자산·암묵 예수금도 알림과 같아진다.
- **B2** 전략 비교 `_build_trade_recommendations`: 멤버 보유분은 "전량 매도", 대표는 "비중 확대"로 나왔다.
  - 그룹 대표 키로 합산하고, 레버리지 멤버는 분석과 같이 평가액×배수로 계산한다.
  - 멤버→대표 매핑은 `group_expansion.group_owner_map`으로 공용화했고 `fold_into_portfolio_groups`가 재사용한다.
  - fold는 투자금 기준이라 배수를 적용하지 않는다(저장 비중 합 100% 유지). 기존 동작 그대로다.
  - `overview_enrichment`의 dict/attr 분기는 `_item_get`으로 바꿨다.
- **B3** 전략 비교 캐시: 주문 실행에서만 지워서 포트폴리오 수정·전술 적용 뒤 1시간 동안 이전 목표 기준 추천이 보였다.
  - `invalidate_rebalancing_analysis_cache`가 `invalidate_rebalancing_strategy_cache`도 호출하게 했다.
  - execution_service의 중복 호출은 제거.

## 배치 C — 62 잔여 중 실버그

- **C1(62 F1)** `TacticalStatusView`에 `key={status.portfolio_id}`.
  - 캐시된 포트폴리오로 돌아가면 "방금 적용" 상태가 이어져 적용 버튼이 사라지거나, 열린 확인창이 다른 포트폴리오에 적용될 수 있었다.
  - 미캐시 포트폴리오는 로딩 중 언마운트되어 재현되지 않으므로 테스트는 캐시된 포트폴리오로 복귀하는 경로로 고정했다.
- **C2(62 C1·C2)**:
  - `invalidateRebalancingAlertData`에 `drift-summary` 추가.
  - `invalidatePortfolioData`에 `rebalancing-alerts`와 `portfolio-expected-metrics`(새 `portfolioExpectedMetricsBase` 프리픽스) 추가.
  - 두 키는 `refetchType: "none"`(stale 표시만)이다. 적용 확인창이 열린 채 무거운 기대지표 재계산을 기다리면 `onSuccess`가 늦어지기 때문이다(테스트에서 실제로 드러남).
- **C3(62 F2)** GET `/tactical/{id}`의 국면 갱신+커밋과 07:40 job 경합 검토.
  - `step_confirmation`이 같은 날·같은 관측에 결정적이다.
  - 알림은 job만 `notified_regime` 비교로 보낸다.
  - 따라서 경합해도 결과가 같다. 코드 변경 없이 근거 주석과 수렴 테스트만 추가했다.

## 배치 D — 문서

- 이 문서와 README 행을 추가하고, 74·76 "미커밋" → PR #154 병합으로 고쳤다. 62 행에는 A8·C1·C2·F1·F2 처리를 반영했다.

## 이관 (이번 범위 밖)

- 62 D(죽은 코드·중복)·E(구조) 전체, 62 F 나머지(스키마 이동·`fred_circuit` 체크·프론트 정리), 62 C3~C5(래퍼 정리·queryOptions 팩토리).
- 67 잔여(바텀시트·virtualizer·InfoTip·실기기), 65 B4(다운로드 병렬화), 66 P3 예열.
- `portfolio_item_members`의 중복 인덱스. `idx_portfolio_item_members_item`은 unique 제약 앞 열과 겹치지만 마이그레이션이 필요해 저가치.
- 동일 티커 다시장 가격 키 충돌(62 이관 유지), 74 수동 실행 모달의 국내 대체 자동 전환.
- 추천 fold의 레버리지 해석: 추천이 레버리지 ETF를 내는 경우는 드물다. 노출 기준으로 바꾸려면 저장 비중 의미부터 정해야 한다.

## 검증

- 백엔드: ruff·format·mypy 클린, `pytest --cov` 3021+ passed(병합 직후 91.69%).
- 프론트: tsc·eslint·prettier 클린, vitest 1823 passed.
- `alembic heads` 단일(`at1_widen_alert_history_alert_type`).
- 회귀 테스트(전부 수정 전 코드에서 실패 확인):
  - `test_insight_service::test_index_group_counts_member_holdings`
  - `test_rebalancing_strategy_service::test_index_group_member_holdings_count_toward_group`·`test_leveraged_member_counts_exposure`
  - `TacticalAllocationTab.test` "포트폴리오를 바꾸면 방금 적용한 상태를 이어받지 않는다"

## 배포 전후 확인

- **배포 전**: 공유 Supabase에 `at1` 적용(`alembic upgrade head`). 10-20 시점엔 ix1도 미적용이었다. 운영은 Render `preDeployCommand`가 수행한다.
- **11-02(월) 09:00 이후**: 연말 리마인더가 `alert_history`에 1건만 남는지 확인.
- 61 문서 하단 배포 후 확인 4건(08:30 다이제스트 1회, 공유 기기 로그아웃 → 다른 계정 로그인 시 이전 계정 푸시 미수신 등).
