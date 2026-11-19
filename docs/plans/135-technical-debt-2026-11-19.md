# 135. 133·134·Dependabot(#281~283) 이후 기술부채 (2026-11-19)

계획 132 이후 변경(133 수기 달러 예수금 이중 합산, 134 환율 표시 불일치, Dependabot 3건)의 첫 감사.

## 점검 결과 — 문제 없음

- Dependabot #281(TruffleHog)·#282(Capacitor 8.6.2 등)·#283(fastapi·sentry-sdk 등): main CI 녹색. Capacitor 8.6.2는 PR #282에서 `android` assembleDebug가 실제로 빌드됨.

## A. 실버그·데이터

- **A1 환율 실패 토스트 5분마다 반복 (134 회귀)** — 134가 `exchangeRateQuery`에 `refetchInterval`(5분)을 넣으면서, 서버가 잠들거나 장애일 때 React Query v5가 실패마다 새 `error`를 만들어 `ExchangeRateContext`의 실패 토스트가 5분마다 다시 떴다(이전 환율은 그대로 표시 중). → 보여 줄 환율이 없을 때만, 연속 실패 중 한 번만 띄운다(성공하면 리셋). 테스트 `ExchangeRateContext.test.tsx` 2건(수정 전 코드에서 실패 확인).
- **A2 133 기간 일별 스냅샷 과다분 보정** — `backend/scripts/fix_manual_usd_double_count_133.py`. 2026-11-02~11-15의 MANUAL 계좌(달러 예수금 > 0) `source=MANUAL` 스냅샷을 후보로, `deposit_usd × 1300`을 뺀 값을 보여 준다(기본 dry-run). 과거 `deposit_usd` 이력이 없어 현재 값으로 계산하므로, 기간 밖 가장 가까운 스냅샷과 비교한 `check` 열(`OK`/`ALREADY_OK?`/`NO_NEIGHBOR`)을 보고 고른 id만 `--apply --ids`로 보정한다. 그날 마지막 쓰기가 종목 저장·현재가 동기화(정상 합계)였던 행은 `ALREADY_OK?`로 걸러진다. 서버 캐시는 프로세스 로컬이라 스크립트가 못 지운다 — TTL 또는 계좌 동기화로 반영. 실 DB 테스트 `test_real_db_upserts.py::TestManualUsdDoubleCountFix`(CI).

## B. 구조 부채 (133 근본)

- **B1** 133 수정은 `account.data_source != MANUAL`로 막아 provider 계약이 아니라 출처에 기대고 있었다(합계에 달러를 넣고 `deposit_foreign`을 비우는 새 provider면 재발). → `BalanceResult.usd_deposit_in_total`(합계에 `deposit_usd` 환산분이 이미 포함) 플래그를 두고 `ManualProvider`가 True. `asset_service` 보정은 이 플래그로 판정. 또 `ManualProvider`가 실제 쓴 환율을 `usd_krw_rate`에 넣어 fallback 1300 기본값이 남지 않게 했다(스냅샷 `usd_krw_rate`도 실환율이면 기록됨).

## C. 134 표시 드리프트 잔여

- **C1** `fmtFxRate` 미적용 4곳 — `BankAccountModal`·`StockDepositFields`(2곳)의 `toLocaleString()`(소수 3자리까지), `StockPositionsModal`의 정수 표기.

## D. 정리

- `docs/remaining-tasks.md` 갱신(A2 운영 실행을 P1에).
- 병합된 브랜치 7개(로컬·origin) 삭제는 사용자 실행:
  `git branch -d docs/remaining-tasks-2026-11-14 fix/a11y-labels-2026-11-14 fix/fx-rate-display-mismatch-134 fix/manual-usd-deposit-double-count-133 fix/pin-dateutil-holidays-2026-11-14 fix/tech-debt-132-2026-11-15 refactor/split-large-files-2026-11-14`
  후 같은 이름으로 `git push origin --delete ...`.

## 의도적으로 하지 않는 것

- `syncSharedUsdRate`가 더 새로 받은 fallback 값을 덮지 않는 엣지 — fallback 토스트·`null` 처리가 있고 다음 5분 재조회로 해소.

## 상태

코드 완료. A2 운영 실행(dry-run 검토 → `--apply --ids`)은 사용자 확인 대기.
