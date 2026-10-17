# 59. 기술부채 감사 (2026-10-16)

## Context

계획 57(PR #134 머지)과 58(종목 현황 모바일 스크롤, 커밋 `9a2e70b1`, 현재 브랜치)의 다음 라운드다. 의존성은 깨끗하다(pip-audit 0건, npm audit prod 0건). 고전적 부채(죽은 코드, `any`, skip 테스트, 문서 목록 누락)도 거의 다 정리됐다. 이번에 나온 것은 네 가지다.
1. **58 신규 코드의 상태 버그**
2. **조용히 틀린 숫자를 내는 집계 버그 2건**: 삭제한 계좌의 입금이 연간 적립에 포함됨, 루프 DB 오류가 연쇄 실패함
3. **실주문 경로의 안전망 2건**: 배포가 겹치는 동안 AUTO 잡이 중복 실행될 수 있음, 국내 지정가의 호가단위
4. **CI/문서 드리프트**

✔ 표시는 코드를 직접 읽어 확인한 항목이고, 나머지는 실행하면서 확인한다.

**정정한 오보**: Explore가 "매도 수량에 상한이 없어 과매도 주문이 나간다"고 보고했지만, 백엔드 `_order_quantity_guard.clamp_sell_orders`가 실제 보유 수량에 맞춰 줄인다. 그래서 실자금 버그가 아니라 **확인 화면 수량 ≠ 실제 주문 수량**이라는 UX 불일치로 격하했다(B3).

## 이번 세션 범위

사용자 결정(2026-10-17): **A + B + D를 구현한다. C(AUTO 중복 실행 claim, 국내 호가단위)는 이 문서에만 남기고 다음 세션에서 한다.**

## 실행 첫 단계
1. 58 브랜치(`feat/holdings-tab-scroll-2026-10-16`)가 머지됐는지 확인한다. 미머지면 그 위에 `fix/tech-debt-2026-10-16`을 만든다.
2. 이 문서를 `docs/plans/59-technical-debt-2026-10-16.md`로 옮기고 README 표에 행을 추가한다.
3. `git status`로 동시 세션 작업이 있는지 확인한다.
4. 배치마다 커밋한다. 실버그에는 회귀 테스트를 붙이고, 수정 전 코드에서 그 테스트가 실패하는지 확인한다.

---

## 배치 A — 백엔드 실버그 (저위험, 최우선)

| # | 문제 | 수정 |
|---|---|---|
| A1 ✔ | **연간 순입금에 삭제 계좌가 포함된다.** `services/asset_aggregator.py` `nd` CTE(~78-86)는 `user_id`로만 거른다. 같은 쿼리의 다른 CTE는 `is_active`·`include_in_total`로 거른다. 계좌 삭제는 soft delete(`api/v1/assets.py:367`)라서 대시보드의 연간 적립 달성률이 부풀려진다. `challenge_service._monthly_net_deposits`(`:73-95`, `account_id=None` 경로)에도 같은 문제가 있다 | `transactions.account_id`가 nullable(SET NULL)이므로 `LEFT JOIN asset_accounts a ON a.id = t.account_id` 후 `(t.account_id IS NULL OR (a.is_active AND a.include_in_total))`로 거른다. 계좌 없는 입출금은 유지한다. 두 곳 모두 고친다. 회귀 테스트: 삭제 계좌에 입금이 있을 때 합계에서 빠지는지 |
| A2 ✔ | **루프 DB 오류가 연쇄 실패한다.** `rebalancing/drift_summary_service.py:56-73`, `insight_service.py:83-87,178-182`는 except에서 로그만 남기고 rollback하지 않는다. DB 오류가 한 번 나면 세션이 failed 상태로 남아 이후 포트폴리오가 전부 `PendingRollbackError`로 조용히 빠진다(57 이관) | `action_items_service.py:165-176` 패턴대로 except에서 `await db.rollback()`. 요청 경로의 읽기 전용 루프라 expire 함정이 없다. 루프 밖에서 읽어 둔 ORM 속성(`portfolio.id` 등)은 루프 전에 지역값으로 빼 둔다. 회귀 테스트: 첫 항목에서 DB 예외가 나도 두 번째 항목이 결과에 남는지 |
| A3 ✔ | `api/v1/rebalancing.py:314`의 `detail=str(e)`(ValueError, 단건 broker-balance)가 57 D에서 빠졌다. Pydantic `ValidationError`도 ValueError라 입력값이 노출될 수 있다 | 같은 파일 `:345`처럼 `public_error_message(e)`를 쓴다. 의도한 ValueError 메시지는 보존되는지 테스트로 확인한다 |
| A4 | `trend_calculator.py:35`의 SQL `CURRENT_DATE`가 DB의 UTC 날짜라, KST 1일 00~09시에 12개월 창이 한 달 밀린다 | `utils/kst.py`의 오늘 날짜를 바인드 파라미터로 넘긴다 |
| A5 | `order_builder.py:131`·`rebalancing/service.py:174`의 `math.floor(value/price)` 부동소수 경계(2.9999→2) | 공용 `floor_shares(x)` = `math.floor(x + 1e-9)`로 두 곳을 바꾼다. 경계값 테스트를 추가한다 |

## 배치 B — 프론트 (58 회귀 + 정리)

| # | 문제 | 수정 |
|---|---|---|
| B1 ✔ | **비중순 정렬 요청이 재마운트할 때마다 다시 적용된다.** `StockHoldingsTable.tsx:267-271` effect는 `sortRequest`가 non-null이면 마운트 때도 `setSort`·`setQuery("")`를 실행한다. `PortfolioPage.tsx:99`가 요청을 페이지 상태로 들고 있어, 다른 탭에 갔다 오면 사용자 정렬과 검색어가 초기화된다 | 마지막으로 적용한 `nonce`를 ref로 기억해 바뀔 때만 적용한다. 또는 적용 후 부모가 요청을 비운다(`onSortRequestHandled`). 테스트: 요청 1회 → 정렬 변경 → 재마운트 → 사용자 정렬 유지 |
| B2 | 모바일 단일 펼침과 데스크톱 다중 펼침이 `expandedSet` 하나를 공유하고, 정렬 요청·positions가 바뀌어도 초기화되지 않는다 | 정렬 요청을 적용할 때와 뷰포트 모드가 바뀔 때 `expandedSet`을 비운다 |
| B3 ✔ | 매도 수량 입력이 `max={currentQty}`(브라우저가 강제하지 않음)뿐이다. reducer `SET_QTY`는 하한만 막는다. 확인 화면은 100주인데 실제로는 백엔드 clamp로 10주가 나간다 | `buildOrders`(`hooks/rebalancingExecution/index.ts:~285`)에서 매도 qty를 `currentQty`로 clamp하고, 입력이 보유 수량을 넘으면 행에 "보유 N주까지" 안내를 띄운다 |
| B4 | `rebalancingExecution/index.ts:259,266,424`의 eslint-disable memo 3개: `actionableItems`(`:162`)가 매 렌더마다 새 배열이라 memo가 무효이고, `overseasUnknown` 의존성이 누락돼 있다 | `actionableItems`를 `useMemo`로 감싸고 의존성을 정직하게 채운 뒤 disable 주석을 제거한다 |
| B5 | `StockAllocationView.tsx:33`이 백엔드 "기타" 라벨에서 정규식으로 개수를 뽑는다. `restPct`가 0.0으로 반올림되면 행이 사라진다 | 백엔드 비중 응답에 `etc_count`를 추가한다(라벨 생성부를 찾아 함께 변경). 프론트는 그 값을 쓰고, `hasRest`는 개수로 판정한다 |
| B6 | `PortfolioPage.tsx` ~362의 `dividendMap`을 인라인으로 만들어 `StockHoldingsTable` memo가 무효다 | `useMemo` |
| B7 | `HorizonSummaryCard.tsx` 데스크톱 그리드가 `withPct`를 두고 pct를 다시 계산한다. 같은 비중 계산이 세 군데에 중복돼 있다 | `withPct`를 재사용하고, `utils/`에 `pctOf(part,total)`을 두어 `RegionAllocationView`·`AllocationCard`가 공유하게 한다 |
| B8 | `StockPositionsModal.tsx:79`의 eslint-disable(불안정한 함수 참조) | `useCallback`으로 고치고 주석을 제거한다 |
| B9 | `no-floating-promises`가 `warn`이다. 현재 경고 0건이라 비용이 없다 | `eslint.config.js`에서 `error`로 올린다 |

## 배치 C — 실주문 안전망 (중위험) — **이번 세션 미구현, 계획만**

| # | 문제 | 수정 |
|---|---|---|
| C1 | **배포가 겹치는 동안 AUTO 잡이 중복 실행될 수 있다.** 스케줄러는 프로세스 내 APScheduler이고, 락(`utils/inproc_lock.py`)도 프로세스 단위다. `jobs/rebalancing_auto_execution.py:86`의 `already_fired_today`는 읽고 나서 쓰는 방식이라, Render 무중단 배포로 두 인스턴스가 겹치면 둘 다 통과할 수 있다. plan leg 매수는 row lock으로 안전하다 | Supabase Transaction Pooler(6543)에서는 session advisory lock을 쓸 수 없다. 대신 **app_state 원자적 claim**을 쓴다: `INSERT ... ON CONFLICT DO NOTHING RETURNING`으로 `(job, alert_id, KST date)` 키를 선점한 쪽만 실행한다. `core/durable_state`(또는 app_state 모델)에 `claim_once(key, ttl)` 헬퍼를 두고 AUTO 실행에 먼저 적용한다. 알림 잡(5·10분 주기)은 중복 메일 정도의 영향이라 같은 헬퍼로 선택 적용한다. 테스트: 동시 claim 2회 중 1회만 True |
| C2 | **국내 지정가에 호가단위 처리가 없다.** `kis/order.py:52`·`kiwoom/order.py:44`가 `int()`로 자를 뿐이다. 수동 실행에서 입력한 지정가(`RebalancingPriceInput`)가 호가 격자에서 벗어나면 broker가 그 leg를 거부한다 | `utils/krx_tick.py`의 `round_to_tick(price, side, is_etf)`: 매수는 내림, 매도는 올림(사용자가 지정한 가격보다 불리해지지 않게). 주식은 KRX 2023 개편 호가표, ETF/ETN은 5원. **착수 전에 현행 호가표와 ETF 판별 소스(기존 ETF 메타)를 확인한다.** 주문 직전 공용 경로에서 적용하고, 프론트 입력에도 같은 표로 보정한 값을 미리 보여준다. 국내만 적용하고 해외는 그대로 둔다 |

## 배치 D — CI·문서·테스트 위생 (저위험)

- D1 `keep-alive.yml`: cron은 10분 주기지만 GitHub 스로틀로 실제 실행 간격이 3~5시간이다. 그래서 스케줄러 슬립 완화가 사실상 동작하지 않는다. 외부 핑(UptimeRobot·cron-job.org 등 무료 5분 주기)을 쓰도록 `backend/CLAUDE.md` "스케줄러 실행 제약"과 루트 CLAUDE.md를 정정한다. 외부 서비스 등록은 사용자 작업이다.
- D2 `build-android.yml`·`ci.yml` secret-scan에 `timeout-minutes`와 최소 `permissions: contents: read`를 추가한다.
- D3 `ci.yml:84`의 중복 `--timeout=60`을 제거한다. `pyproject.toml:89`의 죽은 `omit = ["app/alembic/*"]`도 제거한다.
- D4 dependabot.yml의 stale 주석 2건(vite 8 Rolldown, setup-uv v9)을 고친다.
- D5 `frontend/CLAUDE.md` 드리프트: 존재하지 않는 `useToast()`(L380), `usePortfolioTabFetching.ts`의 export명(L190), `useRebalancingAlertForm.ts`의 export명(L183,400).
- D6 `mock_rate_limiter` 3중 정의(`test_kis_client`·`test_kiwoom_client`·`test_toss_client`)를 conftest로 옮긴다.
- D7 프론트 `npm audit` `continue-on-error`(`ci.yml:158`): 현재 prod 0건이니 백엔드처럼 차단으로 바꾼다(`--omit=dev --audit-level=high`).

## 이관 (이번 미구현, README에 기록)

- 스케줄러 별도 워커 분리 또는 유료 플랜(D1의 근본 해결)
- 데이터 보존 정책: `positions`(snapshot) 증가가 가장 빠르다. `alert_history`·실행 이력·plan 테이블. Supabase 용량 추이를 보고 결정한다
- FK 인덱스 누락 11개(대부분 soft delete라 영향이 작다). 52 G squash 때 함께 처리한다
- `stock_price_service`의 대표 사용자 자격증명, ticker 단일 키 `price_map`
- plan 해외 지정가 1개 실패 시 leg 전체 FAILED(부분 실행 설계 판단)
- 52 B~G(MVO 4중, KIS/키움 매도 clamp 래퍼 복사본, settings PUT 15개, 컬럼 드롭, services 패키지 재편)는 그대로 유효하다
- `capacitor-native-biometric`(Capacitor 3 의존, AGP 3.6, core 이중 설치): 54 이관 그대로 유효하다. 대체 플러그인 선정과 실기기 검증이 필요하다
- `noUncheckedIndexedAccess`: 210 errors(소스 ~117, 테스트 ~93)
- 대형 컴포넌트(`StockHoldingsTable` 678줄 1순위), 커버리지 패딩 테스트 파일 9개(`components.large` 등) 재편, `RebalancingConfirmStep`·`RebalancingOrderTable` 렌더 테스트(56·57 이관)
- 프론트 major 업그레이드(React 19, recharts 3, tailwind 4, TS 7, `@sentry/vite-plugin` 5→11, `vite-plugin-pwa` 2)는 개별 계획으로 한다
- alembic 중복 merge(`al1`) 및 숨은 merge(`c1d2e3f4a5b6`): 동작에는 영향이 없다. 52 G squash 때 정리한다

## 검증

```bash
make lint && make typecheck
make test-backend-cov      # 80% 게이트, Windows 종료코드 -1073741819는 실패 아님
make test-frontend
cd backend && uv run alembic check   # 스키마 변경 없음 확인(B5 etc_count는 응답 필드만)
```
- A1: 삭제 계좌의 입금 유무에 따라 `/dashboard` 연간 적립 값이 바뀌는지 테스트로 확인한다
- B1·B2: 실제 브라우저(모바일 390px 뷰포트)에서 비중순 보기 → 배당 탭 → 종목 현황으로 돌아올 때 정렬이 유지되는지 확인한다
- C1: claim 헬퍼 동시성 단위 테스트, AUTO 잡 중복 호출 시 주문 1회
- C2: 호가 경계(1,999/2,000/4,995/5,000/…/500,000) 단위 테스트, ETF 5원
- 배포 후: Render 로그에서 `auto_execution_claim_skipped`(신규) 발생 여부

---

## 실행 결과 (2026-10-17, 브랜치 `fix/tech-debt-2026-10-16`)

**A·B·D 완료. C는 미착수(위 표 그대로 유효).** 백엔드 2694 tests 91.21%, 프론트 1669 tests, ruff·mypy·tsc·eslint(`--max-warnings 0`)·prettier 클린. 실버그 회귀 테스트는 전부 수정 전 코드에서 실패하는 것을 확인했다.

계획 대비 정정·추가:
- **A1**: 테스트 DB가 mock이라 SQL 텍스트 고정 테스트(기존 패턴)로 막고, 실제 Postgres 파서(pglast)로 두 쿼리의 문법을 확인했다(로컬 Docker 없음). 대시보드는 같은 쿼리의 다른 CTE와 맞춰 `is_active`·`include_in_total`로, 전체 계좌 챌린지는 `is_active`만 거른다.
- **A2**: rollback만 넣으면 루프가 쥔 Portfolio 객체가 expire돼 async lazy load 오류가 난다(57에서 보류한 이유). 실패하면 rollback한 뒤 **포트폴리오를 다시 조회해 남은 id로 계속**한다. insight는 체커 루프에도 rollback을 넣었다. 테스트는 "aborted 세션 + rollback 시 expire"를 흉내 내는 가짜 객체로 작성했다.
- **A3**: `public_error_message`가 pydantic `ValidationError`(ValueError 하위 클래스)를 그대로 통과시키던 것을 타입명으로 바꿨다. 이 처리를 함께 하지 않으면 엔드포인트 한 곳만 고쳐도 효과가 없다.
- **B3 추가 발견**: `getSellRows` 권장 매도량 자체가 보유량을 넘을 수 있었다(같은 종목을 수동 계좌에도 보유한 경우: 합산 매도량 -50, KIS 5주 → 권장 50주). 권장량, 입력(reducer `SET_QTY.max`), `buildOrders` 세 곳 모두 보유량으로 자른다.
- **B4**: disable 주석 3개는 유지하고, 누락된 의존성(`overseasUnknown`·`analysis`)과 `actionableItems` memo를 보강했다. 주석은 "함수가 읽는 값을 전부 나열"로 바로잡았다. 주석까지 없애려면 훅 내부 함수 체인 전체를 useCallback으로 바꿔야 해서 비용 대비 효과가 낮다.
- **B2 부수 수정**: 데스크톱 하위 행 테스트가 모바일 카드 클릭으로 데스크톱 행을 펼치고 있었다. 상태 공유에 기대던 테스트라, 데스크톱 행을 직접 클릭하도록 고쳤다.
- **D1 실측**: `gh run list` 기준 keep-alive 실제 실행 간격이 2~9시간(2026-10-11~17)이다. GitHub cron 스로틀로 슬립 방지 효과가 사실상 없다. 외부 핑 등록은 사용자 작업으로 남긴다. 문서(`backend/CLAUDE.md`·루트 `CLAUDE.md`·`keep-alive.yml` 주석)는 정정했다.
- **D6 철회**: `mock_rate_limiter` 3개는 각각 다른 모듈(kis/kiwoom/toss)을 패치하므로 중복이 아니다. conftest 팩토리로 바꾸면 간접 참조만 늘어난다.
- **D7**: 프론트 `npm audit`을 `--omit=dev --audit-level=high` 차단으로 바꿨다. devDependency는 Dependabot이 관리한다.

배포 후 확인:
- 대시보드 연간 적립액이 삭제 계좌만큼 줄었는지(삭제 계좌에 올해 입금이 있던 사용자)
- Render 로그 `drift_summary_recover_failed`·`insight_portfolio_recover_failed`(새 로그, 나오면 원인 조사)
- 외부 핑 등록 후 keep-alive·스케줄러 잡 로그 간격
