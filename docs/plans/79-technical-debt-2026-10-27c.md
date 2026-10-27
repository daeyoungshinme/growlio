# 79. 계획 78 이관분 처리 (2026-10-27c)

## Context

계획 78(PR #162)은 main에 병합됐다. 이 계획은 78 "이관" 목록에 남은 항목을 코드와 대조해 처리한다. 사용자가 함께 고른 항목도 포함한다: 74 수동 실행 국내 대체, 67 모바일 코드 수정분, 65 B4·66 P3 성능, 중복 인덱스.

브랜치 `fix/tech-debt-2026-10-27c`, 배치별 커밋.

상태: **A·B·C·D·E·F·H 완료, G는 일부 완료(아래), I 이관**.

## 배치 A — 백엔드 저위험 정리 (62 F 잔여·D11)

- **A1**: `api/v1/tactical.py`의 인라인 스키마 2개를 `schemas/tactical.py`로 옮겼다. 비중표 validator는 전술 서비스를 지연 import한다. 스키마 모듈이 기술지표·시세 조회까지 끌고 오지 않게 하기 위해서다.
- **A2**: `_fred_get_observations`·`_parse_fred_obs`를 공개 이름 `fred_get_observations`·`parse_fred_obs`로 바꿨다. 외부 import 10곳과 테스트 patch 경로도 함께 고쳤다.
- **A3**: 백테스트 FRED 조회에 `fred_circuit.is_available()` 사전 확인을 넣었다. 서킷이 열려 있으면 빈 시리즈를 돌려준다. 호출부의 기존 폴백(매크로 없이 계산하고 안내 문구를 붙임)을 그대로 탄다.
- **A4**: ORM `getattr(…, default)` 23건을 직접 접근으로 바꿨다. 대상은 `alert_check`·`plan_generation`·`rebalancing_alerts`다.
  - 기본값이 실제로 쓰인 곳은 테스트의 SimpleNamespace 픽스처뿐이었다. 그래서 픽스처에 모델 기본값을 채웠다.
  - `email_templates/rebalancing.py`는 대상이 덕타이핑 목록이라 제외했다.

## 배치 B — 게이트 차단 알림 통합 (62 D8)

- 세금영향·시장신호·하루한도 보류 알림 3종이 공통 `_notify_gate_blocked` → `dispatch_dual_channel_alert`를 쓴다. 헬퍼에는 `push_data` 인자를 추가했다(`portfolio_id` 전달용).
- **동작 변경**: 이메일과 푸시가 모두 실패하면 이력과 dedup을 남기지 않는다. 다음 평가에서 다시 시도한다. 다른 알림과 같은 규칙이다. dedup은 `after_sent`로 같은 커밋에 기록한다.
- 회귀 테스트 `test_gate_blocked_notifications.py` 6건을 추가했다. 수정 전 코드에서 실패하는 것을 확인했다.

## 배치 C — 매수 예산 공통화 (62 E2)

- `_order_quantity_guard.fit_buy_to_budget()`를 만들었다. FULL clamp와 TWO_PHASE `_execute_buys_within_budget`가 같은 단건 계산을 쓴다.
- 예산 차감 시점은 두 경로가 다르다. FULL은 계획 금액으로, TWO_PHASE는 체결에 성공한 금액으로 뺀다. 이 차이는 각 호출부에 그대로 남겼다.
- 남은 수량 행은 `model_copy`로 만든다. SKIPPED 결과는 `budget_skipped_result`로 만든다.
- `_execute_buys_within_budget` 직접 테스트 4건을 추가했다. 전에는 직접 테스트가 없었다.

## 배치 D — 대형 함수·컴포넌트 분해 (62 E5, 동작 불변)

- **D1**: `build_pending_plan_for_alert`(131줄)를 단계 함수 3개로 나눴다. `_drifting_items_for_alert`, `_check_tax_gate`, `_check_daily_value_cap`이다.
- **D2**: `TacticalAllocationTab` 685줄을 295줄로 줄였다. 표시 조각은 `TacticalStatusParts.tsx`, 확인창은 `TacticalApplyConfirmModal.tsx`로 옮겼다.
  - 계획에 있던 `useTacticalApplyState` 훅은 만들지 않았다. 상태 2개와 파생값뿐이라 훅으로 빼도 얻는 게 없었다.
- **D3**: `RebalancingOrderTable`
  - 4번 반복되던 행 계산을 `rowModel` 하나로 합쳤다.
  - 데스크톱 매도·매수 행을 `DesktopOrderRow` 하나로 합쳤다.
  - 행 조각은 `RebalancingOrderRows.tsx`로 옮겼다.
  - 행 모델은 훅 콜백에 의존한다. 그래서 `rebalancingTradeMath`로 빼지 않고 컴포넌트 안에 뒀다.

## 배치 E — 74 수동 실행 국내 대체 자동 전환

- `rebalancingTradeMath.buyItemForAccount()`는 백엔드 `_buy_target`/`allocate_group_trades`와 같은 규칙을 쓴다. 매수 계좌가 ISA·연금저축·IRP이면 해외 대표 종목 대신 그룹 차액만큼 국내 대체 종목을 산다.
  - 대체 종목이 없거나, 시세가 없거나, 1주도 못 사면 원래 행을 그대로 쓴다.
- 실행 훅의 매수 행과 초기 선택 키가 계좌 세제유형을 반영한다. 대체 후보 시세(`domesticAltCandidates`)도 함께 조회한다. 주문표에는 "국내 대체 (원래 VOO)"를 표시한다.
- **한계**: 같은 종목을 여러 계좌로 나눠 사는 중이면 전환하지 않는다. 배분 수량 단위가 섞이기 때문이다.
- 회귀 테스트: 훅 테스트(ISA면 대체 종목 주문)는 수정 전 코드에서 실패하는 것을 확인했다. 단위 테스트 5건도 추가했다.

## 배치 F — 67 모바일 코드 수정분

- `AppLayout`:
  - `h-screen h-dvh`로 바꿨다. dvh 미지원 WebView에서는 h-screen이 남는다.
  - 상단에 `env(safe-area-inset-top)` 여백을 넣었다. 당겨서 새로고침 인디케이터와 `TopLoadingBar`도 상태바 아래로 옮겼다.
- viewport에 `interactive-widget=resizes-content`를 넣었다.
- `useModalBehavior`가 body와 함께 실제 스크롤 요소인 `<main>`도 잠근다. `<main>`이 없으면 body만 잠근다. 테스트를 추가했다.
- `TransactionHistoryTab` 모바일 카드의 70vh 중첩 스크롤을 50건 단위 "더 보기"로 바꿨다. `TransactionList`와 같은 패턴이다.
- **실기기 확인(사용자)**: Android 상태바 겹침, 키보드가 모달 하단 버튼을 가리는지, 뒤로가기(확인창만 닫히는지)를 직접 봐야 한다.

## 배치 G — 성능 (65 B4·66 P3) — 계획 변경

- **발견(실버그 가능성)**: yfinance 0.2.66 `download()`는 호출마다 전역 `shared._DFS`를 비우고 결과를 모은다.
  - 앱의 배치 다운로드 5곳은 시세 배치 2곳, 일별수익률, 종가 시계열, 백테스트다. 이들이 executor에서 동시에 돌 수 있다(공용 세마포어 5칸).
  - 겹치면 한쪽이 다른 쪽 결과를 지워 종목이 조용히 빠질 수 있었다.
  - 이제 전부 `yahoo_price.yf_download`(프로세스 락)를 거쳐 직렬화된다. 동시 호출이 겹치지 않는다는 테스트를 추가했다.
- **65 B4(청크 병렬 다운로드)는 하지 않는다.** 위 경쟁 때문에 병렬 `yf.download`는 안전하지 않다. 대안으로 종목별 `Ticker.history` 병렬화가 있지만, 실측(66 계측 로그)부터 해야 한다.
- **66 P3(정기 sync 뒤 예열)는 하지 않는다.** 캐시가 프로세스 메모리(`cache_store`)에 있기 때문이다.
  - Render 무료 플랜이 잠들면 18:00 sync 뒤 채운 캐시도 사라진다.
  - 잠든 동안에는 스케줄러 자체가 멈춘다.
  - 외부 핑이나 유료 플랜으로 상시 기동이 되면 다시 검토한다.
- **영향**: 직렬화로 동시 콜드 계산(기간별 추천 조합 등)이 더 느려질 수 있다. 배포 후 `goal_recommendation_timing`을 확인한다.

## 배치 H — 중복 인덱스 제거

- 마이그레이션 `pm1_drop_dup_portfolio_item_members_index`(down_revision `at1`)로 `idx_portfolio_item_members_item`을 삭제한다. 이 인덱스는 `uq_portfolio_item_members_key`의 선두 열과 겹친다. downgrade는 인덱스를 다시 만든다.
- 로컬 `.env`가 공유 Supabase를 가리키고 Docker DB는 꺼져 있어, DB에는 적용하지 않았다. 대신 `alembic heads`(pm1 단일)와 `--sql` 오프라인 upgrade/downgrade 출력으로 검증했다. 운영 적용은 Render `preDeployCommand`가 한다.

## 배치 I — `untracked_holdings` 백엔드 필드 제거 — 이관

- 조건은 Android APK가 #162 이후 빌드로 재배포되는 것이다. 그런데 #162 이후 태그나 APK 빌드가 없다(마지막 빌드는 2026-05 실패). 구버전 번들은 필드가 없으면 `.forEach`에서 크래시가 나므로 유지한다.

## 이관 (이번 범위 밖)

- `untracked_holdings` 백엔드 필드 제거(APK 재배포 뒤).
- 65 B4 대안(종목별 `Ticker.history` 병렬)과 66 P3: 실측 또는 상시 기동 뒤.
- 67 바텀시트·InfoTip, 실기기 확인.
- 동일 티커 다시장 가격 키 충돌: KR 코드와 US 티커는 형식이 달라 실제로 충돌하지 않는다(잠재 위험).
- 62 D11 나머지 `getattr` 기본값(덕타이핑 대상 제외), 100줄 넘는 함수 6개.
- 메이저 업그레이드(react 19·recharts 3·tailwind 4·TS 7·plugin-react 6).

## 검증

- 백엔드: ruff·format·mypy 클린, `pytest --cov` 3047 passed, 91.79%.
- 프론트: tsc·eslint(`--max-warnings 0`)·prettier 클린, `vitest --coverage` 1833 passed(임계값 통과).
- 마이그레이션: `alembic heads` = `pm1_drop_dup_portfolio_item_members_index` 단일.

## 배포 전후 확인

- **78 이월(필수)**: 11-02(월) 09:00 KST 전에 공유 Supabase `alembic current`를 확인한다. #162 배포 뒤에는 `at1`, 이 브랜치 배포 뒤에는 `pm1`이어야 한다.
- G 배포 뒤: `goal_recommendation_timing`과 시세 배치 지연이 크게 늘지 않았는지 본다.
- B 배포 뒤: 게이트 보류 알림이 하루 1회 수준인지 본다(두 채널 실패 시에만 재시도).
