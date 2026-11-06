# 115. 남은 기술부채 — 동기화·알림·인증·푸시 감사 (2026-11-06c)

> **진행 상태**: 완료. 브랜치 `chore/tech-debt-2026-11-06c`.

요청은 "남은 기술부채 확인해서 수정 계획"이다. 114(PR #242)는 머지된 상태다. 이번 계획은 세 갈래로 점검했다.
- ① 114 변경의 회귀
- ② 그동안 덜 감사된 백엔드 영역(동기화·알림·인증·푸시·잡)
- ③ 프론트·인프라

사용자 결정:
- 알림 메일 주소 인증은 하지 않고 **발송 한도만** 둔다.
- Render 자동 배포는 **`checksPass`**로 바꾼다.

## 배치 0 — 확인·정리

- 공유 Supabase의 `alembic current`는 `gd1_goal_start_date_to_date`(head)다. 114의 fk1·gd1은 적용된 상태다. 114 회귀 점검에서 코드 회귀는 없었다.
  - 미적용이었다면 투자계획 분석이 500으로 실패한다(`relativedelta`에서 aware datetime과 date를 섞음).
  - 목표 폼이 시작일을 빈칸으로 받아, 다음 저장 때 오늘 날짜로 덮어썼을 것이다.
- 머지된 worktree `growlio-td113`·`growlio-td114`는 제거했다. 병합된 로컬 브랜치 삭제는 계속 사용자가 실행한다.

## 배치 A — 백엔드

| # | 문제 | 수정 |
|---|---|---|
| A1 | `sync_accounts`(sync-all, 15:30/18:00 잡)가 계좌 락 `sync_lock_key`를 안 잡았다. 그래서 단건 `/sync`와 병렬로 돌 수 있었다. 이때 현재 포지션 delete→insert가 READ COMMITTED에서 둘 다 살아남아 보유 종목과 총자산이 두 배가 될 수 있다 | `sync_one`이 같은 락(ttl 120)을 잡는다. 이미 잡혀 있으면 실패가 아닌 skip으로 처리한다 |
| A3 | 환율·주가 알림은 메일이 실패하면 푸시도 안 보냈다. Resend 미설정이거나 주소가 잘못되면 어느 채널로도 안 나가고 5~10분마다 재시도했다 | `notify_and_record_trigger(email_sent=...)`가 푸시를 따로 시도하고, 한 채널이라도 성공하면 발동을 기록한다. 메일 예외는 Sentry로 보고하고 삼킨다 |
| A8 | 주가 알림 폼은 "목표가 (원)"인데, 해외 종목은 USD 원시가와 비교했다. 그래서 BELOW가 즉시 거짓 발동했다(예: SCHD 28 < 38,000). `rows[0]` 유저의 KIS로 전원 시세를 조회했고, 티커 키가 시장 간에 충돌했다 | `fetch_prices_batch_krw(kis_accounts={})`를 시장별로 호출한다. `fetch_prices_batch_krw`에 `kis_accounts` 전달 인자를 추가했다 |
| A4 | FCM v1(firebase-admin 7.7)은 폐기 토큰을 `UnregisteredError("Requested entity was not found.")`로 던진다. 문자열로 판정해서 토큰이 정리되지 않았다 | 예외 클래스 이름(`UnregisteredError`·`SenderIdMismatchError`)으로 판정한다. 테스트가 firebase 모듈을 Mock으로 바꾸므로 isinstance 대신 이름을 쓴다. `InvalidArgumentError`는 페이로드 오류와 구분이 안 돼 제외한다 |
| A5 | `verify_supabase_token`의 `PyJWKClient`가 300초마다 동기 urllib로 JWKS를 받았다. 이때 이벤트 루프가 최대 5초 멈췄다 | `deps._verify_token`이 `asyncio.to_thread`로 감싼다 |
| A6 | `/test-email`은 분당 한도만 있었다(하루 약 4천 통). 4xx도 재시도해 Resend 호출과 Sentry 이벤트가 두 배였다. 월간 리포트는 메일이 미설정이어도 유저마다 대시보드를 집계했다(catch-up으로 1~3일 매시간) | `3/minute;10/hour;20/day`로 바꿨다. 재시도는 연결·타임아웃·5xx·429만 한다(`_is_retryable_email_error`). 공개 `email_configured()`를 만들고, 미설정이면 월간 리포트가 루프 전에 끝난다 |
| A7 | 06:00 토큰 갱신이 `force_refresh` 없이 호출해 남은 토큰을 그대로 받았다. 전날 15:30 발급분이 장중에 만료됐다 | 만료까지 18h 미만(또는 행 없음)일 때만 `force_refresh=True`로 부른다 |
| A9 | `get_kis_user_credentials`가 복호화를 try 밖에서 해 키 회전 시 500이 났다. sync-profile 이중 호출이 PK 충돌로 500이 났다. 월간 리포트 로그에 이메일이 평문으로 남았다 | 복호화를 try 안으로 옮겨 None을 돌려준다. `IntegrityError`가 나면 rollback 후 먼저 생긴 행을 돌려준다. `mask_email`을 쓴다. 환율·주가 알림 쿼리에 `User.is_active`를 추가했다 |
| A10 | `test_settings_api` 목표 저장 테스트가 `in (200, 422)`라 실패해도 통과했다 | 200 단언과 저장 타입(`date`) 단언으로 바꿨다. 외부 API에 date 직렬화(`"2024-01-01"`) 테스트를 추가했다 |

**확인 결과 문제없음 (감사 오진)**
- `sync_account` 실패 처리의 rollback 후 `account.data_source` 접근이 `MissingGreenlet`을 낸다는 지적: sqlite로 재현해 보니 commit 중 flush가 만료 속성을 SELECT로 먼저 다시 로드한다(greenlet 안). 그래서 commit 뒤 접근은 IO가 없다. 바꾸지 않았다.
- `/test-email`의 `RuntimeError` 분기가 죽은 코드라는 지적: 메일이 미설정이면 `send_test_email`이 실제로 던진다. 유지했다.
- `rebalancing/alert_check.py:340`의 이메일 로그 노출 지적: 로그가 아니라 함수 인자다.
- 18:00 동기화의 `User.is_active` 필터: 코드 어디서도 사용자를 비활성화하지 않는다. 동기화 쪽에는 넣지 않았다.

## 배치 B — 프론트

- **B1 PWA precache.**
  - 문제: `globPatterns`에 js·css가 없었다. 배포 후 SW가 내준 옛 index.html이 사라진 해시 청크를 가리켜, React가 뜨기 전에 404가 났다(부팅 멈춤).
  - 수정: js·css를 추가했다(빌드 기준 precache 157개, 2.2MB). `vite:preloadError`가 나면 1분에 1회만 새로고침한다(`setupPreloadErrorReload`, sessionStorage에 기록이 안 되면 새로고침하지 않음).
- **B2** 비밀번호 재설정 `redirectTo`를 `VITE_REDIRECT_URL`로 바꿨다. Capacitor origin이 `https://localhost`이기 때문이다.
- **B3** `build-android.yml` 변수 검사에 `VITE_REDIRECT_URL`을 추가했다. 웹 빌드 assert는 넣지 않았다(Vercel 환경변수를 확인할 수 없어 배포를 막을 위험이 있음).
- **B4** 푸시 setup: `setup().catch` → `error` 상태, `registrationError` 리스너 추가. 예전에는 throw하면 `requesting`에 멈췄다.
- **B5** 접근성:
  - 주문 행 체크박스에 `aria-label`(종목명)을 달았다.
  - 시장 select 2곳에 `aria-label`과 `focus-visible:ring`을 달았다.
- **B6** 정리:
  - v4에서 제거된 `placeholder-gray-*` 2곳을 `placeholder:text-*`로 바꿨다. 이전에는 CSS가 생성되지 않았다.
  - `fmtMd`/`fmtMonthDay` 중복을 `utils/format.fmtMonthDay`로 합쳤다.
  - bare `rounded`는 v4에서도 같은 값(0.25rem)이라 두었다.

## 배치 C — 인프라

- **C1** `render.yaml`: `autoDeployTrigger: checksPass`. Blueprint 동기화 상태여야 반영되므로 대시보드에서 확인한다. 마이그레이션은 여전히 머지 전에 수동으로 적용한다.
- **C2** `ci.yml` `android` 잡을 추가했다.
  - `frontend/android/`·`package*.json`·`capacitor.config.*`가 바뀐 경우만 웹 빌드 → `cap sync` → `assembleDebug`를 실행한다.
  - 스텝 단위 조건이라, 변경이 없으면 녹색으로 생략된다.
- **C3** `frontend/package.json`에 `engines.node: 24.x`를 넣었다(Vercel Node 고정). lock 루트에도 반영했다.
- **C4** `Makefile` `clean`의 리터럴 `\n`을 줄 이음으로 고쳤다.

## 검증

- 백엔드:
  - ruff·ruff format·mypy 0건.
  - pytest 3702 통과, 커버리지 93.20%(게이트 91).
- 프론트:
  - eslint `--max-warnings 0`·prettier·tsc(앱·테스트) 0건.
  - vitest 188파일·2027 통과(coverage).
  - `npm run build` 후 `dist/sw.js` precache에 js·css 143개가 들어간 것과 `placeholder\:text-gray-400` CSS 생성을 확인했다.
- **확인 못 한 것**:
  - CI android 잡 실제 실행(이 PR은 `package*.json`을 바꾸므로 PR CI에서 처음 돈다)
  - Render `checksPass` 반영
  - 실기기 푸시·재설정 메일 링크
  - 배포 후 PWA 갱신 동작

## 작업 시 함정

- worktree에서 `uv run`이 main venv를 잡을 수 있다. 그럴 때는 `.venv/Scripts/python -m pytest`에 CI 환경변수(`KIS_CRED_ENCRYPTION_KEY`·`DATABASE_URL`·`APP_ENV=development`)를 넣어 직접 돌린다. `uv sync --extra dev`는 coverage trampoline 권한 오류가 나도 pytest까지는 설치된다.
- 월간 리포트 발송 테스트는 `email_configured`를 patch해야 한다(파일 단위 autouse fixture).

## 계속 보류

- 포지션 부분 unique 인덱스(`account_id, ticker, market WHERE snapshot_id IS NULL`): 기존 중복 데이터를 먼저 점검해야 한다. A1 락으로 신규 발생은 막았다.
- keep-alive 제거(외부 핑 등록 후), 600줄대 파일 분할, 미사용 export 타입 약 40개, `clearAnalysisCache`(테스트 전용).
- `vite.config` `advancedChunks` deprecated 경고(→ `codeSplitting`).
- Sentry EU 호스트 CSP: DSN이 EU일 때만 필요하다.
- 알림 메일 주소 인증: 사용자 결정으로 한도만 둔다.
