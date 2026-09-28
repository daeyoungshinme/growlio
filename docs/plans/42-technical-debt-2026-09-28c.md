# 42. 계획 41 이관 기술부채 처리 (2026-09-28, 3차)

계획 41의 이관 항목 중 사용자가 고른 **저·중위험 묶음**을 처리했다. 브랜치는 `fix/tech-debt-2026-09-28`로 같다.
처리 범위는 N3-c, A1 후속, 36 #6(캐시 LRU), 36 #12 중 키움 NASDAQ 폴백과 2-leg 부분실행 가시성이다.

같은 시간에 다른 세션이 **36 #1(브로커 자격증명 스펙 테이블화 + 프론트 `BrokerCredentialFields` 단일화)**을
`a3f48bf`로 커밋했다. 이 문서의 범위는 아니지만 아래 이관 목록에서는 뺐다.

## 구현 완료

**1. N3-c: 해외 실현손익 조회의 타임아웃 범위 축소** (`24da113`)

- 원래 문제: `asyncio.wait_for`가 `with_token_refresh` 전체를 감쌌다. 그래서 토큰 발급(`store_token`)이
  공유 세션에서 commit하는 도중에 취소가 떨어질 수 있었다.
- 계획 41은 `get_or_fetch_token` 체인에 commit 인자를 뚫는 방안을 검토 대상으로 적었다. 실제로는 더 작게 풀었다.
  타임아웃을 순수 HTTP 조회(`get_overseas_realized_pnl`)에만 건다.
- 토큰 발급 HTTP는 공용 httpx 클라이언트 타임아웃(30초)으로 이미 상한이 있다. 그래서 취소가 commit에 닿을 경로가 없다.
- 테스트: 토큰 발급이 타임아웃보다 오래 걸려도 성공하고, 조회 HTTP가 느리면 `TimeoutError`가 난다.

**2. A1 후속: 보존 해외 포지션 Yahoo 재평가** (`b21b041`)

- `asset_service._revalue_preserved_overseas`를 추가했다. 해외 미확인 동기화에서 보존된 해외 포지션을
  Yahoo 현재가(USD) × 이번 동기화 환율로 제자리 갱신한다(`current_price`, `value_krw`, `usd_rate`).
- 그 결과 스냅샷 금액과 현재 포지션 둘 다 직전 동기화 값보다 새 값이 된다.
- 다음 경우에는 기존 값을 유지한다(best-effort).
  - Yahoo 예외
  - 서킷 열림(빈 dict)
  - 가격 없는 종목
  - 환율이 `usd_krw_fallback_rate`인 경우. 폴백 환율로 재평가하면 오히려 부정확하다.

**3. 36 #6: in-memory 캐시 LRU 축출 감시** (`99502bf`)

- 상한(2만) 초과 시 **만료 항목을 먼저 치우고**, 그래도 넘칠 때만 살아 있는 LRU 항목을 축출한다.
  전에는 만료 항목이 남아 있어도 살아 있는 락·토큰 키가 밀려날 수 있었다.
- 살아 있는 항목 축출 수는 Prometheus `cache_lru_eviction_total`로 센다.
- 15분 주기 `cache_sweep` 잡은 `take_lru_evictions()`로 직전 이후 축출 수를 읽는다. 0이 아니면
  `cache_lru_evictions` 경고(`evicted`, `entries`)를 남긴다. 경고가 반복되면 `_MAX_ENTRIES` 상향을 검토할 것.
- 락 키를 축출 대상에서 빼는 보호는 하지 않았다. 현실적 위험이 낮아 감시만 한다.

**4. 36 #12: 키움 해외 주문 NASDAQ 폴백** (`38eafbe`)

- 실제 결함: Yahoo가 **이름만 찾고 상장 시장은 못 찾은** 부분 결과(`{"name": X, "market": None}`)가
  7일 TTL로 캐싱됐다. 그래서 1주일 동안 매 동기화에서 NASDAQ 폴백이 적용됐다. 그 기간에 NYSE/AMEX 종목의
  키움 해외 주문은 `stex_tp=ND`로 라우팅됐다. 완전 실패(`None, None`)는 원래 캐싱하지 않았다.
- 수정 내용:
  - 부분 결과는 `TTL_OVERSEAS_STOCK_META_PARTIAL`(1시간)로만 캐싱한다.
  - 폴백을 적용할 때 `overseas_market_fallback` 경고를 남긴다.
  - `kiwoom/order.py`에서 미지 시장이 들어오면 `kiwoom_overseas_order_unknown_market` 경고를 남긴다.
    이 모듈에는 logger가 없어 새로 추가했다.
- 권위 있는 거래소 소스가 없어서 폴백 자체는 남는다. `backend/CLAUDE.md`의 `_overseas_name_enrichment` 항목에 적었다.

**5. 36 #12: 2-leg 부분실행 가시성(계획 27 #2의 최소 범위)** (`36148e6`)

- `GET /rebalancing/plans`는 EXECUTED leg를 빼고 돌려준다. 그래서 "매도 체결 + 매수 실패/만료" 플랜을
  목록만 보고는 알 수 없었다.
- `plan_service.executed_plan_ids(plan_ids, db)`를 추가했다. 쿼리 1회로 형제 leg 체결 여부를 조회한다.
- `RebalancingPlanLegSummary.partially_executed`를 추가했다. 기본값은 False라 공개 preview 경로는 변화가 없다.
  - True 조건: 종료 상태(FAILED, EXPIRED, REJECTED, CANCELED)이면서 같은 플랜에 EXECUTED leg가 있음
  - PENDING은 정상 진행 중(매도 체결 후 매수 대기)이라 제외한다.
- 프론트 이력 탭(`RebalancingHistoryTab` `PendingPlanRow`)에 "일부 실행" 배지와 안내 문구를 넣었다.
  - 문구: "같은 계획의 매도/매수 주문은 이미 체결됐어요… 진단 탭에서 다시 분석해 보세요"
- 실행 로직은 바꾸지 않았다. 실패 leg 자동 재시도(확장 범위)는 하지 않았다.

## 이관

**41번에서 유지**

1. goal `_compute_*` 분해(스냅샷 하네스 선행), `create_rebalancing_execution_plan`, `_check_user_goals`(36 #4)
2. 대형 컴포넌트 `RecommendationCard` 806줄 + 메이저 업그레이드 React 19, recharts 3, tailwind 4(36 #10).
   `StockAccountModal`은 `a3f48bf`에서 일부 줄었으니 재측정할 것.
3. 경쟁기능 격차(정기 자동매수, ETF TER). 로드맵 전용이다.
4. 2-leg 확장 범위: 실패 leg 자동 재시도. 실거래 리스크가 있어 별도 설계가 필요하다.

**보류(제품 판단)**

- **N6**: DCA 알림이 여러 개일 때 사용자 단위 `monthly_deposit_amount` 비교의 의미가 모호하다.

**관찰**

- `test_circuit_breaker::test_probe_failure_reopens_circuit_without_letting_others_retry`가 전체 스위트에서
  1회 실패했다. `reset_timeout=0.01`인데 마지막 `assert not cb.is_available()` 전에 10ms가 지나면 half-open으로
  바뀌는 타이밍 플레이크로 보인다. 이번 변경과 무관하다(해당 파일 미수정). 재현되면 `reset_timeout`을 늘릴 것.

## 검증

```bash
cd backend && .venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80 -q   # 2416 passed(+ 위 플레이크 1), 90.48%
cd backend && .venv/Scripts/python.exe -m ruff check app tests && .venv/Scripts/python.exe -m ruff format --check app tests && .venv/Scripts/python.exe -m mypy app
cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src --max-warnings=0
cd frontend && ./node_modules/.bin/vitest run && npx prettier --check src && npm run build   # 1605 passed
```

- 백엔드 커버리지는 90.48%다(다른 세션의 `a3f48bf` 포함).
- 프론트는 1605 tests다.
- ruff, ruff format, mypy, tsc, eslint, prettier, build 모두 클린이다.
- 실계좌·실브라우저 검증은 하지 않았다.

배포 뒤 확인할 것:
1. `overseas_market_fallback` 로그 빈도. 반복되는 티커는 Yahoo 검색이 거래소를 못 주는 종목이다.
2. `cache_lru_evictions` 경고 발생 여부
3. 해외 조회가 실패한 날의 스냅샷 해외분이 전일과 비슷한 수준으로 유지되는지
4. 이력 탭 "일부 실행" 배지가 실제 반쪽 실행 플랜에만 붙는지
