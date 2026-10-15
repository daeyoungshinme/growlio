# 57. 기술부채 감사 (2026-10-15 저녁)

## Context

계획 56이 브랜치 `fix/tech-debt-2026-10-15b`(PR #133, 미머지)로 끝났다. 이번 감사는 세 축이다.
1. **56 신규 코드 회귀**: 레이트리밋 IP 키, 잔고 페이지 상한 raise, 비밀번호 재설정 플래그.
2. **56에서 중단된 백엔드 신규 축**: 입력 범위, `str(e)` 노출, N+1, 잡 격리, float 금액.
3. **의존성 보안**: `pip-audit`를 처음 돌렸다. 12개 패키지에서 69건이 나왔다. npm audit(prod)은 0건이다.

✔ 표시는 코드를 직접 읽어 확인한 항목이다. 나머지는 Explore가 보고한 것이라 실행 중에 확인한다.

깨끗했던 영역: 연속키 반복 검사의 오탐, `sync_account` 실패 시 포지션 보존, `quantity: float` 소비처, `useTimeout`, `useStockSearch` abort, 핵심 대시보드·포트폴리오 쿼리(IN 쿼리 사용), 대부분의 잡(사용자별 세션+try), KRW 반올림, npm audit, 600줄 넘는 백엔드 파일(0개).

**실행 첫 단계**
1. 56 PR 머지 여부를 확인한다. 미머지면 56 브랜치 위에 `fix/tech-debt-2026-10-15c`를 만든다.
2. 이 문서를 `docs/plans/57-technical-debt-2026-10-15c.md`로 옮기고 README에 행을 추가한다.
3. `git status`로 동시 세션 작업이 있는지 확인한다.
4. 배치마다 커밋한다. 실버그는 회귀 테스트를 붙이고, 수정 전 코드에서 실패하는지 확인한다.

---

## 배치 A — 의존성 취약점 (최우선, 저위험)

| # | 문제 | 수정 |
|---|---|---|
| A1 ✔ | `pip-audit` 69건: starlette 1.0.0(10건), pillow 12.2.0(25건), cryptography 48.0.1(6건), urllib3·anyio·h2·hpack·httplib2·msgpack·pyasn1·soupsieve·pip | `uv lock --upgrade-package <pkg>`로 전이 의존성을 패치 버전으로 올린다. starlette는 fastapi 0.143의 허용 범위 안에서 올라가는지 확인하고, 막히면 fastapi도 함께 올린다 |
| A2 ✔ | `pyproject.toml:27`의 `cryptography>=42.0.0,<49.0.0` 상한 때문에 수정 버전(49/50)을 설치할 수 없다 | 상한을 `<51`로 올린다. `app/core/crypto`의 Fernet 사용부 테스트로 확인한다 |
| A3 | 재발 방지 | CI(`ci.yml`) 백엔드 잡에 `pip-audit` 단계를 추가한다(처음에는 `continue-on-error: true`로 경고만 낸다. 수정 버전이 없는 항목 때문에 CI가 막히지 않게 하려는 것이다. 안정되면 차단으로 바꾼다). Dependabot이 전이 의존성을 못 잡았다는 점도 README에 메모한다 |

## 배치 B — 56 회귀

| # | 문제 | 수정 |
|---|---|---|
| B1 ✔ | **IP 키를 위조할 수 있다.** `limiter.py:55`가 `X-Forwarded-For`의 맨 왼쪽 값을 쓴다. Render origin(`growlio-w5wc.onrender.com`)은 공개 주소라 직접 호출할 수 있고, 요청마다 헤더를 바꾸면 매번 새 버킷이 생긴다. 그래서 `find-account` 3/hour, `sell/decision` 5/min 같은 한도를 무제한 시도할 수 있다. uvicorn에는 `--proxy-headers`도 없다 | 신뢰할 수 있는 홉이 붙인 값을 쓴다. Render는 요청을 넘기며 접속 IP를 XFF 맨 뒤에 붙이므로 그 값을 기준으로 한다. Vercel을 거치면 그 값이 Vercel egress IP라 Vercel 경로에서는 오른쪽에서 두 번째 값을 쓰는 등의 규칙이 필요하다. **먼저 운영에서 헤더 형태를 확인한다**: 일시적으로 XFF·`true-client-ip`·`cf-connecting-ip`를 구조화 로그로 남기거나, Render 문서를 확인한다. 그다음 규칙을 정하고 단위 테스트를 단다(직접 호출·Vercel 경유·헤더 없음 세 경우) |
| B2 | **로그인 사용자도 공용 IP 버킷을 쓴다.** 종목 검색(30/min)·지수지역·환율이 IP 키로 바뀌어, 통신사 CGNAT나 사무실처럼 IP를 공유하면 사용자끼리 한도를 나눠 쓴다. 검색은 키 입력마다 요청하므로 429 → "종목 검색에 실패했습니다" 토스트가 뜬다 | 이 세 라우트는 `rate_limit_key`로 되돌린다. 위조 `sub`로 할 수 있는 건 자기 버킷을 바꾸는 것뿐이고, 상류 호출은 캐시가 막는다. docstring에 구분 기준(값이 큰 공개 라우트만 IP 키)을 적는다 |
| B3 ✔ | 56 A2의 `RuntimeError`(페이지 상한·연속키 반복)를 `kis_provider.py:91-120`이 매핑하지 않아 500과 "서버 오류"가 나간다. 키움은 `ProviderApiError(502)`로 매핑한다 | KIS에도 `except RuntimeError → ProviderApiError(..., http_status=502)`를 추가한다. 더 나은 방법: 두 balance 모듈이 전용 예외(`BalancePaginationError`)를 던지게 하고 두 provider가 같은 방식으로 매핑한다 |
| B4 | `lib/supabase.ts:18`의 `passwordRecoveryDetected`가 리셋되지 않는다. 한 번 복구 링크를 연 탭에서는 이후 일반 로그인 세션으로도 `/reset-password` 폼이 열린다 | `consumePasswordRecovery()`로 읽으면서 false로 되돌린다(또는 `ResetPasswordPage` 성공·언마운트 시 리셋). 테스트를 추가한다 |
| B5 | 해외 잔고 조회가 실패해도(`_safe_overseas` ok=False) `fetch_broker_balance`가 이를 알리지 않는다. 그래서 실행 모달에서 해외 매도 행이 조용히 사라진다(56 이전부터 있던 문제) | `BrokerBalanceResponse`에 `overseas_ok: bool`을 추가하고, 프론트 실행 모달에서 false면 경고 배너를 띄우고 해외 매도를 차단한다 |

## 배치 C — 백엔드 실버그 (입력·트랜잭션)

| # | 문제 | 수정 |
|---|---|---|
| C1 ✔ | **`POST /external/transactions`가 금액을 검증하지 않는다** (`external.py:251-254`, `amount: float`). 음수 DEPOSIT은 MANUAL 계좌 예수금을 줄이고(`:329-330`), 1e16을 넘는 값은 Numeric 오버플로로 500이 난다. `notes`에는 길이 제한이 없다 | 내부 `TransactionCreate`가 쓰는 `validate_positive_amount`·`MAX_AMOUNT_KRW`(`schemas/_validators.py`)를 재사용하고 `notes`에 max_length를 둔다. NaN도 거부한다(C5) |
| C2 ✔ | **실패한 plan leg가 PENDING에 영구히 남을 수 있다.** `plan_execution.py:263`이 `token_consumed_at`을 먼저 커밋하고, `_execute_leg`의 except(`:155-166`)는 rollback 없이 FAILED를 커밋한다. 원인 예외가 DB 오류면 이 커밋이 `PendingRollbackError`를 던져 leg가 PENDING+consumed로 남는다. 이런 leg를 정리하는 경로가 없다(`token_consumed_at` 사용처 3곳 모두 skip). `execute_due_buy_legs`·`expire_due_sell_legs`에는 leg별 try가 없어 한 건이 실패하면 나머지 leg도 처리되지 않는다 | ① except에서 `await db.rollback()` 후 `db.get`으로 leg를 다시 읽고 FAILED를 기록한다(rollback 후 ORM expire 함정에 주의, 계획 39·40 참고. 필요한 값은 rollback 전에 지역변수로 빼 둔다). ② 두 루프에 leg별 try/except와 rollback을 넣는다. ③ 안전망: `token_consumed_at`이 N분 넘게 지났는데 PENDING인 leg를 FAILED("execution_state_unknown")로 마감하는 sweep을 기존 expire 잡에 붙인다. 실주문이 나갔을 수 있으니 재실행하지 않고 알림만 보낸다 |
| C3 ✔ | **`check_rebalancing_alerts`(`alert_check.py:339`)에 알림별 try가 없다.** `build_rebalancing_orders`, `save_alert_history`, commit 중 하나만 실패해도 남은 사용자의 알림이 전부 처리되지 않는다. `stock_price_service.py:42`, `exchange_rate_service.py:48`도 같은 구조다 | 루프 본문을 try/except와 rollback으로 감싸고 실패를 로그로 남긴다. 계획 40의 "알림 루프 항목별 세션" 패턴을 쓴다(내부 commit이 있어 savepoint는 쓸 수 없다). 요청 경로의 `drift_summary_service.py:56-76`·`insight_service.py:169-180`에도 `action_items_service.py:165-176`처럼 rollback을 넣는다 |
| C4 ✔ | **목표 연도에 상한이 없다.** `settings.py:68`은 하한만 검사한다. 10000을 저장하면 `goal_return_solver.py:26`의 `date(target_year,12,31)`이 실패해 목표 추천이 계속 500이 난다. `invest.py:38`의 `target_year: int = Query(...)`에도 범위가 없다 | 상한을 `today+100`으로 둔다(검증기와 Query `ge/le` 모두). `birth_year`도 범위를 확인한다 |
| C5 | Pydantic 입력 범위 일괄 정리. 문자열이 DB 컬럼 길이를 넘으면 422 대신 500이 난다 | 대상: `schemas/portfolio.py`(name 100, ticker 20, name 200, market Literal), `schemas/asset.py`(name·institution·notes·키 필드 max_length, `ManualPosition.current_price ≥ 0`), `schemas/transaction.py`(ticker 50), `stock_price_alerts.py`·`exchange_rate_alerts.py`(길이, target 상한: Numeric(10,2)), `settings.py`(`api_key`·`fcm_token` 512, 금액 `MAX_AMOUNT_KRW`), `schemas/rebalancing/execution.py`(`side: Literal["BUY","SELL"]`, `quantity` gt=0, `orders` max_length). `_validators.py`에 `math.isfinite` 검사를 넣어 NaN·Inf를 막는다. 각 스키마의 컬럼 길이는 모델에서 확인한다 |
| C6 | `limit` 쿼리 파라미터에 하한이 없다. `rebalancing_execution.py:162`(`le=100`만 있어 음수면 Postgres 500), `stocks.py:47`. 백테스트 `start_date` 하한도 없다(`backtest_service.py`가 일 단위로 루프), `portfolio_ids`·`account_ids` 리스트에 길이 상한이 없다 | `ge=1`, 백테스트 시작일은 최대 30년 전까지, 리스트는 `max_length` |
| C7 ✔ | `/portfolio-analysis/risk`가 `portfolio_id`를 받지만 캐시 키에만 쓰고(`risk_service.py:110`) 계산은 늘 전체 계좌로 한다. 임의 문자열로 캐시 키를 무한히 만들 수 있다. `/rebalancing-strategy`는 `str`을 UUID 컬럼과 비교한다 | 프론트 호출부에서 `portfolio_id`를 실제로 쓰는지 확인한다. 쓰지 않으면 파라미터를 삭제하고, 쓰면 `UUID` 타입으로 받아 계산에 반영한다. `/rebalancing-strategy`도 `UUID` 타입으로 바꾼다 |

## 배치 D — 예외 메시지 노출

| # | 문제 | 수정 |
|---|---|---|
| D1 ✔ | 원시 예외 텍스트가 응답과 DB에 그대로 들어간다. `_order_executor_common.py:78` `error_msg=str(e)`(catch-all), `execution_service.py:90,110` `str(error)`, `plan_execution.py:158,165` `error_message=str(exc)`(알림에도 포함), `rebalancing.py:344` `error=str(r)`. SQLAlchemy 오류 문자열에는 SQL 파라미터(토큰 등)가 들어갈 수 있다 | 공용 헬퍼 `public_error_message(exc)`를 만든다. `AppError`·`HTTPException`·`ProviderError`는 그 메시지를 쓰고, 나머지는 "내부 오류(타입명)"로 바꾼다. 내부 구현은 `core/logging.py`의 `redact_secrets`·`format_sync_error`를 재사용한다. 네 곳에 적용한다 |
| D2 | `providers/_error_mapping.py:17,19`가 `str(HTTPStatusError)`로 폴백하는데, 이 문자열에는 쿼리스트링에 계좌번호(CANO)가 담긴 URL이 들어 있다. `http_client.py:190,195`가 `RuntimeError(f"...{e}")`를 만들고 키움이 이를 `str(e)`로 전달한다 | 폴백 메시지에서 URL을 빼고 상태코드만 남긴다. `mask_account_no`·`redact_secrets`를 거치게 한다 |

## 배치 E — 성능·프론트 정리 (선택)

- E1 N+1: `external.py:98-99`(계좌별 `get_latest_snapshot`, 최대 200개, 외부 호출 빈도 무제한)와 `external_queries.py:97-98`을 `_snapshot_queries.latest_snapshot_subquery`를 쓰는 IN 쿼리 하나로 바꾼다. `challenge_service.py:239,326`은 `_monthly_net_deposits`를 챌린지 id 목록 하나로 묶어 조회한다.
- E2 `useSyncAllWatcher.ts`: 이전 폴링이 진행 중이면 다음 회차를 건너뛰고(in-flight 가드), 오류는 연속 3회일 때만 종료한다(55 이관).
- E3 `api/client.ts:63-65`: 대기열에서 재시도하는 요청에 `_retry = true`를 설정한다(55 이관).
- E4 inline `staleTime` 5곳(`RebalancingHistoryTab.tsx:414,420`, `useWidget.ts:17`, `staleTime: 0` 2곳)을 `STALE_TIME` 상수로 바꾼다(55 이관). `staleTime: 0`은 의도된 값이라 상수 `STALE_TIME.NONE`으로 둔다.
- E5 `usePositionsEditor.ts:78`: 가격 스피너를 인덱스 대신 `_rowKey`로 추적한다. `RebalancingExecutionModal.tsx:114`: 가격 로딩 중에는 지정가 누락 경고 대신 "가격 불러오는 중"을 표시한다.
- E6 `RebalancingConfirmStep`·`RebalancingOrderTable` 렌더 테스트(56 이관).

## 이관 (이번 미구현)

- 국내 지정가 호가단위 반올림(`kis/order.py:51`·`kiwoom/order.py:43`의 `int()` 절사): 호가 테이블과 ETF 예외 규칙 확인이 필요하다. 실주문 경로라 별도 계획으로 한다
- `plan_execution` 해외 지정가 1개 실패 시 leg 전체 FAILED: 설계 판단이 필요하다(부분 실행 허용 여부)
- `stock_price_service` 대표 사용자 1명의 자격증명 사용, `price_map`이 ticker만 키로 쓰는 문제(캐시 키는 이미 market 포함)
- `order_builder.py:131`의 `math.floor(float)` 경계 오차(2.9999 → 2): 실관측이 생기면 처리한다
- 55 이관: 보존 정책, 스케줄러 락, FK 인덱스, `uq_positions_account_ticker_current`, lite overview 타입 분리(현재는 빈 배열이라 형태는 일치한다)
- 대형 컴포넌트 15개(400줄 이상, `StockHoldingsTable` 650줄), `noUncheckedIndexedAccess`, `no-floating-promises` error 승격

## 검증

```bash
make lint && make typecheck
make test-backend-cov     # 기준선 2652 tests / 91.13%
make test-frontend        # 기준선 1653 tests
cd backend && uv run --no-sync pip-audit   # A 후 0건(또는 수정 버전 없는 항목만)
```
- B1: 헤더 형태 세 경우 단위 테스트. 배포 후 Render 직접 호출에 XFF를 위조해도 같은 버킷인지 수동 확인한다
- C1·C2·C3·C4·B3·B4: 수정 전 실패하는 회귀 테스트를 먼저 작성한다. C2는 `execute_rebalancing`이 DB 오류를 던지는 mock으로 leg가 FAILED가 되는지, 다음 leg가 처리되는지 확인한다
- A: 백엔드 전체 테스트와 `make dev-backend` 기동 스모크(starlette·cryptography 업그레이드)
- 마지막에 `backend/CLAUDE.md`(레이트리밋 키 규칙, 예외 메시지 헬퍼)와 `docs/plans/README.md` 57행을 갱신한다
