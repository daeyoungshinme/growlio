# 105. 기술부채 — 104 이관분 처리 (2026-10-31)

## 배경

"남은 기술부채 수정계획" 요청. 104 "이관" 섹션의 항목을 코드에서 다시 확인했고, 전부 그대로 남아 있었다. 시작할 때 main은 깨끗했다(#203 머지 직후).

사용자 결정:
- 범위는 **전부**(배치 C + 세금 이중 조회 + 정리 소항목)다.
- OTHER 시장은 **상수만 통일하고 동작은 유지**한다.
- 총자산 엔진 통일은 계속 보류한다.

## 결과

| # | 문제 | 수정 |
|---|---|---|
| D1 | `float(x) if x is not None else None` 9곳이 남아 있었다(challenge·plan_execution·rebalancing service) | `opt_float`로 바꿨다 |
| D2 | 국내 시장 집합이 2벌이었다. `constants.DOMESTIC_MARKETS`는 `{KOSPI,KOSDAQ,KRX}`, `tax_service._DOMESTIC_MARKETS`는 `{KOSPI,KOSDAQ,KONEX}`였다 | 로컬 집합을 지우고 상수를 쓴다. 포지션 `market`은 `VALID_MARKETS`(KONEX·KRX 없음)로 검증되고, 브로커 동기화도 KOSPI/KOSDAQ만 쓰므로 실데이터 결과는 같다. OTHER가 세금 요약 미실현에서는 빠지고 실현손익에서는 해외로 잡히는 현재 동작을 테스트 2건으로 고정했고, 양쪽 docstring에 "세무 판단 보류"를 적었다 |
| E | 세금 API·인사이트·절세 액션이 `get_overseas_positions_detail`로 스냅샷을 읽고, `get_tax_summary` 안의 `_calc_stock_unrealized`가 같은 스냅샷을 다시 읽었다 | `load_tax_stock_rows`가 행과 해외 포지션을 함께 돌려준다. 포지션은 실현손익(`overseas_positions=`)에, 행은 `get_tax_summary(stock_rows=)`에 넘긴다. 요약 내부도 행 1회 로드 → 순수 함수 2개(`_stock_unrealized_from_rows`·`_overseas_positions_from_rows`)로 계산한다. 기존 공개 함수 2개는 얇은 래퍼로 남겼다. 테스트 patch 24곳을 옮겼고, "1회 조회 / 넘긴 행은 재조회 안 함" 테스트를 추가했다 |
| C1 | `utils/cache_keys.py`(656줄)에 키 빌더와 무효화가 섞여 있었다 | 무효화 13개(`_scan_unlink` 포함)를 `utils/cache_invalidation.py`로 옮겼다. **재노출하지 않았다** — 상호 import는 `cache_invalidation`을 먼저 읽는 경로에서 깨진다. import 출처는 import 문 단위로 이름을 갈라 16파일에서 옮겼다(계획의 "약 65개"는 과대 추정이었다). 키 문자열과 SCAN 패턴은 그대로이고, 103 A14 드리프트 테스트가 새 모듈을 검사한다 |
| C2 | `tactical/tactical_allocation_service.py`가 755줄이었다 | `tactical_regime.py`(국면 판정·제안 비중, 순수)와 `tactical_apply.py`(적용 계획·그룹 재구성·할 일 판정, 순수)로 나눴다. 원 모듈에는 `evaluate_market`·전략 CRUD·`build_status`·`apply_regime_to_portfolio`가 남고(336줄), 옮긴 심볼은 `__all__`로 재노출한다. 테스트가 `patch.object(tactical, …)`로 바꾸는 4개(evaluate_market·get_owned_portfolio·get_strategy·list_strategies)는 원 모듈에 남겼으므로 patch 25건이 그대로 유효하다 |
| C3 | goal `_compute_*` 3개 분해 | **실익이 없어 종결했다.** 세 함수는 이미 `_goal_recommendation_common` 헬퍼를 순서대로 부르는 조립부다. 기간별 추천은 조합 루프 + `asyncio.gather` 구조라 모양이 다르다. 전체·연령대 두 함수의 공통 꼬리(수익률 조회 → 최적화 → 응답 조립)를 뽑으면 인자가 11개가 되어, 계획의 중단 기준(인자 5개 초과)에 걸린다 |

## 검증

- 백엔드: 3223 tests 통과(+4), 커버리지 92.74%(게이트 89%)
- ruff·ruff format·mypy 클린. 프론트는 변경하지 않았다
- `/openapi.json`이 변경 전 커밋(495a5669)과 **바이트 단위로 같다**
- **미검증**: 실서버 세금 탭·인사이트 숫자가 이전과 같은지

## 이관

- **판단 필요(보류 유지)**
  - 총자산 엔진 2벌(`composition_calculator.build_asset_totals` vs `portfolio_service._calc_account_amounts`)
  - OTHER 시장의 세무 기준
- 그대로 두는 것: 메이저 업그레이드, pyproject 상한, vite-plugin-pwa low 4건, keep-alive 외부 핑, CI uv 미고정(101 D2), 라우터 `ValueError` 3곳(101 B3)
