# 93 — 남은 기술부채 처리 3차 (2026-10-29c)

## 배경

계획 92(PR #181)의 이관 목록을 다시 확인하고, 92 머지 코드와 나머지 영역을 백엔드·프론트·인프라 세 축으로 감사했다. 92의 패키지 이동에서 생긴 회귀는 없었다(옛 평면 경로 0, CLAUDE.md 목록 드리프트 0). 새로 찾은 실버그는 92 0-1과 같은 관측성 계열이다.

브랜치: `chore/tech-debt-2026-10-29c`. 클러스터마다 커밋 1개.

## 결과

| # | 항목 | 결과 |
|---|---|---|
| A | 처리된 실패의 Sentry 누락 | **실버그(관측성).** structlog는 stdlib logging을 거치지 않는다. 그래서 `except` + `logger.error`만 하는 곳은 Sentry에 남지 않았다. 해당 실패: AUTO leg 실행(`_execute_leg`)·매수 tick·stuck sweep·매도 만료, 환율/주가 알림 루프(`run_isolated_alert_loop`), 리밸런싱 알림 이메일·overview·분석, 계좌 동기화(계좌별·전체), `send_push_safely`(호출부 6곳)·이중 채널 이메일, 플랜 알림 이메일 3곳. `core/job_runner.py`에 `report_handled_failure`(redact 로그 + 스택 없는 `capture_message`)를 두고 적용했다. 기존 인라인 capture 2곳도 이 헬퍼로 옮겼다. 시세 조회 폴백처럼 예상된 실패는 노이즈라 적용하지 않았다 |
| B | 프론트 직접 무효화 | `invalidateTacticalData({ dcaLinked })`·`invalidateDcaData({ goalRecommendation })` 옵션으로 옮겼다. 알림 이력 무한 스크롤 키는 `QUERY_KEYS.alertHistoryPages`로 올렸다. 페이지 재시도 버튼 3곳은 유지했다(계획 54) |
| C | 저위험 정리 | `validate_*_amount`에 overload를 달아 `type: ignore` 3개를 없앴다(11→8). `datetime.now(_KST)` 직접 호출 4곳을 `today_kst()`로 바꿨다. 죽은 `send_push`를 지웠고 테스트는 `PushResult`로 정확히 단언한다. `goal_start_date`의 UTC 자정 저장 계약은 주석으로 남겼다. 백테스트 차트의 이중 `!`를 지웠다 |
| D | 테스트 `noUncheckedIndexedAccess` | **완료(92 이관).** `tsconfig.test.json`에서 off를 지웠다. 145건은 TS 컴파일러 API로 오류 지점에만 `!`를 넣고, 피연산자가 nullable이 아닌 불필요한 단언 2건은 다시 걷어냈다. 스프레드·구조분해 10건은 수동으로 처리했다 |

검증: 백엔드 3132 tests, ruff/format/mypy 클린. 프론트 1885 tests, tsc(앱·테스트)/eslint/prettier/build 클린. 서버 기동 스모크는 하지 않았다. 로컬 `.env`가 공유 Supabase를 가리켜 스케줄러가 실제 알림을 보낼 수 있다.

## 계획과 달라진 점

- **D `firstCall()` 헬퍼 미도입.** 오류 지점만 기계적으로 고쳤다(`!`). 헬퍼를 넣으려면 145곳의 호출 모양을 바꿔야 해서 이득이 없다.
- **A 계좌별 동기화 실패도 capture.** 브로커 점검시간처럼 예상된 실패가 매일 쌓일 수 있다. 다만 같은 이벤트·타입은 Sentry에서 한 이슈로 묶이므로 유지했다. 운영에서 노이즈가 크면 `account_sync_failed`만 되돌린다.

## 이관

- **firebase-admin 7.x `Message.token` deprecated**(새로 발견): 권장 대체는 `fid`(Firebase 설치 ID)다. 앱이 보내는 FCM 등록 토큰과 다른 값이라 그대로 바꿀 수 없다. 클라이언트가 FID를 보내도록 바뀐 뒤(APK 재배포)에 처리한다. 테스트 경고 1건으로 남아 있다.
- **머지된 브랜치 정리**: 로컬 7개, 원격 9개(28c·28d 포함). 사용자 확인 뒤 삭제한다.
- **유지**: 52 G2 alembic squash(선행 조건 충족, 운영 head 확인·baseline stamp·nestlio용 `transactions.external_ref`·인덱스 보존 필요, 단독 PR), `PATCH /settings` 단일화(APK 재배포 뒤), 프론트 메이저·yfinance·pandas 3(Dependabot ignore), 400줄 초과 컴포넌트 12개(기능 작업 때 분리), 사용자 작업(외부 keep-alive·APK Variables·79/80/89 실기기·#179/#180 배포 로그).
