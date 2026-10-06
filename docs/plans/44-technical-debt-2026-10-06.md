# 44. 기술부채 감사 (2026-10-06)

직전 감사(계획 42/43, 09-28) 이후 들어온 변경은 다음 네 가지다.

- ETF 중복·TER 기능(`41e4a9e`)
- KOSDAQ Yahoo 심볼 수정(`06c34fa`)
- 자산추이에 증권예수금 포함(`d6d5625`)
- Sentry 10→11 Dependabot 범프(`b301278`)

이 변경분을 중심으로 백엔드·프론트를 Explore 2개로 재조사했다. 버그로 보고된 항목은 코드로 직접 재확인했다.
고전적 부채(`any`, TODO, `except: pass`, 700줄 초과 파일)는 여전히 0건이다. 새 부채는 대부분 ETF 중복 기능에 몰려 있었다.

사용자는 **배치 A(실버그)와 배치 B(저위험 정리)**를 선택했다. 배치 C는 이관했다. 브랜치는 `fix/tech-debt-2026-10-06`이다.

## 구현 완료

### 배치 A — 실버그 (`aa28234`)

**A1. 월배당·분기배당 쌍이 "같은 지수 중복"으로 오탐됨**
- 원인: `distribution_frequency`는 큐레이션 유니버스 항목에만 있다. 저장된 후보(`GoalCandidateTicker`), 요청 바디
  (`OverlapCandidateIn`), 보유 종목에는 이 필드가 없다. 그래서 446720(월배당)과 458730(분기배당)이 `SAME_INDEX`로 묶였다.
- 같은 결함이 이전부터 `goal_candidate_service.detect_duplicate_tracking_index_note`에도 있었다.
- 수정: `recommendation_universe.resolve_distribution_frequency(ticker, market, explicit)`를 추가했다.
  `_UNIVERSE_TRACKING_INDEX_BY_KEY`와 같은 방식으로 조회한다. 두 곳 모두 후보와 보유 양쪽에 적용했다.
- 테스트 2건을 추가했다. 수정 전 코드에서는 실패하고 수정 후 통과하는 것을 확인했다.

**A2. 부분 시세 결과가 24시간 캐싱됨**
- 원인: Yahoo 서킷이 열리면 `fetch_yf_close_series`는 국내 심볼만 pykrx로 채운 부분 dict를 돌려준다.
  "비어 있지 않음"만 검사하고 있어서 해외 상관 판정이 빠진 결과가 하루 동안 캐싱됐다.
- 수정: `_fetch_weekly_returns`가 `(frame, 전부 받았는지)`를 반환하고, 일부라도 빠지면 캐싱하지 않는다.
- `price_data_available`의 의미는 바꾸지 않았다. 프론트가 이 값을 읽지 않는다.

**A3. 동기화 후 목표 추천·후보 중복 패널이 최대 1시간 stale**
- 원인: 프론트 `invalidateSyncData`와 `invalidateAccountData`가 `goal-recommendation` prefix를 무효화하지 않았다.
  백엔드는 이미 `invalidate_account_caches`에서 goal 캐시를 지우고 있었다.
- overlap 캐시는 입력 해시가 키라서 보유 변경 시 자동으로 새 키가 된다.

**A4. Sentry v11이 로컬에 설치되지 않은 상태**
- lockfile은 11.0.0이었지만 `node_modules`는 10.75.0이었다.
- `npm ci` 후 tsc, vitest, build가 모두 통과했다. 코드 변경은 필요 없었다(`init`, `browserTracingIntegration`, `captureException`만 사용).

### 배치 B — 백엔드 정리 (`96dedd3`)

- `MAX_GOAL_CANDIDATE_TICKERS`를 `app.constants`로, `GoalCandidateTicker`를 `schemas/rebalancing/goal.py`로 옮겼다.
  schema가 service를 import하던 것을 없애기 위해서다.
  - `OverlapCandidateIn`은 `GoalCandidateTicker`를 상속한다. `asset_class`가 `AssetClass` enum이 됐고 길이 제약만 추가로 걸었다.
  - 제약을 상위 모델에 걸지 않은 이유: 레거시 저장 행 응답이 깨질 수 있다.
- 후보 중복 점검의 라우터 로직(편집 목록 / 저장 목록 / 보유 종목 선택)을 `etf_overlap_service.analyze_candidate_overlap_for_user`로 옮겼다.
  API 테스트의 patch 경로도 서비스 모듈로 이동했다.
- `yahoo_price.run_yf_bounded(func, *args)`를 추가했다. 공유 세마포어 + executor만 담당하고, 서킷은 다루지 않는다
  (스스로 서킷을 기록하는 `fetch_yf_*`용).
  - private `_yfinance_sem`과 수동 `run_in_executor`를 쓰던 5곳을 치환했다.
  - `_fetch_naver_etf_analysis`를 공개 이름으로 바꿨다.
  - 테스트 쪽: `price_service._yfinance_sem`을 patch하던 죽은 코드 3곳을 제거했다. 스냅샷 테스트의 세마포어 교체 fixture는 소유 모듈 하나로 정리했다.
- `etf_profile_service`
  - 캐시 키에 `_ETF_PROFILE_VERSION`을 붙였다.
  - Yahoo가 `quoteType`으로 "ETF 아님"을 명시한 종목은 7일 캐싱한다(이전에는 1일).
  - 전체 조회에 20초 상한을 걸었다. 초과하면 그때까지 받은 프로필만 쓰고 나머지는 캐싱하지 않는다.
  - `type: ignore` 1곳을 제거했다.
  - 계획 단계의 "개별주 `.info` 조회가 yahoo 서킷을 오염시킨다" 가정은 틀렸다. 개별주는 `quoteType=EQUITY`인 비어 있지 않은 응답을
    돌려주므로 서킷에 실패로 기록되지 않는다. 그래서 장기 캐싱만 했다.
- 자산추이 SQL의 `('KOSPI','KOSDAQ','KRX')` 하드코딩을 `DOMESTIC_MARKETS` expanding bind로 바꿨다.
  FRED 관련 `date.today()` 2곳에는 의도를 설명하는 주석을 달았다.
- `refresh_kosdaq_tickers`: 빈 결과면 warning을 남긴다. 집합이 비어 있는 상태(기동 직후 첫 로드 실패)에서만 5분 뒤 1회 재시도한다.
- `test_circuit_breaker`
  - 0.01초 `reset_timeout` + sleep 조합을 `FakeClock`으로 바꿨다(계획 42 관찰 플레이크 제거).
  - 모듈의 `time` 이름만 교체한다. 전역 `time.monotonic`을 바꾸면 asyncio 루프 시계까지 멈추기 때문이다.

### 배치 B — 프론트 정리 (`5b7fabd`)

- `GoalCandidateManagerModal`
  - 제거 버튼을 44px(`TOUCH_TARGET_MIN_MOBILE_ONLY`)로, 자산군 select를 `min-h-9`로 키웠다.
  - `AlertTriangle`을 `TriangleAlert`로 바꿨다.
  - `profileByKey` 이중 조회를 1회로 줄였다.
- `OverlapGroupsBlock`: `fmtKrwPrice`를 쓴다.
- `RecommendationWeightList`: `has` + `get as number` 대신 한 번만 조회한다.
- `GoalSettingWizard`의 "이 추천으로 포트폴리오 만들기"도 `normalizeWeights`를 거친다(계획 42/43 관찰 항목 종결).
- 테스트를 추가했다: `OverlapGroupsBlock` 렌더 4건, `useCandidateOverlap` enabled 게이팅 4건, `RecommendationWeightList` terMap 1건.
- **조치 불필요로 확인**: 사유 없는 `eslint-disable` 6곳이라는 보고는 오보였다. 6곳 모두 바로 윗줄에 사유 주석이 있다.

## 이관

**배치 C (중위험 구조 정리 — 이번 세션 제외)**

1. `create_rebalancing_execution_plan`(`api/v1/rebalancing_execution.py`, 약 160줄)을 `quick_execute_plan()` 서비스 + 결과 enum으로 옮긴다.
   라우터에는 enum→메시지 매핑만 남긴다. 기존 API 테스트의 patch 경로를 먼저 확인해야 한다.
2. `jobs/goal_achievement._check_user_goals`의 ASSET/DEPOSIT/DIVIDEND 3중 블록을 테이블 기반 `_notify_goal`로 합친다.
3. `RecommendationAgeTab`/`OverallTab`의 미설정 CTA와 빈 상태 블록을 공통화한다.
   요약문 조각은 `formatRecSummaryParts()`로 뽑는다. `RecommendationHorizonTab`의 `stockAccounts` prop 독스트링 불일치도 함께 고친다.

**기존 이관 유지**

- 메이저 업그레이드: React 19, recharts 3, tailwind 4
- 2-leg 실패 leg 자동 재시도(실거래 설계 필요), 정기 자동매수(로드맵)
- N6(DCA 알림 여러 개일 때 `monthly_deposit_amount` 비교 의미) — 제품 판단 보류

**신규 관찰 (제품 판단 또는 저우선)**

- 자산추이 `CASH_STOCK` 잔차: 포지션이 없는 수동 증권계좌의 평가액까지 "예수금(증권계좌)"로 표시된다.
  docstring상 의도된 흡수지만 라벨 정확도 문제가 있다. 계좌별 차액 계산(composition_calculator 방식)으로 바꿀지는 판단이 필요하다.
- `GoalSettingWizard`(563줄) 분해, `useBrokerCredentialVerify` 핸들 memo화, 후보 관리 모달에서 편집할 때마다 overlap 재요청(디바운스 검토)
- `HIGH_CORR`는 배당주기 예외를 두지 않는다. 446720/458730은 같은 지수라 시세가 있으면 "움직임 유사"로 묶일 수 있다.
  기존 설계(같은 지수 판정에만 예외)대로 뒀다.
- Sentry: react-router 7에서 `reactRouterV7BrowserTracingIntegration`을 쓰면 트랜잭션이 라우트 단위로 묶인다(지금은 raw URL).
- dev 전이 의존성 `virtualenv` 21.7.8에 PYSEC-2026-4014가 있다(21.7.12에서 수정). pre-commit 경유라 런타임과 무관하다.

## 검증

```bash
cd backend && .venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80 -q   # 2499 passed, 90.69%
cd backend && .venv/Scripts/python.exe -m ruff check app tests && .venv/Scripts/python.exe -m ruff format --check app tests && .venv/Scripts/python.exe -m mypy app
cd frontend && npm ci && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src --max-warnings=0
cd frontend && ./node_modules/.bin/vitest run && npx prettier --check src && npm run build   # 1631 passed
```

- 실계좌와 실브라우저 검증은 하지 않았다.
- 배포 뒤 `etf_profile_fetch_deadline`과 `kosdaq_tickers_refresh_empty` 로그 빈도를 확인할 것.
