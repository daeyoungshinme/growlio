# 계획 2: 드리프트 임계값 추천 로직 백엔드 dead code 제거

**리스크: 낮음 — 순수 함수 삭제 + 테스트 정리, 실행 경로에 영향 없음.**

## 배경 (Why)

`backend/app/services/rebalancing/order_builder.py::recommend_drift_threshold_pct(tax_type, investment_horizon)`가 정의되어 있지만 API/다른 서비스 어디서도 호출되지 않는다(테스트에서만 직접 import해서 검증). 반면 프론트엔드는 **완전히 동일한 로직**을 `frontend/src/utils/rebalancingThresholdRecommendation.ts::recommendDriftThresholdPct()`로 자체 재구현해서 실제로 사용 중이다(`useRebalancingAlertForm.ts`에서 PER_ACCOUNT 알림 생성 폼의 임계값 초기값 제안용).

프론트 파일 3번째 줄 주석: `// 백엔드 backend/app/services/rebalancing_order_builder.py::recommend_drift_threshold_pct와 동기화 유지.` — **이미 이 주석 자체가 낡았다**(파일 경로가 `rebalancing_order_builder.py`인데 실제로는 `rebalancing/order_builder.py`로 패키지 분리된 지 오래됨). 이 상태로는 두 로직 중 하나만 수정되어도 자동으로 어긋남을 감지할 방법이 없다.

## 현재 코드 상태 (2026-07-19 기준 — 실행 전 재확인 필수)

**백엔드 (미사용, 삭제 대상):**
- `backend/app/services/rebalancing/order_builder.py:166-176` — 함수 본문:
  ```python
  def recommend_drift_threshold_pct(tax_type: str, investment_horizon: str) -> float:
      """계좌 tax_type·investment_horizon 기반 PER_ACCOUNT 알림 임계값 추천치를 계산한다. ...
      어디까지나 알림 생성 UI의 초기값 제안이며, 사용자가 언제든 override 가능하고
      drift 판정(`rebalancing/service.py`)이나 AUTO 게이트에는 관여하지 않는다.
      """
      base = _TAX_TYPE_BASE_THRESHOLD_PCT.get(tax_type, _TAX_TYPE_BASE_THRESHOLD_PCT["GENERAL"])
      adjustment = _HORIZON_THRESHOLD_ADJUSTMENT.get(investment_horizon, 0.0)
      return round(min(max(base + adjustment, _MIN_RECOMMENDED_THRESHOLD_PCT), _MAX_RECOMMENDED_THRESHOLD_PCT), 1)
  ```
  이 함수가 참조하는 `_TAX_TYPE_BASE_THRESHOLD_PCT`, `_HORIZON_THRESHOLD_ADJUSTMENT`, `_MIN_RECOMMENDED_THRESHOLD_PCT`, `_MAX_RECOMMENDED_THRESHOLD_PCT` 상수들이 **이 함수 외에 다른 곳에서도 쓰이는지 먼저 확인** — 만약 아니라면 상수까지 같이 제거, 다른 곳에서도 쓰인다면 함수만 제거.
- 테스트: `backend/tests/test_rebalancing_alert_service.py:1178-1218` — `recommend_drift_threshold_pct` 관련 테스트 클래스/케이스 전체(6개 assert 블록). `from app.services.rebalancing.order_builder import recommend_drift_threshold_pct` import가 있는 라인들.

**프론트 (유지, 유일한 실사용 로직):**
- `frontend/src/utils/rebalancingThresholdRecommendation.ts` (37줄, 전체 파일) — `recommendDriftThresholdPct(taxType, investmentHorizon)`. 사용처: `useRebalancingAlertForm.ts`.

## 구현 단계

1. **사전 확인**: `backend/app/services/rebalancing/order_builder.py`에서 `_TAX_TYPE_BASE_THRESHOLD_PCT`/`_HORIZON_THRESHOLD_ADJUSTMENT`/`_MIN_RECOMMENDED_THRESHOLD_PCT`/`_MAX_RECOMMENDED_THRESHOLD_PCT`가 `recommend_drift_threshold_pct` 외에 다른 함수에서도 참조되는지 grep으로 재확인 (같은 파일 내 `_flatten_account_tax_types` 등 다른 함수들이 비슷한 이름의 `_TAX_DEFERRED_TYPES` 같은 별도 상수를 쓰는 걸로 보이므로 착각하지 말 것 — 이름이 비슷해도 다른 상수일 수 있음, 정확히 확인).
2. **백엔드 삭제**: 함수 본문 삭제 + (1번에서 확인 후) 미사용 상수 삭제.
3. **테스트 삭제**: `test_rebalancing_alert_service.py:1178-1218`의 관련 테스트 케이스 제거. 파일 전체가 깨지지 않는지 앞뒤 클래스 구조 확인 후 삭제.
4. **프론트 주석 정리**: `rebalancingThresholdRecommendation.ts:3`의 "백엔드와 동기화 유지" 주석을 제거하거나, "이 로직은 프론트에서만 관리되는 단일 소스(백엔드에 대응 함수 없음)"로 갱신.
5. **backend/CLAUDE.md 확인**: `order_builder.py` 설명에 이 함수가 명시적으로 언급되어 있지 않다면 갱신 불필요 — 있다면 제거.
6. **검증**: `cd backend && uv run pytest && uv run ruff check . && uv run mypy app/`. 프론트는 주석만 바꾸는 거라 별도 테스트 불필요하지만 `npm run typecheck`로 확인.

## 대안 (삭제 대신 통합하고 싶다면)

만약 "중복 제거"보다 "단일 소스화"가 더 낫다고 판단되면, 반대로 프론트가 백엔드 API를 호출하도록 바꾸는 방법도 있다 — 단, PER_ACCOUNT 알림 생성 폼은 계좌 선택 즉시 임계값이 실시간으로 바뀌어야 하는 UX라(`useRebalancingAlertForm.ts`), 매번 API 왕복이 생기면 반응성이 떨어진다. **이 계획은 "백엔드 삭제 + 프론트 유지"를 기본 권장안으로 삼되, 구현 세션이 실제 UX를 보고 반대로 판단해도 무방하다.**

## 주의사항

- [01-auto-gate-tax-impact.md](01-auto-gate-tax-impact.md)가 같은 파일(`order_builder.py`)에 새 함수(`is_tax_impact_blocking_auto_mode`)를 추가하는 작업을 한다 — 두 작업이 동시에 진행되면 병합 충돌 가능성이 있으니 README의 순서 권장(2 먼저, 그다음 1) 참고. 이 계획(삭제만 하는 작은 diff)을 먼저 끝내는 편이 안전.
