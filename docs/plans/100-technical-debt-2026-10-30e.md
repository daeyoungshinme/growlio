# 100 — 99 이관 기술부채 처리 (2026-10-30e)

## 배경

99(PR #192)의 "이관" 절에 남은 항목을 코드와 대조해 처리했다. #192가 아직 머지 전이라 이 브랜치는 그 위에 올렸다(stacked).

- 브랜치: `chore/tech-debt-2026-10-30e`
- 커밋: 클러스터마다 1개

## 결과

| # | 항목 | 결과 |
|---|---|---|
| A | 서비스 계층 `HTTPException` | rebalancing 서비스 5개 파일(order_cancel·execution·plan_execution·quick_execute·alert_scope)의 35곳을 `app.exceptions`의 `AppError` 하위 예외로 바꿨다. `NotFoundError`·`ConflictError`·`UnprocessableError`는 새로 만들었고, 502는 기존 `ExternalAPIError`를 쓴다. 전역 `app_error_handler`가 같은 status와 `{"detail"}`로 응답하므로 API 계약은 그대로다(파라미터화 테스트로 고정). 취소 경로의 `except HTTPException: raise`는 `except AppError: raise`로 바꿨다. 자격증명 400이 아래 `except Exception`의 502로 덮이지 않게 하기 위해서다(회귀 테스트 추가). `app/services`에 남은 `fastapi` import는 0건이다 |
| B | KIS 해외 취소 수량 | 해외 정정취소(TTTT1004U)에는 국내의 `QTY_ALL_ORD_YN` 같은 "잔량 전부" 플래그가 없어 수량을 직접 보내야 한다. 그런데 원주문수량을 보내고 있어서 부분 체결된 주문은 취소가 거부될 수 있었다. 이제 취소 직전에 미체결내역(TTTS3018R)을 조회해 남은 수량을 보낸다. 주문이 목록에 없으면(이미 체결) 증권사를 부르지 않고 CANCEL_FAILED로 기록한다. 조회가 증권사 오류로 실패하면 CANCEL_FAILED가 되고 재시도할 수 있다. 네트워크 오류면 원수량으로 폴백하지 않고 기존 502 경로로 간다. 모의투자는 이 TR을 지원하지 않아 원수량을 그대로 보낸다. 새 테스트 3건은 수정 전 코드에서 실패하는 것을 확인했다 |
| C1 | authStore의 api 우회 | `/auth/me`·`sync-profile`·`find-account`·`password-reset-complete`를 부르던 8곳을 `api/auth.ts`의 `fetchAuthMe`·`syncProfile`·`findAccount`·`markPasswordResetComplete`로 옮겼다. 401 재시도는 `getHttpStatus` 기준이라 동작이 같다. `findAccount`는 감싸는 함수로 남겼다. store를 만드는 시점에 import를 바로 읽으면 `@/api/auth`를 부분 mock하는 테스트가 깨지기 때문이다 |
| C2 | `!` 단언 | 지역 변수, 구조분해, Map 조회 재작성으로 좁혔다. 대상은 StockAccountCard·StockAccountModal·BacktestResultChart·DCAProjectionChart·AnalysisPanel·RebalancingCells·marketSignalRows다. 동작은 바뀌지 않는다 |
| D1 | 마이그레이션 docstring | `aa2_add_snapshots_user_date_index`의 `Revises`를 실제 `down_revision`(`ak1_…`)으로 고쳤다. `104aa75dc751`은 docstring(`age_group`)이 실제 컬럼과 맞으므로 **오기가 아니다**. 파일명만 `birth_year`인데, 이름을 바꾸면 이력만 더 헷갈리므로 그대로 둔다 |
| D2 | 로컬 `node_modules` | `npm ci` 뒤 `@typescript-eslint/parser`가 8.72.1(lock과 같음)이 됐다 |
| D3 | vite-plugin-pwa low 4건 | `npm audit`로 다시 확인했다. deepmerge → @rollup/plugin-node-resolve → workbox-build → vite-plugin-pwa 경로의 4건이 그대로 남아 있다. 상위에서 고쳐 주기를 기다린다 |

## 검증

- 백엔드:
  - ruff·format·mypy 클린
  - 3199 passed, 커버리지 92.21%(게이트 89%)
- 프론트:
  - eslint `--max-warnings 0`·prettier·`npm run typecheck` 클린
  - 1907 tests
- **미검증**: 실계좌에서 해외 부분 체결 주문 취소. 응답 필드명(`odno`·`nccs_qty`)과 `OVRS_EXCG_CD`별 조회 범위는 KIS 공개 예제를 기준으로 했으며, 공식 문서로 확정하지 못했다.

## 이관

- `!` 단언 중 남은 것:
  - 여러 변수에 걸친 조건: `goalChips`(`canShowReturnGap`)·`GoalTimelineCard`
  - 클로저 안의 속성: `RebalancingStatusCard`의 `action_url`
  - 다른 함수의 판정에 기대는 경우: `RebalancingWeightTable`의 `isTradableItem`

  모두 구조를 바꿔야 한다. `PortfolioGroupItemRow`의 `item.group!`(99에서 제외)과 `api/client.ts`의 큐 토큰은 계약상 안전하다.
- 그대로 두는 것:
  - 메이저 업그레이드(React 19, recharts 3, tailwind 4, TS 7, plugin-react 6)
  - keep-alive 크론(외부 핑 서비스를 아직 정하지 않음)
  - vite-plugin-pwa low 4건
