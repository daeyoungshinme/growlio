# 40. 계획 39 이관 기술부채 처리 (2026-09-28)

`docs/plans/39`에서 이관된 18건(36번 유지분 11건과 신규 N1~N7)을 origin/main(`e0eb3d5`) 코드와 대조했다.
**18건 모두 유효**했고 해소된 항목은 없었다. `_token_cache.py`는 조회 3단계만 공용화돼 있고,
`_fetch_and_store_token`은 kis/kiwoom/toss `auth.py` 3곳에 그대로 남아 있다.

사용자가 정한 범위는 다음과 같다.

- **저위험·중위험만 처리한다.** 대형 분해(36 #1~#4, #10)는 다시 이관한다.
- **N5**: 주문 경로에서만 재시도를 끈다.
- **N7**: 처리한다. **N6**은 보류한다.

브랜치 `fix/tech-debt-2026-09-28`, 커밋 10개(마지막은 이 문서).

## 구현 완료

### 배치 A: 백엔드

**A1. N5: 주문 경로의 KIS rt_cd "1" 재시도 비활성화** (`7c8f69a`)

- `kis_request`에 `retry_transient_rt_cd` 인자를 추가하고, `kis/order.py`의 국내·해외 주문 2곳에서만 False로 넘긴다.
- 조회 경로의 1회 재시도는 유지한다.
- `test_broker_order_requests.py`에 rt_cd "1" 응답이면 요청이 1회만 나가는지 확인하는 케이스 2건을 추가했다.

**A2. N3: 공유 세션 알림 루프를 항목별 세션으로 격리** (`c1d63cb`)

계획 단계 정정: savepoint(`begin_nested`)는 쓰지 않았다.
- `set_durable`과 `dispatch_dual_channel_alert`가 **내부에서 `db.commit()`을 한다.** 그래서 nested 블록 안에서
  바깥 트랜잭션이 커밋되어 버린다.
- 이걸 고치려면 모든 호출부의 commit 책임을 옮겨야 한다. 중위험 범위를 넘는다.

대신 다른 잡(per-user `AsyncSessionLocal`)과 같은 패턴을 썼다.
- `expire_on_commit=False`라서 바깥 세션에서 읽은 ORM 객체를 그대로 쓸 수 있다.

실제로 세션을 공유하던 루프는 2곳이었다.
- `jobs/dca_cash_shortfall.py`: 알림 단위로 세션을 분리했다.
- `alerts/market_signal_alert_service.check_market_signal_level_change`: 유저 단위로 세션을 분리했다. 이 루프는
  **예외 격리도 없었다.** 한 유저의 예외가 나머지 유저 발송을 전부 중단시켰다.

나머지 잡(goal_achievement, challenge_*, monthly_report, digest, drift, tax_reminder)은 이미 유저별 세션을 쓰고 있었다.

**발견**: `test_market_signal_alert_service`의 등급변경 테스트가 **실제 `AsyncSessionLocal`(로컬 .env의 DB)에 연결하고
있었다.** 이번 변경으로 드러났다. FK 위반으로 롤백돼 데이터는 남지 않았고, mock으로 교체했다.
다른 테스트에도 패치되지 않은 `AsyncSessionLocal` 경로가 있을 수 있으니 이관 #N3-b에 기록한다.

**A3. N1: 해외 포지션 조회를 요청당 1회로** (`78bf979`)

- `get_tax_summary`와 `get_overseas_realized_summary`에 `overseas_positions` 선택 인자를 추가했다.
- `tax_action_service`와 `/tax/summary` 라우트가 포지션을 한 번 읽어 두 함수에 넘긴다. 호출 횟수가 3→1회, 2→1회로 줄었다.

**A4. N2: `should_fire_today`와 `is_auto_schedule_day` 규칙 단일화** (`aded6dc`)

- 두 함수를 `_is_schedule_day(roll=...)` 하나로 합쳤다.
  - NOTIFY는 `_same_day`를 쓴다: 지정일을 그대로 둔다.
  - AUTO는 `_roll_to_weekday`를 쓴다: 주말 지정일을 월요일로 이월한다.
- 동작은 바뀌지 않았다. 2년치 날짜로 두 가지를 검증했다.
  - 이전 NOTIFY 규칙과 결과가 같은지
  - "평일 NOTIFY일이면 AUTO일이고, AUTO에만 해당하는 날은 월요일뿐"인지

**A5. #7: yahoo private 함수 직접 호출 제거** (`2cea473`)

- `yahoo_price.fetch_usdkrw`, `fetch_yahoo_price`, `fetch_yahoo_batch`를 추가했다.
  - 서킷이 열려 있으면 조회를 생략한다.
  - 세마포어를 거치고, 성공·실패를 서킷에 기록한다.
- `api/v1/stocks.py` 4곳과 `utils/currency.py`를 이 함수들로 교체했다.
- `price_service`는 이미 서킷과 세마포어를 직접 쓰고 있다. 테스트 patch 경로가 `price_service._sync_*`라서 이번에는 두었다.

**A6. #8: 네이버 재시도 설정 통합** (`2ea3e79`)

- 새 파일 `app/utils/naver_retry.py`에 `NAVER_RETRY`와 `NAVER_MOBILE_UA`를 둔다. `_NAVER_RETRY` 2벌과 UA 3벌을 여기로 합쳤다.
- 재시도 대상을 `Exception` 전체에서 연결 오류, 타임아웃, 429, 5xx로 좁혔다. 404가 나면 1회로 끝난다.

**A7. #11: 토스 보유종목 시장 판정을 통화 기준으로** (`d616bf5`)

- `balance.py`의 `marketCountry`를 `currency == "KRW"` 판정으로 바꿨다. provider의 해외 보강 기준과 통일한 것이다.

### 배치 B: 프론트

**B1. N4: 해외 양도세 플래너가 백엔드 공제·세율을 사용** (`5b6d308`)

- `useTaxSimulation(positions, autoRealized, rule)`로 바꿨다.
  - `TaxOptimizationCard`가 `/tax/summary`의 `overseas_gain_deduction_krw`와 `rates.overseas_tax_rate_pct`를 넘긴다.
  - 상수는 폴백으로만 남는다.
- `dcaCashShortfallKrw`는 계정 데이터만으로 계산하는 화면 경고라 대체할 응답 필드가 없다. 백엔드 대응
  함수(`is_cash_short`)를 주석으로 명시하는 데 그쳤다.

**B2. #9: api 모듈 우회 정리** (`ed6f1df`)

- `api/settings`에 추가: `updateGoalSettings`, `saveDartApiKey`, `deleteDartApiKey`, `updateNotificationEmail`, `sendTestEmail`
- `api/assets`에 추가: `fetchAccountPositions`, `replaceAccountPositions`, `syncAccountPositionPrices`
- 호출부 8파일을 교체했다.
- 깨진 테스트 2개는 도메인 모듈 mock(`vi.mock("@/api/assets")` 등)으로 전환했다.

**B3. N7: UX 2건** (`f59ba19`)

- `InvestPlanPage`: `?from=recommendation`을 진입 시 state로 읽고, URL에서는 replace로 지운다.
- `RebalancingPage`: 시장신호 조회가 실패하면 물가 지표를 단독 카드로 표시한다.

## 이관 (이번 세션 미착수)

**36/39번에서 유지**

1. `assets.py` 브로커 스펙테이블화 + 프론트 `*CredentialFields` 3벌 단일화(36 #1)
2. `_fetch_and_store_token` 3벌 공용화(36 #2) — `_token_cache.get_or_fetch_token`에 발급·저장 단계를 추가하는 방향이다.
3. `market_signal_service.py`(835줄) 분해(36 #3)
4. goal_* `_compute_*` 분해(스냅샷 하네스 선행), `create_rebalancing_execution_plan`, `_check_user_goals`(36 #4)
5. in-memory 캐시 LRU 축출(36 #6). 모니터링 노트로 둔다.
6. 대형 컴포넌트와 메이저 버전 업그레이드(36 #10)
   - 컴포넌트: `RecommendationCard` 806줄, `StockAccountModal` 616줄
   - 메이저: React 19, recharts 3, tailwind 4
7. 해외 미확인(`overseas_known=False`) 동기화 시 스냅샷 금액이 국내분만 반영되는 문제(36 #11)
8. 키움 NASDAQ 폴백 캐시, 2-leg 부분실행 가시성, 경쟁기능 격차(36 #12)

**이번 라운드 부분 처리분의 잔여**

- **#7-b**: `price_service`가 `_sync_yahoo_*`를 직접 import해 서킷과 세마포어를 인라인으로 반복한다.
  `fetch_yahoo_*`로 바꾸면 `test_price_service.py`의 patch 경로(`price_service._sync_*`) 4곳을 옮겨야 한다.
- **#9-b**: 아직 `@/api/client`를 직접 쓰는 곳이 남아 있다: `authStore`(인증 인프라라 의도적일 수 있음),
  `useDividendData`, `PortfolioPage`. 테스트 mock 형태도 파일마다 다르다(`api`만 / `apiGet` 헬퍼 포함).
  공용 mock 모듈을 도입할지 검토한다.
- **N3-a**: `durable_state.set_durable`과 `dispatch_dual_channel_alert`의 내부 commit을 호출부 책임으로 옮기면
  savepoint 패턴을 쓸 수 있다. 다음 두 곳도 같은 해법으로 풀린다.
  - `overseas_realized_service`의 타임아웃 격리(39 A3)
  - challenge 잡의 유저 내부 챌린지 루프: 한 유저의 챌린지끼리는 세션을 공유한다.
- **N3-b**: 테스트가 패치되지 않은 `AsyncSessionLocal`로 실제 DB에 연결하는 경로를 전수 점검한다.
  conftest에서 `AsyncSessionLocal` 사용 시 실패하게 만드는 가드를 검토한다.

**보류(제품 판단)**

- **N6**: DCA 잡이 사용자 단위 `monthly_deposit_amount`를 알림마다 비교한다. DCA 알림이 여러 개인 사용자에게는 의미가 모호하다.

## 검증

```bash
cd backend && .venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80 -q   # 2391 passed, 90.23%
cd backend && .venv/Scripts/python.exe -m ruff check app tests && .venv/Scripts/python.exe -m mypy app
cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src --max-warnings=0
cd frontend && ./node_modules/.bin/vitest run && npx prettier --check src && npm run build   # 1595 passed
```

- 백엔드: 2363 → 2391 tests, 커버리지 90.18% → 90.23%
- 프론트: 1591 → 1595 tests
- ruff, ruff format, mypy, tsc, eslint, prettier, build 모두 클린이다.
- 실계좌·실브라우저 검증은 하지 않았다.

배포 뒤 확인할 것:
1. 절세 액션 플랜과 세금 요약 값이 이전과 같은지(A3)
2. AUTO 주문 path의 로그에 `kis_transient_error_retry`가 더 이상 나오지 않는지(A1)
3. 토스 계좌 동기화 뒤 국내·해외 분류가 이전과 같은지(A7)
