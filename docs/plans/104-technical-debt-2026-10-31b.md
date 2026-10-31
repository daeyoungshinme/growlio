# 104 — 남은 기술부채 처리 (2026-10-31)

## 배경

"남아있는 기술부채 수정계획" 요청. 101·102·103이 끝난 뒤 이관 항목(103의 "다음 세션(배치 B)"와 "이관", 101·100의 "이관")을 모아 코드에서 다시 확인했다. 시작할 때 열린 PR은 없었고 main은 깨끗했다(#202 머지 직후).

사용자 선택: 이번 세션 범위는 **배치 0 + B**. 배치 C(구조 분리)는 다음 세션으로 넘긴다. 총자산 엔진 통일은 보류.

다시 확인했을 때 이미 해소돼 있던 것:

- `httpx2` dev 의존성: 아직 필요하다. starlette testclient가 먼저 import하고, 없으면 httpx 폴백과 폐기 경고가 난다(pyproject 주석대로).

## 결과 — 배치 0 (저위험 단건)

| # | 문제 | 수정 |
|---|---|---|
| 0-1 | 환율이 None인데 해외 종목 시세가 있으면, `reprice_positions_krw`가 USD 가격을 그대로 원화 현재가로 저장했다(103 이관). `fetch_usd_krw`가 기본으로 fallback을 돌려주므로 실제로는 드물다 | 해외 종목은 환율이 있을 때만 시세로 갱신하고, 없으면 기존 현재가 → 평단을 유지한다(시세가 없을 때와 같은 분기). 회귀 테스트는 수정 전 코드에서 실패한다 |
| 0-2 | `api/deps.get_owned_or_404`의 `type: ignore[attr-defined, arg-type]` | `id`·`user_id`를 가진 `_UserOwned` Protocol을 TypeVar bound로 걸었다. mypy 전체가 통과하므로 모든 호출부가 Protocol을 만족한다. B3에서 쓸 `options=`(관계 로드) 인자도 추가했다 |
| 0-3 | 101 이관: 신규 컴포넌트·훅에 직접 테스트가 없었다 | `TacticalApplyConfirmModal`·`RebalancingOrderRows`(보유 안내·배분·수량 입력·재조회)·`PortfolioGroupItemRow`(레버리지 후보 제외·멤버 빼기·국내 대표면 대체 선택 숨김)·`useMediaQuery`·`useRebalancingUrlState`(예전 `rtab=전술` 호환)·`stockHoldings/holdings`. 32 tests |

## 결과 — 배치 B (라우터 → 서비스, 동작 불변)

| # | 내용 | 비고 |
|---|---|---|
| B2 | `settings.py`(10클래스)·`external.py`(9클래스)의 인라인 스키마 → `schemas/settings.py`·`schemas/external.py`. `float(x) if x is not None else None` 14곳 → `utils/numbers.opt_float`. 목표 추천 기본값 40%/10년/80% 3벌 → `app/constants.DEFAULT_GOAL_*`(설정 응답·옵션 기본값·goal 서비스 3곳) | 라우터가 스키마를 import하므로 기존 `from app.api.v1.settings import GoalUpdate`는 그대로 동작한다 |
| B3 | 포트폴리오 생성·수정·목록·순서 변경 → `services/portfolio/portfolio_crud_service`. `target_portfolio_id` 채우기 2벌 → `_claim_target`, 해제 → `_release_target`. 계좌 소유 검증은 `BadRequestError`, 수정 대상 없음은 `NotFoundError`(응답 동일) | 캐시 무효화는 라우터에 남겨 테스트의 `app.api.v1.portfolios.*` patch 경로를 유지했다. 인라인 "소유 + 관계 로드 + 404" 중 `db.scalar`를 쓰던 2곳(`rebalancing` expected-metrics·`rebalancing_alerts`)은 `get_owned_or_404(options=)`로 바꿨다. 포트폴리오 수정은 테스트 mock이 `db.execute`를 쓰므로 서비스 안에서 같은 쿼리를 유지했다 |
| B5 | 최신 스냅샷 + 계좌(+포지션) 조회 5벌 → `accounts/_snapshot_queries.latest_snapshot_rows(account_ids·asset_types·with_positions)` | 배당 orchestrator의 `like("STOCK%")` → `POSITION_STOCK_ASSET_TYPES`. 현재 enum 기준으로 같다는 것을 테스트로 고정했다(STOCK* 유형이 추가되면 실패) |
| B6 | KIS·키움 계좌의 매도 → 매수 실행 → `_broker_order_flow.execute_sell_then_buy` | 실행기 이름은 유지했다. 람다가 호출 시점에 모듈 이름을 조회하므로 patch 55줄은 그대로다 |
| B4 | 알림 경로 3곳(`alert_check`·`alert_test`·`plan_generation`)의 계좌 범위 → overview → 분석 → `alert_scope.load_alert_overview`·`analyze_alert_overview`. 주문 미리보기 복붙 2곳 → `order_builder.build_alert_order_preview` | `build_portfolio_overview`·`analyze_rebalancing`은 헬퍼 안에서도 호출 시점에 import한다(기존 patch 유지). `alert_check`의 overview/분석 실패 Sentry 이벤트 이름은 그대로다 |
| B1 | `analyze_portfolio` 파이프라인 → `services/rebalancing/portfolio_analysis_service.analyze_portfolio_rebalancing`. 라우터는 소유 확인만 한다. 추천 3종(전체·기간별·연령별)의 캐시 → stale+백그라운드 → 계산 → `_serve_recommendation`. expected-metrics의 CAGR lookback 재구현 → `_cagr_lookback_years_from_settings` | 계획은 테스트 13개의 patch 이동이었다. 실제로 파이프라인을 patch하는 테스트는 1개(6곳)였고, 그 경로만 서비스 모듈로 옮겼다. 추천 3종 테스트의 `app.api.v1.rebalancing.get_cached_*` patch는 라우터가 함수를 인자로 넘기므로 그대로 유효하다 |

계획에서 뺀 것:

- **`get_tax_summary`의 스냅샷 이중 조회**: 호출부 3곳(`api/v1/tax.py`·`insight_service`·`tax_action_service`)이 모두 `get_overseas_positions_detail`로 포지션을 먼저 읽는다. 그다음 `get_tax_summary`의 `_calc_stock_unrealized`가 같은 스냅샷을 다시 읽는다. 없애려면 행을 호출부에서 넘기도록 시그니처 3곳을 바꾸고, 두 함수를 patch하는 `test_tax_service` 약 20곳을 고쳐야 한다. 요청 1회에 쿼리 1회를 아끼는 이득에 비해 커서 이관했다

## 검증

- 백엔드: 3219 tests 통과, 커버리지 92.72%(게이트 89%)
- 프론트: 1960 tests(181 files) 통과
- ruff·ruff format·mypy·eslint `--max-warnings 0`·tsc(앱+테스트) 클린. prettier는 변경 파일 기준 클린이다. 저장소 전체 `--check`가 566개를 경고하는 것은 Windows `core.autocrlf=true` 체크아웃의 CRLF 때문이고 CI(LF)와 무관하다
- B2·B3·B1: `/openapi.json`을 변경 전 커밋과 비교해 **동일**하다(응답 계약 불변)
- 0-1: 회귀 테스트가 수정 전 코드에서 실패한다
- **미검증**: 실서버 동작. B1·B4는 운영 리밸런싱 분석·알림 발송으로 확인할 수 있다

## 이관

- **배치 C (구조 분리, 사용자 결정으로 다음 세션)**
  - `utils/cache_keys.py`(656줄)의 무효화 로직 → `cache_invalidation.py`. 103 A14의 드리프트 테스트를 안전망으로 쓴다
  - `tactical/tactical_allocation_service.py`(755줄) → 국면 엔진 / 포트폴리오 적용. `patch.object(tactical, …)` 23건은 재노출로 유지한다
  - goal `_compute_*` 3개 분해. 하네스가 fetcher를 모듈 경로로 patch하므로 공용 헬퍼는 fetcher를 인자로 받는다
- `get_tax_summary` 스냅샷 이중 조회(위 "계획에서 뺀 것")
- `opt_float` 적용 확대: settings·external 외에 같은 패턴이 8곳 남아 있다(동작 동일, 정리만)
- **판단 필요(103에서 이관, 이번에도 보류)**
  - 총자산 엔진 2벌: `composition_calculator.build_asset_totals`(스냅샷 없는 주식계좌 = 포지션+예수금)와 `portfolio_service._calc_account_amounts`(`manual_amount` 없으면 0). 통일하면 리밸런싱·목표 화면 숫자가 바뀐다. 사용자가 보류로 결정했다
  - 해외 판정 기준: `overseas_realized_service`는 "국내가 아니면 해외", `tax_service`는 `OVERSEAS_MARKETS` 기준이라 KONEX/OTHER가 갈린다. 세무 판단이 필요하다
- 그대로 두는 것: 메이저 업그레이드, pyproject 상한, vite-plugin-pwa low 4건, keep-alive 외부 핑, CI uv 미고정(101 D2), 라우터 `ValueError` 3곳(101 B3)
