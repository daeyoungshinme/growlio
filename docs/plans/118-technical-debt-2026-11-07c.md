# 118. 남은 기술부채 — 117 회귀·푸시/DART/위젯·세금 연도 필터·CI 실 DB 테스트 (2026-11-07c)

> **진행 상태**: A~D 구현 완료. 브랜치 `chore/tech-debt-2026-11-07c`. 마이그레이션 없음.

요청은 "남은 기술부채 수정 계획"이다. 115~117(PR #243~#245)은 머지됐고 main CI는 녹색이다. 감사는 세 갈래로 했다.
1. 백엔드: 117 회귀, 113~117에서 다루지 않은 모듈
2. 프론트: 117 회귀, 미감사 화면
3. 인프라: CI·의존성·테스트

깨끗했던 영역(재조사 금지):
- 117의 find-account 잔여물, `syncProfile()` 호출부, 사용자별 키
- 쿼리 키 파라미터, KST 날짜, 라우트 링크, `vercel.json` rewrite
- CLAUDE.md 파일 목록(백·프 모두)
- Actions SHA 고정, 미사용 deps, alembic head 1개, 영구 skip 없음
- challenges/alert 라우터, `_alert_crud`, `fx_plan_service`, `dca_cash_shortfall_service`, `portfolio_history_service`, `sync_all_service`, `action_items_service`의 소유권·`is_active`·KST·Sentry

## 배치 A — 백엔드 실버그 (117 회귀)

- **A1 챌린지가 COMPLETED로 바뀌지 않을 수 있음** — `jobs/challenge_monthly_wrap.py`
  - 117 B2 이후 완료 전환이 알림 성공 때만 일어났다. 알림 채널이 없는 사용자(FCM 토큰 없음·메일 미설정)는 영영 ACTIVE로 남았다. RETURN_PCT는 다음 달 수익률이 내려가면 달성 자체가 사라졌다.
  - 수정:
    - 완료는 알림과 무관하게 저장한다.
    - 조회 대상은 ACTIVE + 이번 달(KST 월초 이후) 완료분이다. 완료분은 dedup 키가 없으면 알림을 재시도하고, 이미 완료된 챌린지는 수익률이 내려가도 달성으로 본다.
    - 지난달 이전 완료분은 조회에서 빠지므로 새 월 키로 재발송되지 않는다.
- **A2 상쇄로 기초 잔액이 0이 되면 당일 입금이 이중 계산됨** — `services/portfolio/returns_calculator.py`
  - `anchored_cashflows(original_openings=...)`는 당일 거래를 버릴지를 상쇄 전 기초 잔액으로 판정한다.
  - 원래부터 0인 기초 잔액(117 A3, 입금 전 동기화)은 그대로 당일 입금을 남긴다.

## 배치 B — 백엔드 정리

- **B1 DART**
  - 실패 쿨다운 키를 sha256으로 바꿨다. 평문 키를 프로세스 메모리에 두지 않기 위해서다.
  - `DELETE /settings/dart`도 배당 캐시를 무효화한다.
  - `DartApiKeyUpdate`가 앞뒤 공백을 지운다(`str_strip_whitespace`).
- **B2 ETF 빈 응답** — `etf_profile_service._resolve_overseas`
  - 다른 심볼은 응답한 배치에서 시작된 빈 응답이 3번 이어지면 "데이터 없음"(1일)으로 캐싱한다. 연속 횟수는 캐시(`…:empty`)에 남긴다.
  - 배치 전체가 비어서 시작한 연속은 세지 않는다. 서킷브레이커나 네트워크 실패와 구분되지 않기 때문이다.
  - 함수 복잡도(C901) 때문에 해외 조회를 모듈 함수로 분리했다.
- **B3 세금 연도 필터**: `tax_service`·`pension_contribution_service`·`isa_service`의 `extract(year)`를 날짜 범위로 바꿨다.
- **B4 페이지 검증**: 계좌 목록과 주가 알림 목록의 `skip`/`limit`를 `Query(ge…, le=500)`로 검증한다. 음수 skip은 500 대신 422가 된다.
- **B5 `manual_amount` 정의**: 수동 종목 저장도 `ManualProvider.sync`와 같이 평가액 + 예수금(스냅샷 금액과 같은 값)으로 저장한다.
- **B6 죽은 입력**: `SyncProfileRequest`를 제거했다. 예전 클라이언트가 보내는 본문은 무시된다.

## 배치 C — 프론트

- **C1 푸시 끄기 실패**
  - 토큰 삭제가 실패하면 끈 기록·"꺼짐" 표시 없이 켜진 상태를 유지하고 toast로 알린다.
  - 예전에는 서버에 토큰이 남아 푸시가 계속 왔고, 앱은 다시 등록하지 않았다.
- **C2 DART 키 저장 후 배당 stale**: `invalidateDartKeyData`를 추가했다. 대상은 settings, 배당 3종, `dividendPlan`, `monthlyOptimization`이다. 저장할 때는 키를 trim해서 보낸다.
- **C3 로그아웃 위젯 잔류**: `useLogout`이 `clearWidget()`으로 위젯을 "—"(위젯 기본값)으로 되돌린다. Java 변경은 없다.
- **C4 매매 수정 중 계좌 변경**: 수정 모드를 끝낸다. 예전에는 옛 계좌의 기록이 수정됐다.
- **C5 매매 후 인사이트**: `invalidateTradeData`에 `insights`를 추가했다.
- **C6 해외 주가 알림 목표가**: USD로 입력받아 현재 환율로 원화 환산해 저장하고, "≈ ₩" 힌트를 보여 준다.
- **C7 온보딩 배너 닫기**: 사용자별 키(`targetPortfolioBannerDismissedKey`·`challengeEmptyStateDismissedKey`)로 바꿨다. 옛 기기 단위 키 3개는 부팅 때 지운다(`removeLegacyDeviceKeys`).
- **C8 접근성**: 설정 폼(알림 이메일·주가/환율 알림·DART)의 label을 입력칸과 연결했다.
- **C9 문서**: `dividendPlanQuery`를 공용 쿼리 목록에 추가했다.

## 배치 D — 인프라·테스트

- **D1 실 DB 테스트**: `tests/test_real_db_upserts.py`(`@pytest.mark.db`)
  - 대상: durable upsert·claim, 스냅샷 ON CONFLICT, 연금 납입 연도 경계
  - `GROWLIO_TEST_DATABASE_URL`이 있을 때만 돈다(CI 서비스 컨테이너). 로컬 `.env`의 DB는 공유 Supabase일 수 있어 쓰지 않는다.
  - 각 테스트는 바깥 트랜잭션을 롤백한다.
- **D2** CI에서 `alembic downgrade -1` 뒤 `upgrade head`를 다시 실행한다. 재적용을 검증하고, 테스트가 head 스키마로 돈다.
- **D3** coverage exclude에서 `useBiometric`·`usePushNotifications`·`useWidget`을 뺐다. 임계값은 그대로 통과한다.
- **D4** `make install-backend`에 `--locked`를 붙였다. **D5** hatchling에 `<2` 상한을 걸었다.
- **D6** 문서를 정리했다: CLAUDE.md의 Node·`make lint` 설명, `push_service` firebase-admin 상한 메모.

## 보류·이관

- 115~117 보류 항목은 그대로 둔다. Sentry EU CSP는 DSN 확인 후로 미룬다.
- 무단언 테스트 2개(`test_currency_and_cache_keys.py:470`, `test_http_client.py:79`)는 영향이 미미하다.
- 설정 외 화면의 감싸지 않은 label(약 47개)은 별도 접근성 계획으로 넘긴다.
- 실 DB 테스트에서 확인한 점: core upsert(`set_durable`·`upsert_snapshot`)는 세션 identity map을 갱신하지 않는다. 운영은 요청·잡마다 새 세션이라 문제없다. 같은 세션에서 ORM 조회 → core upsert → 재조회하는 코드를 새로 쓸 때는 `expire`/`refresh`가 필요하다.

## 검증

- 백엔드:
  - ruff·format·mypy 0건
  - pytest 3734 통과, 커버리지 93.36%
  - 실 DB 테스트 4건은 로컬에서 skip(Docker 없음)이고, CI에서 확인한다.
- 프론트:
  - eslint·prettier·tsc(앱·테스트) 0건
  - vitest 192파일·2028 통과(coverage, D3 후 임계값 통과)
  - `npm run build` 성공
- **확인 못 한 것**:
  - 실기기: 푸시 끄기 실패 시 상태 유지, 로그아웃 후 위젯 초기화
  - 수동: DART 키 붙여넣기 후 배당 즉시 갱신, 해외 주가 알림 USD 입력
