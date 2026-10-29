# 91 — 남은 기술부채 처리 (2026-10-29)

## 배경

계획 84·87·90을 거치며 신규 저위험 부채는 소진됐다(TODO/FIXME 0건, 정적 검사 클린). 남은 것은 계획 52의 이관 항목이었다. 90 "이관 유지"를 현재 코드와 대조하니 전부 그대로 남아 있었다. 사용자는 E·B3·G1·D·F·프론트 전부를 범위로 정했다.

브랜치는 두 개다.
- `chore/tech-debt-2026-10-29`: 아래 커밋 전부
- `chore/drop-dead-columns-2026-10-29`: 그 위에 쌓은 G1-2 하나. **G1-1 배포가 끝난 뒤 머지한다**

## 결과

| # | 항목 | 결과 |
|---|---|---|
| E | 알림 계층 | **완료.** `send_push_safely`로 수동 푸시 try/except 6곳과 `dispatch_dual_channel_alert`를 통일했다. **실버그**: `notify_and_record_trigger`(환율·주가 알림)는 푸시 예외가 trigger 갱신을 막아, 이미 나간 이메일이 다음 실행에 재발송될 수 있었다. 이제 푸시 실패는 로깅만 한다. `run_per_user` 러너로 잡 4개(목표 달성·월간 리포트·챌린지 독려/결산)의 Semaphore·유저별 실패 보고·수신 이메일 결정을 하나로 모았다 |
| B3 | KIS·키움 주문 흐름 | **완료.** `_broker_order_flow.py`가 매도 보유수량 clamp와 FULL 매수 예산 clamp를 맡고, 브로커별 차이는 `BrokerOrderOps`로 주입한다. 기존 executor 테스트는 **한 줄도 바꾸지 않고** 통과했다. ops 콜러블이 모듈 이름을 호출 시점에 조회해 `patch.object`가 유지된다. 해외 키 차이(KIS `ticker:거래소`, 키움 ticker 단독) 회귀 테스트를 추가했다 |
| G1 | 죽은 컬럼 | **부분 완료.** G1-1: 모델에서 `amount_original`·`token_type`×3을 제거하고 `user_ticker_settings`를 드롭했다(`dc1`, 조회 코드가 없어 한 번에 처리). G1-2: 컬럼 드롭(`dc2`)은 별도 브랜치에 있다. 두 컬럼 모두 server_default가 있어 INSERT는 영향이 없다 |
| D | 설정 API | **방향 변경 후 완료.** 아래 "계획과 달라진 점" 참고. on/off PUT 7개를 테이블 등록(`_TOGGLE_SETTINGS`)으로 통합했다. 경로·응답·엔드포인트별 rate limit은 그대로다. 경로→컬럼 매핑을 테이블과 독립된 기대값으로 고정하는 테스트 14건을 추가했다 |
| F | services 패키지 | **6개 클러스터 완료**: `market_signal/`·`etf/`·`backtest/`·`tactical/`·`tax/`·`goal/`. 평면 모듈은 66→36개다. 파일명은 유지하고 shim은 두지 않았다. 클러스터마다 patch 대상 문자열 439개가 전부 resolve되는지 검사했고, 수집 테스트 수(3126)가 전후 동일했다. goal 스냅샷 하네스는 무변경으로 통과했다 |
| 프론트 | 대형 컴포넌트 | **완료.** `StockHoldingsTable` 705→270줄(`stockHoldings/`), `InvestmentGoalCard` 571→105줄(`investmentGoal/`). 마크업·동작은 바뀌지 않았다 |
| 프론트 | `noUncheckedIndexedAccess` | **측정 후 이관.** 켜면 오류 249건(소스 104, 테스트 145)이다. 기준(150건)을 넘었다. 소스 오류는 `TransactionHistoryTab`(15)·`TransactionList`(12)·`useSwipeNavigation`(8)·`rebalancingExecution/index`(8)에 몰려 있다 |

검증: 백엔드 3126 tests 92.03%, ruff/format/mypy 클린. 프론트 1878 tests(coverage 게이트 통과), tsc/eslint/prettier/build 클린. 마이그레이션은 로컬 `.env`가 공유 Supabase를 가리키고 Docker가 없어 로컬에서 돌리지 않았다. CI의 upgrade head → downgrade -1이 검증한다.

## 계획과 달라진 점 (정정)

- **D — `PATCH /settings` 단일화 보류.** 설치된 APK가 기존 PUT을 호출하므로 PUT을 지울 수 없다. 지금 PATCH를 더하면 경로가 15→16개로 늘어 부채만 커진다. 실제 중복이던 on/off 토글 7개만 통합했다. 단일화는 APK 재배포 뒤 `untracked_holdings` 제거와 함께 한다.
- **E — 수신 이메일 헬퍼 15곳 치환 생략.** `a or b` 한 줄을 함수로 감싸면 간접층만 늘어난다. 잡 4곳은 `run_per_user`가 대신 결정한다. 알림 서비스 2곳(digest·drift)은 services→jobs import 금지(90 C5) 때문에 러너를 적용하지 않았다.
- **G1 — `composite_level_at_plan` 유지.** "쓰기만 함"이지만 AUTO 플랜 생성 시점의 시장등급 감사 기록이다. 생성 함수 시그니처(위치 인자)에 걸려 있어 제거 이득이 작다.
- **G1 — `needs_password_reset`는 죽은 컬럼이 아니다.** `/auth/me`가 DB 값을 그대로 내린다. m1 마이그레이션이 기존 유저를 TRUE로 채웠고 DB에서 FALSE로 바꾸는 코드가 없다(`resetPassword`는 프론트 상태만 끈다). 그래서 m1 이전 유저에게는 재설정 배너가 계속 뜰 수 있다. 제거할지, 재설정 시 DB를 갱신할지는 사용자 판단이 필요하다.
- **B3 — `is_overseas_market` 이동 철회.** KIS 주문 거래소(US 3곳) 기준이다. `app.constants.OVERSEAS_MARKETS`(TSE·HKEX 등 포함)로 옮기면 그 거래소 주문이 해외 주문 API로 라우팅된다. 공용 모듈에 주석으로 남겼다.
- **B3 — 로그 이벤트명.** FULL 매수 예산 조회 실패 이벤트를 `{prefix}full_strategy_buy_budget_failed`로 통일했다. 이전 이름은 `full_strategy_orderable_cash_failed` / `kiwoom_full_strategy_deposit_lookup_failed`다.

## 이관

- **G1-2 머지**: G1-1 배포 확인 후
- **`needs_password_reset` 처리 방향**: 사용자 결정 필요(위 정정 참고)
- **D 본편**(PATCH 단일화 + PUT 삭제): APK 재배포 뒤
- **F 나머지**: market_data(`yahoo_price`·`price_service` 등)·portfolio·accounts·notifications(`push_service`·`email_service`). 테스트에서 수십 곳 patch되는 공용 계층이라 클러스터마다 영향이 크다
- **`noUncheckedIndexedAccess`**: 소스 104건부터. 테스트는 별도 tsconfig로 분리하는 방안을 검토한다
- **유지**: 52 G2(alembic squash), M9 알림 병합, 이메일 래퍼 압축, 90의 사용자 작업 대기·로드맵 항목
