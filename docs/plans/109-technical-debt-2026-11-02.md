# 109. 기술부채 — 주문 동시성·잔고 정확성 재점검 (2026-11-02)

## 배경

108 머지 뒤 main은 깨끗했고 고전적 부채(TODO, `any`, 큰 파일)는 이번에도 0건이었다. 그래서 이전 감사에서 덜 본 축을 새로 봤다: 주문 동시성, 브로커 실응답의 의미, 로그의 민감정보, 실패가 "없음·0원"으로 보이는 화면.

결과적으로 **이중 주문 경로와 잔고 왜곡 경로**가 나왔다. 스캐너 보고는 소스로 재확인한 뒤 반영했다.

## 결과

### A. 주문·자동화

| 항목 | 문제 | 수정 |
|---|---|---|
| A1 | 승인 경합 이중 주문. `_lock_leg`가 `FOR UPDATE`로 다시 읽어도 세션에 남은 옛 `token_consumed_at`으로 판정해 동시 승인이 둘 다 통과 | `populate_existing=True` (`order_cancel_service`에 있던 패턴) |
| A2 | 대기 플랜 중복 생성. pending 확인이 락 밖 | 락 안에서 재확인 |
| A3 | 수동 실행 멱등성 없음. 타임아웃·5xx 후 버튼이 다시 켜지고 실행 중에도 모달을 닫을 수 있음 | 선택 필드 `idempotency_key` + `claim_durable`(중복 409). 프론트는 응답 불명확 시 재실행 차단, 명확한 4xx만 새 키로 재시도, 실행 중 닫기 차단 |
| A4 | 자동화를 꺼도 대기 매수 실행. 알림 FK SET NULL이면 시장 게이트까지 DISABLED | 알림 삭제·AUTO 해제·스코프 전환 삭제·포트폴리오 삭제 시 `cancel_pending_buy_legs`. 매도 leg는 승인이 필요하므로 유지 |
| A5 | 전 주문 실패해도 EXECUTED → 일일 한도에 합산돼 이후 플랜 차단 | 전 주문 미접수면 FAILED + 실패 알림. 부분 체결은 EXECUTED 유지 |
| A6 | 닫힌 시장의 매수가 조용히 사라짐 | 만료 시 이력·푸시. 시각 미지정 알림은 포트폴리오 시장이 열릴 때까지 평가 보류(claim 안 남김). 설정 화면에 혼합 포트폴리오 안내. 이월은 하지 않음 |
| A7 | NOTIFY 알림의 `account_id` 소유권 미검증 | 값이 있으면 항상 `get_owned_account` |

### B. 잔고·스냅샷

| 항목 | 문제 | 수정 |
|---|---|---|
| B1 | KIS 해외 이중 집계. 공식 샘플상 `[실전] NASD : 미국전체`인데 NYSE·NASD·AMEX를 모두 합침 | NYSE→AMEX→NASD 순 조회 + ticker 중복 제거. API 의미가 어느 쪽이든 안전 |
| B2 | KIS 달러 예수금 0 덮어쓰기. 공식 컬럼 매핑상 `frcr_dncl_amt_2`는 present-balance 필드이고 호출 중인 inquire-balance에 없음 | **1단계만 적용**: 필드 없으면 `None`(미확인 → 기존 값 유지, 스냅샷 합계에도 포함, "해외 없음" 캐싱 금지). 2단계는 이관 |
| B3 | 전량 매도 후 오늘 스냅샷에 유령 포지션 | 빈 목록도 `sync_snapshot_positions` 호출 |
| B4 | 파싱 실패·잘림이 정상 동기화로 저장 | `BalanceResponseError` 신설. 키움 수량·평가금액·예수금은 `_parse_required_num`, KIS `output2` 누락과 키 없는 연속조회는 예외 → 동기화 실패로 기존 데이터 보존 |
| B5 | 재시작 직후 환율 캐시가 비면 fallback 1300이 드리프트 수량에 쓰임(`composition_calculator`의 `fetch_usd_krw`) | 해외 포함 포트폴리오는 분석 전에 `get_live_or_cached_usd_krw`, 실환율 없으면 `UsdRateUnavailable`로 생성 안 함(잡은 다음 tick 재평가). 동기화·표시 경로는 이관 |
| B6 | 외부 입금 예수금 lost update | 수동 계좌 행을 `refresh(with_for_update=True)` |

### C. 로그·개인정보

- C1 느린 쿼리 로그에서 바인드값 제거. C2 메일 로그 `mask_email`.
- C3 `exc_info` 트레이스백이 redact를 우회 → `format_exc_info`를 redact 앞에 둠(`_with_redaction`).
- C4 Sentry `include_local_variables=False`.
- C5 삭제 계좌: 자격증명·토큰 삭제, 이 계좌로 주문하는 알림 비활성화, 대기 매수 취소. 복구 경로 없음을 확인했다.
- C6 탈퇴: 로컬 delete·flush → Supabase 삭제 → commit. 실패 시 rollback. KIS 사용자 토큰·토스 토큰 캐시도 삭제.

### D. 프론트 오표시

- **돈과 직결**: 알림 조회 실패 시 기본 폼 대신 재시도(저장 시 AUTO 덮어쓰기 방지). 승인 페이지 네트워크 실패 분기, 승인 실패 시 버튼 유지. 이력 탭 실패를 "이력 없음"으로 안 보임. 후보 ETF는 설정 로드 전 추가·저장 차단.
- **저장값**: 메모·수수료·기관을 지우면 실제로 지움(서버 `model_fields_set`, 프론트 null 전송 — 구버전 APK는 안 보내므로 기존 값 유지). 거래 수정 시 계좌 잠금. 수정 후 예수금 제안은 차액만(`utils/depositDelta`). 매매 기록 수정 중 종목 변경 시 수정 모드 종료. 환율 알림은 로드 전 등록 차단.
- **표시**: 계좌 조회 실패 시 온보딩 안 띄움, 거래 CUD 후 종목별 배당 무효화, 로그아웃 시 `syncStore.reset()`, section ErrorBoundary 메시지는 DEV에서만, 라우트 이동 시 오류 화면 해제(`resetKey`), 연간 합계 실패·로딩 시 "—", 세금 카드 실패 표시, 로그인 오류 문구 구분, 자동 조정 무반응 시 토스트.
- **접근성**: 주문 수량·지정가·매수 종목 추가 라벨, USD 금액 라벨, 유형 버튼 `aria-pressed`.

### E. 게이트

- E2 CI에 `alembic check` 추가.
- E3 테스트 외부 네트워크 가드(`conftest.py`). DNS 단계에서 막고 시도하면 테스트 실패. 누수 3건을 잡아 mock을 추가했다.
- E4 2월 29일에 터지는 시간 의존 테스트를 `_one_year_before`로.
- E5 주가 알림 100개·환율 알림 50개 상한(`count_user_alerts`, 초과 409).

### 계획과 달라진 것

- **E3은 `pytest-socket`을 쓰지 않았다.** 소켓 생성을 막으면 Windows에서 asyncio 이벤트 루프가 뜨지 않는다. `socket.getaddrinfo` 가드로 대체했다. `curl_cffi`(yfinance)는 C 레벨 DNS라 이 가드에 안 걸린다.
- **가드가 드러낸 것**: 로컬에서 테스트가 `.env`의 **실제 FRED 키**로 호출하고 있었다. `settings.fred_api_key`를 테스트에서 비워 키 없는 CI와 동작을 맞췄다.
- A4에 포트폴리오 삭제·스코프 전환 경로를 추가했다. 삭제하면 같은 함정이 있었다.
- E1(Docker CMD에서 마이그레이션)은 적용하지 않았다. Render 로그 확인이 먼저다.

## 검증

- 백엔드: 3,282 tests 통과, 커버리지 92.81%(게이트 89%). ruff·format·mypy clean.
- 프론트: 1,992 tests 통과, typecheck(앱+테스트)·eslint `--max-warnings 0`·`npm run build` 통과.
- 새 백엔드 회귀 테스트는 수정 전 코드에서 실패함을 확인했다(`test_rebalancing_order_safety.py` 24 failed).

### 검증하지 못한 것

- **실제 row 락 경합은 재현하지 못했다.** 테스트가 실DB를 막으므로 A1·A2·B6은 쿼리 옵션·호출 순서로만 고정했다.
- **KIS 실계좌 응답 미확인.** B1·B2·B4는 공식 샘플 기준이다. B4의 연속조회 예외는 KIS가 마지막 페이지에 `tr_cont=M`과 빈 키를 함께 준다면 정상 동기화를 실패시킨다. 첫 실계좌 동기화에서 확인 필요.
- **`alembic check`는 로컬에서 돌리지 못했다**(Docker 없음, `.env`는 공유 Supabase). PR CI가 첫 판정이다. 실패하면 드리프트 내용을 보고 판단한다.
- 브라우저·실기기 수동 확인 안 함. 실주문 안 함.

## 이관

- **사용자 확인 필요**
  - Render 무료 플랜에서 `preDeployCommand`가 도는지(배포 로그). 안 돌면 Docker CMD에서 `bootstrap → alembic upgrade head → uvicorn`.
  - KIS 실계좌 읽기 전용 조회: NYSE 종목 이중 집계 여부, `frcr_dncl_amt_2` 유무. 이중 집계가 맞으면 과거 스냅샷 부풀림 범위를 보고 보정 여부 결정(자동 보정 안 함).
  - Dependabot alerts가 저장소에서 꺼져 있음. 이전 이관(APK 스모크, 운영 Postgres 버전, APK Variables).
- **B2 2단계**: 달러 예수금을 present-balance TR로 조회(공식 문서로 TR 확정, 실조회 후). 그 전까지 KIS 달러 예수금은 수동 값이 유지되고 자동 갱신되지 않는다. 또 국내 전용 KIS 계좌도 "해외 없음"으로 캐싱되지 않아 동기화마다 해외 조회 3회가 나간다.
- 암호화 키 회전, 월간 잡 보충 실행, PG 실DB 통합 테스트, 데이터 보존 잡, FK 인덱스 12개(공유 Supabase 마이그레이션 필요).
- 체결 직후 옛 스냅샷으로 재생성(동기화 신선도 게이트), TWO_PHASE 시장가 현금 부족, KIS 실현손익 10페이지 잘림, 실행 이력 페이지네이션, 환율 fallback의 동기화·표시 경로, 차트 대체 텍스트.
- **미감사**: `dca_service`, `tax_action_service`, `pension_contribution_service`, `tactical_apply`, goal 계열.
- 그대로 두는 것: 프론트 메이저, yfinance 1.x·pandas 3, 총자산 엔진 2벌, 500줄대 파일.

### 부채 아님으로 확인

- `http_client.py` `verify=False`: KIS 모의투자 전용.
- `assert` 3곳: 타입 좁히기.
- ruff `BLE001` 118건·`PLR0913` 129건: 코드베이스 스타일. 일괄 수정 가치 없음.
