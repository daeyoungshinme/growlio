# 55. 기술부채 감사 (2026-10-15)

## Context

"기술부채 확인 + 수정 계획" 요청. 계획 54(어제)가 A·B·C 모두 끝났고(PR #131 열림), 그 뒤 변경은 Dependabot 마이너 범프뿐이다. 그래서 52(백엔드 구조)·53(모바일 UX)·54(프론트 코드·CI)에 없는 **새 축 3개**를 병렬로 조사했다(Explore 3개).
1. 백엔드: 금액 정밀도, 브로커 API 견고성, 비동기 정확성, 로그 내 비밀정보
2. 프론트: 타입 우회, 응답 검증, effect 누수, Query 설정, NaN
3. DB·설정: 모델↔마이그레이션 드리프트, 인덱스, 보존, 스케줄러, 인증·레이트리밋

**실버그 후보는 모두 코드를 직접 읽어 확인했다.** 특히 실주문 경로에서 3건이 확정됐다(A1~A3).

깨끗했던 영역(조치 없음): 프론트 `as any`/`@ts-ignore` 0개, mutation 전부 onError 있음, httpx 타임아웃·`async with` 정상, yfinance/pykrx 전부 executor, 스케줄러 coalesce/max_instances/misfire 설정, CORS·보안헤더, `noqa`/TODO 0개, alembic 단일 head.

사용자 결정:
- 범위는 A+B+C 전부. D는 시간이 남으면 한다
- B6 페이지네이션은 포함한다(fixture 테스트로 확인, "실계좌 미검증"으로 기록)

**실행 첫 단계**
1. 이 계획을 `docs/plans/55-technical-debt-2026-10-15.md`로 옮기고 `docs/plans/README.md`에 행을 추가한다.
2. PR #131(계획 54)이 머지된 뒤 origin/main 기준으로 브랜치 `fix/tech-debt-2026-10-15`를 만든다. 머지 전이면 #131 브랜치 위에 쌓는다.
3. 시작 전에 `git status`/`git diff`로 동시 세션 변경이 있는지 확인한다.
4. 배치마다 커밋한다. 실버그는 회귀 테스트를 붙이고, **수정 전 코드에서 실패하는지 확인**한다.

**계획 52와의 경계**
- A1은 52 B3(KIS/키움 sell clamp 병합) **이전에** 고친다. B3에서 병합할 때 고친 키 규칙을 공용 헬퍼로 그대로 가져가도록 52 문서 B3 행에 한 줄 메모를 남긴다.
- B6(알림 루프 커밋)은 52 E1 러너와 겹치지 않는다. E1은 사용자 단위 잡 대상이고, 가격·환율 알림 루프는 E1 대상 목록에 없다.
- C6의 인덱스 복구는 52 G squash **전에** 해야 baseline에 반영된다.

---

## 배치 A — 실주문 경로 실버그 (최우선)

| # | 문제 (확인 근거) | 수정 |
|---|---|---|
| A1 | **키움 해외 매도가 전부 SKIPPED된다.** `_kiwoom_order_executor.py:93-98`은 보유수량 맵 키를 `ticker:market`으로 만드는데, 잔고의 market은 `kiwoom/balance.py:232`의 `_UNRESOLVED_MARKET = "US"`이고 주문의 market은 NYSE/NASDAQ/AMEX다(`is_overseas_market`이 그 3개만 해외로 분류). 그래서 `AAPL:US` ≠ `AAPL:NASDAQ`이라 보유 0으로 판정된다. b60aa0f(2026-09-07)에서 잔고 market이 "US" 센티널로 바뀐 뒤부터다. 테스트는 잔고 mock을 `"NASDAQ"`으로 줘서 못 잡았다(`tests/test_kiwoom_order_executor.py:140`). KIS는 실제 거래소명을 돌려줘서 해당 없다 | 키를 `ticker`(해외는 키움 단일 해외계좌라 거래소 구분 불필요) 또는 `ticker:market_group(market)`으로 양쪽을 정규화한다. `order_builder.market_group`을 재사용한다. 테스트 mock을 실제 응답과 같은 `"US"`로 바꾸고, 그 상태에서 수정 전 코드가 실패하는지 확인한다 |
| A2 | **해외 지정가가 원화 값으로 달러 주문에 나갈 수 있다.** `order_builder.py:311-316`은 `current_price_krw`(`fetch_prices_batch_krw`, KRW)를 `limit_price`로 쓴다. `plan_generation.py:106`도 해외 MARKET→LIMIT 강제 시 KRW인 `reference_price`를 지정가로 넣는다. `plan_execution.py:109-113`은 실행 직전 `fetch_prices_batch`(현지통화)로 다시 받을 때만 이를 덮어쓴다. 조회가 실패하면(Yahoo 서킷 열림 등) KRW 값이 `kis/order.py:114`·`kiwoom/order.py:102`에서 `:.2f` 달러로 전송된다. 매수는 약 1,400배 지정가, 매도는 미체결이다 | 규칙 하나로 통일한다: **해외 `limit_price`는 항상 현지통화, `reference_price`는 KRW.** ① 계획 생성 시 해외 종목은 현지통화 가격으로 limit을 채운다(`fetch_prices_batch` 재사용, 실패하면 limit=None). ② `plan_generation` 강제 LIMIT은 현지통화 가격이 있을 때만 하고, 없으면 SKIPPED로 남긴다(지금도 reference 없으면 skip). ③ `plan_execution`에서 갱신에 실패한 해외 LIMIT은 저장값을 쓰지 않고 FAILED/SKIPPED로 처리한다. ④ 최후 방어로 실행기(`_order_executor_common`)에서 해외 LIMIT이 `limit_price > reference_price_krw / 100`처럼 원화로 보이면 거부한다(환율 의존 없는 단순 상식 검사) |
| A3 | **주문 POST가 HTTP 5xx에서 재시도된다.** `providers/http_client.py:172-175`. `retry_on_request_error=False`(`kis/order.py:73,138`)는 전송 오류만 막고, 502/504는 최대 `retries`회 재전송된다. 브로커가 이미 접수한 뒤의 5xx면 중복 주문이 난다 | `broker_request`에 `retry_on_server_error: bool = True`를 추가한다. 주문 호출(KIS 2곳, 키움 주문)은 `False`를 넘긴다. 5xx면 "처리 여부 불명" 메시지로 raise해 기존 `retry_on_request_error=False` 경로와 같은 결과(FAILED + 확인 안내)가 되게 한다. 429/rate-limit 본문 재시도는 그대로 둔다 |
| A4 | (예방) 주문 방향은 `diff_krw` 부호, 수량은 `shares_to_trade`로 서로 다른 필드에서 온다(`order_builder.py:289,299`). `refresh_live_prices`가 일부 종목 가격 조회에 실패하면 두 값의 기준 시점이 달라 부호가 어긋날 수 있다 | 방향을 `shares_to_trade` 부호에서 정하고, `diff_krw` 부호와 다르면 `reason="direction_mismatch"`로 건너뛰고 로그를 남긴다 |

## 배치 B — 데이터·화면 정확성 실버그

| # | 문제 | 수정 |
|---|---|---|
| B1 | **토스 소수점 주식 수량이 잘린다.** `toss/balance.py:133` `"qty": int(qty)` → 0.5주는 0주, 평가액 0. `Position.qty`는 `Numeric(18,4)`라 자를 이유가 없다 | `float(qty)`로 유지한다. 소비처에서 `int(qty)`를 가정하는 곳(포지션 집계·period_purchase)을 grep으로 확인한다. 토스는 주문 불가 계좌(`isOrderExecutableAccount`)라 주문 경로 영향은 없다 |
| B2 | **AsyncSession 동시 사용이 남아 있다**(09-17 대시보드 수정과 같은 종류). `composition_calculator.py:82,104`, `insight_service.py:77`, `api/v1/stocks.py:216`(`_kis_price_fallback`이 토큰 저장 commit), `price_service.py:168`(KIS 폴백) | 같은 세션을 쓰는 gather는 순차 await로 바꾼다. 세션을 쓰지 않는 네트워크 폴백만 gather로 남긴다(`domestic_price_fallback`은 그대로). 09-17 수정과 같은 패턴이다 |
| B3 | **목표 마법사가 저장에 실패해도 추천을 보여준다.** `useGoalSettings.ts:190-193`은 실패해도 `finally`에서 `saving=false`로 바꾸고, `useRecommendationStepAutosave.ts:29-34`는 `saving` true→false만 보고 `settingsPersisted=true`로 둔다. 그래서 이전 설정 기준 추천과 "이 추천으로 포트폴리오 만들기"가 노출된다. 추천 쿼리 실패 시 `GoalWizardRecommendationStep`은 빈 화면이다 | `onSave`가 성공 여부(boolean)를 반환하게 하고, autosave는 성공일 때만 persisted로 둔다. 실패하면 재시도 버튼이 있는 에러 상태를 보여준다. 쿼리 에러 분기도 추가한다. `openEdit`/`openWizard`의 `void` 호출에는 catch와 토스트를 단다(지금은 실패하면 모달이 조용히 안 열림) |
| B4 | 프론트 소규모 확정 버그: `StockPositionsModal.tsx:57-71` fetch 경합(계좌 전환 시 이전 응답이 덮어씀, unmount 후 setState), `usePositionsEditor.ts:101-108` blur 지연 콜백의 stale `suggestIdx`, `usePortfolioItemsEditor.ts:102-108`의 `totalValue === 0`에서 NaN 비중이 백엔드로 전송됨 | cancelled 플래그, 행 인덱스를 콜백 인자로 캡처, 0 가드(전부 0이면 균등 또는 가져오기 거부) |
| B5 | **가격·환율 알림 루프가 전체 사용자를 한 트랜잭션으로 처리한다.** `alerts/exchange_rate_service.py:34-76`, `alerts/stock_price_service.py:22-80`, `rebalancing/alert_check.py:321-424`는 메일을 보낸 뒤 맨 끝(`finalize_alert_batch`)에서 한 번 commit한다. 중간에 DB 오류가 나면 이미 발송한 알림의 `last_triggered_at`이 롤백돼 다음 실행에 중복 메일이 간다 | 발송 직후 항목별로 commit한다(계획 40에서 만든 "알림 루프 항목별 세션" 패턴을 재사용하고, 내부 commit 때문에 savepoint는 쓸 수 없다). `finalize_alert_batch`는 메트릭과 로그만 남긴다. `alert_check.py:65`의 `set_durable(commit=True)`가 배치 중간에 부분 commit하는 것도 이 수정으로 정리된다 |
| B6 | **KIS·키움 잔고 조회에 페이지네이션이 없다.** `kis/balance.py:47-48,158-159`는 연속조회 키를 빈 값으로 한 번만 보낸다. 원인은 `broker_request`가 응답 헤더(`tr_cont`)를 버리는 것이다. 실계좌 기준 한 페이지(KIS 국내 약 50행)를 넘는 보유종목이 사라져 매도된 것처럼 보인다. `kis/realized.py`만 올바르게 구현돼 있다(`_MAX_PAGES` + 반복 키 검사) | `broker_request`에 헤더를 함께 돌려주는 옵션(`return_headers`)을 추가하고, `realized.py`의 루프 패턴을 잔고 2곳에 적용한다. 키움 kt00018/ust21070은 `cont-yn`/`next-key`로 같은 처리를 한다. **실계좌로 검증할 수 없으니** 응답 fixture 기반 2페이지 테스트로만 확인하고, 문서에 "실계좌 미검증"으로 남긴다 |

## 배치 C — 보안·DB 하드닝

| # | 문제 | 수정 |
|---|---|---|
| C1 | **레이트리밋이 사용자 전체에 걸린 하나의 버킷일 가능성이 높다.** `limiter.py:8`은 `get_remote_address`를 쓰는데, 요청은 Vercel rewrite → Render 프록시를 거치고, `render.yaml`의 uvicorn에는 `--proxy-headers`/`--forwarded-allow-ips`가 없다. 그러면 `/auth/account/delete`·`/auth/find-account`(3/hour), 자산 동기화(3/minute)를 모든 사용자가 공유한다 | 먼저 확인: 운영 로그에서 `request.client.host`가 여러 사용자에 걸쳐 같은 값인지 본다(임시 debug 로그 1줄 또는 Render 로그). 수정: key_func를 **인증된 요청은 JWT `sub`(검증 없이 디코드, 버킷 구분용), 그 외는 `X-Forwarded-For`의 첫 hop**으로 바꾼다. Render 진입점이 하나뿐이므로 `startCommand`/Dockerfile에 `--proxy-headers --forwarded-allow-ips='*'`를 추가한다. key_func 단위 테스트를 붙인다 |
| C2 | **가입 시 같은 이메일의 기존 사용자를 데이터째 삭제한다.** `auth.py:53-61`의 "고아 row 정리"는 새 토큰의 email만 보고 CASCADE 삭제한다. Supabase 프로젝트를 nestlio와 공유하므로, 같은 이메일이 다른 sub로 들어오는 경로(미연결 OAuth identity, 이메일 확인 설정 변경)가 생기면 남의 데이터가 지워진다. JWT `iss` 검증도 없다(`auth_service.py:37-44`) | 삭제 전에 Supabase admin API(`service_role`, 계정 삭제 경로에 있는 기존 호출을 재사용)로 옛 `orphan.id`가 Auth에 **없는지** 확인하고, 있으면 409를 반환하고 Sentry로 보고한다. JWT 디코드에 `issuer=f"{supabase_project_url}/auth/v1"`를 추가한다. 로그의 email 필드는 마스킹한다 |
| C3 | **로그 마스킹이 dict를 지나친다.** `core/logging.py:38-42`는 최상위 str만 redact한다. `http_client.py:142` `body=error_body`(dict), `kis/auth.py:99` `response=data`가 마스킹 없이 나간다. 계좌번호는 `kis_provider.py:55,99,104`, `kiwoom_provider.py:52,83,89`, `_kis_order_executor.py:178`에서 평문으로 찍힌다 | processor가 dict/list를 재귀로 돌며 redact하게 바꾼다. 계좌번호 로그는 `mask_account_no()`(뒤 4자리만) 헬퍼로 바꾼다. 비슷한 헬퍼가 이미 있으면 재사용한다 |
| C4 | 운영에서 `/redoc`·`/openapi.json`이 노출된다(`main.py:75`는 `docs_url`만 끈다) | prod에서 `redoc_url=None, openapi_url=None` |
| C5 | Supabase 설정 3개의 기본값이 `""`인데 prod 시작 검증(`_validate_secrets`)에서 확인하지 않는다. 비어 있으면 앱은 뜨고 모든 요청이 401이다 | `_validate_secrets`에 prod 필수 항목으로 추가한다 |
| C6 | **autogenerate가 인덱스를 지웠다.** `a64e36a53a40`이 `uq_positions_account_ticker_current`(현재 포지션 중복 방지 부분 유니크)와 `ix_asset_accounts_target_portfolio_id`를 드롭했다. 모델에 선언돼 있지 않았기 때문이다. 원인은 `alembic/env.py`에 `include_name` 필터가 없는 것이다. nestlio와 스키마를 공유하므로 autogenerate가 nestlio 테이블 드롭도 제안할 수 있다. DESC 인덱스 2개는 autogen마다 drop/create가 반복된다 | ① `env.py`에 growlio 모델 테이블만 비교하는 `include_name`을 추가한다. ② 두 인덱스를 모델 `__table_args__`에 선언하고 재생성 마이그레이션을 만든다. **유니크 인덱스는 먼저 운영에서 중복 행 수를 조회**하고, 있으면 정리 SQL을 마이그레이션에 포함한다(현재 포지션은 sync가 재생성하므로 최신 1행만 남긴다). ③ DESC 인덱스는 `sa.text("snapshot_date DESC")`로 모델에 선언해 반복을 멈춘다. ④ `alembic revision --autogenerate --sql`로 빈 diff인지 확인한다 |
| C7 | **`app_state` 만료 행이 쌓이기만 한다.** `durable_state.py:27`은 같은 키를 다시 읽을 때만 지우는데, 날짜가 포함된 dedup 키(`cache_keys.py:315-350`)는 다시 읽히지 않는다 | 기존 일일 잡에 `DELETE FROM app_state WHERE expires_at < now()`를 추가한다(새 스케줄 등록 없음) |

## 배치 D — 저위험 정리 (선택)

- D1 persist 캐시 `buster: "v1"` 고정 → 빌드 버전(`import.meta.env` 빌드 해시/`__APP_VERSION__`)에 묶는다. 배포 후 응답 형태가 바뀌어도 24h 동안 옛 캐시가 렌더되는 문제를 막는다. `App.tsx:140-146`의 "세션 만료 시 persist 보존" 주석은 `queryClient.clear()`가 persister에 빈 상태를 쓰므로 실제 동작과 다르다. 주석을 실제 동작에 맞춘다(동작은 지금처럼 비우는 쪽이 공용 기기에서 더 안전하다).
- D2 `api/client.ts` 401 갱신 큐(`failedQueue`/`processQueue`/`session-expired`) 테스트를 신설한다. 테스트가 없는 가장 위험한 로직이다.
- D3 `api/dashboard.ts:37` 백엔드에 없는 `benchmark_sp500_pct` 필드를 삭제한다. `fetchPortfolioOverviewLite`의 반환 타입을 `PortfolioOverviewLite`(positions 없음)로 분리해, 나중에 `.positions`를 읽으면 컴파일 에러가 나게 한다.
- D4 PR #129(vite-plugin-pwa 2.0): **이미 머지됨**(550cf91). 조치 없음.

## 이관 (이번 미구현)

- `asset_snapshots`·`positions`·`alert_history`·리밸런싱 이력 보존 정책: 제품 결정(보관 기간)이 필요하다
- 스케줄러 다중 인스턴스 락: 지금은 Render 단일 인스턴스라 안전하다. 스케일아웃 시점에 advisory lock
- FK 무인덱스 5개, 중복 인덱스(asset_snapshots 3중 등): 52 G squash와 같이
- `stock_price_service.py:37` 대표 사용자 1명의 KIS 자격증명으로 전원 가격 조회 + ticker 단독 키
- `users.needs_password_reset` server_default 불일치: 52 G에서 컬럼 드롭
- 응답 런타임 검증(Zod): 비용 대비 효과가 낮다. D1·D3로 대체한다
- inline staleTime 6곳 → `STALE_TIME` 상수, 미해제 타이머 5곳(저위험)
- `useSyncAllWatcher` 폴링 겹침과 1회 오류 시 종료, `rebalancingExecution` 잔고 1회 로드
- 국내 지정가 호가단위 반올림, 모델 `Mapped[float]` ↔ Numeric(Decimal) 타입 힌트
- persist 캐시의 계좌번호: 토큰과 같은 신뢰 경계(계획 28 결론)라 유지한다

## 검증

```bash
make lint && make typecheck
make test-backend-cov      # 기준선 2612 tests / 91.12%
make test-frontend
cd backend && uv run alembic upgrade head --sql | tail   # C6 오프라인 렌더
cd backend && uv run alembic check                        # C6 후 autogenerate diff 없음
```

- A1~A4, B1, B2, B5, B6, C1~C3: 회귀 테스트를 붙이고, 수정 전 코드에서 실패하는지 확인한다(A1은 잔고 mock을 실제 "US" 응답 형태로)
- A2: 해외 LIMIT 3경로(계획 생성·강제 LIMIT·실행 갱신 실패) 각각 테스트
- B3: 마법사 저장 실패 → 추천 미노출 + 재시도 버튼 컴포넌트 테스트
- C6: 운영 중복 조회 SQL 결과를 기록한 뒤 마이그레이션을 적용한다. 운영 DB 적용은 사용자 확인 후에 한다
- C1: 배포 후 Render 로그에서 서로 다른 사용자의 레이트리밋 키가 분리되는지 확인한다
- 마지막에 `backend/CLAUDE.md`(broker_request 옵션·로그 마스킹·레이트리밋 키)와 `docs/plans/README.md` 55행을 갱신한다
