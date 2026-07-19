# 계획 1: AUTO 자동매매 게이트에 세금영향(양도세 추정치) 반영

**리스크: 높음 — 실제 자금 이동(자동 매수/매도) 로직을 건드린다. 신중하게 진행하고, 가능하면 구현 후 사용자에게 실제 동작을 데모하고 확정할 것.**

## 배경 (Why)

리밸런싱 진단 화면(`GET /rebalancing/portfolios/{id}/analyze`)은 이미 시장상황(거시 8종 복합신호) + 리스크지표(VaR/베타/분산도) + 세금영향(양도세 추정치)을 종합해서 보여준다(`backend/app/services/rebalancing/diagnosis_service.py`). 그런데 실제 **AUTO 자동매매 실행 여부를 차단하는 게이트**(`market_condition_mode`)는 시장신호만 본다 — 리스크·세금은 화면 표시에만 쓰이고 자동실행 차단에는 관여하지 않는 비대칭이 여러 세션(2026-07-03, 2026-07-06)에 걸쳐 "신중한 논의 필요"로 보류되어 왔다.

2026-07-19 세션에서 사용자에게 확인한 결과: **"세금 영향 추가 반영"**을 선택함 (리스크 지표는 반영하지 않음 — 분산도/변동성 등은 계속 진단·알림 표시 전용으로만 남긴다). 이유: ISA/IRP 등 과세이연 계좌 보호에 초점을 맞추고, 리스크 게이트는 판단 기준이 더 모호해 이번 라운드에서 제외.

## 현재 코드 상태 (2026-07-19 기준 — 실행 전 재확인 필수)

**시장신호 게이트 (참고할 기존 패턴):**
- `backend/app/models/alert.py:83-84` — `market_condition_mode: Mapped[str]` (DISABLED/CAUTIOUS/STRICT), 컬럼 옆 주석에 의미 설명.
- `backend/app/services/rebalancing/order_builder.py::is_market_signal_blocking_auto_mode(market_condition_mode, composite_level, data_freshness="LIVE")` — 순수 함수, 게이트 판정의 단일 소스.
- `backend/app/jobs/rebalancing_auto_execution.py:81-90` (`_run_auto_execution` 내부) — 계획 생성 직전 이 함수를 호출해 차단 여부 판정 후 `continue`(플랜 생성 자체를 건너뜀, 알림도 안 감).
- 프론트: `frontend/src/constants/rebalancingConfig.ts:80-88` (`MARKET_CONDITION_OPTIONS`, 3개 옵션 + 라벨/설명), `RebalancingAlertModal.tsx`에서 이 옵션으로 셀렉트 렌더.

**세금영향 계산 (재사용 대상):**
- `backend/app/services/tax_service.py:75` `estimate_overseas_transfer_tax(realized_gain_krw, year=None)` — 실현손익 → 양도세 추정(250만원 공제, 22%).
- `backend/app/services/rebalancing/diagnosis_service.py:99` `_build_tax_preview(analysis, overview)` — `RebalancingAnalysis.items` 중 `diff_krw < 0`(매도 대상)에 대해 취득원가 lot 기반 실현손익을 추정하고, 해외 종목은 `estimate_overseas_transfer_tax()`로 세금까지 계산해 `(total_gain, overseas_gain_sum, total_fee, notes, tax_items: list[TaxImpactItem])`를 반환. **현재 private(`_` prefix), 진단 화면 표시 전용으로만 호출됨.**

**AUTO 플랜 생성 흐름 (게이트를 넣을 지점):**
- `backend/app/services/rebalancing/plan_service.py::build_pending_plan_for_alert(alert, portfolio, db, composite_level, ...)` (165줄 부근) — 내부에서 이미 `overview = await build_portfolio_overview(...)`와 `analysis = analyze_rebalancing(portfolio, overview, include_implicit_cash=True)`를 계산한 뒤 `drifting`을 필터링하고 `generate_pending_plan_for_alert(...)`를 호출해 실제 주문(buy/sell leg)을 만든다. **`_build_tax_preview(analysis, overview)`가 필요로 하는 입력을 이미 이 함수 안에서 갖고 있다** — 즉 새 DB 조회 없이 세금 추정치를 재사용할 수 있다.
- 호출부: `backend/app/jobs/rebalancing_auto_execution.py::_run_auto_execution()` (33-115줄) — `is_market_signal_blocking_auto_mode` 체크(82-90줄) 다음이 게이트를 추가할 자연스러운 위치.

## 설계 결정 (제안, 구현 세션이 확정)

- **트리거 조건**: `_build_tax_preview`가 반환하는 세금 추정 총합(양도세, 필요시 배당소득세 미포함하고 순수 매도로 인한 양도세만)이 알림에 설정된 임계값을 넘으면 차단.
- **차단 시 동작**: 시장신호 게이트와 동일하게 **이번 사이클의 AUTO 플랜 생성 자체를 건너뛴다**(`continue`) — BUY leg를 만들되 승인을 요구하는 방식보다 기존 아키텍처(플랜 없으면 알림도 없음)와 일관되고 구현이 단순함. 대신 사용자가 "왜 이번엔 자동실행이 안 됐는지" 알 수 있도록 **별도의 경량 알림**(기존 "리밸런싱 점검 권장" 이메일 패턴과 유사, `email_templates.py` 참고)을 1일 1회만 발송 — 매 5분 tick마다 스팸처럼 가지 않도록 dedup 필요(`already_fired_today` 류 패턴 재사용 검토).
- **설정 필드**: `RebalancingAlert`에 필드 추가. `market_condition_mode`와 대칭으로 가되, 세금은 GREEN/YELLOW/RED 같은 등급이 없으므로 **금액 임계값**이 더 자연스럽다. 제안:
  ```python
  # DISABLED(기본) | ENABLED — 켜져 있으면 max_tax_impact_krw 초과 시 AUTO 보류
  tax_impact_gate_mode: Mapped[str] = mapped_column(String(10), nullable=False, default="DISABLED")
  max_tax_impact_krw: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
  ```
  (2단계 모드보다 단순한 on/off + 금액 하나가 UX상 더 이해하기 쉬울 수 있음 — 구현 세션이 UI 붙여보고 판단)
- **AUTO 실행 결과 재조회 함정 주의**: [[project_account_scoped_rebalancing_2026-07-06]] 메모리에 기록된 과거 버그(최근 실행결과를 잘못 재조회)와 같은 계열 실수를 반복하지 않도록, 이 게이트는 플랜 **생성 여부**만 결정하고 이후 실행/조회 로직은 건드리지 않는다.

## 구현 단계

1. **모델 + 마이그레이션**: `backend/app/models/alert.py`의 `RebalancingAlert`에 `tax_impact_gate_mode`, `max_tax_impact_krw` 컬럼 추가. `alembic heads`로 현재 head 확인 후 새 리비전 생성(`cd backend && uv run alembic revision --autogenerate -m "add tax impact gate to rebalancing alert"` 또는 짧은 prefix 컨벤션(`tg1_...`)으로 수동 작성 — 최근 마이그레이션은 `rm1_`, `z1_`, `z2_` 같은 짧은 prefix와 해시 기반 리비전이 혼재하므로 기존 관례 참고). `alembic/env.py`는 이미 `models/alert.py`를 import하고 있을 가능성 높음 — 확인만.
2. **세금 미리보기 공개 함수화**: `diagnosis_service.py::_build_tax_preview`를 그대로 두거나(private 유지) `plan_service.py`에서 import해서 재사용 — 순환참조 주의(`plan_service.py`가 이미 `rebalancing.service`를 지연 import하는 패턴을 쓰므로 동일하게 함수 내부 `from app.services.rebalancing.diagnosis_service import _build_tax_preview` 지연 import 권장).
3. **게이트 함수 추가**: `order_builder.py`에 `is_market_signal_blocking_auto_mode`와 나란히 `is_tax_impact_blocking_auto_mode(gate_mode: str, estimated_tax_krw: float, max_tax_impact_krw: float | None) -> bool` 순수 함수 추가 (단위테스트 용이하게 순수함수로 유지).
4. **plan_service.py 통합**: `build_pending_plan_for_alert`가 `analysis`/`overview` 계산 직후, `drifting` 필터링 직후(주문 생성 전) 세금 추정치를 계산하고 게이트 함수 호출 → 차단이면 특수 반환값(예: `None`이 아닌 별도 sentinel, 또는 `(None, "TAX_BLOCKED")` 같은 튜플)으로 job에 알려 job이 로그+알림을 분기하도록.
5. **rebalancing_auto_execution.py 통합**: `_run_auto_execution()`에서 시장신호 게이트 통과 후, 플랜 생성 결과가 "세금 차단"이면 별도 알림 발송(1일 1회 dedup) + `logger.info("rebalancing_auto_skipped_tax_impact", ...)`.
6. **알림 dedup**: `already_fired_today` 류 헬퍼(`app/services/alerts/calculator.py`) 패턴을 참고해 세금 차단 알림도 같은 알림에 대해 하루 1회만 발송되도록.
7. **프론트**:
   - `frontend/src/api/alerts.ts`(또는 rebalancing 알림 타입 정의 위치) — `tax_impact_gate_mode`/`max_tax_impact_krw` 필드 추가.
   - `frontend/src/constants/rebalancingConfig.ts`에 `MARKET_CONDITION_OPTIONS`(80-88줄)와 나란히 세금 게이트 on/off 토글 + 금액 입력 옵션 추가.
   - `RebalancingAlertModal.tsx`(AUTO 모드 선택 시에만 노출, `market_condition_mode` 셀렉트 근처)에 UI 추가.
8. **테스트**:
   - 백엔드: `backend/tests/test_rebalancing_auto_execution.py`에 시장신호 게이트 테스트와 대칭으로 "세금영향 초과 시 AUTO 플랜 미생성 + 알림 발송" 테스트 추가.
   - `order_builder.py`의 새 순수함수 단위테스트(`test_rebalancing_alert_service.py` 또는 신규 파일).
9. **검증**: `cd backend && uv run pytest && uv run ruff check . && uv run mypy app/`, 프론트 `npm run test && npm run typecheck && npm run lint`.

## 주의사항

- 이 파일과 [02-threshold-recommendation-dedup.md](02-threshold-recommendation-dedup.md)가 같은 파일(`order_builder.py`)을 건드린다 — README의 "동시 진행 가능 조합" 참고.
- 실제 자금 이동 경로라 과거 3차례 매도주문 버그([[project_rebalancing_sell_bug_2026-07-02]] 계열)가 있었던 민감 영역 — 최소 침습으로, 기존 `build_rebalancing_orders`/`generate_pending_plan_for_alert` 핵심 로직 자체는 건드리지 말고 "플랜 생성 여부"만 좁게 제어할 것.
