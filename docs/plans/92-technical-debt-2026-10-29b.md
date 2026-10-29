# 92 — 남은 기술부채 처리 2차 (2026-10-29)

## 배경

계획 91(PR #179·#180)의 이관 중 사용자가 F 나머지(services 공용 계층 4갈래)와 프론트 `noUncheckedIndexedAccess`를 범위로 정했다. 시작 전에 91 머지 코드를 감사해 나온 것(0)을 먼저 처리했다.

브랜치: `chore/tech-debt-2026-10-29b`. 클러스터마다 커밋 1개.

## 결과

| # | 항목 | 결과 |
|---|---|---|
| 0-0 | dc1·dc2 머지 간격 | **확인 요청(코드 없음).** #179와 #180이 9초 간격으로 머지돼 같은 preDeploy에서 두 마이그레이션이 돌았을 수 있다. 그 사이 옛 인스턴스가 드롭된 컬럼을 SELECT하다 실패했을 수 있다. Render 배포 로그·Sentry로 확인한다. 91 문서와 README의 "배포 후 머지" 문구를 고쳤다 |
| 0-1 | 유저별 알림 루프 | **실버그(관측성).** 연말 절세·추천 비중 변화·시장신호 매일 요약이 자체 Semaphore와 `logger.error`만 써서 유저 단위 실패가 Sentry에 가지 않았다. `run_per_user`·`report_job_failure`를 `app/core/job_runner.py`로 옮기고(services→jobs import 금지) 세 서비스를 그 위로 옮겼다. 등급 전환 루프는 순차·발송 수 집계가 필요해 `report_job_failure`만 적용했다. 서비스마다 실패 격리 + 보고 테스트를 추가했다 |
| 0-2 | 91 잔여 | 국내 지정가 호가 보정(KIS·키움 동일 블록)을 `snap_domestic_limit_price`로 합쳤다. 키움 executor의 안 쓰는 logger, `GoalChipsResult` export를 지웠다. `changePassword`는 플래그가 켜져 있을 때만 reset-complete를 호출하고 실패는 `console.warn`으로 남긴다. backend/CLAUDE.md 불일치(estimation 위치 등)를 고쳤다 |
| A1~A4 | services 패키지 | **완료.** `accounts/`(7)·`portfolio/`(9)·`market_data/`(5)·`notifications/`(`push_service`·`email_service`·`email_templates/`). 평면 모듈은 36→13개다. 파일명 유지, shim 없음. 클러스터마다 tests의 patch 문자열 219개 전부 resolve, 수집 수 3131 동일, 전체 테스트·mypy 통과, 모든 모듈 import 스모크 통과 |
| B | `noUncheckedIndexedAccess` | **앱 코드 완료.** 소스 103건(33파일)을 고쳤다. 테스트는 `tsconfig.test.json`(플래그 off)으로 분리했다. `npm run typecheck`가 두 설정을 모두 돌리고, eslint `parserOptions.project`도 둘 다 본다. `tsc -b`(build)는 앱만 본다 |

검증: 백엔드 3131 tests(coverage 92.05%), ruff/format/mypy 클린. 프론트 1883 tests(coverage 게이트 통과), tsc(앱·테스트)/eslint/prettier/build 클린. 로컬 `.env`가 공유 Supabase를 가리켜 서버 기동(스케줄러가 실제 알림을 보낼 수 있음) 대신 전 모듈 import 스모크로 대신했다.

## 계획과 달라진 점

- **0-2 `goal_achievement` 로그 레벨 원복 생략.** `send_push_safely`가 호출부 6곳 모두 error로 로깅한다. 한 곳만 warning으로 돌리려고 파라미터를 더할 이득이 없다.
- **0-2 호가 보정은 `execute_single_order` 안이 아니라 별도 헬퍼.** 브로커별 `_place` 클로저가 `order`를 캡처하므로 클로저 정의 전에 보정해야 한다.
- **B `.at()` 미사용.** `lib`이 ES2020이라 `.at()`이 없다. 마지막 원소는 `arr[arr.length - 1]` + 가드로 처리했다.

## 이관

- **`noUncheckedIndexedAccess` 테스트 145건**: `tsconfig.test.json`에서 켜고 고친다.
- **유지**: `PATCH /settings` 단일화(APK 재배포 뒤), 52 G2 alembic squash, 사용자 작업(keep-alive·APK Variables·실기기 확인), 프론트 메이저·yfinance 1.x·pandas 3(Dependabot ignore).
