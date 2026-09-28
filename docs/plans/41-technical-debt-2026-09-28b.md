# 41. 계획 40 이관 기술부채 처리 (2026-09-28, 2차)

계획 40 직후(같은 브랜치 `fix/tech-debt-2026-09-28`, 신규 커밋 없음) 40번 이관 13건을 코드와 대조했다.
**13건 모두 유효**했다. 사용자가 정한 범위는 **저·중위험 전부 + 대형 분해 1건(`market_signal_service`)**이다.
나머지 대형 분해는 다시 이관한다.

커밋 8개(마지막은 이 문서).

## 구현 완료

### 배치 A: 실버그 + 테스트 안전망

**A1. 해외 미확인 동기화의 스냅샷이 국내분만 반영(36 #11)** (`ab2038f`)

- `overseas_known=False`면 현재 포지션은 해외분을 보존했다. 그런데 `_upsert_snapshot(amount_krw=balance.total_value_krw)`와
  스냅샷 포지션 복사는 국내분만 받았다. 그래서 그날 스냅샷(월별 대표값 후보)이 해외분만큼 급락했다.
- KIS·키움 provider 확인 결과: 해외 조회에 실패하면 `total_value_krw`에 해외 종목뿐 아니라 **외화예수금도 빠진다**.
- 수정 내용(`asset_service._preserved_overseas_positions`):
  - 보존된 해외 포지션의 `value_krw`와 기존 `deposit_usd × 환율`을 스냅샷 금액에 더한다.
  - 매입금액과 손익도 보존분만큼 보정한다.
  - 스냅샷 포지션 = 국내 결과 + 보존 해외 포지션
- 보존 포지션의 `value_krw`는 직전 동기화 시점 값이라 약간 stale하다. 하지만 0으로 빠지는 것보다 훨씬 정확하다.

**A2. 테스트의 실DB 접속 차단 가드(40 N3-b)** (`86c3641`)

- `tests/conftest.py`: `engine.sync_engine`의 `do_connect` 이벤트에서 RuntimeError를 낸다.
- 잡 루프는 `except Exception`으로 예외를 삼킨다. 그래서 접속 시도를 기록해 두고 autouse 픽스처 teardown에서
  `pytest.fail`로 실패시킨다. 예외를 삼키는 프로브 테스트로 이 동작을 검증했다.
- **전수 점검 결과**: `test_api_routes::TestHealth`가 로컬 `.env` DB에 **실제로 접속**하고 있었다
  (`/health`의 `SELECT 1`, 200/503 둘 다 허용하는 assert라 드러나지 않았다).
  - `app.main.get_db`를 patch해 "200(DB 정상)"과 "503(DB 실패)" 결정적 테스트 2개로 나눴다.
- CI의 postgres 서비스는 alembic 마이그레이션 전용이라 이 가드와 무관하다.

### 배치 B: 중복 정리

**B1. `_fetch_and_store_token` 3벌 공용화(36 #2)** (`bdae10d`)

- `providers/_token_cache.store_token()`을 추가했다. 캐시 `setex(TTL−버퍼, 최소 60초)`와 DB 암호화 upsert를 담당한다.
- 브로커별로는 발급 요청, 만료 파싱, upsert 충돌 대상만 남는다.
  - KIS: 계좌/유저 2종 + `index_where`
  - 키움, 토스: `account_id`. 토스는 `is_mock_mode` 컬럼이 없다.
- `store_token` 단위 테스트 2건을 추가했다: TTL 계산·충돌 SQL·암호화, 단수명 토큰의 60초 하한.

**B2. `durable_state` commit 인자 → 챌린지 잡 savepoint(40 N3-a)** (`9891209`)

- `get_durable`, `set_durable`, `delete_durable`에 `commit: bool = True`를 추가했다. `get_durable`도 만료 row를 삭제하며
  커밋하므로 셋 모두에 넣었다. 기존 호출부의 동작은 그대로다.
- `challenge_deposit_reminder`, `challenge_monthly_wrap`을 챌린지 단위 `begin_nested()`와 챌린지별 커밋으로 바꿨다.
  내부 헬퍼는 전부 `commit=False`(dispatch, set/get_durable)로 호출한다.
  - 한 챌린지의 예외가 같은 유저의 나머지 챌린지 발송을 막지 않는다.
  - 월간결산의 완료 상태 `db.commit()`은 `flush()`로 바꿨다. 챌린지 단위 커밋에 포함된다.
- **`overseas_realized_service` 타임아웃 격리(39 A3)에는 적용하지 않았다.** 루프 안의 `get_access_token` →
  `store_token`이 토큰 발급 체인 깊숙이에서 커밋한다. savepoint로 감싸려면 `get_or_fetch_token` 클로저 체인 전체에
  commit 인자를 뚫어야 한다. 위험 창이 수 ms라 유지하고 이관한다(#N3-c).

**B3. `price_service`가 yahoo 진입점을 사용(40 #7-b)** (`855c13c`)

- 인라인 서킷·세마포어 3곳을 교체했다: `fetch_yahoo_price`, `fetch_yahoo_batch`, 신설한 `fetch_yahoo_returns_batch`.
  `_run_guarded`와 의미가 같다(예외는 서킷 기록 없이 전파).
- 테스트 patch 경로를 `yahoo_price.*`로 옮겼다. `_yfinance_sem`은 pykrx 경로가 계속 쓴다.

### 배치 C: 대형 분해 — `market_signal_service.py`(835줄 → 245줄, 36 #3) (`db32068`)

| 모듈 | 줄 수 | 내용 |
|---|---|---|
| `market_signal_indicators.py` | 543 | fetcher 12개 + `_inflation_bucket`/`_latest_value`/`_latest_date` |
| `market_signal_scoring.py` | 111 | `compute_composite_signal`, 임계값 상수(순수 함수) |
| `market_signal_service.py` | 245 | `get_market_signal`, `_fetch_all_signals`, hysteresis 함수군, 공개 심볼 재노출(`__all__`) |

- 로직 변경 없이 순수하게 이동만 했다. 외부 import 8곳은 그대로다.
- patch 경로 함정이 실제로 발생했다.
  - fetcher끼리 내부 호출을 한다: 인플레이션 → CPI/PCE, 금리커브 → 장단기/인하기대.
  - 그래서 `market_signal_service.fetch_{cpi,pce,yield_curve,rate_cut}_*`를 patch하던 테스트가 효력을 잃었다.
  - 해당 patch와 `patch.object(market_signal_service.fred_circuit)` 5곳, 총 10곳을 `market_signal_indicators` 경로로 옮겼다.
  - `get_market_signal`(43곳)과 `_fetch_all_signals`(3곳) patch는 파사드에 그대로 유효하다.
- `backend/CLAUDE.md` services 항목에 분리 구조와 patch 경로 규칙을 추가했다.

### 배치 D: 프론트

**D1. `@/api/client` 직접 사용 정리(40 #9-b)** (`b4bf270`)

- `useDividendData`의 `/dividends` 3종을 `api/dividends`(`fetchDividend{Positions,Summary,ByTicker}`)로 옮겼다.
- `PortfolioPage`의 `/portfolio/overview`는 `api/portfolios.fetchPortfolioOverview(accountId)`로 옮겼다.
  - 계좌 인자가 없으면 기존과 같은 호출 형태를 유지한다.
  - 프로덕션 호출부가 없던 무인자 함수를 확장한 것이다.
- `authStore`는 인증 부트스트랩(401 재시도 등)이라 제외하고 주석으로 명시했다.
- 공용 mock 모듈은 도입하지 않았다. `hooks.dividend` 테스트는 client mock에 `apiGet`을 추가해 기존 URL/params assert를 유지했다.

## 이관

**36/40번에서 유지**

1. `assets.py` 브로커 스펙테이블화 + 프론트 `*CredentialFields` 3벌 단일화(36 #1)
2. goal `_compute_*` 분해(스냅샷 하네스 선행), `create_rebalancing_execution_plan`, `_check_user_goals`(36 #4)
3. in-memory 캐시 LRU 축출 모니터링(36 #6)
4. 대형 컴포넌트 `RecommendationCard` 806줄, `StockAccountModal` 616줄 + 메이저 업그레이드 React 19, recharts 3, tailwind 4(36 #10)
5. 키움 NASDAQ 폴백 캐시, 2-leg 부분실행 가시성, 경쟁기능 격차(36 #12)

**신규**

- **#N3-c**: `overseas_realized_service` 계좌 루프의 타임아웃 격리. 토큰 저장 커밋이 `get_access_token` 체인 안에
  있어 savepoint가 불가하다. `get_or_fetch_token`에 commit 위임 인자를 도입할지 검토한다.
- **A1 후속**: 보존 해외 포지션의 `value_krw`는 직전 동기화 시점 값이다. 해외 미확인 동기화에서도 Yahoo 현재가로
  재평가할지 검토한다(우선순위 낮음).

**보류(제품 판단)**

- **N6**: DCA 알림이 여러 개일 때 사용자 단위 `monthly_deposit_amount` 비교의 의미가 모호하다.

## 검증

```bash
cd backend && .venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80 -q   # 2399 passed, 90.26%
cd backend && .venv/Scripts/python.exe -m ruff check app tests && .venv/Scripts/python.exe -m ruff format --check app tests && .venv/Scripts/python.exe -m mypy app
cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src --max-warnings=0
cd frontend && ./node_modules/.bin/vitest run && npx prettier --check src && npm run build   # 1595 passed
```

- 백엔드: 2391 → 2399 tests, 커버리지 90.23% → 90.26%
- 프론트: 1595 tests(수 변동 없음)
- ruff, ruff format, mypy, tsc, eslint, prettier, build 모두 클린이다.
- 실DB 가드가 켜진 상태에서 전체 스위트가 통과한다. 이제 실DB에 접속하는 테스트는 없다.
- 실계좌·실브라우저 검증은 하지 않았다.

배포 뒤 확인할 것:
1. 해외 조회가 실패한 날의 스냅샷 금액이 전일 대비 급락하지 않는지(A1)
2. KIS·키움·토스 토큰 발급 로그(`*_token_issued`)와 재사용이 정상인지(B1)
3. 매월 25일 독려와 1일 결산 알림이 챌린지별로 발송되는지(B2)
