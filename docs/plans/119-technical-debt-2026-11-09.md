# 119. 남은 기술부채 — 백테스트 캐시·해외 주가 알림 단위·매수 예산 실패·/health 한도·실 DB 테스트 침묵 skip (2026-11-09)

> **진행 상태**: A~D 구현 완료(D4만 보류). 브랜치 `chore/tech-debt-2026-11-09`. 마이그레이션 없음.

요청은 "남은 기술부채 확인 후 수정 계획"이다. 115~118(PR #243~#246)은 머지됐고 main CI는 녹색이며 열린 PR이 없었다. 감사는 세 갈래로 했다.
1. 백엔드: 118 회귀, 113~118에서 다루지 않은 모듈
2. 프론트: 118 C 회귀, 미감사 화면
3. 인프라: CI·keep-alive·의존성·문서

고위험 부채는 없었다. 아래는 실버그와 그 주변 리스크다.

깨끗했던 영역(재조사 금지):
- 118 변경분: XIRR `original_openings`, 세금 연도 범위, 페이지 검증, DART 키 해시·삭제 시 캐시 정리
- 패턴: naive `date.today()`·`datetime.now()`, `except Exception: pass`, TODO, 금액 float 비교, `as any`, `!` 단언, `toISOString().slice`, 직접 `invalidateQueries`
- 전술 라우터·서비스·국면 잡, 공개 플랜 라우터, 백테스트 소유권, 계좌 삭제, 실거래 주문 흐름(409·4xx 멱등)
- CLAUDE.md 파일 목록(백·프), `uv.lock` 최신, 모든 백엔드 의존성 상한

사용자 결정 3건:
- 옛 해외 주가 알림: 데이터는 고치지 않는다. 판정에서 빼고 재입력을 안내한다.
- 생체인증 플러그인: `overrides` 임시조치만 한다(@capgo 교체는 실기기 검증이 필요해 별도).
- keep-alive: 외부 핑을 아직 등록하지 않아 유지한다. 실패 로깅만 보강한다.

## 배치 A — 백엔드 실버그

- **A1 백테스트 결과 24시간 stale**
  - 원인: 키 `backtest:{user}:{요청 해시}`(TTL 24h)를 지우는 곳이 없었다. 포트폴리오 비중 수정·전술 적용·동기화 뒤 같은 조건으로 다시 돌리면 옛 결과가 나왔다.
  - 수정: `invalidate_backtest_cache`를 추가했다. 포트폴리오 단위·전체 리밸런싱 분석 무효화에서 함께 부른다. 계좌 무효화는 전체 무효화를 거치므로 동기화도 덮인다.
  - 요청 해시에 포트폴리오가 드러나지 않아 유저 단위로 지운다.
- **A2 sync-prices의 `manual_amount` 예수금 누락**: 118 B5가 놓친 곳이다. 저장 경로와 `_manual_total_krw` 헬퍼를 공유한다.
- **A3 118 C6 이전 해외 주가 알림**
  - 원인: 예전 화면은 "목표가 (원)"으로 받아 SCHD $27이 27원으로 저장됐다. 이하 알림은 영영 안 울리고, 이상 알림은 즉시 거짓 발동한다.
  - 판정 기준 `is_suspect_usd_unit`: 해외 시장이면서 목표가가 1,000원 미만이다.
  - 계획은 "현재가의 1% 미만"이었지만 바꿨다. 목록 API가 시세를 조회하게 되고(yfinance 지연), 판정 잡과 목록이 같은 규칙을 써야 해서다. 한계: $0.7 미만 페니주는 오탐이고, 1,000원 이상으로 잘못 저장된 값(예: BRK.A)은 못 잡는다.
  - 판정 잡은 해당 알림을 건너뛰고, 응답에 계산 필드 `needs_reentry`를 추가했다.

## 배치 B — 백엔드 리스크·정리

- **B1** `/health`에 `@limiter.exempt`를 붙였다. Render healthCheckPath라 기본 한도(120/min)에 걸리면 unhealthy로 보인다. keep-alive 429는 앱이 낸 것인지 확인하지 못했다(D2 참고).
- **B2 ETF 빈 응답 연속 카운트**
  - 원인: 첫 빈 응답만 걸러서, 한 번 센 정상 ETF가 Yahoo 장애 중 요청 두 번으로 "데이터 없음"(1일)에 닿았다.
  - 수정: 조회 전에 서킷이 열려 있으면 세지 않는다. 정상 응답이 오면 연속 횟수를 리셋한다.
  - 처음엔 "배치 전체 빈 응답이면 안 센다"로 고치려 했지만 버렸다. 다른 심볼이 캐시되면 상장폐지 심볼이 영영 확정되지 않는다(118 B2 테스트가 잡음).
- **B3 수동 완료 챌린지에 "달성 🎉"**
  - 완료 경로를 구분할 컬럼이 없다. 결산 잡이 완료로 바꿀 때 durable 키 `challenge_wrap_completed:{id}:{월}`을 남긴다.
  - 키 없이 COMPLETED인 챌린지는 결산을 건너뛴다. app_state 테이블이라 스키마 변경은 없다.
- **B4 FULL 전략 매수 예산 조회 실패**
  - 원인: 예산을 모른 채 원래 수량으로 발주했다(KIS·키움·토스 공용 `execute_buys_with_cash_check`).
  - 수정: TWO_PHASE처럼 예산 0으로 보고 매수를 SKIPPED로 남기고, Sentry(`report_handled_failure`)로 보낸다.
  - 매도 clamp 실패는 동작을 유지한다(초과 매도는 브로커가 거부할 뿐이다). Sentry 보고만 추가했다.
- **B5 목표 포트폴리오 일괄 지정**: 중복 ID가 있으면 403이 났다. 이제 중복을 제거하고, 삭제 계좌는 대상에서 뺀다(`list_accounts_by_ids`의 `is_active`).
- **B6 정리**
  - 팩터·프론티어·전략 캐시의 계좌 suffix를 `account_ids_suffix`로 통일했다. 구분자 `_`는 유지해 기존 키가 그대로다.
  - `get_factor_analysis_for_portfolio`(`user_id` 키워드 필수)와 프론티어 비교 포트폴리오 조회에 소유자 필터를 넣었다(116 보류분).

## 배치 C — 프론트

- **C1** `clearWidget()`을 `authStore.logout()`으로 옮겼다. 세션 만료(App.tsx) 경로도 위젯을 비운다. 푸시 토큰 대기 뒤에 실행해, 그 사이 갱신이 덮어쓰지 못한다.
- **C2** 목표가를 입력한 단위(ref)와 새로 고른 종목의 단위가 다르면 숫자를 지운다. 검색 중에는 `selectedStock`이 null이라 현재 `inUsd`와 비교하면 달러→원 전환을 놓친다.
- **C3** `needs_reentry` 알림에 재입력 안내를 붙였다. 목록·삭제 확인의 가격은 `fmtKrwPrice`로 표시한다.
- **C4** 푸시 끄기 요청 중에는 상태를 `requesting`("확인 중...", 버튼 비활성)으로 둔다. 실패하면 이전 상태로 되돌린다.
- **C5** `utils/platform.ts`에 `randomId()`를 추가했다. `crypto.randomUUID`가 없는 구형 WebView에서는 `getRandomValues`로 v4를 만든다. 주문 멱등 키·포지션 행 키에 쓴다.
- **C6** 백테스트 결과를 실행 조건 키에 묶었다(조건이 바뀌면 숨김). 빈 날짜면 실행할 수 없다.
- **C7** 목표 조정 탭의 청크 선로딩 실패를 삼킨다. 미처리 rejection이 Sentry로 가지 않는다.
- **C8 생체인증 core 중복**
  - `overrides`로 `capacitor-native-biometric`의 `@capacitor/core`를 루트(8.6)에 맞췄다.
  - lock의 중첩 3.9 항목을 지웠고, `npm ls`에서 단일 버전이다.
  - `npm run build`와 로컬 `assembleDebug`가 성공했다. jcenter·AGP 3.6 문제는 그대로이며, Gradle 9 전에 플러그인을 교체해야 한다.

## 배치 D — 인프라·테스트·문서

- **D1** 실 DB 테스트 fixture가 `CI` 환경인데 `GROWLIO_TEST_DATABASE_URL`이 없으면 skip이 아니라 fail한다.
- **D2** keep-alive curl을 `--fail-with-body --include`로 바꿔, 다음 429의 헤더·본문이 로그에 남는다. 2026-11-08 1회(최근 40회 중 1회) 실패는 원인을 확정하지 못했다.
- **D3** frontend `npm audit`를 테스트 앞으로 옮겼다(backend와 같게).
- **D4 보류**: Dependabot `pre-commit` 생태계. 지원 여부를 확인하지 못했다. 잘못된 값은 dependabot.yml 전체를 깨므로 넣지 않았다.
- **D5** `usePullToRefresh`·`useRegisterRefresh` 테스트를 추가하고 coverage exclude에서 뺐다.
- **D6** README 110·111 행과 111 헤더를 고쳤다. FK 인덱스는 114 `fk1`에서 완료됐다.

## 보류·이관

- @capgo 생체인증 교체(실기기). 접근성 label 약 38개와 하드코딩 라벨 클래스(별도 접근성 계획).
- 600줄대 백엔드 4개(`goal_portfolio_optimizer` 678, `rebalancing/service` 649, `_goal_recommendation_common` 614, `tax_action_service` 609)와 500줄대 프론트 3개.
- `periodic_catchup`·월간 잡 claim 원자화, `period_purchase` 하한, Sentry EU CSP(DSN 확인 후), 해외 알림 `target_price_usd` 저장(환율 변동 추적, 스키마 변경).
- `GoalCandidateManagerModal`의 후보 수 검사 경합: 서버가 막는다. 프론트 금액 포맷 잔여분(`PriceCell`·`BankAccountCard`·`MonthlyDividendChart` 등).
- Dependabot `pre-commit`(D4).

## 검증

- 백엔드:
  - ruff·format·mypy 0건
  - pytest 3740 통과, 커버리지 93%
  - `/health` 한도 테스트는 exempt를 빼면 실패하는 것을 확인했다.
- 프론트:
  - eslint·prettier·tsc(앱·테스트) 0건
  - vitest 194파일·2040 통과(coverage 임계값 통과)
  - `npm run build` 성공
  - C2 테스트는 수정을 빼면 실패하는 것을 확인했다.
- Android: `cap sync` 뒤 로컬 `assembleDebug` 성공.
- **확인 못 한 것**:
  - CI에서 실 DB 테스트가 실제로 도는지(PR CI에서 확인)
  - 실기기: 세션 만료 후 위젯 "—", 구형 WebView `randomId`, 생체인증 동작(core dedupe 후)
  - 수동: 옛 해외 알림 재입력 안내, 백테스트 재실행 반영
