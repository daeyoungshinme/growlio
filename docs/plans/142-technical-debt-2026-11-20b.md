# 142. 기술부채 — 141 첫 감사 (2026-11-20)

`docs/remaining-tasks.md`의 이관 항목은 모두 실계좌·실기기·운영 확인이나 사용자 결정을 기다린다(코드로 처리할 항목 없음).
열린 PR 0건, main CI 성공, TODO 0건, 백엔드 pip-audit 0건이라 범위는 아직 감사하지 않은 141(PR #290) 신규 코드와 의존성 점검이다. 마이그레이션 없음.

## A. 실버그

### A1. 141 A1(해외 매도 대금 가산)이 AUTO 플랜 매수 leg에 닿지 않음 (141 회귀)

- 141은 `_execute_kiwoom_account_orders`가 **같은 실행**의 매도 결과만 `pending_sell_usd`로 넘긴다.
  AUTO 2단계 플랜은 매도 leg(이메일 승인)와 매수 leg(대기 후 자동)가 **각각 별도의 `execute_rebalancing` 호출**이라,
  매수 leg 실행 땐 매도 대금이 0 → 결제 전이면 일반 계좌 해외 매수가 거짓 SKIPPED → 전부 SKIPPED면 leg FAILED.
  141이 고쳤다고 적은 "AUTO leg FAILED"가 그대로 남아 있었다. 매도와 매수를 나눠 실행하는 수동 경로도 같다.
- 수정: `market_hours.last_us_session_close_datetime()`(직전 정규장 마감, 조기 폐장 반영) 이후 같은 사용자·계좌의
  이전 실행 결과 중 접수 성공 해외 매도(취소된 주문·가격 모름 제외)의 `수량 × 가격`을 `_prior_overseas_sell_proceeds_usd`로 읽어
  이번 실행 매도 대금과 더한다. 이번 실행 결과는 아직 저장 전이라 겹치지 않는다. 해외 매수가 있을 때만 조회하고,
  조회 실패는 Sentry에 남기고 0(141 동작)으로 후퇴한다.
- 141 A1과 같은 전제(키움 `fc_entra`에 결제 전 매도 대금이 없음)에 기대므로 실계좌 확인 결과가 반대면 둘을 함께 뺀다.

## B. 정리

- B1. 프론트 개발 의존성 npm audit moderate 10건(운영 의존성은 0건) → 0건.
  `@typescript-eslint/*` 8.72.2 → 8.73.0(minimatch 11), `npm audit fix`로 lock 범위 안 갱신(rimraf → glob 14),
  `workbox-build`의 `glob@^11`은 `overrides`로 `^14.0.3` — workbox는 `globSync`만 쓰고, 빌드 precache 169개가 전후 동일.
  npm이 제안한 `vite-plugin-pwa` 1.1.0은 다운그레이드라 쓰지 않았다. workbox-build가 glob 14 이상을 요구하면 override를 지운다.
- B2. 로컬 `node_modules`가 lock과 어긋나 있었음(Dependabot 머지분) — `npm ci`로 맞춤. 코드 변경 없음.
- B3. 머지된 브랜치(로컬·원격 `feat/rebalancing-timing-diagnosis-136`·`feat/diagnosis-tab-review-137`·`fix/tech-debt-138-2026-11-19`·
  `fix/tax-planner-recommendation-139`·`feat/kiwoom-fx-deposit-order-140`·`fix/tech-debt-141`, 로컬 `fix/tech-debt-135-2026-11-19`) — 삭제는 사용자.

## 남은 일 / 사용자 확인

- 키움 해외 매도 직후 `fc_entra` 반영 여부 실계좌 1회(`remaining-tasks` P1, 141 A1 줄에 병기).
