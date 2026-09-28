# 43. goal `_compute_*` 분해 (2026-09-28, 4차)

계획 42 이관 1번(36 #4) 중 **목표 역산 추천 계산부 분해**만 처리했다. 브랜치는 `fix/tech-debt-2026-09-28`로 같다.
같은 항목의 `create_rebalancing_execution_plan`(라우터→서비스)과 `goal_achievement._check_user_goals`
3중 블록은 계산 로직이 아니라 범위에서 빼고 재이관한다.

순수 이동·추출이며 동작 변경은 없다. 스냅샷 하네스로 **바이트 단위 동일**함을 확인했다.

## 1. 선행: characterization 스냅샷 하네스

`backend/tests/test_goal_recommendation_snapshots.py` + `backend/tests/snapshots/goal_recommendation.json`

- 대상: 세 진입점(`get_goal_recommendation` 12개 / `get_age_based_recommendation` 7개 /
  `get_horizon_recommendations` 4개 시나리오)과 `_optimize_goal_portfolio`(9개 시나리오). `generated_at`을 뺀 **출력 전체**를 고정한다.
  - 분기 범위: 성공, 조기 반환(미설정·목표연도 경과·이미 달성·역산 불가·후보 없음), 수익률 데이터 부족,
    배당 unreachable/improvable/optimal, 단일 세제유형(연금 제외·ISA 큐레이션 보강), 현금성 합성 후보,
    IRP·단기·해외전용 조합, 시장신호 YELLOW/RED, 옵티마이저 no_spread·배당 fallback·달성 불가.
- 고정값으로 바꾼 것: CAGR, 일별수익률(심볼 crc32 시드), 배당수익률, 시장신호, DB, `months_until_year_end`,
  **`RECOMMENDATION_UNIVERSE`**. 그래서 실제 유니버스가 바뀌어도 스냅샷은 깨지지 않는다.
- 실수 비교 허용오차는 0.15다. 플랫폼마다 BLAS가 달라 SLSQP 결과의 마지막 자리가 흔들릴 수 있어서다.
  문자열(노트 문구)은 완전 일치로 비교한다. 시나리오를 삭제·개명해 스냅샷에 고아 키가 남으면 실패한다.
- 갱신 방법: `UPDATE_GOAL_SNAPSHOTS=1 uv run pytest tests/test_goal_recommendation_snapshots.py`.
  **의도적으로 동작을 바꿨을 때만** 쓴다.
- 함정: 모듈 전역 `_yfinance_sem`은 처음 대기가 걸린 이벤트 루프에 묶인다. 투자기간별 조합이 5개를 넘어
  실제로 대기하면 다음 테스트에서 `bound to a different event loop`가 난다. 하네스는 테스트마다 새 세마포어로 patch한다.

기준 스냅샷은 HEAD(`c6b8ca1`) 코드로 별도 worktree에서 생성했다. 그 worktree에서 한 번 통과를 확인한 뒤
본 트리로 복사했다. 이후 리팩터링된 코드로 `UPDATE` 모드 재생성한 JSON과 기준을 `diff`한 결과 **IDENTICAL**이었다.

## 2. 분해 내용

| 함수 | 전 (전체/코드 줄) | 후 |
|---|---|---|
| `goal_recommendation_service._compute_goal_recommendation` | 174 / 161 | 104 / 91 |
| `goal_age_recommendation_service._compute_age_based_recommendation` | 201 / 183 | 113 / 95 |
| `goal_horizon_recommendation_service._build_horizon_result` | 180 / 140 | 102 / 62 |
| `goal_horizon_recommendation_service._compute_horizon_recommendations` | 209 / 196 | 108 / 95 |
| `goal_portfolio_optimizer._optimize_goal_portfolio` | 210 / 152 | 137 / 79 |

**공통 골격을 `_goal_recommendation_common.py`로 옮겼다(세 경로가 복붙하던 부분)**

- 입력 준비
  - `_GoalCandidate` NamedTuple: 과거 5-튜플 두 벌(overall은 `(sym, tk, cagr, dividend, asset_class)`,
    age/horizon은 `(sym, tk, cagr, is_equity, dividend)`)을 통일했다.
  - `_candidates_with_cagr(equity_vs_other=)`, `_has_real_safe_asset`, `_cash_equivalent_candidate`
  - `_max_weight_from_settings`, `_cagr_lookback_years_from_settings`, `_required_dividend_yield_pct`
- 조회·최적화 실행
  - `_fetch_candidate_returns(fetch_daily_returns, …)`, `_run_goal_optimizer`
- 결과 조립
  - `_weighted_dividend_yield`, `_includes_cash_equivalent`, `_apply_dividend_suggestions`
  - `_join_notes`: 곳곳의 `f"{a} {b}" if a and b else a or b`를 대체했다.

**외부 조회는 각 진입점 모듈에 남겼다(patch 경로 보존)**

- `get_historical_returns`, `fetch_yf_daily_returns`, `build_portfolio_overview`, `query_latest_position_map` 등은
  기존 테스트 수백 곳이 진입점 모듈 경로로 patch한다. 그래서 공통 모듈로 옮기지 않았다.
- `_fetch_candidate_returns`는 조회 함수를 **인자로** 받는다. 호출 시점에 호출 모듈의 전역 이름을 넘기므로
  patch가 그대로 먹는다. 기존 테스트의 patch 경로는 하나도 바꾸지 않았다.

**모듈별 추출**

- overall: `_resolve_required_return`(자산목표 유무 → 화면용 필요수익률, 옵티마이저 하한, 조기 반환),
  `_overall_market_filter`(람다 기본인자 트릭 제거)
- age: `_resolve_age_dividend_target`(명시 목표 우선, 없으면 연령대 기본값 + 안내 문구)
- horizon:
  - 7-튜플 → `_HorizonCombo` NamedTuple
  - 조합 선택: `_select_combo_candidates`, `_combo_eligible_classes`, `_in_combo_market`, `_combo_market_filter`
  - 설정·계좌: `_accounts_by_horizon_tax_pair`, `_horizon_required_dividend_yield_pct`,
    `_short_term_equity_floor_from_settings`
  - 결과 조립: `_horizon_equity_bounds`, `_horizon_policy_note`
  - `_build_horizon_result`의 공통 필드 8개는 `common` dict로 묶어 반환 지점 4곳에서 재사용한다.
- optimizer: `_valid_optimizer_inputs`, `_annualized_covariance`, `_max_achievable_return`,
  `_signal_adjusted_frontier_fraction`, `_return_constraints`(CONSERVATIVE 부등식 / 프론티어 보간 등식 / no_spread),
  `_weights_to_items`

**테스트**: `test_goal_recommendation.py`는 `_optimize_goal_portfolio` import 경로 1줄만 바꿨다
(`goal_recommendation_service` 재노출 → `goal_portfolio_optimizer` 직접). 나머지는 무수정으로 통과한다.

## 이관

**42번에서 유지**

1. `create_rebalancing_execution_plan`(라우터→서비스), `goal_achievement._check_user_goals` 3중 블록(36 #4 잔여)
2. 메이저 업그레이드: React 19, recharts 3, tailwind 4(36 #10)
3. 경쟁기능 격차(정기 자동매수, ETF TER). 로드맵 전용이다.
4. 2-leg 확장: 실패 leg 자동 재시도. 별도 설계가 필요하다.

**관찰(42번에서 유지)**

- `GoalSettingWizard`의 "이 추천으로 포트폴리오 만들기"는 `normalizeWeights`를 거치지 않는다.

**보류(제품 판단)**: N6(DCA 알림 여러 개일 때 `monthly_deposit_amount` 비교 의미)

## 검증

```bash
cd backend && .venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80 -q   # 2450 passed, 90.51%
cd backend && .venv/Scripts/python.exe -m ruff check app tests && .venv/Scripts/python.exe -m ruff format --check app tests && .venv/Scripts/python.exe -m mypy app
```

- 백엔드는 2416 → 2450 tests다(+33 스냅샷, 동시 세션분 포함). 커버리지는 90.51%다.
- ruff, ruff format, mypy 모두 클린이다. 프론트는 변경하지 않았다.
- 실추천 결과는 기준 스냅샷과 바이트 단위로 동일하다. 배포 뒤 따로 확인할 동작 변화는 없다.
