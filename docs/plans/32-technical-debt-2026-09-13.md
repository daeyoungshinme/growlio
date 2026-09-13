# 32. 기술부채 감사 (2026-09-13)

`docs/plans/31`(2026-09-09) 이후 HEAD 전진분은 tech-debt 커밋 3개(`1b55921`/`f76df87`/`5fafb10`)
+ 신규 기능/수정 커밋 6개(적립식 챌린지 `4957613`, 키움/KIS 예수금 D+2 전환 `7f18163`, DB 커넥션
풀 고갈 수정 `36c14ca`, 모바일 부팅 성능 `8d9d79d`/`aca907d`, LRU 캐시 상한 `5c774d4`, mypy
platform 고정 `9251277`, 계좌 동기화 상태 추적 `3b0bf1a`). Explore 2개(백/프) 병렬 조사 +
plan 31 이관 항목 11건 재검증.

## 같은 세션에 구현 완료

### 배치 A — 백엔드 저위험
- **챌린지 진행률 캐시 무효화 누락**(신규 발견, 실질 버그) — `transactions.py`의
  `_invalidate_tx_caches`와 `external.py`(nestlio 연동 입출금 기록)가 `dashboard_summary_key`/
  `monthly_trend_key`는 무효화하지만 `challenge_progress_key`는 빠뜨려, 입금 기록 직후 챌린지
  진행률/스트릭 카드가 최대 5분(`TTL_CHALLENGE_PROGRESS`) 지연 갱신되던 버그. 두 호출부에
  `challenge_progress_key(user_id)` 추가.
- **동기화 실패 메시지 truncate 로직 중복** — `asset_service.py`/`sync_all_service.py`가 서로
  다른 커밋(`3b0bf1a`/`36c14ca`)에서 각각 `redact_secrets(str(e))[:200]`을 독립 구현. `core/logging.py`에
  `format_sync_error(error: BaseException | str) -> str` 공용 헬퍼 추가(예외 객체와, 이미
  `str(e)`로 저장된 값 양쪽을 받도록 설계) 후 양쪽에서 재사용.
- **"전체 갱신" 진행 중 폴링 응답의 `failed`가 항상 0** — `sync_all_service.py`의 `on_progress`
  콜백이 매번 `"failed": 0`을 하드코딩. `jobs/asset_sync.py`의 `ProgressCallback` 타입을
  `Callable[[int, int, int], Awaitable[None]]`(done, total, failed_count)로 확장하고
  `sync_one`에서 `len(failed)`를 실어 보내도록 수정 — 실패 리스트는 append가 progress_lock
  획득보다 먼저 일어나 콜백 호출 시점에 이미 최신 상태(asyncio 단일스레드라 안전). 유일한
  소비처(`sync_all_service.py`)만 있어 파급 범위 작음.
- **순입금 SQL 패턴 중복 — 조사 후 정리 보류**: `challenge_service.py`/`asset_aggregator.py`가
  `CASE WHEN transaction_type='DEPOSIT' THEN amount ELSE -amount END`를 각자 raw SQL로 구현하고
  있으나, `asset_aggregator.py`의 두 CTE는 컬럼 한정자가 다르게 섞여 있어(`transaction_type` vs
  `t.transaction_type`) 한 줄짜리 CASE 식을 공용 문자열 상수로 뽑아 f-string 주입하면 오히려
  가독성이 떨어지는 과도한 추상화. `returns_calculator.py`의 유사 패턴(XIRR 현금흐름 부호)은
  애초에 부호 관례 자체가 반대(DEPOSIT이 음수 현금흐름)라 같은 개념이 아님 — 셋 다 그대로 둠.
- **문서 드리프트 보강**(`backend/CLAUDE.md`) — LRU 캐시 상한(`_MAX_ENTRIES=20,000`), mypy
  `platform=linux` 고정 이유, `sync_all_service.py`의 "브로커 HTTP 호출 구간만 짧게 스코프된
  `AsyncSessionLocal()`로 재진입" 패턴(DB 커넥션 풀 고갈 방지 아키텍처 관례) 반영.

### 배치 B — 프론트엔드 저위험
- **`clampPct` 유틸 추출** — `Math.min(Math.max(x, 0), 100)`이 `ChallengeCard.tsx`/
  `ChallengeProgressCard.tsx`/`HealthInsuranceRiskCard.tsx`/`InvestmentGoalCard.tsx`/
  `PensionContributionCard.tsx` 5곳에 동일하게 존재(신규 챌린지 기능이 기존 4곳의 중복 패턴을
  답습해 5곳으로 확대). `utils/format.ts`에 `clampPct(pct)` 추가, 5곳 치환 + 단위 테스트.
- **`ChallengeMonthGrid` 접근성** — 월별 달성 상태가 색상+`aria-hidden` 기호로만 전달되어
  스크린리더가 달성 여부를 알 수 없었음. 각 셀에 `role="img"` + `aria-label="9월, 완료, 50만원"`
  형태로 상태 포함 라벨 추가(기존 `title` 툴팁은 유지).
- **`useRebalancingPrices.ts` 가격 폴백 계좌 필터** (plan 31 이관 #1, 재검증 후 수정) —
  `findKisAccountId`가 `STOCK_KIS`만 필터해 KIWOOM 단독 보유 종목의 가격 폴백이 안 먹을 수
  있던 문제. 기존 `isOrderExecutableAccount()`(라운드#2에 만든 헬퍼)로 교체해 실행 경로와
  동일 기준으로 통일, `findExecutableAccountId`로 개명.
- **동기화 실패 사유가 `title` 툴팁 전용(모바일 접근 불가)** — `StockAccountCard.tsx`(3b0bf1a
  추가분)의 "동기화 실패" 배지가 hover 전용이라 터치 환경에서 전체 메시지를 볼 방법이 없었음.
  `<span>`을 `<button>`으로 바꿔 탭하면 `toast(error, "error")`로 전체 메시지 노출, 단위 테스트 추가.

### 배치 C — 기계적 정리
- **lucide-react deprecated alias 스윕 완료** — plan 31 이관 #2("~20개 파일" 추정)를 재확인한
  결과 실제로는 29개 파일(`AlertTriangle`→`TriangleAlert` 20곳, `LineChart`→`ChartLine` 31곳,
  `BarChart2`→`ChartNoAxesColumn`/`BarChart3`→`ChartColumn` 8곳, `MoreVertical`→
  `EllipsisVertical` 2곳, `Edit2`→`Pen` 2곳, `Wand2`→`WandSparkles` 4곳). 전체 sed 일괄 치환 후
  **`recharts`가 별도로 export하는 동명의 `LineChart`(실제 차트 컴포넌트, 아이콘과 무관)까지
  잘못 치환된 것을 발견**해 `DCAProjectionChart.tsx`/`SavingsSimulatorCard.tsx`/
  `BacktestResultChart.tsx`(recharts 소비 컴포넌트) + `test/setup.tsx`/
  `pages.low-coverage.test.tsx`(recharts mock) 5개 파일만 되돌림 — 이름 충돌 라이브러리를
  기계적 스윕할 땐 반드시 import source까지 확인해야 함(이번처럼 `git diff`로 각 rename의
  `from "..."` 라인을 대조).
- **프론트 커버리지 임계값 재측정** — `vite.config.ts` 주석이 2026-07-29 실측 기준으로
  stale. 이번 배치 A/B/C 반영 후 재측정(lines 69.04/functions 55.87/branches 55.08/
  statements 67.78%)해 임계값을 65/51/51/63 → **66/52/52/64**로 상향(~3%p 마진 유지).

## 이관 항목 (이번 세션 미착수)

### 1. 대형 `_compute_*` near-clone 5개 분해 — 구 plan 30 #2 / 31 #1
`goal_portfolio_optimizer._optimize_goal_portfolio`(~212줄) 외 4개(`goal_age_recommendation_service`/
`goal_horizon_recommendation_service` ×2/`goal_recommendation_service`). 이번 범위 커밋에서
전혀 손대지 않아 여전히 유효. **characterization 스냅샷 테스트 하네스 선행 필수** — 실추천
결과 회귀 표면 큼, 멀티 세션.

### 2. `assets.py` 브로커 분기 스펙테이블화 — 구 plan 30 #3 / 31 #2
`create_account`/`update_account`의 KIS/키움/토스 near-identical 분기 3벌. `36c14ca`는
`update_account`의 스냅샷 순서 버그만 수정, 분기 구조 자체는 미변경 — 여전히 유효. 계좌 생성
경로 회귀테스트 필수.

### 3. `market_signal_service.py`(835줄) 분해 — 구 plan 24 #2 / 29 #3 / 30 #5 / 31 #3
이번 범위에서 미변경. AUTO 게이트 신호원이라 hysteresis/raw 양쪽 회귀 리스크, 저긴급.

### 4. 키움 해외 주문 NASDAQ 폴백 7일 캐시 — 구 plan 31 #4
`_overseas_name_enrichment.py`/`TTL_OVERSEAS_STOCK_META`(7일) 이번 범위 미변경, 로직 그대로 —
여전히 유효. 권위 있는 거래소 소스 부재로 완전 수정 불가, 최소안(경고 로그+문서화)만.

### 5. 토스 `market` 판별 필터 불일치 — 구 plan 31 #5
`toss/balance.py`(marketCountry) vs `toss_provider.py`(currency) 라인만 소폭 이동, 불일치
자체는 미해소 — 여전히 유효(현재는 토스 KR+US만 지원해 잠재 상태).

### 6. 2-leg 부분실행 가시성 재확인 — 구 plan 27 이관분 / 31 #7
`7f18163`(키움 clamp 예산을 `deposit_krw`→`orderable_krw`로 정밀화)로 **부분 개선**됐으나
"매도/매수 분리 실행 결과가 API 응답에 명확히 구분되는지"는 이번 조사에서도 심층 확인 못함 —
재확인 필요로 계속 이관.

### 7. `useRebalancingExecution`(525줄) 커버리지 45% — 구 plan 31 #9
이번 범위에서 미변경, 추가 분해보다 커버리지 보강 우선(기존 결론 유지).

### 8. 경쟁앱 대비 기능격차 — 로드맵 전용(변경 없음)
정기 자동매수, ETF TER. 실자금 이동/리서치성 과제라 착수 계획 없음, 기존 결정 유지.

## 검증

```bash
cd backend && uv run pytest -q && uv run ruff check . && uv run mypy app/
cd frontend && npm run test && npm run lint && npx tsc --noEmit && npm run build
```

백엔드 2158 tests, ruff/mypy 클린. 프론트 1508 tests, lint/tsc/build 클린, 커버리지 임계값
66/52/52/64로 상향(실측 69.04/55.87/55.08/67.78%).
