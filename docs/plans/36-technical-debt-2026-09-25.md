# 36. 기술부채 감사 (2026-09-25)

`docs/plans/34`(09-15)·`35`(09-24) 이후 재감사. Explore 3개 병렬(이관 항목 코드대조 / 백엔드 신규 스캔 /
프론트 신규 스캔) 후 **P1 후보는 전부 직접 코드를 읽어 재확인**했다. 이번 라운드는 "기술부채"보다
**실버그 3건**(KIS 해외잔고 묵음 실패, UTC 날짜, 키움 계좌번호 미검증)이 핵심이었다.

브랜치 `fix/tech-debt-2026-09-25`, 커밋 5개(`c217394` `3cf8726` `097332d` `0ad1408` `4c35e92`).

## 이관 항목 재검증 결과

- **종결**: `useRebalancingExecution` 커버리지(구 31 #9 / 32 #7 / 34 #7) — 이미
  `hooks/rebalancingExecution/`(index/reducer/types)로 분리되고 `hooks.rebalancing.test.ts`에 직접 테스트 존재.
- **종결**: `cache_keys.py` 비대화(34 #9) — 키 빌더·TTL 상수 전수 grep 결과 미사용 0건. 규모는 크지만 죽은 코드 아님.
- **유지**: 나머지(아래 "이관" 절).

## 같은 세션에 구현 완료

### 배치 A — 실버그

**A1. KIS 해외잔고 실패가 "해외 없음"으로 확정·캐싱** (`c217394`)
- `kis/balance.get_overseas_balance`가 거래소(NYSE/NASD/AMEX)별 예외를 `except Exception: continue`로 무로그
  삼킴 → 전 거래소 실패여도 정상 dict 반환 → 바깥 `_overseas_cache._safe_overseas`가 실패를 못 봐 `ok=False`
  미부착 → ① `has_overseas=0`이 TTL 동안 캐싱 ② `deposit_usd=0`이 확정값으로 반영 ③ 토큰 만료 예외까지 삼켜
  `with_token_refresh` 재시도 우회. 09-12 stale-USD 보호장치(`deposit_foreign=None`)를 KIS에서만 무력화하고
  있었다(키움은 원래 예외 전파).
- 수정: `KisTokenExpiredError`는 re-raise, 나머지는 거래소별 warning 후 **하나라도 실패하면 루프 뒤 raise**
  (부분 결과를 확정값처럼 쓰면 실패 거래소 종목이 삭제되므로).
- 부작용 메모: 해외주식 미신청 계좌가 KIS에서 에러 응답을 준다면 매 동기화마다 `ok=False`(미확인)로 처리되어
  "해외 없음" 캐싱 이득을 잃는다(기존 값 보존이라 데이터는 안전). 실계좌 로그에서 `kis_overseas_exchange_fetch_failed`
  빈도를 확인할 것.

**A2. 해외 조회 실패 시 기존 해외 포지션 삭제 + 전량 매도 시 stale 포지션** (`c217394`)
- `asset_service.sync_account`는 provider 결과로 현재 Position 전체를 delete→insert — 해외 조회가 실패(국내-only
  결과)하면 해외 포지션이 사라졌다. `BalanceResult.overseas_known` 추가, False면 KRW 포지션만 교체.
  (`DOMESTIC_MARKETS`에 KONEX가 없어 시장명 대신 `currency == "KRW"` 기준 사용)
- `if balance.positions:` 게이트 때문에 브로커 결과가 빈 리스트(전량 매도)면 포지션이 안 지워지던 문제 —
  브로커 소스는 빈 결과도 교체(MANUAL은 DB 포지션을 읽어 반환하므로 제외).
- sync 실패 시 `last_sync_error` 기록 전 `rollback()`.
- **남은 한계**: 해외 미확인일 때 스냅샷 `amount_krw`/스냅샷 포지션은 여전히 국내분만 반영 → 추이 차트에 일시
  하락이 찍힐 수 있다. 이관 #11.

**A3. 운영 서버 UTC인데 `date.today()` 51곳** (`3cf8726`)
- Dockerfile/render.yaml 모두 TZ 미설정. KST 00~09시 동기화 스냅샷이 전날 날짜로 저장되고, "월별 대표값=해당 월
  마지막 sync일" 규칙상 월초 새벽 동기화가 전월 값을 덮었다. 알림 dedup·월간 리포트 기준월도 하루 어긋남.
- `app/utils/kst.py`(KST/now_kst/today_kst) 신설, 32개 파일 치환. 흩어진 `_KST` 상수 9곳(ZoneInfo·고정오프셋
  혼재) 통일, 리밸런싱 이메일의 `fromtimestamp(ts + 9h)`(서버 로컬TZ 이중 적용) → `astimezone(KST)`,
  `dart_service`의 deprecated `utcnow()` 정리.
- **예외**: `economic_indicator_service`(FRED)는 미국 날짜보다 미래인 `realtime_start`를 400으로 거부하므로
  `date.today()` 유지(주석 명시).
- 기존에 저장된 스냅샷 날짜는 소급 수정하지 않음.

**A4~A6. 프론트** (`097332d`)
- 키움 신규 등록에 `kiwoomValid` 게이트 — 키 검증만 통과하면 빈 계좌번호로 제출돼 백엔드 400으로만 드러났다.
  키움 계좌번호는 백엔드도 형식 검증 없이 주문 API에 그대로 넘기므로 **존재 여부만** 확인(KIS regex 강제는
  유효한 키움 형식을 막을 위험이 있어 계획에서 변경).
- 연동 해제(`CredentialDisconnectButton`) 후 리밸런싱 알림/대기 플랜 캐시도 무효화(`invalidateBrokerCredentialData`),
  이메일 링크 승인/취소 페이지(`RebalancingPlanConfirmPage`)도 플랜·이력 무효화. 하드코딩 쿼리키 2개 → `QUERY_KEYS`.
- `index.html`의 존재하지 않는 호스트(`growlio-api.onrender.com`) preconnect 제거(네이티브는 `VITE_API_DOMAIN` 사용).

### 배치 B — 저위험 정리

**백엔드** (`0ad1408`)
- `report_job_failure`(jobs/_job_helpers.py): 잡 실패를 `sentry_sdk.capture_exception`. **계획 단계 정정**:
  처음엔 `exc_info=True`로 Sentry 스택을 확보하려 했으나, structlog가 stdlib logging을 거치지 않아(PrintLogger)
  Sentry LoggingIntegration이 애초에 못 잡고, `_redact_processor`는 문자열 필드만 마스킹해 traceback은 redact를
  우회한다 → 로그엔 계속 `str(e)`만, Sentry는 명시 capture. `token_refresh`는 자격증명이 스택 지역변수라 제외.
- 스케줄러 `EVENT_JOB_ERROR|EVENT_JOB_MISSED` 리스너, 15분 주기 잡 id `rebalancing_plan_sell_expiry_daily` →
  `rebalancing_plan_sell_expiry`(메모리 jobstore라 id 변경 안전).
- 키움 토큰 발급 거부: 문자열 매칭(`"토큰 발급 실패" in msg`) → `KiwoomTokenIssueError`(RuntimeError 하위, 기존
  `except RuntimeError` 호환). `MaxRetriesExceededError`(RuntimeError 하위)가 502로 나가던 것 → KIS/토스와 같은 429.
- KIS sync에만 없던 `asyncio.wait_for(SYNC_TIMEOUT_SECONDS)` 추가.
- verify 3개 라우트 공통 HTTP 오류 매핑 `_verify_http_error` 헬퍼(응답 코드/메시지 불변).
- KIS/키움 잔고·주문 `_auth_headers`·계좌번호 분리 중복 → 각 `client.py`의 `auth_headers`/`split_account_no`.
  (시세 조회 모듈의 GET 헤더는 Content-Type이 없어 의도적으로 제외)
- 토큰 캐시 키 하드코딩 3곳 → 브로커 상수. ISA/연금 TypedDict를 실제 반환 타입으로(라우트는 FastAPI
  response model화 방지 위해 `dict(...)` 반환 유지). 미사용 예외 7개·`AlertDirection` 삭제.
- pyproject: `requests` 직접 의존 명시, `uvicorn`/`pydantic-settings`/`defusedxml`/`pytest-asyncio`/`pytest-httpx`
  상한, dev 중복 `httpx` 제거. uv.lock 재생성(버전 변동 없음, uv 0.11 마커 표기 변경분 포함).
- **하지 않음**: `token_refresh` 잡이 만료 전 토큰을 그대로 반환하는 no-op — 만료 시 `with_token_refresh`가
  사후 갱신하므로 강제 갱신의 이득이 추가 DB 조회 비용보다 작다고 판단.

**프론트** (`4c35e92`)
- 차트 팔레트 사본 6곳 → `PIE_COLORS`(8색 사본은 8번째 색만 달랐음 — 공용 팔레트로 통일).
- `≈ ₩{convertUsdToKrw(...).toLocaleString()}` 5곳 → `formatUsdAsKrw`. 정밀 원화 표시(`BankAccountCard`/
  `PriceCell`/`HeroSummaryCard`)는 `fmtKrw`가 만원/억원으로 축약해 UX가 바뀌므로 유지.
- 스캐너가 "사유 없음"으로 보고한 `exhaustive-deps` 억제 7곳 중 6곳은 이미 직전 줄에 사유 주석이 있었음 —
  `NotificationSettingsPage` 1곳만 사유 추가(`useCollapsible` setter가 비안정 참조라 dep 추가 시 접기 불가).
- `X-Frame-Options` SAMEORIGIN → DENY(vercel/nginx, `frame-ancestors 'none'`·백엔드와 일치), nginx CSP
  `connect-src`에 Sentry 도메인 동기화, `@capacitor/cli` → devDependencies, `@typescript-eslint/parser` 범위 정렬.
- **유지 판단**: `openapi-typescript`는 `frontend/CLAUDE.md`에 문서화된 수동 타입 생성 워크플로라 미사용 아님.

## 이관 (이번 세션 미착수)

1. **`assets.py` 브로커 스펙테이블화** (구 30 #3 → 35 #2, 우선순위 상향 유지) — 이번에 verify 에러 매핑만
   헬퍼화. 남은 create/update/delete/`_account_response`/`_CREDENTIAL_FIELDS`의 브로커별 반복 약 150줄.
   차이점(스펙 필드): data_source, 키/시크릿 필드명, 계좌번호 필수 여부(KIS 아님/키움·토스 필수), 강제
   asset_type(키움·토스), 라벨, verify 함수 시그니처(KIS만 user_id·cache), 추가 에러(키움 TokenIssue/토스
   TossApiError 403), 생성 후처리(KIS만 `promote_user_token_to_account`), delete 서비스 함수.
   프론트도 `Kis/Kiwoom/TossCredentialFields` 3벌이 이미 드리프트(`""` vs `undefined`, 라벨 색상) →
   `BrokerCredentialFields` + `BROKER_CONFIG` 단일화.
2. 브로커 `_fetch_and_store_token` 3벌(캐시 setex→암호화→upsert→commit) → `providers/_token_cache.py` 공용화,
   KIS/키움 해외 합산 후처리(`kis_provider`/`kiwoom_provider`) 공용화.
3. `market_signal_service.py`(835줄) 분해 — 경계: fetchers(52~575) / composite(순수) / state(704~779) / service.
4. goal_* `_compute_*` 5개 분해(스냅샷 하네스 선행) + `create_rebalancing_execution_plan`(161줄, 라우터→서비스)
   + `goal_achievement._check_user_goals` 3중 블록.
5. **실주문 함수 테스트 부재** — `kis/order.py`·`kiwoom/order.py`는 전부 mock으로만 호출됨. TR id·계좌번호
   분리·요청 바디를 pytest-httpx로 고정하는 테스트 필요(실거래 경로라 우선순위 높음).
6. in-memory 캐시 LRU(`core/cache_store.py`, 상한 20k)가 만료 안 된 lock/토큰 키를 축출할 수 있음 — 현실적
   위험 낮음, 모니터링 노트.
7. `api/v1/stocks.py`·`utils/currency.py`가 `yahoo_price._sync_*` private 함수를 직접 호출해 세마포어·서킷 우회.
8. 네이버 스크래핑 재시도 데코레이터 2벌 중복 + 모든 예외 재시도(404도 3회).
9. 프론트 `api/*` 모듈 우회 직접 호출(`useGoalSettings`/`useDividendPlanSettings`/`SettingsPage`/
   `NotificationEmailSection`/`StockPositionsModal`) — 테스트 mock 형태가 파일마다 달라 이번엔 보류.
10. 프론트 대형 컴포넌트(`RecommendationCard` 781줄 탭별 분리, `StockAccountModal` 609줄), React 19/recharts 3/
    tailwind 4 메이저. `StockAccountModal` 수동 입력·ISA·예수금 흐름 테스트.
11. **(신규)** 해외 미확인(`overseas_known=False`) 동기화의 스냅샷 금액·스냅샷 포지션이 국내분만 반영되는 문제 —
    직전 스냅샷의 해외분을 이월하거나 스냅샷 upsert를 건너뛰는 방안 검토.
12. 기존 유지: 토스 market 판별 불일치(`balance.py` marketCountry vs `toss_provider.py` currency), 키움 NASDAQ
    폴백 캐시, 2-leg 부분실행 가시성, 경쟁기능 격차(정기 자동매수·ETF TER).
13. 사전 존재 Prettier 불일치 4파일(`api/marketSignals.ts`, `api/rebalancingPlan.ts`, `hooks/useDividendData.ts`,
    `stores/pushNotificationStore.ts`) — pre-commit은 변경 파일만 검사해 누적됨.

## 검증

```bash
cd backend && .venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80 -q   # 2202 passed, 89.30%
cd backend && .venv/Scripts/python.exe -m ruff check app tests && .venv/Scripts/python.exe -m mypy app
cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src --max-warnings=0
cd frontend && ./node_modules/.bin/vitest run && npm run build                       # 1560 passed
```

백엔드 2187→2202 tests(커버리지 89.00→89.30%), 프론트 1554→1560 tests, ruff/mypy/tsc/eslint/build 클린.
`uv pip install -e ".[dev]"` 재설치로 새 상한 충돌 없음 확인. 실브라우저·실계좌 검증은 하지 않음 — A1/A2는 배포 후
KIS 해외 보유 계좌에서 동기화 로그(`kis_overseas_exchange_fetch_failed`)와 포지션 보존을 확인할 것.
