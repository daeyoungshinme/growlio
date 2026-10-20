# 61. 기술부채 감사 (2026-10-20)

## Context

계획60(PR #136) 이후 main은 Dependabot patch 범프 3건만 전진했다(프론트 deps 그룹·vitest·setup-java, 전부 patch/minor → 회귀 위험 없음). 구조 지표는 여전히 깨끗하다(`type: ignore` 11, `noqa` 0, `@ts-ignore` 0, `as any` 27건 전부 테스트, 잔여 `date.today()`는 FRED 경로뿐).

그래서 이번 감사는 55~60에서 다루지 않은 축을 봤다: **인증·세션·사용자 전환, 푸시 토큰, 알림 중복판정, 스키마 검증, 영속 캐시**. Explore 3개의 보고 중 아래 A·B 항목은 전부 코드를 직접 읽어 재확인했다. 정정 1건: Explore는 "AUTO 경로의 실시간 가격도 호가 격자를 벗어난다"고 했지만, 실시간 현재가는 체결가라 원래 격자 위에 있다. 따라서 C2(호가단위)의 위험은 **수동 지정가 입력**에만 해당한다.

상태: **A·B·C·D 완료**(아래 "실행 결과"). 브랜치 `fix/tech-debt-2026-10-20`, 배치별 커밋.

## 배치 A — 백엔드 실버그 (최우선)

| # | 문제 (확인함) | 수정 |
|---|---|---|
| A1 | **연말 절세 리마인더의 이력 저장이 매번 실패한다.** `models/alert.py:153`의 `AlertHistory.alert_type`은 `String(20)`인데 `"YEAR_END_TAX_REMINDER"`는 21자다(`tax_reminder_service.py:105`). 메일·푸시를 보낸 뒤 이력 commit이 실패하고 except에서 로그만 남는다. 결과: 앱 알림 이력에 안 남고, `_already_sent_reminder_today`가 항상 False라 재실행하면 중복 발송된다. `MARKET_SIGNAL_DIGEST`·`RECOMMENDATION_DRIFT`는 정확히 20자다 | alembic 마이그레이션으로 `alert_type`을 `String(40)`으로 넓힌다(ALTER TYPE varchar 확장은 메타데이터만 바뀌어 잠금이 짧다). 모델도 갱신하고, 주석 `# EXCHANGE_RATE \| REBALANCING \| STOCK_PRICE`를 실제 타입 목록으로 고친다. 테스트: 전체 alert_type 리터럴 길이 ≤ 컬럼 길이(코드 grep 대신 상수 모음이나 파라미터화 테스트) |
| A2 | **같은 날 중복판정이 KST 09:00(UTC 자정)에 끊긴다.** `market_signal_alert_service.py:134`, `recommendation_drift_alert_service.py:71`, `tax_reminder_service.py:67`이 `datetime(today_kst()…, tzinfo=UTC)`를 쓴다. 다이제스트는 08:30 KST(=전날 23:30 UTC)에 실행되므로 dedup이 항상 False가 되고, 재시작·misfire 재실행 때 중복 발송된다 | `tzinfo=KST`로 바꾼다(`jobs/goal_achievement.py:32`가 이미 이렇게 한다). 세 곳이 같은 코드이니 `utils/kst.py`에 `kst_day_start(d) -> datetime` 헬퍼를 두고 공유한다. 테스트: 08:30 KST 이력이 있으면 같은 날 재실행 시 True |
| A3 | **챌린지 수정이 생성 시 검증을 우회한다.** `schemas/challenge.py:97` `ChallengeUpdate`에 `target_amount/pct/months` 범위 검증이 없고, `update_challenge`(`challenge_service.py:296`)는 명시적 null도 setattr한다. `{"title": null}`이면 NOT NULL 500, `target_pct: 99999`면 Numeric(6,2) 오버플로 500, RETURN_PCT 챌린지의 `target_pct`를 null로 비울 수 있다 | `ChallengeBase`의 범위 validator를 공용 함수로 빼서 Update에도 적용한다. `title`·`reminder_enabled`·`status`의 null은 거부한다. 서비스에서 setattr한 뒤 유형 규칙(`_validate_type_targets`와 같은 규칙)을 병합된 상태로 재검사해 422를 낸다 |
| A4 | **FCM 토큰이 사용자 간에 공유된다.** `PUT /settings/push-token`(`api/v1/settings.py:575`)은 내 row만 갱신하고, 같은 토큰을 가진 다른 사용자 row는 그대로 둔다. 공유 기기에서 A가 로그아웃하고 B가 로그인하면 A의 포트폴리오·목표 알림이 B 기기로 간다. 또 FCM unregistered 응답 시 로그만 남긴다(`push_service.py:75`) | ① 토큰을 등록할 때 `UPDATE user_settings SET fcm_token=NULL WHERE fcm_token=:t AND user_id<>:me`를 먼저 실행한다. ② `send_push`가 invalid-token을 반환하도록 결과를 구분하고(bool → 상태값), 호출부(`send_push_to_user`)가 해당 사용자 토큰을 null로 만든다. 세션 commit 경계는 호출부 패턴을 확인하고 정한다 |
| A5 | **삭제한 계정이 `/auth/sync-profile`로 되살아난다.** `auth.py:35-101`은 JWT 서명만 확인하고 row가 없으면 생성한다. 기기 A에서 탈퇴해도 기기 B는 유효한 access token(~1h)을 갖고 있어서, `/auth/me`가 401을 받으면 sync-profile이 실행되고(`authStore.ts:198`) 이메일이 다시 저장된다 | 신규 생성 분기 직전에 `supabase_user_exists(user_id)`를 호출한다(기존 orphan 분기와 같은 httpx 에러→503 처리). False면 401을 낸다. 가입 직후 1회 호출이라 비용이 작다 |

## 배치 B — 프론트 실버그

| # | 문제 (확인함) | 수정 |
|---|---|---|
| B1 | **화면을 이동할 때마다 푸시 설정이 다시 돈다.** `usePushNotifications.ts:146`의 deps에 `navigate`가 있는데, `BrowserRouter`(non-data router)의 `useNavigate`는 `locationPathname`이 바뀌면 새로 만들어진다. 그래서 이동할 때마다 리스너 해제·재등록, `requestPermissions`/`register`, `PUT push-token`(10/min 레이트리밋)이 실행된다. `AppLayout.tsx:39-56`의 Android 뒤로가기 리스너도 같은 원인이고, 해제가 비동기라 리스너 두 개가 잠깐 겹칠 수 있다 | `navigate`를 `useRef`에 담는다(기존 `useLatestRef` 류 훅이 있으면 재사용한다. 착수 시 grep). 두 effect의 deps에서 `navigate`를 뺀다. 테스트: rerender로 경로가 바뀌어도 `register` 호출이 1회인지 |
| B2 | **로그아웃해도 이 기기의 푸시 토큰이 지워지지 않는다.** null 전송은 설정 토글(`disablePushNotifications`)에서만 한다 | `authStore.logout`과 `DeleteAccountModal`에서 native이고 상태가 registered이면 `signOut` **전에** `registerPushToken(null)`을 best-effort(실패해도 무시)로 호출한다. 세션 만료 경로는 인증이 없어 호출할 수 없다. 이 경우는 A4①(다음 로그인 사용자 등록 시 정리)이 덮는다 |
| B3 | **다른 사용자가 로그인하면 이전 사용자의 캐시가 보인다.** 앱이 닫힌 사이 세션이 죽으면 `checkAuth`는 `setLoggedOut()`만 한다(`authStore.ts:227`). 쿼리키에 user id가 없고 persist는 24h다 | `setLoggedIn(user)`에서 직전 user id(메모리 값, 없으면 persisted `auth-me` 캐시의 id)와 비교한다. 다르면 `queryClient.clear()`와 persister `removeClient()`를 호출한다. `checkAuth`의 로그아웃 분기도 캐시를 정리한다 |
| B4 | **persist 필터가 실패한 쿼리도 저장한다.** `main.tsx:56`의 custom `shouldDehydrateQuery`가 기본값(성공한 쿼리만)을 대체한다. 그래서 앱이 에러 상태로 부팅될 수 있다. `buster: "v1"`은 2026-06-09 이후 한 번도 바뀌지 않았다 | `defaultShouldDehydrateQuery(query) && PERSIST_QUERY_KEYS.has(...)`로 바꾼다. buster는 빌드 시점 값(`define: __APP_BUILD__` = package version + git sha 또는 빌드 타임스탬프)으로 바꿔서 배포마다 캐시를 무효화한다. 타임스탬프는 매 배포 첫 부팅이 콜드가 되는 트레이드오프가 있으므로, 착수 시 "명시 상수를 올리는 규칙 + CLAUDE.md 기록"과 비교해 정한다 |
| B5 (저) | `useWidget.ts:14-19`가 로그아웃 상태에서도 dashboard를 조회해 `/register` 등에서 "세션 만료" 토스트가 뜰 수 있다. `IsaMaturityCard.tsx:17`은 date-only를 `new Date()`로 파싱한다(UTC 해석). `useDividendPlanSettings.openEdit`의 `fetchSettings` 실패가 처리되지 않는다 | `enabled: native && isAuthenticated`로 바꾼다. `parseYmd`를 쓴다. openEdit에 try/catch + 토스트를 넣고, 가능하면 `QUERY_KEYS.settings` 캐시를 `fetchQuery`로 재사용한다 |

## 배치 C — 실주문 안전망 (중위험, 별도 커밋, 계획59 C 이관)

| # | 문제 | 수정 |
|---|---|---|
| C1 | **AUTO 잡: 항목 하나가 실패하면 나머지가 연쇄로 실패하고, 하루 1회 보장이 원자적이지 않다.** `jobs/rebalancing_auto_execution.py:117`의 try는 `build_pending_plan_for_alert`만 감싸고 rollback이 없다. `notify_*`(내부 commit)에는 try가 없다. `last_triggered_at`은 plan commit(`plan_generation.py:272`) 뒤 메모리에만 기록되고 루프 끝(:144)에 commit된다. 그래서 중간에 크래시하거나 예외가 나면 같은 날 재생성될 수 있고, 배포가 겹친 두 인스턴스는 in-proc 락으로 막을 수 없다 | ① 루프 본문 전체를 `alert_check.py:442-459` 패턴(항목별 try + `db.rollback()` + 남은 row 재조회 + Sentry 타입명만)으로 감싼다. ② `utils/durable_state.py`에 `claim_durable(db, key, ttl) -> bool`을 추가한다: 만료된 row를 지운 뒤 `insert(AppState).on_conflict_do_nothing(index_elements=[key]).returning(key)`. 키는 `rebalancing_auto_fired:{alert_id}:{kst_date}`, TTL 2일. 플랜 생성 직전에 claim하고, 생성이 None·게이트 차단으로 끝나면 claim을 유지할지는 기존 `already_fired_today` 의미(게이트 차단 시 last_triggered_at 갱신 여부)와 맞춘다. ③ `last_triggered_at`은 plan과 같은 트랜잭션에서 commit되게 `:402` 대입을 `:272` commit 앞으로 옮긴다. 테스트: claim 2회 중 1회만 True, 두 번째 alert가 예외를 내도 세 번째가 처리됨 |
| C2 | **수동 국내 지정가에 호가단위 보정이 없다.** `kis/order.py:52`·`kiwoom/order.py:44`는 `int()`만 한다. 프론트 `RebalancingPriceInput`은 `step=1`이고 `getLimitPriceNative`(`rebalancingExecution/index.ts:197`)는 해외만 반올림한다 | 백엔드 `utils/krx_tick.py`의 `round_to_tick(price, side, is_etf)`: 매수는 내림, 매도는 올림. 주식은 KRX 2023 호가표, ETF/ETN은 5원. **착수 전에 현행 호가표를 확인한다.** ETF 판별은 `goal_candidate_service.looks_like_korean_etf`(이름 기반)를 쓴다. 판별이 불확실하면 주식 호가표가 ETF 격자(5원)의 배수 관계라 매수 내림이 항상 유효 가격이 되는지 확인하고, 안전한 쪽을 택한다. 적용 위치는 두 broker의 국내 주문 함수 직전(모든 경로가 모이는 곳)이다. 프론트는 같은 표로 보정값을 입력 옆에 미리 보여준다 |

## 배치 D — 저위험 위생

- `economic_indicator_service.py:89,143,186`: `date.today()`(서버 UTC)는 KST 09~15시에 미국 날짜보다 하루 앞서 FRED `realtime_start`가 미래가 되어 400이 난다 → `datetime.now(ZoneInfo("America/Chicago")).date()`로 바꾸고 주석을 정정한다(FRED는 St. Louis, US Central)
- `schemas/auth.py:7` `display_name` `max_length=100`(컬럼 String(100)), `schemas/asset.py:293` `IsaPnlOverrideUpdate.cumulative_pnl_krw` 유한값·범위 검증(`_validators.py` 기존 헬퍼 재사용)
- `dca_service._calc_months_to_goal`: 이미 목표에 도달했으면 0을 반환하게 한다(호출부 표시 확인)
- `auth_service.verify_password`: 429/5xx를 "비밀번호 불일치"로 표시하지 않고 503으로 구분한다
- 문서: `backend/CLAUDE.md`에 `claim_durable`·`kst_day_start`·alert_type 길이 규칙, `frontend/CLAUDE.md`에 persist buster 규칙·사용자 전환 캐시 정리

## 이관 (README에 기록, 이번 미구현)

- JWKS 동기 네트워크 호출이 이벤트 루프를 막을 가능성(`auth_service.py:36`, PyJWT 캐시 기본값 미확인) — 검증 필요
- 백테스트 결측일 가중치 재정규화(`backtest_metrics.py:118-125`, 한국 휴장일·중도 상장) → forward-fill + 고정 수량. 하네스(스냅샷) 선행
- 알림 이메일 주소 미검증·unsubscribe 헤더 없음(제품 판단)
- 위젯 데이터를 로그아웃 시 지우기(`WidgetPlugin`에 clear 메서드 필요, Java + 실기기 검증)
- 세금 요약의 배당 15.4%가 실수령액 기준인지(입력 의미 확인, 제품 판단). 배당 집계 `is_active` 미필터는 계획60에서 "의도된 동작"으로 이미 결정
- 계좌 소프트 삭제 시 브로커 자격증명·토큰 보존, `alert_history` 보존 정책(기존 "데이터 보존" 이관에 합류), 계좌번호 비마스킹 응답, 배당 unique index(같은 날 특별배당)
- 프론트 L 항목: `fmtKrw` 경계(99,995,000 → "10,000만원", 음수 floor), 배당 월 금액 두 계산식, 목표 마법사 prefill 재덮어쓰기, mousedown 리스너 재구독
- 계획59 이관 목록 전체 유지(스케줄러 워커 분리, FK 인덱스, 52 B~G, biometric 플러그인, `noUncheckedIndexedAccess`, 대형 컴포넌트, 프론트 major)

## 재사용할 기존 코드

- `utils/kst.py`(`today_kst`, `KST`), `jobs/goal_achievement.py:32` 패턴
- `services/rebalancing/alert_check.py:442-459` 항목별 격리 + 재조회 패턴
- `utils/durable_state.py`(`set_durable`의 `insert…on_conflict` 스타일), `jobs/app_state_sweep.py`
- `auth_service.supabase_user_exists`, sync-profile orphan 분기의 503 처리
- `schemas/_validators.py`, `ChallengeBase` validators
- 프론트 `utils/date`의 `parseYmd`, `@tanstack/react-query`의 `defaultShouldDehydrateQuery`, `api/settings.registerPushToken`

## 검증

```bash
make lint && make typecheck
make test-backend-cov    # 80% 게이트, Windows 종료코드 -1073741819는 실패 아님
make test-frontend
cd backend && uv run alembic check   # A1 마이그레이션 후 드리프트 없음
```
- 실버그 회귀 테스트(A1~A5, B1~B4, C1)는 **수정 전 코드에서 먼저 실패하는지** 확인한다(59·60과 같은 절차)
- A1 마이그레이션: upgrade/downgrade SQL을 `alembic upgrade --sql`로 확인한다. Supabase 공유 DB이므로 `growlio_alembic_version` 경로로 적용한다
- C1 SQL: 텍스트 고정 + `uvx --with pglast`로 문법을 확인한다
- 배포 후 확인: 11월 첫 월요일 연말 리마인더가 알림 이력에 남는지, 08:30 다이제스트가 1회만 가는지, 공유 기기 로그아웃 → 다른 계정 로그인 시 이전 계정 푸시가 안 오는지(실기기)
- 완료 후 메모리 `project_tech_debt_2026-10-20.md` + MEMORY.md 한 줄

---

## 실행 결과 (2026-10-20, 브랜치 `fix/tech-debt-2026-10-20`)

**A·B·C·D 완료.** 백엔드 2769 tests 91.37%, 프론트 1689 tests. ruff·ruff format·mypy·tsc·eslint(`--max-warnings 0`)·prettier 클린. 커밋: A `91cf4f70`, B `42074b69`, C1 `7c17b476`, C2 `97da6d94`, D(이 문서와 함께).

회귀 테스트가 수정 전 코드에서 실패하는 것을 확인한 항목: A1(길이 20으로 되돌리면 실패), A2(3건), A3(8건), B1(register 3회), C2(3건). A4·A5·B2~B4는 새 헬퍼나 분기를 추가한 것이라 동작 테스트로 고정했다. C1은 구조를 바꿔(`_process_one_alert`·`_load_auto_alert_rows` 신설) 수정 전 코드에 같은 테스트를 걸 수 없다.

계획 대비 정정·추가:
- **A4**: `send_push`(bool)는 그대로 두고 `deliver_push`가 결과 상태(`PushResult`)를 돌려주게 했다. 호출부 12곳은 바꾸지 않았다. 폐기된 토큰은 `send_push_to_user`가 **별도 세션**에서 지운다. 호출부들이 각자 트랜잭션 중간에 푸시를 보내기 때문이다. 그 사이 사용자가 새 토큰을 등록했을 수 있어서 토큰 값까지 같을 때만 지운다.
- **A5**: 기존 orphan 분기의 503 처리를 `_supabase_user_exists_or_503`으로 묶어 두 곳에서 같이 쓴다. 새 sub 확인을 orphan 정리보다 **먼저** 한다. 존재하지 않는 sub 때문에 고아 row가 지워지는 일을 막기 위해서다.
- **B2**: 탈퇴는 서버 CASCADE로 토큰이 지워지므로 로그아웃만 고쳤다. api 기본 타임아웃이 60초라서 토큰 삭제는 최대 3초까지만 기다린다.
- **B3**: `authStore`에서는 queryClient에 접근할 수 없다. 그래서 `claimCacheOwner`가 persist 키를 지우고, `CACHE_OWNER_CHANGED_EVENT`(동기 window 이벤트)를 받은 App이 `queryClient.clear()`를 호출한다. 소유자 기록 없이 캐시만 남은 기기(배포 전 캐시)는 한 번 비운다.
- **B4**: buster는 배포마다 자동으로 바꾸지 않고 명시 상수 `PERSIST_CACHE_BUSTER`로 했다. 자동으로 바꾸면 매 배포 첫 부팅이 콜드가 된다. 응답 형태를 바꿀 때 날짜로 올린다(`frontend/CLAUDE.md`). 필터는 `shouldPersistQuery`로 옮겨 테스트했다.
- **B5**: `openEdit`는 `fetchQuery` 캐시 재사용을 넣지 않았다. staleTime 동안 저장 직후의 이전 값이 보일 수 있어서 기존처럼 항상 새로 조회한다.
- **C1**: claim은 **플랜을 실제로 만든 경우에만 유지**한다. 게이트 차단·주문 없음·락 경합·생성 예외면 해제한다. 이전에는 이 경우들에 `last_triggered_at`을 기록하지 않아 다음 tick에 재평가했는데, 그 의미를 바꾸지 않기 위해서다. claim과 해제 사이에 크래시가 나면 그날은 실행하지 않는다. 실주문 경로에서는 중복보다 이쪽이 안전하다. `generate_pending_plan_for_alert` docstring의 "alert를 절대 mutate하지 않는다"는 원래도 사실이 아니었다(이전에도 build에서 `last_triggered_at` 대입). 문구를 사실에 맞게 고쳤다. 실패 시 rollback이 내부·외부에서 두 번 일어나는 것은 무해하다.
- **C2**: 모듈 위치는 `utils/`가 아니라 `services/rebalancing/krx_tick.py`로 했다. 서비스(ETF 이름 판별)를 import하기 때문이다. ETF 판별에는 이름 기반 `has_korean_etf_name`만 쓴다(`looks_like_korean_etf`에서 추출). 코드 prefix 폴백은 일반주 오판 위험이 있어 쓰지 않는다. executor가 보정한 **사본**을 쓰므로 `OrderResult.price`에도 실제 주문가가 남는다. 프론트에는 보정값 미리보기 대신 안내 문구만 넣었다. 미리보기를 하려면 ETF 브랜드 목록을 TS로 복제해야 하기 때문이다. 현행 호가표는 웹 검색으로 2023 개편 표와 일치하는 것을 확인했다. ETF 5원은 별도 출처로 재확인하지 못했다(이 위험은 위 설계로 다룬다).
- **D**: `_calc_months_to_goal`의 0 반환은 **보류**했다. 호출부 4곳이 `if months_to_goal`로 판정하므로, 0을 반환하면 "이미 달성"이 "계산 불가" 분기로 빠진다. `verify_password`는 `httpx.TransportError` 전체와 429/5xx를 예외로 넘기고, 탈퇴 라우트는 `httpx.HTTPError`를 503으로 바꾼다.
- **검증 메모**: 개발 DB(공유 Supabase)에는 마이그레이션을 적용하지 않았다. 읽기 전용 `compare_metadata`로 확인한 결과는 다음과 같다. 이번 차이는 `alert_type` 1건이다. 계획55의 `ix1` 인덱스도 개발 DB에 미적용 상태다. 나머지는 DESC 인덱스 오탐이다. 전체 pytest를 다른 명령과 병렬로 실행했을 때 한 번 97건이 실패했지만(루트 경로 기준으로 수집됨) 재현되지 않았다. 단독 재실행에서는 전부 통과했다.

배포 후 확인:
- Render `preDeployCommand`로 `at1_widen_alert_history_alert_type`이 적용되는지(varchar 확장이라 잠금이 짧다)
- 11월 첫 월요일 연말 리마인더가 알림 이력에 남는지, 08:30 다이제스트가 하루 1회인지
- 공유 기기에서 로그아웃 → 다른 계정 로그인 시 이전 계정의 푸시가 오지 않는지, 이전 계정 캐시가 보이지 않는지(실기기)
- 수동 실행 국내 지정가(호가 밖 값)가 거부되지 않고 체결 화면에 보정가로 표시되는지
