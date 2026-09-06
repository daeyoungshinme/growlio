# 30. 기술부채 감사 (2026-09-06)

`docs/plans/29`(2026-08-31) 이후 커밋은 넷뿐이고 HEAD가 직전 감사 커밋(`e82fae4`)이었다.
실질 신규 부채는 **토스증권 연동(`b8a3d37`)이 프론트에서 절반만 배선된 상태**와 백엔드에
남은 소량의 죽은 코드·문서 드리프트뿐. Explore 2개(백엔드/프론트) 병렬 재조사.

브랜치 `tech-debt-2026-09-06`.

## 같은 세션에 구현 완료

### 배치 A — 토스 배선 완성 + 죽은 코드 + 문서 드리프트 (커밋 예정)
- **토스 리밸런싱 진단 게이트 확장 (읽기 전용)**: `_account_queries._BROKER_ASSET_TYPES`에
  `STOCK_TOSS` 추가(→ `/broker-balance-all` 전파), `rebalancing.py` broker-balance
  엔드포인트 400 조건에 토스 포함. **주문 실행 게이트(`execution_service.py`/
  `order_builder.py`의 자체 `_BROKER_ASSET_TYPES`)는 KIS/키움 유지** — 토스 Open API에
  주문 클라이언트(`app/toss/order.py`)가 없다. 토스는 잔고·진단까지만, 주문은 토스 앱에서 직접.
- **프론트 배선 버그 수정**: 하드코딩된 `data_source === "KIS_API" || "KIWOOM_API"` 체크가
  기존 헬퍼(`SYNCABLE_DATA_SOURCES`/`isSyncableAccount()`)를 무시하고 곳곳에 남아
  토스 계좌가 반쪽 상태였음:
  - `StockAccountCard.tsx` — 동기화 버튼 안 뜸 + "토스 API 키" 배지 없음
  - `useAccountMutations.ts` — 생성 후 자동 동기화 안 됨 + 에러 토스트 "KIS"로 오표기
    (`STOCK_TYPE_LABELS[asset_type]`로 3-way)
  - `RebalancingAccountSyncSection.tsx` — `SOURCE_LABEL`에 토스 없어 빈 라벨
  - `AllocationHistoryChart.tsx` — `TYPE_COLORS`에 `STOCK_TOSS` 없어 폴백 색
  - `AnalysisPanel.tsx` — 리밸런싱 잔고 조회 필터, `AssetManagementPage` 포지션 readonly
    (신규 `isBrokerBalanceAccount()` 헬퍼)
- **백엔드 죽은 코드**: `decrypt_toss_credentials()`(호출부 0), `TOSS_EXCHANGE_RATE_PATH`
  (참조 0) 제거.
- **문서 드리프트**: `credential_service.py`/`_error_mapping.py`/`http_client.py` 독스트링
  "KIS/키움" → 토스 포함, `backend/CLAUDE.md`의 stale한 `# noqa: E712` 예시
  (배치 A(plan 29)에서 repo 전역 제거됨) 갱신.
- 테스트: `test_broker_balance_service` 토스 케이스, `accounts.test.ts` 헬퍼 케이스.

### 배치 B — 자격증명 검증 중복 제거 (커밋 예정)
- 프론트: `useKisCredentialVerify`/`useTossCredentialVerify`의 동일 상태 머신을
  `createCredentialVerify(apiCall)` 제네릭 팩토리로 통합(`useSettingsToggle` 선례). 두 훅은
  검증 API 호출부만 클로저로 넘기는 한 줄 래퍼.
- 프론트: `TossCredentialFields`/`KisCredentialFields`에 문자 단위로 중복이던 "자격증명 확인"
  버튼+결과 표시(~22줄)를 `CredentialVerifyButton.tsx`로 추출.
- 백엔드: `_SYNC_TIMEOUT`(50.0) 2벌 → `providers/base.SYNC_TIMEOUT_SECONDS`.
  `toss_provider`의 edge-blocked 코드 집합 → `_EDGE_BLOCK_CODES` frozenset.

## 이관 항목 (이번 세션 미착수)

### 1. `goal_recommendation_service.py` 공통 모듈 추출 — 배치 C1, 이관
`e82fae4`의 투자기간별 분리는 크기를 옮겼을 뿐 줄이지 못했다(grs 782 / horizon 626 / age 346).
`goal_horizon_recommendation_service.py`·`goal_age_recommendation_service.py`가 각각 grs에서
**private 심볼 ~13개**를 import한다:

- 무해한(테스트 미patch) 부분 — 상수 `_NON_BINDING_RETURN_FLOOR`/`_CASH_EQUIVALENT_*`/
  `_DEFAULT_CAGR_LOOKBACK_YEARS`/`_DIVIDEND_*_PCT` + 순수 함수 `_cash_equivalent_daily_returns`/
  `_equity_class_bounds`/`_not_configured`/`_no_recommendation`.
- **엉킨 부분** — `_fetch_dividend_yields`/`_fetch_market_signal_level`(`get_market_signal` 경유)/
  `_suggest_for_dividend_goal`/`_attach_dividend_yield`. `tests/test_goal_recommendation.py`
  (4332줄, repo 최대 테스트)가 `_fetch_dividend_yields`를 **~40곳**에서
  `patch("app.services.goal_recommendation_service._fetch_dividend_yields")` 형태로,
  autouse `_mock_dividend_yields` fixture가 **3개 모듈 경로**를 patch한다.

**왜 이번에 안 했나**: 무해한 부분만 옮기면 "공통 헬퍼가 2파일에 흩어짐"으로 오히려 악화.
엉킨 부분까지 제대로 옮기려면 (a) 새 `_goal_recommendation_common.py`가 소유하고 모든 소비자가
`import _goal_recommendation_common as _gc; _gc.fn()` 모듈 참조 호출로 통일 + (b) ~40개
test patch 경로 sed 이전 + autouse fixture 경로 단일화(3→1)가 필요. 순수 이동이지만 추천
엔진 회귀 표면이 커 `plan 29 #1`가 이미 한 차례 미룬(그때는 112곳 sed) 성격의 작업.

**다음 세션 착수 시**: 리팩터 전후 `pytest tests/test_goal_recommendation.py`(166개) 동일
출력 확인. autouse fixture는 새 모듈 1경로만 patch하도록 단순화, `goal_age`/`goal_horizon`
경로 patch는 제거.

### 2. 대형 `_compute_*` 함수 분해 — 배치 C2, 이관 (1번 이후)
3개 진입점의 `_compute_*`가 166~209줄 near-clone shape:
- `goal_portfolio_optimizer._optimize_goal_portfolio` 209 (`:219`)
- `goal_age_recommendation_service._compute_age_based_recommendation` 198 (`:148`)
- `goal_horizon_recommendation_service._compute_horizon_recommendations` 195 (`:431`)
- `goal_horizon_recommendation_service._build_horizon_result` 179 (`:206`)
- `goal_recommendation_service._compute_goal_recommendation` 166 (`:574`)

공통 스켈레톤(후보 유니버스 구성 → 배당수익률 attach → MVO 최적화 → 결과 빌드 → 배당후보
제안)을 1번의 공통 모듈에 헬퍼로. characterization 스냅샷 테스트로 실추천 결과 회귀 확인.

### 3. `assets.py` 브로커 분기 정리 — 배치 B4, 이관
`create_account`(`:186-219`)·`update_account`에 KIS/키움/토스 3개 near-identical 분기
(자격증명 존재검증 → encrypt → asset_type). `{data_source: (asset_type, required_fields,
encrypt_fields, error_msg)}` 스펙 테이블 + 루프로 축약. **KIS 분기만 `asset_type`을 안
설정하는 기존 quirk**(스키마 validator가 채우는 듯) 먼저 확인 필요. 계좌 생성 경로라
회귀테스트 필수 — 저위험이지만 시간 소요.

### 4. provider 에러 핸들링 래더 — 조사 후 보류
`kis_provider`/`kiwoom_provider`/`toss_provider`의 `except` 캐스케이드가 유사하나
브로커별 특수 케이스(KIS `rt_cd` 메시지, 키움 `RuntimeError` 토큰, 토스 403 edge-blocked)가
충분히 갈려 공통 컨텍스트매니저는 per-broker 훅이 필요해 실익이 작다. 가치 있는 80%
(`map_http_status_error`/`map_network_error`)는 `_error_mapping.py`로 이미 추출됨. **추가
추상화 불필요.**

### 5. `market_signal_service.py`(835줄) 분해 — plan 24 #2 / 29 #3, 유지
8개 `fetch_*_signal` + 조립. AUTO 게이트 신호원이라 hysteresis/raw 양쪽 회귀 필요. 저긴급.

### 6. `AssetAccount.is_active == True` 반복 — plan 29 #9, **종결(조치 불필요)**
재확인 결과: 반복 ~31곳이 `AssetAccount`/`User`/`RebalancingAlert`/`ExchangeRateAlert`/
`StockPriceAlert` **5개 모델**에 걸쳐 있어 단일 `ACTIVE_ACCOUNT_CONDITION` 상수로 커버
불가. `Model.is_active == True`는 관용적이고 명확·정확·일관됨. 계좌 조회는 이미
`_account_queries` 헬퍼 존재. **상수화 실익 없음으로 종결.** `backend/CLAUDE.md` 문구만
헬퍼 사용 권장으로 갱신.

### 7. plan 27 이관분 (#7 2-leg 부분실행 가시성, #8 AUTO 매수 leg 실행 직전 잔고 clamp) — 유지
실자금 리스크. 별도 설계 세션.

### 8. #10 의존성 취약점 스캔 블로킹 — 유지
pip-audit 전이 취약점 다수라 `continue-on-error` 유지, Dependabot 주간 PR로 점진 해소.
(npm은 0건.)

### 9. alembic 버전 컬럼 hotfix (`ai2_expand_alembic_version_col.py`) — 관찰만
체인 중간 마이그레이션이 자기 버전 테이블(신규 DB는 alembic이 VARCHAR(32)로 생성)을
VARCHAR(255)로 확장하는 구조. `0d0cb0a` 후 CI 통과 확인. `bootstrap_alembic.py`는 기존 DB
경로만 넓게 생성. 기능상 정상이나 신규 리비전 ID가 32자 초과인 한 ai2가 체인에 남아야 함.
조치 불필요.

## 검증

```bash
cd backend && uv run pytest -q          # 2086 passed (배치 A 토스 테스트 +1)
cd backend && uv run ruff check . && uv run mypy app/
cd frontend && npm run test             # 1463 passed (+2)
cd frontend && npm run lint && npx tsc --noEmit
```
