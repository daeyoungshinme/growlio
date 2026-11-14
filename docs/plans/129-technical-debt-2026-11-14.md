# 계획 129 — 기술부채: PR #266(키움 원화주문) 첫 감사 + 128 이관 (2026-11-14)

## Context

사용자 요청: "남은 기술부채 있으면 수정 계획". 마지막 감사(계획 128, 2026-11-13) 뒤 PR #266(키움 원화주문 계좌, `d8260cde`)이 감사 없이 들어왔다. 128 "이관" 12건은 재검증 결과 전부 남아 있었다.

#266에서 깨끗했던 것(재조사 금지): 계좌 수정 무효화(`invalidateAccountData`가 `fxPlanBase` 포함), 키움 외 계좌로 플래그가 넘어가도 `uses_krw_overseas_order`가 asset_type으로 거름, kw1(기본값 false — 옛 코드 호환), 실환율 없을 때 매수여력 None.

## 배치 A — 원화주문 계좌를 아직 "달러 계좌"로 보던 곳 (완료)

#266은 실행 직전 판정과 환전 계획 필요 달러만 바꿨다. 같은 정액 적립을 다루는 나머지 경로가 옛 가정 그대로였다.

- **A1 적립 사전 부족 알림**(`dca_cash_shortfall_service._fixed_amount_shortfall`): 원화주문 계좌에도 "해외 몫 $X 환전 필요"를 보냈고, 원화는 국내 몫만 비교해 해외 몫까지 원화로 나가는 계좌의 원화 부족을 놓쳤다. → 달러 비교를 하지 않고 `max(0, 해외 몫 − 보유 달러) × 실환율 × KRW_ORDER_FX_MARGIN`을 원화 필요액에 더한다(달러 먼저, 실환율 없으면 판정 보류). `KRW_ORDER_FX_MARGIN`은 `constants`로 옮겨 실행 판정과 공유.
- **A2 환전 계획 WAITING_FX 상쇄**(`fx_plan_service._waiting_fx_required_usd`): 원화주문 계좌 leg가 대기 중이면 원화까지 모자란 것인데 "지금" 달러 환전 구간에 넣었다 → 그 계좌 leg는 뺀다.
- **A3 환전 대기 안내**(`plan_notifications.notify_dca_fx_required`·메일 템플릿·`action_items_service._fx_waiting_items`): `available_usd`가 원화 환산분을 포함하는데 "보유 달러"로 표시하고 환전을 안내했다 → 원화주문 계좌는 "원화 예수금 부족 / 매수여력(원화 환산 포함)"과 원화 입금 안내.

## 배치 B — 128 이관 정합성 항목 (완료)

- **B1 같은 계좌 두 leg의 달러 이중 통과**: 매수 잡·환전 대기 재확인이 leg마다 계좌 전체 여력과 비교해, 두 포트폴리오의 정액 leg가 같은 계좌면 둘 다 통과하고 두 번째가 증권사 거부로 FAILED가 됐다. → `check_usd_shortfall(..., ledger)`: 한 잡 실행 안에서 계좌별로 통과시킨 필요 달러(`UsdLedger`)를 다음 leg 판정에서 뺀다. 두 번째 leg는 WAITING_FX로 남는다. **실행 간에는 빼지 않는다** — 증권사 예수금이 방금 낸 주문을 언제 반영하는지 몰라 이중 차감으로 거짓 대기를 만들 수 있다(남은 공백: 서로 다른 분에 실행되는 leg).
- **B2 달러 기준 시각**: 해외 조회 실패로 `deposit_usd`를 유지한 동기화도 `last_synced_at`을 갱신해 환전 계획이 stale 달러를 "방금"으로 보였다. → `asset_accounts.deposit_usd_synced_at`(확정될 때만 갱신), 환전 계획이 그 값을 쓴다. 마이그레이션 **du1**(기존 행은 `last_synced_at`으로 채움).
- **B3 생성 상한 경합**: 환율·주가 알림 생성, 추가 환전 항목, 환전 계획 알림 맞추기가 "개수 세기 → 비교 → insert"라 동시 요청이 상한을 넘을 수 있었다. → `utils/quota_lock.lock_user_for_quota`가 세기 전에 users 행을 `FOR UPDATE`.
- **B4**: fx3 FK 인덱스 `idx_fx_extra_needs_reserved_account`(du1), `EXTRACT(year)` 5곳 → 날짜 범위(배당 집계 3·배당 연도별·연간 순입금, 실 DB 테스트에 배당 연 경계 추가), 전술 틸트 캐시 키에 마지막으로 끝난 미국 거래일(v2).
- **B5**: PWA precache에서 `icon-16/32/48.png` 제외(빌드로 확인), `docs/mobile-ux-audit-2026-07.md` → `docs/plans/`.

## 배치 C — 백엔드 메이저 상한 7개 (할 일 없음)

cryptography·structlog·tenacity·firebase-admin·pytest-httpx·mypy·websockets 모두 PyPI 최신이 상한 아래(다음 메이저 미출시, 2026-11-14 확인). 지금 상한을 여는 건 검증할 대상이 없어 하지 않았다. 다음 메이저가 나오면 Dependabot PR 또는 계획 85·86 절차로.

## 이관

- 550줄↑ 백엔드 11·500줄↑ 프론트 4 파일 분할, drift N+1(의도적 순차), 해외 주가 알림 `target_price_usd`(저장 단위 = 제품 결정)
- B1의 실행 간 차감 — 키움·KIS 실계좌에서 주문 직후 달러 예수금이 줄어드는지 확인되면 PENDING·최근 실행 leg의 `required_usd`로 확장
- 사용자 작업:
  - **kw1·du1 공유 Supabase 적용 후 배포**(둘 다 컬럼·인덱스 추가라 옛 코드 호환)
  - 키움 REST 주문이 원화주문 설정을 따르는지 실계좌 1회
  - 병합 브랜치 삭제, 외부 핑 등록 후 `keep-alive.yml` 제거, 2027 수능일 `_KRX_CSAT_DAYS` 추가

## 검증

- 백엔드: ruff·format·mypy 0건, pytest 3975 passed / 6 skipped(실 DB — CI에서 실행)
- 프론트: `vite.config.ts`만 변경 — prettier 통과, `npm run build`로 precache 167건에 16/32/48 아이콘 없음 확인
- 마이그레이션 du1: 로컬 `.env`가 공유 Supabase를 가리키고 Docker가 없어 로컬 `alembic upgrade`는 하지 않았다 — CI의 실 DB 마이그레이션 재적용 검증에 맡긴다
