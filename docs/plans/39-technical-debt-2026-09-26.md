# 39. 기술부채 감사 (2026-09-26)

`docs/plans/36`(09-25) 이후 하루 동안 추가된 코드(계획 37 수정분, 절세 액션 플랜 E2, nestlio 외부 API,
E6/E7, 약 3.5k줄)를 대상으로 재감사했다. Explore 3개를 병렬로 돌렸다(36번 이관 재검증 / 백엔드 신규 코드 /
프론트 신규 코드). **P1 후보는 전부 직접 코드를 읽어 재확인**했다.

브랜치 `fix/tech-debt-2026-09-26`, 커밋 5개: `a772770`, `08aab09`, `5693326`, `6c24c53`, `20ce5bb`.

## 이관 항목 재검증 결과

- 36번 이관 13건은 **전부 유효**하다. 해소된 항목은 없다.
- `RecommendationCard.tsx`(781→806줄)와 `StockAccountModal.tsx`(609→616줄)는 오히려 커졌다.
- 신규 코드에서 새로 들어간 규칙 위반은 0건이다: `date.today()`, 묵음 예외, 토스 누락, gather 세션 공유.
- 신규 `kis/realized.py`는 `client.auth_headers`/`split_account_no`를 재사용하고 있다.

## 같은 세션에 구현 완료

### 배치 A: 실버그

**A1. 연금 추천에서 일반주가 ETF로 오판됨** (`a772770`)

`goal_candidate_service._looks_like_korean_etf`가 브랜드를 `name.startswith(prefix)`로만 비교했다. 그래서
"BNK금융지주"(138930, 일반주)가 브랜드 "BNK"에 걸려 ETF로 판정됐고, `pension_ineligibility_reason`이
연금저축·IRP 계좌에서 매수를 허용했다. 후보에는 사용자 보유 종목이 들어가므로 실제로 발생할 수 있었다.

- 수정: 브랜드 뒤에 공백이 오거나 이름이 거기서 끝날 때만 매칭한다.
- 판별이 모호하면 제외 쪽으로 기우는 기존 보수 원칙과 일치한다. 공백 없이 붙여 쓴 ETF명은 이제 제외되지만,
  이 경우에도 종목코드 기반 `is_korean_etf`가 폴백으로 남아 있다.

**A2. 계좌 CRUD 후 해외 양도세 캐시가 stale함** (`a772770`)

`tax:overseas:*`와 `tax:overseas_realized:*` 캐시는 sync 경로(`invalidate_account_caches`)에서만 지워졌다.
그래서 계좌 삭제, tax_type의 ISA 변경, API 키 등록 뒤에도 최대 1시간 동안 옛 세금 추정이 보였다.

- 수정: `invalidate_tax_overseas_caches` 헬퍼를 만들고 `invalidate_asset_account_caches`에서도 호출한다.

**A4~A6. 프론트** (`08aab09`)

- `invalidateTransactionData`에 `isaStatus`를 추가했다. 백엔드 `isa_service`는 입금·배당 거래를 합산하는데,
  거래를 바꾼 뒤 절세 액션 플랜만 갱신되고 ISA 카드는 옛 값이어서 두 카드의 숫자가 어긋났다.
- `invalidateAccountData`에 `pensionContributionBase`를 추가했다(연금 계좌 CRUD 반영).
- 알림 이력의 `YEAR_END_TAX_REMINDER`가 raw 코드로 표시되던 것에 라벨을 붙였다. 백엔드의 `alert_type=` 전수를
  grep해 보니 누락은 이것뿐이었다.

**계획 단계 정정: 수정하지 않은 2건**

- **A3** `overseas_realized_service`의 조회 실패(타임아웃) 뒤 `db.rollback()` 추가 — 하지 않았다.
  - rollback은 세션의 모든 ORM 객체를 expire시킨다. 이 루프는 이후 `acc.name` 등에 접근하므로 async에서
    MissingGreenlet 위험을 새로 만든다.
  - 반면 원래 걱정한 "commit 도중 취소"의 창은 KIS 토큰 HTTP 호출 뒤 수 ms에 불과하다.
- **A7** `dca_cash_shortfall` 알림별 except의 rollback — 역시 하지 않았다.
  - 잡 전반(`app/jobs`, `services/alerts`)에 rollback 패턴이 전혀 없어 신규 코드의 버그가 아니라 공통 설계
    이슈다.
  - 올바른 해법은 알림 단위 savepoint(`begin_nested`)다. 이관 #N3으로 넘긴다.

### 배치 B: 저위험 정리

**백엔드** (`5693326`)

- `constants.py`에 다음 3개를 추가했다:
  - `PENSION_TAX_TYPES`
  - `TAX_DEFERRED_TAX_TYPES`
  - `COMPREHENSIVE_TAX_THRESHOLD_KRW`

  서비스 3곳의 로컬 사본과, `tax_service`의 private 이름(`_TAX_DEFERRED_TYPES`)을 import하던 3곳을 여기로
  통일했다: `overseas_realized_service`, `order_builder`, `diagnosis_service`.
- `asset_aggregator`와 `portfolio_history_service`의 raw SQL에 하드코딩된 `('STOCK_KIS', …)` 리터럴을
  `POSITION_STOCK_ASSET_TYPES` expanding bind로 바꿨다. "브로커를 추가할 때는 constants.py만 고친다"는 규칙을
  복원한 것이다. 이에 맞춰 SQL 불변식 테스트도 바인드 파라미터를 검사하도록 갱신했다.
- `tax_service.pick_year_rule`: 연도별 세법 테이블 룩업을 `_get_rates`와 `tax_action_service._get_rules`가
  공유한다.
- 절세 액션 문구의 "연 2,000만원(총 1억원)"과 "2,000만원"을 `isa_service` 한도 상수와 종합과세 기준 상수에서
  파생하게 했다(`_fmt_limit`).
- `dca_cash_shortfall._DCA_AUTO_BUY_PRESET`: 잡 쿼리 조건과 `is_dca_auto_buy`가 이 한 곳을 공유한다. 전에는
  이 함수가 테스트에서만 쓰였고 쿼리가 조건을 따로 반복했다.
- `calculator`의 `datetime.now(_KST).date()`를 `today_kst()`로 바꿨다.
- `external.py`의 불필요한 `getattr`을 제거했다. 테스트의 가짜 스냅샷에 필드가 없어서 들어가 있던 것이다.

**프론트** (`6c24c53`)

- `TaxActionPlanCard`: 데이터가 없을 때 `null`을 반환하던 것을 바꿨다. 로딩 중에는 헤더와 스켈레톤을, 실패 시에는
  안내와 "다시 시도" 버튼을 보여준다.
- `TransactionHistoryTab`
  - 유형 필터 칩을 `TX_TYPES`/`TX_LABELS`에서 파생시켰다.
  - 연간 이자 합계를 추가했다(E7 INTEREST가 합계에서 빠져 있었다).
  - 칩에 `TOUCH_TARGET_COMPACT_MOBILE_ONLY`를 적용했다.
- `utils/format`에 `parseYmd`/`daysUntilYmd`를 추가하고, 인라인 `split("-")` 파싱 2곳을 통일했다.
- `InvestPlanPage`의 모바일 "더보기" 버튼을 44px로 맞췄다.
- 사전 존재하던 Prettier 불일치 4파일을 정리했다(36 #13 종결).

**검토 후 유지로 판단**

- `TaxActionCategory`: `TaxAction` 타입이 사용하므로 미사용이 아니다.
- `TaxOptimizationCard`의 `interest_tax_krw ?? 0`: persistQueryClient 오프라인 캐시에 E7 이전 응답이 남아
  있을 수 있어 NaN을 막는 가드로 유효하다.
- accounts 쿼리 `staleTime` 불일치: 전부 invalidate로 갱신되고 값 차이는 UX에 영향이 없다.
- `_get_income_bracket`: 컬럼 1개만 조회하므로 전체 row를 읽는 `get_settings_row`보다 가볍다.
- `pension_contribution_service` 노트의 "이 화면에서는 세액공제율을 계산하지 않음": 해당 카드에 대해서는 여전히
  사실이다.
- 인라인 "지금 설정하기" 텍스트 버튼: 문장 안의 링크라 WCAG 예외에 해당한다.

### 배치 C: 이관 1건 착수 (`20ce5bb`)

**실주문 함수 요청 형태 고정** (36 #5 종결). 새 테스트 파일 `tests/test_broker_order_requests.py`는 25개
케이스로 다음을 pytest-httpx로 고정한다:

- 대상 함수: KIS/키움의 `place_domestic_order`/`place_overseas_order`
- 고정 항목:
  - TR id / api-id(매수·매도 × 실·모의)
  - 계좌번호 분리(KIS)와 원본 전달(키움)
  - 주문구분 코드(국내 1자리 / 해외 2자리)
  - 가격 포맷(원화 정수, 달러 소수 둘째 자리)
  - 거래소 코드 폴백
- 네트워크 오류 시 **요청이 1회만 나가는지**(중복 체결 방지)도 확인한다.

KIS `AsyncRateLimiter`는 케이스마다 약 1초를 기다리게 만들어 테스트 안에서 무력화했다.

- **발견(미수정)**: `kis_request`는 rt_cd `"1"`(MCI 전송 오류)을 1초 뒤 한 번 재시도하고, 이는 주문 경로에도
  적용된다. 실패 응답이라 접수되지 않은 주문일 가능성이 높지만, KIS 문서로 "미접수 보장"을 확인하지는 못했다.
  이관 #N5로 넘긴다.

## 이관 (이번 세션 미착수)

**36번에서 유지**

1. `assets.py` 브로커 스펙테이블화, 프론트 `*CredentialFields` 3벌(36 #1)
2. `_fetch_and_store_token` 3벌 공용화(36 #2)
3. `market_signal_service.py`(835줄) 분해(36 #3)
4. goal_* 분해(36 #4)
5. LRU 축출(36 #6)
6. yahoo private 호출(36 #7)
7. 네이버 재시도 2벌(36 #8)
8. 프론트 api 우회 9곳(36 #9)
9. 대형 컴포넌트(36 #10)
10. 해외 미확인 스냅샷(36 #11)
11. 토스 market 판별(36 #12)

**신규**

- **N1.** `tax_action_service.get_tax_action_plan` 한 번에 `get_overseas_positions_detail`(비캐시, 스냅샷+포지션
  로드)이 3번 호출된다. `/tax/summary`에서도 2번이다. 요청 스코프 메모화나 인자 전달로 줄일 수 있다.
- **N2.** `calculator.is_auto_schedule_day`가 `should_fire_today`의 월간 타깃·최소 간격 로직을 복제한다(주말
  이월만 추가). 두 로직이 어긋날 위험이 있다.
- **N3.** 잡 루프들이 공유 세션 하나를 쓰면서 항목별 except에 rollback/savepoint가 없다. 한 항목의 DB 오류가
  이후 항목을 전부 실패시킬 수 있다. `begin_nested` 패턴을 검토한다. `overseas_realized_service`의 타임아웃
  격리(A3)도 같은 해법으로 해결된다.
- **N4.** 프론트가 백엔드 계산을 복제하는 곳이 2군데다:
  - `useTaxSimulation`(250만 공제, 22%)
  - `dcaAutoBuy.dcaCashShortfallKrw`

  이미 응답에 오는 `overseas_tax_free_room_krw` 등으로 대체할 수 있다.
- **N5.** KIS rt_cd `"1"` 재시도가 주문 경로에도 적용되는 문제. 주문 경로에서는 재시도를 끌지 KIS 문서로
  확인이 필요하다.
- **N6.** DCA 잡이 사용자 단위 `monthly_deposit_amount`를 알림마다 비교한다. DCA 알림이 여러 개인 사용자에게는
  의미가 모호하다(제품 판단 필요).
- **N7.** UX 판단이 필요한 2건:
  - `InvestPlanPage`의 `?from=recommendation` 파라미터가 새로고침·뒤로가기 뒤에도 남는다.
  - 인플레이션 지표가 시장신호 조회 실패 시 함께 숨는다(구 `InflationSummaryCard`는 독립적이었다).

## 검증

```bash
cd backend && .venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80 -q   # 2363 passed, 90.18%
cd backend && .venv/Scripts/python.exe -m ruff check app tests && .venv/Scripts/python.exe -m mypy app
cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src --max-warnings=0
cd frontend && ./node_modules/.bin/vitest run && npx prettier --check src && npm run build   # 1591 passed
```

- 백엔드: 2331 → 2363 tests. 신규 파일은 주문 테스트 25건이다.
- 프론트: 1587 → 1591 tests.
- ruff, mypy, tsc, eslint, prettier, build 모두 클린이다.
- 실브라우저·실계좌 검증은 하지 않았다.
- raw SQL 바인드 변경(`asset_aggregator`/`portfolio_history_service`)은 mock DB 테스트라 SQL 컴파일
  수준까지만 확인했다. 배포 뒤 대시보드 누적수익률과 자산추이 국내/해외 분할이 이전과 같은지 확인할 것.
