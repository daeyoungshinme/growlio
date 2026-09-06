# 29. 기술부채 이관 항목 (2026-08-31 감사)

2026-08-31, "기술부채 검토 후 수정 계획" 요청으로 마지막 감사(`docs/plans/26`, 2026-08-13)
이후 커밋 4건의 변경분에 초점을 두고 백엔드/프론트를 병렬 재조사(Explore 2개). 저위험 항목은
같은 세션에 배치 A·B·C2로 구현 완료(커밋 `fd4ac30`·`7654894`·`830feb1`):

- **배치 A** — 죽은 코드(FE `useRegisterRefresh` 중복 사본·미사용 상수 6종, `isOverseasMarket` import
  경로 통일), 무효 `# noqa: E712` 40건 제거 + `RUF100` 룰 추가(추가 무효 noqa 9건 정리 —
  `portfolio_optimizer.get_efficient_frontier`의 `# noqa: C901`이 **이미 임계 이하**로 확인되어
  자동 제거됨, plan 24 #3 종결), `numpy`/`pandas` 직접 의존성 명시, `contextlib.suppress(Exception)`
  → 로깅 동반(`plan_notifications.py` 5건 비대칭 해소 포함), 프로덕션 `assert` → `raise`,
  eslint `no-explicit-any` `warn`→`error`.
- **배치 B** — `email_service.py` 15개 `send_*` 함수의 반복 골격을 `_send_templated()` 헬퍼로
  축약(시그니처·로그 이벤트명 불변). `services/alerts/_dispatch.py` 신규
  (`dispatch_dual_channel_alert()`) — 등급전환/매일요약/추천드리프트/연말절세 4개 호출부의
  "이메일→푸시→AlertHistory" 블록 통합.
- **배치 C2** — `RecommendationCard.tsx`의 전체/연령대/기간별 3탭이 각각 갖던 3개 `useMutation` +
  3개 `<ConfirmModal>` 블록을 단일 `applyMutation` + `applyConfirm` 계산값 + 단일 모달로 통합.

검증: 백엔드 2067 tests 88.7%, 프론트 1456 tests, ruff/mypy/tsc/eslint 클린.

이 문서는 손이 많이 가거나(테스트 patch 경로 대량 이전) 실거래·핵심 로직 리스크가 있어 **다음
세션으로 이관**하는 항목만 기록한다.

## 이관 항목

### 1. `goal_recommendation_service.py`(1333줄) 투자기간별 경로 분리 — 배치 C1, ✅ 완료 (2026-09-01)
- `goal_horizon_recommendation_service.py` 신규(170줄, `get_horizon_recommendations`/
  `_compute_horizon_recommendations`/`_build_horizon_result`/`_build_horizon_candidate_universe`/
  `_single_candidate_horizon_result` + `_HORIZON_*`/`_DEFAULT_{SHORT_TERM_EQUITY,IRP_SAFE_ASSET}_FLOOR_PCT`
  상수). grs는 1311→793줄. 아래 (b) 방식 채택: 새 모듈이 true-source collaborator
  (`get_historical_returns`/`fetch_yf_daily_returns`/`query_latest_position_map`/
  `build_portfolio_overview`/`prefetch_accounts_snapshot_positions`/`compute_total_assets_krw`)를
  직접 import, grs 소유 헬퍼(`_fetch_dividend_yields`/`_attach_dividend_yield`/
  `_suggest_for_dividend_goal`/`_fetch_market_signal_level`/`_equity_class_bounds`/
  `_cash_equivalent_daily_returns`)는 grs에서 import. 순환참조 없음 — grs는 새 모듈을 import하지 않고,
  소비자(`api/v1/rebalancing.py`·`alerts/recommendation_drift_alert_service.py`)가 새 모듈에서 직접 import
  (age 서브모듈 전례와 동일).
- 테스트: `TestGetHorizonRecommendations`(단일 연속 클래스) 내 112곳 patch 경로를 sed로 새 모듈로 이전.
  `_suggest_for_dividend_goal`(grs 네임스페이스 실행)이 `_fetch_dividend_yields`를 grs에서 룩업하므로
  배당 제안을 검증하는 5곳은 grs 경로도 함께 patch(age 테스트 4097/4101 전례). autouse
  `_mock_dividend_yields`에 새 모듈 경로 추가. `_mock_market_signal`은 그대로(horizon이
  `get_market_signal`을 직접 호출하지 않고 grs `_fetch_market_signal_level` 경유).
- 검증: `pytest tests/test_goal_recommendation.py` 166 passed(분리 전과 동일), 전체 2085 passed 88.38%,
  ruff/mypy 클린.

<details><summary>원래 이관 사유 (완료됨)</summary>
- 최대 파일. plan 11(1113→720)·plan 26(1622→1332, 연령대별 분리) 후에도 재비대. 남은 대형 함수:
  `_compute_horizon_recommendations`(195), `_build_horizon_result`(179), `_compute_goal_recommendation`(166).
- `get_horizon_recommendations`/`_compute_horizon_recommendations`/`_build_horizon_result`/
  `_build_horizon_candidate_universe`/`_single_candidate_horizon_result`(~520줄)를
  `goal_horizon_recommendation_service.py`로 분리하는 것이 자연스러운 다음 단계
  (`goal_age_recommendation_service.py` 분리 전례와 동일 패턴).
- **왜 이번에 안 했나**: 이 블록이 호출하는 12개 collaborator(`get_historical_returns`/
  `build_portfolio_overview`/`query_latest_position_map`/`prefetch_accounts_snapshot_positions`/
  `compute_total_assets_krw`/`fetch_yf_daily_returns`/`_fetch_dividend_yields`/`_suggest_for_dividend_goal`/
  `_attach_dividend_yield`/`_equity_class_bounds`/`_cash_equivalent_daily_returns`/`_fetch_market_signal_level`)를
  `tests/test_goal_recommendation.py`가 `patch("app.services.goal_recommendation_service.X", ...)` 형태로
  **투자기간별 테스트 클래스 안에서만 ~113곳** patch한다. 깔끔한 분리(true source에서 import)는 이
  113곳의 patch 경로를 새 모듈로 전부 이전해야 하고, 그 대안(새 모듈이 `goal_recommendation_service`
  모듈 객체를 통해 `grs.X()`로 호출)은 결합도가 줄지 않는 "가짜 분리"라 채택하지 않음.
- **다음 세션 착수 시**: (a) 먼저 투자기간별 테스트를 collaborator patch 대신 상위 진입점 mock으로
  단순화할 수 있는지 검토(테스트 자체 리팩터가 선행), 또는 (b) 새 모듈이 collaborator를 true source에서
  import하고 patch 경로를 sed로 일괄 이전 + `_mock_dividend_yields`/`_mock_market_signal` autouse
  fixture에 새 모듈 경로 추가(plan 26 교훈). 순수 이동이라 로직 변경 0, 리팩터 전후
  `pytest -k goal_recommendation`(≈167개) 동일 출력 확인.
</details>

### 2. 프론트 대형 컴포넌트 워치리스트 — 배치 C3, 미착수
- `GoalSettingWizard.tsx`(559줄) — 6개 스텝이 인라인. 스텝별 컴포넌트 추출은 공유 state 15개+를
  props로 threading해야 해 회귀 위험 대비 실익이 작음(500줄대는 plan 24 #4에서 "긴급하지 않음"으로
  분류). `useGoalSettings.ts`가 이미 `wizardStep`/`wizardMode`를 관리하므로, 착수 시 스텝 컴포넌트가
  훅에서 직접 소비하는 방향 권장.
- `hooks/rebalancingExecution/index.ts`(528줄) — plan 24 #1에서 이관. `eslint-disable
  react-hooks/exhaustive-deps` 4곳, 실거래 실행 경로. characterization test 선행 필수, 별도 세션.
- `InvestPlanPage.tsx`(519)/`StockAccountModal.tsx`(519)/`InvestmentGoalCard.tsx`(513)/
  `RebalancingOrderTable.tsx`(511)/`StockHoldingsTable.tsx`(508) — 참고용 기록만.

### 3. `market_signal_service.py`(835줄) 분해 — plan 24 #2에서 이관, 유지
- AUTO 게이트·등급전환 알림의 신호원(8개 매크로 지표). hysteresis(`get_confirmed_composite_level`)와
  raw 값 양쪽 회귀 검증 필요. 실자금 게이트 영향으로 신중히.

### 4. `plan_service.py` 계열 추가 분해 — plan 27 #4에서 이관, 유지
- 2026-08-20에 `plan_generation.py`/`plan_execution.py`/`plan_notifications.py` 3분할 완료.
  `plan_generation.py`가 이미 401줄로 재성장 중. "최소 1릴리스 안정화 후" 상태 유지.

### 5. Kiwoom 해외주식 주문 API-ID 실계좌 검증 — plan 20 #1 → 24 #5 → 26, 유지
- 서드파티 오픈소스 클라이언트 소스 기반으로만 확정. 실계좌 첫 해외 매수/매도 시 응답 필드 실측
  검증 권장. **실계좌 필요, 사용자 트리거 대기.**

### 6. 시장신호 방법론 Phase 2/3 — `docs/plans/21`, 유지
- Phase 2(AUTO 게이트 raw score 반영), Phase 3(국내 리스크 지표 리서치). 실자금 게이트 판정 로직
  변경이라 의도적 보류.

### 7. 2-leg 부분 실행 복구·가시성 — plan 27 #2, 유지
- 최소 범위(이력 탭 "부분 실행됨" 배지)도 미착수. 확장 범위(실패 leg 자동 재시도)는 별도 설계 세션.

### 8. AUTO 대기 매수 leg 실행 직전 잔고 clamp — plan 27 #3, 유지
- FULL 전략 예산 clamp는 2026-08-20에 추가됐으나 "대기 중 예수금 감소"(다른 매수 leg 선체결·수동 출금)
  대응은 부분적.

### 9. 활성 계좌 WHERE절 fragment 헬퍼 — plan 20 #3, 재확인 필요
- join/컬럼-select 쿼리 9개 파일(`dca_service.py`/`tax_service.py`/`backtest_service.py` 등)에
  `AssetAccount.is_active == True` 반복. `_account_queries.active_accounts_stmt()`는
  `Select[tuple[AssetAccount]]`만 반환해 맞지 않음. **버그는 아니고** 반복 작성일 뿐 —
  `ACTIVE_ACCOUNT_CONDITION` 단순 상수를 만들지, 현행 유지가 나을지 다음 세션에서 실제 가치 재확인.
  (배치 B의 `_dispatch.py` 작업 중 재확인 결과, 이 항목은 여전히 "가치 불명확"으로 판단.)

### 10. 의존성 취약점 스캔 블로킹 전환 — plan 24/26, 유지
- 백엔드 `pip-audit` 전이 의존성 취약점(pillow/starlette/pyasn1 등) 다수라 CI `continue-on-error: true`
  유지. Dependabot 주간 PR로 점진 해소 중. (2026-08-31 재확인: `npm audit` 0건으로 프론트는 클린.)

### 11. `pyproject.toml addopts` 커버리지 강제 — ✅ 완료 (2026-09-01)
- `addopts`를 `"--tb=short"`로 축소(`--cov=app --cov-report=term-missing` 제거). 로컬 `pytest` 실행
  (`-k`·`--collect-only`·단일 파일)에서 커버리지 측정 마찰 제거.
- **CI 무영향**: `.github/workflows/ci.yml`이 이미 `--cov=app --cov-report=xml --cov-fail-under=80`을
  명시적으로 전달 → 80% 게이트 그대로 유지.
- 로컬 커버리지 원커맨드: `make test-backend-cov`(신규 Makefile 타깃,
  `pytest --cov=app --cov-report=term-missing --cov-fail-under=80`). 루트/백엔드 CLAUDE.md 갱신.

### 13. 토스 연동 후 문서/독스트링 드리프트 — ✅ 완료 (2026-09-01, 신규)
- `b8a3d37`(토스 연동) 이후 `broker_balance_service.py`(모듈+`fetch_broker_balance` 독스트링),
  `asset_credential_service.py` 독스트링, `backend/CLAUDE.md` `broker_balance_service.py` 줄이
  여전히 "KIS/키움"만 언급 → "KIS/키움/토스"로 갱신.
- **부수 발견(미해결, 판단 필요)**: `fetch_broker_balance`에 `STOCK_TOSS` 분기가 구현돼 있으나
  현재 **도달 불가능** — `/broker-balance/{id}` 엔드포인트 게이트, `_account_queries._BROKER_ASSET_TYPES`
  (`active_broker_accounts_stmt`), 프론트 `AnalysisPanel.tsx`/`useRebalancingBalances.ts` 필터가 전부
  KIS/키움만 통과시킨다. 토스 실시간 잔고를 리밸런싱 진단 화면에 노출할지(백+프론트 게이트 3곳
  확장) 아니면 사변적으로 추가된 이 분기를 제거할지는 기능 판단 — 실계좌 E2E 미검증 상태와 함께
  다음 세션/사용자 결정 대기. 독스트링에 현 상태를 명시해둠.

### 12. `portfolio_optimizer.get_efficient_frontier` `# noqa: C901` — plan 24 #3, **종결**
- 배치 A에서 `RUF100` 추가 시 이 noqa가 **이미 불필요**함이 드러나 자동 제거됨(함수가 리팩터 누적으로
  복잡도 임계 이하로 내려온 상태). 추가 조치 불필요.
