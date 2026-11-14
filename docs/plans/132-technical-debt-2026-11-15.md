# 계획 132 — 기술부채 (2026-11-15)

## Context

`docs/remaining-tasks.md`의 P1~P4는 모두 사용자 확인·외부 트리거·결정 대기라 지금 코드로 할 수 있는 것이 없었다. 그래서 그 뒤에 들어온 코드(계획 129 수정, 130 파일 분할, 131 label, Dependabot 병합)를 백엔드·프론트·인프라로 나눠 다시 감사했다. 실버그 3건은 모두 129와 키움 원화주문(#266)에서 생긴 회귀다.

## 처리

### A. 실버그 (백엔드)

| # | 문제 | 수정 |
|---|---|---|
| A1 | 환전 계획이 원화주문 계좌의 정액 해외 몫은 필요 달러에서 빼면서, 그 계좌의 `deposit_usd`는 보유 달러로 상쇄했다. 원화주문 계좌 $500 + 일반 계좌 정액이면 필요 달러가 $500 적게 나와, 일반 계좌 매수가 `WAITING_FX`에 들어간다(그 달러는 원화주문 계좌 자신의 매수가 먼저 쓴다) | 정액 경로에서 원화주문 계좌를 보유 달러 합계·계좌별 내역·기준 시각에서 뺀다. `WAITING_FX` 상쇄는 실행 계좌 기준이라 그대로 |
| A2 | `UsdLedger`가 판정 통과 즉시 그 leg 몫을 더했다. 이후 재잠금 실패나 주문 전부 실패로 빠진 leg 몫이 남아, 같은 계좌의 다음 leg가 거짓 환전 대기 + "달러 환전 필요" 메일·푸시를 받았다 | 판정 통과는 가예약(`hold`), 주문이 나갔거나(leg가 FAILED가 아님) 환전 대기에서 재개됐을 때만 `confirm`. 달러를 확인하지 않은 leg는 확정하지 않는다(앞 leg의 남은 가예약을 대신 확정하지 않게) |
| A3 | 원화주문 계좌에 실환율이 없으면 사전 부족 판정 전체를 건너뛰어, 국내 몫 원화 부족도 알리지 않았다 | 해외 몫의 원화 환산만 건너뛰고 원화 부족은 판정 |

### B. 회귀·안정성 (백엔드)

- **B1** `test_fx_extra_needs._sync_need`가 계획 130 분할 뒤에도 `fx_plan_service.today_kst`를 patch해 무효였다 — 고정 `due=TODAY+30`이 지나는 2026-12-12부터 실패할 테스트였다. `fx_plan_alerts.today_kst`로 고쳤다. 다른 patch 대상은 감사에서 모두 유효함을 확인했다.
- **B2** `lock_user_for_quota`의 `FOR UPDATE`는 users를 참조하는 INSERT가 잡는 `FOR KEY SHARE`(FK 확인)까지 막는다. 알림 발동 잡(알림 UPDATE → 이력 INSERT)과 `sync_fx_plan_alerts`(사용자 잠금 → 알림 DELETE)가 역순으로 기다리는 교착이 가능했다. `FOR NO KEY UPDATE`(`key_share=True`)로 — 상한 판정끼리는 여전히 직렬화된다. 실 Postgres 동시성 재현은 하지 않았다(락 규칙으로 판단).
- **B3** `sync_fx_plan_alerts`가 기존 알림을 읽고 분류한 뒤에 잠갔다. 인스턴스가 둘이면(`inproc_lock`은 단일 프로세스) 같은 목표를 둘 다 만들 수 있어 잠금을 조회 앞으로 옮겼다.
- **B4** 계좌 수정으로 `deposit_usd`가 바뀌어도 `deposit_usd_synced_at`이 옛 동기화 시각으로 남았다. 값이 바뀌면 그 시각으로 찍는다.

### C. CI·의존성

- **C1** `ci.yml` setup-uv가 0.13.7로 Dockerfile(0.13.8, Dependabot #272)과 어긋나 있었다. 0.13.8로 맞추고, Dependabot은 Dockerfile만 올리므로 둘이 다르면 실패하는 step을 추가했다(`# uv-version` 주석이 붙은 줄을 읽는다).
- **C2** `undici` override(`^7.30.1`)가 jsdom 31의 요구(`^8.12.3`)보다 낮은 메이저를 강제하고 있었다 → 제거(8.12.4). `form-data`·`tar`·`@babel/core` override도 빼도 해석 버전이 같고 `npm audit` 결과(14건, CI 기준 high 0)가 같아 제거했다. `@typescript-eslint/parser` 선언 범위를 lock(8.72.2)에 맞췄다.
- **C3** setup-java SHA는 v6.2.0인데 주석이 `# v5`였다. checkout(v6.1.0)·cache(v5.1.0)·upload-artifact(v7.0.2) 주석도 정확한 버전으로 맞췄다.

### D. 프론트

- **D1** 실행 계좌 label(`AlertAutoModeSection`·`AlertQuickDcaSection`)이 계좌 0·1개나 계좌별 설정일 때 렌더되지 않는 select를 가리켰다. select가 있을 때만 label, 아니면 `<p>`.
- **D2** `a11y.labels.test.ts`에 `htmlFor`·`aria-labelledby` 값이 같은 파일의 `id`로 쓰이는지 대조를 추가했다(조건식은 갈래별, `undefined` 갈래 제외). self-closing `<label/>`도 실패로 본다. 렌더 조건까지는 못 본다 — D1 같은 경우는 여전히 사람이 봐야 한다.
- **D3** `QUERY_KEYS.rebalancingPlans`를 이력 탭과 적립 배너가 각자 queryFn·staleTime으로 정의하던 것을 `api/queryOptions.ts`의 `rebalancingPlansQuery`로 모았다.
- **D4** `FxPlanCard` 기본 탭을 `FX_PLAN_DEFAULT_MONTHS`에서 파생 — 주석으로만 맞추던 값.
- **D5** 미사용 `FxExtraNeedForm` 타입 제거. `foldIntoPortfolioGroups`는 백엔드 짝 함수로 문서에 올라 있어 export를 유지했다.

### E. 문서

- `docs/plans/README.md` 123행의 "fx2·fx3 수동 적용 필요"를 적용됨으로(체인 fx3→kw1→du1, kw1·du1 적용 확인).
- `docs/remaining-tasks.md` P1에 "예수금이 주문 직후 바로 줄면 같은 실행 내 ledger도 이중 차감"을 추가.
- `frontend/CLAUDE.md` 입력 스타일 목록에 `FORM_INPUT_SM`, 공용 쿼리 목록에 rebalancing-plans.

## 의도적으로 남긴 것

- `ExchangeRateAlertSection`은 `useAlertCrud`에 key·queryFn을 따로 넘긴다. `exchangeRateAlertsQuery`와 값이 같고, 바꾸려면 `useAlertCrud` 시그니처를 바꿔야 해 범위 밖.
- 입력 클래스 문자열 인라인 12곳, `TransactionForm`/`TransactionModal`·`TickerSearchField`/`TransactionTickerField` 이중 구현, 단일 화면 inline queryKey 약 40곳 — 동작 문제 없음, 정리 규모가 커서 범위 밖.
- `DcaSettingsSummaryCard`의 "더보기" 상태가 탭 전환 때 초기화(130 분할로 생긴 차이) — 모바일 보조 표시라 수용.
- 원화주문 계좌의 사전 부족 알림(동기화 `deposit_krw`, 버퍼 없음)과 실행 판정(`orderable_krw`, `FX_FEE_BUFFER` 0.3%)의 임계값 차이 — 경계에서 알림 없이 환전 대기가 될 수 있으나 차이가 작고, 원천(동기화 vs 실시간) 차이는 본질적이다.
- `.python-version`·`.nvmrc` 없음 — 버전은 pyproject·engines·CI가 일치.

## 검증

- 백엔드: `ruff check`·`ruff format --check`·`mypy app/`·`pytest`(커버리지 게이트 포함)
- 프론트: `typecheck`·`lint --max-warnings 0`·`format:check`·`vitest run`(201파일 2138건)
- CI uv 비교 step은 로컬 bash로 일치/추출을 확인. 마이그레이션 없음.
