# 56. 기술부채 감사 (2026-10-15 오후)

## Context

계획 55가 오늘 오전 끝나 PR #132로 머지됐다(71131ef). 그 뒤 변경은 없다. 그래서 이번 감사는 두 축이다.
1. **55에서 새로 쓴 코드의 회귀** — 방금 쓴 코드에 버그가 숨는다. 실제로 2건 확정.
2. 55까지 안 다룬 축 — 프론트 입력 검증·비동기 경합·테스트 품질. 백엔드 신규 축 조사는 세션 한도로 중단됐다. 인가 검사만 휴리스틱(경로 id 라우트 37개 중 user 검사 없는 곳 grep)으로 확인했고, 토큰 기반 공개 라우트 3개 외엔 이상이 없었다.

실버그 후보는 코드를 직접 읽어 확인했다(✔ 표시).

깨끗했던 영역: 프론트 queryKey 누락·`/undefined` 요청 0건, 미사용 의존성 없음(차트·HTTP 라이브러리 단일), `pytest.mark.skip` 사유 누락 0, 55의 broker_request 5xx·429 분기, 알림 루프 commit 세션(`expire_on_commit=False`), 가입 orphan 검사, app_state_sweep, 55 AsyncSession 순차화.

**실행 첫 단계**: 이 계획을 `docs/plans/56-technical-debt-2026-10-15b.md`로 옮기고 README에 행 추가 → `git status`로 동시 세션 확인 → 브랜치 `fix/tech-debt-2026-10-15b` → 배치마다 커밋. 실버그는 회귀 테스트를 붙이고 수정 전 코드에서 실패하는지 확인한다.

---

## 배치 A — 55 회귀 (최우선)

| # | 문제 | 수정 |
|---|---|---|
| A1 ✔ | **토스 소수점 보유 시 브로커 잔고 API가 깨진다.** 55 B1로 `Position.qty`가 float가 됐는데 `schemas/rebalancing/execution.py:72` `KisBalancePosition.quantity: int`가 남았다. `broker_balance_service.py:91`이 0.5를 넣으면 Pydantic이 거부 → `GET /rebalancing/broker-balance/{id}` 400, `/broker-balance-all`은 해당 계좌 positions=[] | `quantity: float`로 바꾼다. 프론트 `api/rebalancing.ts` 타입과 수량 표시(정수 포맷 가정)를 확인한다. 토스 0.5주 fixture로 회귀 테스트 |
| A2 ✔ | **페이지 상한(20) 도달 시 잔여 보유종목이 DB에서 지워진다.** `kis/balance.py:57-58`, `kiwoom/balance.py:70-71`은 경고만 남기고 부분 목록을 반환하고, `asset_service.py:178-194`는 현재 포지션을 전부 지우고 받은 것만 다시 넣는다. 같은 연속키를 반복하는 응답이면 같은 행이 20배로 쌓인다 | 상한 도달 시 raise해 동기화 실패로 처리(기존 포지션 보존 경로). 연속키가 직전과 같으면 즉시 raise(`kis/realized.py`의 반복 키 검사 재사용). 두 경우 테스트 |
| A3 | 레이트리밋 키: `limiter.py:15` docstring의 "위조 토큰은 401뿐"이 틀렸다. ① 자체 limit이 있는 공개 라우트(종목 검색·환율·`rebalancing_plan_public` 토큰 라우트)는 매 요청 다른 `sub`로 우회 가능 ② 데코레이터 없는 라우트는 인증 전에 키를 계산하므로, 피해자 UUID로 기본 120/min 버킷을 소진시킬 수 있다 ③ 깊게 중첩된 JSON payload는 `RecursionError` → 500 | 서명 미검증 `sub`는 **인증이 필요한 라우트에서만** 쓰고, 공개 라우트는 IP 키로 고정한다(라우트 데코레이터에 `key_func=` 지정 또는 경로 prefix 판단). payload 디코드 예외를 `Exception`으로 넓히고 길이 상한. docstring 정정 |
| A4 | `core/logging.py:60` `type(value)(generator)`가 namedtuple에서 `TypeError` → 로깅 호출부에서 예외 | tuple 서브클래스는 `tuple(...)`로 재구성(또는 `_fields` 있으면 그대로 redact 후 `_make`) |
| A5 | 55 C6 `include_name`이 있어도 `aa2_add_snapshots_user_date_index`의 raw SQL 인덱스 `idx_snapshots_user_date_desc`가 모델에 없어 `alembic check`가 diff를 낸다. `env.py:28-34` 주석은 막는 것처럼 읽힌다 | 모델에 `Index(..., sa.text("snapshot_date DESC"))`로 선언하거나 `include_object`로 해당 인덱스를 제외한다. 52 G squash 전까지는 후자(제외+주석 정정)가 저위험. `alembic check` 빈 diff 확인 |

## 배치 B — 프론트 실버그

| # | 문제 | 수정 |
|---|---|---|
| B1 ✔ | **음수 목표 비중이 저장된다.** `PortfolioItemRow.tsx:128` `min={0}`은 입력만 막지 않고, 프론트 저장 게이트(`usePortfolioItemsEditor.ts:29-30`)와 백엔드 `validate_portfolio_weights`(`_validators.py:24`)가 합계만 본다. A=110, B=-10 저장 가능. 빈 티커 행도 그대로 전송 | 백엔드 `PortfolioItem.weight`에 `Field(ge=0, le=100)`, ticker `min_length=1`. 프론트 게이트에 음수·빈 티커 검사와 안내 문구 |
| B2 ✔ | **LIMIT 주문 한 행의 가격이 비면 전체 배치가 422.** `rebalancingExecution/index.ts:273-276,292-295` `getLimitPriceNative(...) \|\| null` → 백엔드 `execution.py:21-24`가 LIMIT+null을 거부. 미국 시세 1개만 실패해도(`livePricesUsd[ticker] ?? 0`) 전부 실패 | 실행 버튼 활성 조건에 "LIMIT인데 가격 0인 선택 행 없음"을 추가하고 해당 행을 강조·문구 표시. 실행 직전 검증 함수로 분리해 단위 테스트 |
| B3 ✔ | **비밀번호 재설정 페이지가 무한 "확인 중"에 머물 수 있다.** `api/client.ts:22`가 부팅 시 Supabase를 초기화하며 URL 세션을 소비하고 `PASSWORD_RECOVERY`를 1회 발생시킨다. `ResetPasswordPage.tsx:27-47`는 지연 청크 로드 후 구독하므로 이벤트를 놓칠 수 있다 | `AuthCallbackPage.tsx:74-78`처럼 구독 후 `getSession()`을 확인해 세션이 있으면 ready. URL에 `type=recovery`가 없었는데 세션만 있는 경우(일반 로그인 상태)와 구분하는 방법을 구현 시 확인하고, 타임아웃 후 "링크 만료" 안내를 둔다 |
| B4 ✔ | **현재가가 엉뚱한 행에 들어간다.** `usePositionsEditor.ts:73-93` `loadPrice`가 await 후 인덱스로 `setRow`. 로딩 중 위 행 삭제나 같은 행 종목 재선택 시 오염 | 인덱스 대신 행의 `_rowKey`로 대상 지정, 응답 시점에 그 행의 ticker가 요청 ticker와 같을 때만 반영. 경합 테스트 2개 |
| B5 | `GoalRecommendationOptionsModal.tsx:70-73` 단기 주식 하한을 비우면 `Number("")=0`이 저장됨(다른 필드는 null 처리) | `""` → null로 다른 필드와 통일 |
| B6 | `useStockSearch.ts:36-41` 중단된 이전 검색의 finally/catch가 새 검색 중 스피너를 끄고 결과를 비움 | abort된 요청이면 상태를 건드리지 않는다 |
| B7 | 포지션 편집기 수량 0·음수가 백엔드 422로만 드러남(어느 행인지 모름) | 저장 전 행 단위 검증 메시지 |

## 배치 C — 테스트 품질

- C1 `tests/test_kiwoom_order_executor.py:140,196` 잔고 mock `"market": "NASDAQ"` → 실제 응답 형태 `"US"`로 교체(55 A1과 같은 함정 재발 방지).
- C2 무의미 단언 보강: `test_snapshot_queries.py:18,23,28,34`(WHERE 절 컴파일 문자열 검사), `test_returns_calculator.py:52`(XIRR 기대값), `test_dca_service.py:289`, `test_token_refresh_job.py:24`(갱신 호출 0회 단언), `test_rebalancing_auto_execution.py:1040`(알림 2개로 루프 계속 확인).
- C3 UTC/KST 불일치: `test_goal_recommendation.py:3798-3801`, `test_tax_service_extended.py:328`를 `today_kst()` 기준으로. (freezegun 도입은 하지 않는다 — 기존 `FakeClock`/monkeypatch 패턴 사용)
- C4 커버리지 0% 실주문 화면: `RebalancingExecutionModal`·`RebalancingConfirmStep`·`RebalancingOrderTable` 최소 렌더·실행 버튼 게이트 테스트(B2 테스트와 함께).

## 배치 D — 저위험 정리 (선택)

- D1 미해제 타이머 5곳(`PerAccountRebalancingAlertList.tsx:71`, `AlertActionsSection.tsx:71`, `TickerSearchField.tsx:86`, `TransactionTickerField.tsx:77`, `GoalCandidateManagerModal.tsx:214`) cleanup — 55 이관 항목 종결.
- D2 `package.json`의 `generate:api-types` 스크립트(존재하지 않는 파일 생성) 삭제 또는 문서화.
- D3 `plan_execution.py:117` 미국 지정가 1개 갱신 실패 시 국내 포함 leg 전체 FAILED → 이번엔 문서 메모만(설계 판단 필요, 이관).

## 이관 (이번 미구현)

- 백엔드 신규 축 감사(Pydantic 입력 범위·N+1·`str(e)` 노출·float 금액·잡 사용자별 격리) — 중단됨, 다음 감사에서
- 55 이관 목록 그대로 유지(보존 정책, 스케줄러 락, FK 인덱스, `uq_positions_account_ticker_current` 등)
- 대형 컴포넌트(`StockHoldingsTable` 650줄 등 15개 400줄+), tsconfig `noUncheckedIndexedAccess`, eslint `no-floating-promises` warn→error

## 검증

```bash
make lint && make typecheck
make test-backend-cov     # 기준선 2640 tests / 91.11%
make test-frontend        # 기준선 1637 tests
cd backend && uv run alembic check   # A5 후 빈 diff
```
- A1·A2·A3·B1~B4는 수정 전 코드에서 실패하는 테스트를 먼저 확인
- B3은 가능하면 Playwright로 재설정 링크 흐름 스모크(실 이메일 링크 불가 시 단위 테스트+코드 리딩으로 기록)
- 마지막에 `backend/CLAUDE.md`(레이트리밋 키 규칙), `docs/plans/README.md` 56행 갱신
