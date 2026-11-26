# 152. 기술부채 — 147~151 첫 감사 (2026-11-26)

상태: 배치 A 구현(A8 보류·A10 확인 대기), 배치 B 구현(B5 시간대·B7 보류), 배치 C 구현. PR #324(A) → #325(B) → #326(C) 순서로 머지.

## Context
마지막 기술부채 감사(146, 2026-11-22) 이후 낙폭 추매(147·148·#312·#313), 환전 탭(149), 메뉴 재점검(150), 속도 개선(151 배치 0·A·B), recharts 3 업그레이드가 머지됐지만 감사는 아직 없다.
현재 상태: ruff·mypy·tsc·eslint 통과, pip-audit·npm audit 0건, TODO 0건, 열린 PR·미병합 브랜치 없음. 그래서 이번 범위는 위 신규 코드에서 나온 실버그·회귀다.
주의: 로컬 `frontend/node_modules`가 아직 recharts **2.15.4**다(package.json은 3.11). 로컬 typecheck·vitest가 v3를 검증하지 않으므로 작업 시작 전에 `npm ci`부터 한다.

산출물: `docs/plans/152-technical-debt-2026-11-26.md`(이 내용을 다듬어 저장) + `docs/plans/README.md` 행 추가. PR은 배치 A→B→C 3개로 스택한다. ✔ 표시는 코드를 직접 읽어 확인한 항목이다.

---

## 배치 A — 낙폭 추매 실버그 (백엔드 위주, PR 1)

**A1 ✔ 한 번 알림한 구간은 사용자가 사지 않으면 영영 다시 알리지 않음**
- 위치: `backend/app/services/dip_buy_calculator.py` `should_reset`, `dip_buy_service.reset_if_recovered`
- 원인: 리셋 조건이 `completed`와 `cycle_base_krw`만 본다. 알림만 받은 사이클(`notified_tiers`만 있음)은 회복해도 리셋되지 않는다. 그래서 다음 하락에서 `new_due_tiers`가 그 구간을 계속 빼 버린다.
- 수정: `should_reset`에 `notified_tiers`를 인자로 추가하고 셋 중 하나라도 있으면 리셋한다. 호출부 2곳을 함께 고친다.
- 테스트: `test_should_reset`에 `notified_tiers`만 있는 경우를 추가한다. job 수준에서는 "알림 → 회복 → 재하락 시 재알림" 시나리오를 확인한다.

**A2 ✔ "지수가 회복해 이번엔 추매 안 함"(CANCELLED) 알림이 회복이 아닌 이유로도 발송됨**
- 위치: `backend/app/jobs/dca_dip_buy_notice.py:126-133`
- 원인: 사전 알림을 보냈고 당일 금액이 0이면 무조건 CANCELLED로 보낸다. 실제로는 "추매했어요"로 완료했거나, 여윳돈을 0으로 바꿨거나, 규칙을 껐을 때도 금액이 0이 된다.
- 수정: 활성 규칙 전부가 첫 구간 위로 회복했을 때만(DUE·DONE 구간이 없을 때만) CANCELLED를 보낸다. 그 외 이유로 0이면 조용히 넘어간다.
- 테스트: 완료 후 금액 0 → 발송 없음. 회복 → CANCELLED.

**A3 환율 캐시가 비면 수량·달러가가 약 10% 어긋남**
- 위치: `dip_buy_service.py:240-267` (`attach_etfs`)
- 원인: `fetch_prices_batch_krw`가 캐시 미스일 때 폴백 환율 1300으로 환산한다. 바로 뒤의 `get_live_or_cached_usd_krw`는 실시간 환율을 받아 `is_live=True`로 표시한다. 08:10 job은 캐시가 비어 있는 경우가 많다.
- 수정: 환율을 먼저 조회한 뒤 가격을 조회한다. 또는 `require_live_rate=True`로 호출한다. 같은 환율로 원화가와 달러가를 계산한다.
- 테스트: 기존 테스트는 두 함수를 따로 mock해서 이 어긋남을 못 잡는다. 환율 일관성 테스트를 추가한다.

**A4 "추매했어요" 이중 기록 → 여윳돈 이중 차감**
- 프론트: `DipBuyCard.tsx:403-412` — `isPending` 중 확인 버튼을 비활성화한다(`ConfirmModal`에 disabled를 전달하거나 가드를 둔다).
- 백엔드: `mark_completed`(`dip_buy_service.py:488-526`) — 규칙을 `with_for_update()`로 읽고, 이미 완료된 구간이면 아무것도 하지 않는다(멱등).
- 테스트: 같은 구간을 두 번 호출해도 차감은 1회.

**A5 비활성 사용자에게도 낙폭 추매 알림 발송**
- 위치: `dca_dip_buy_notice.py:82` — `User.is_active == True` 조인을 추가한다. 다른 알림 job과 같은 기준이다(`dca_cash_shortfall_service.py:277`).

**A6 구간 낙폭을 바꿔도 이전 기준의 완료·알림 기록이 남음**
- 위치: `dip_buy_service.py:465-468`
- 수정: 구간별 `drawdown_pct`가 바뀐 인덱스는 그 구간의 `completed`·`notified_tiers` 기록을 지운다. 금액만 바뀐 경우는 유지한다.

**A7 알림에 "0주" 표시**
- 위치: `dip_buy_service.py:250`, 알림 job `:176`, 메일 템플릿 `email_templates/rebalancing_blocked.py:278`
- 수정: `shares == 0`이면 "1주 미만(1주 약 N원)"으로 표시한다. 푸시도 금액만 표시한다.

**A8 조회 경로 안의 commit — 보류(구현 안 함)**
- 판단: action-items의 다른 소스는 조회만 하므로 이 commit에 섞일 다른 쓰기가 없다. 리셋을 미루면 홈 행이 옛 DONE 구간으로 계산된다. 새 쓰기 소스가 action-items에 생기면 그때 다시 본다.
- (원래 계획)
- 위치: `summarize_user`(`dip_buy_service.py:313-314`) — 홈 action-items(`action_items_service.py:252`)가 공유하는 세션을 commit한다.
- 수정: `summarize_user`는 리셋 여부만 반환하고 commit하지 않는다. commit은 `GET /invest/dip-buy`와 job이 각자 한다. action-items 경로는 commit하지 않는다(리셋은 다음 조회나 job이 반영).

**A9 소소한 정리**
- `invalidateTacticalData`(`frontend/src/utils/queryInvalidation.ts:234-253`)에 `dipBuy` 키를 추가한다. 전술 보류 안내가 최대 5분 동안 옛 상태로 남는 문제다.
- `DipBuyCard.tsx:101,132`의 배분 합계 %를 반올림해 표시한다(`99.99000000000001%` 방지).
- `plan_generation.py:388`의 docstring에서 dip_buy 언급을 삭제한다.

**A10 (조건부) db2 마이그레이션 데이터 이관**
- 먼저 운영 적용 여부를 확인한다. 메모리 기준으로는 "db2 수동 적용 대기"다.
- 미적용이면 `db2_dip_buy_user_level.py:71-92`를 고친다. 같은 지수의 여러 플랜에서 `completed`를 모두 합치고, `is_active`는 하나라도 켜져 있으면 켠다.
- 이미 적용됐으면 마이그레이션은 손대지 않고 README에 기록만 남긴다.

## 배치 B — 계획151 회귀 (PR 2)

**B1 ✔ 10분 가격 미스 캐시가 짧은 Yahoo·Naver 장애를 10분으로 늘림**
- 위치: `market_data/price_service.py:157`(현재가), `:274-278`(기간 수익률)
- 원인: 서킷이 열리면 `_run_guarded`가 `{}`를 돌려준다. 그러면 전 종목이 `TTL_PRICE_MISS=600`으로 미스 표시된다. 서킷은 120초 뒤에 닫힌다.
- 수정: 배치 전체가 빈 결과이거나 서킷이 열린 경우에는 미스를 기록하지 않는다. 같은 배치에서 다른 종목은 성공했는데 실패한 종목만 기록한다.
- 테스트: 전부 실패 → 미스 기록 없음. 일부 실패 → 실패 종목만 기록.

**B2 ✔ ISA 손익 수정이 세금 할 일 캐시(이제 15분)를 무효화하지 않음**
- 위치: `api/v1/assets.py` `update_isa_pnl_override` — `invalidate_tax_action_items_cache`를 호출한다. 캐시 없음이라고 잘못 적힌 주석도 고친다.

**B3 ✔ `/dashboard` 부가 필드 계산이 다른 호출부까지 무겁게 하고, 실패 결과가 15분 캐시됨**
- 위치: `portfolio/asset_aggregator.py:312-347` (`_home_extras`)
- 원인:
  - `get_dashboard_summary`를 `/challenges`·`/insights`·`/external`·목표 달성 job·월간 리포트 job도 부른다. 이들은 `stock_pnl`·`goal_expected_month`를 쓰지 않는데도 콜드에서 overview와 목표 계산을 돌린다. DB 오류도 이 경로를 통해 500으로 번진다.
  - extras가 실패해 None이 된 결과도 15분 동안 캐시된다.
- 수정:
  - 부가 필드는 `/dashboard` 엔드포인트에서만 붙인다(`get_home_dashboard`, 별도 캐시 `dashboard_home_extras_key` — 요약 키를 지우는 3곳에서 함께 삭제).
  - extras가 실패하면 짧은 TTL(예: 60초)로 캐시하거나 extras만 캐시하지 않는다.
  - `compute_goal_expected_month`(`dca_service.py:61-77`)는 가속 시나리오 계산을 건너뛰는 경로를 쓴다.
- 테스트: extras가 예외를 던져도 요약 캐시 TTL이 짧은지. `/challenges` 경로에서는 extras를 호출하지 않는지.

**B4 리밸런싱 내비 배지 개수가 1로 표시됨**
- 위치: `frontend/src/hooks/useNavBadges.ts:22-26` — drift-summary를 펼칠 때만 받게 바뀌면서, 그 전에는 `rebalance:all` 행 하나만 센다.
- 수정: 백엔드 action item의 묶음 행에 포트폴리오 수(`count`)를 싣고, 배지는 그 값을 쓴다. 이미 필드가 있으면 재사용한다.

**B5 챌린지 넛지 날짜 기준 — memo만 수정**
- 결과: 프론트는 기기 로컬 날짜를 KST로 보는 관례(`localToday`)라 시간대는 그대로 두고, 날짜를 memo 의존성에 넣어 자정을 넘겨도 배지가 갱신되게만 했다.
- 위치: `frontend/src/hooks/useChallengeNudge.ts:32-34`
- 수정: 기기 시간대 대신 KST 오늘 날짜를 쓴다. 기존 KST 날짜 유틸이 있으면 재사용한다. memo 의존성에 날짜를 넣는다.

**B6 persist 버전 갱신**
- `PERSIST_CACHE_BUSTER`(`constants/queryConfig.ts:11`)를 올린다. 새 필드를 읽기 시작했으니 문서 규칙대로 갱신한다.

**B7 (기존 문제) `/stocks/price`가 폴백 환율로 `price_krw` 반환 — 보류**
- 판단: `useRebalancingPrices`가 해외 `price_krw` null을 원화가 없는 것으로 다뤄 리밸런싱 수량 회귀 위험. 원래부터 있던 동작이라 이득보다 위험이 크다.
- 위치: `api/v1/stocks.py:136` — 실시간 환율이 아니면 `price_krw: None`을 반환한다. 프론트 소비처가 null을 처리하는지 확인한다.

## 배치 C — 프론트·recharts 3·문서 (PR 3)

**C1 `REBALANCING_STALE_SNAPSHOT_BLOCKED` 푸시 딥링크 없음** — 해결이 계좌 동기화라 자동화 설정 모달이 아니라 계좌관리(`assetManagementUrl()`)로 연다. 테스트 추가.

**C2 낙폭 추매 딥링크가 적립 분석 로딩·실패에 묶임** — `InvestPlanPage.tsx:212-310`에서 `#dip-buy` 카드를 `!dcaPending && !dcaFailed` 분기 밖으로 뺀다. 결과: 실패 화면 아래에도 같은 카드를 그린다. 로딩 중에는 위 내용 높이가 바뀌어 스크롤이 어긋나므로 `useScrollToAnchor`는 그대로 로딩 끝을 기다린다.

**C3 recharts 3: 배당 차트 빈 곳 클릭 시 1월 선택** — `MonthlyDividendChart.tsx:46-49`. `activeTooltipIndex == null`이면 무시한다.

**C4 recharts 3 기본값 변경 되돌리기**
- 모든 차트에 `accessibilityLayer={false}`를 준다(8개 파일). `role="img"` 래퍼 안에 포커스 가능한 svg가 중첩되는 문제다.
- `Legend`에 `itemSorter`를 지정해 v2의 렌더 순서를 유지한다(`AllocationHistoryChart`, `BacktestResultChart`).
- `ReferenceLine`은 v3 기본 z-index 0이라 영역(100)·막대(300) 아래 — 조정 불필요(recharts `DefaultZIndexes` 확인).
- 범례 정렬은 `utils/chart.legendOrder(keys)`(시리즈 순서) — `null`은 렌더마다 순서가 바뀔 수 있다는 문서 경고로 쓰지 않음.

**C5 문서·잔재 정리**
- `backend/CLAUDE.md:207`: `#fx-plan`·`FX_PLAN_ANCHOR` 설명을 `?tab=환전`으로 고친다.
- `PortfolioPage.tsx:106`의 고아 주석을 삭제한다.
- `types/index.ts`의 `stock_allocation` 필드 주석은 필드가 아직 전송·사용(`topStock`)되므로 유지.

---

## 제외
- 151 배치 C·D·B2: 151 계획서에서 이어서 진행하며, 운영 기준선 실측이 먼저다.
- 150 D("갱신" 라벨)·E4: 사용자 결정 대기.
- yfinance 세마포어 점유(factor·frontier): 151 배치 C의 종가 캐시 공유에서 다룬다.
- 부팅 프리페치가 `/login` 진입 때 건너뛰어지는 문제: 체감 영향이 작다.

## 검증
- 시작 전: `cd frontend && npm ci`(recharts 3 설치 확인: `npm ls recharts`).
- 배치별:
  - `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pytest`(최종은 커버리지 91% 게이트)
  - `D:\project\growlio\frontend`(대문자 경로)에서 `npm run lint -- --max-warnings 0 && npm run format:check && npm run typecheck && npm run test`
- 신규 테스트:
  - 낙폭 추매 리셋·CANCELLED 조건·환율 일관성·`mark_completed` 잠금·재호출 400 (`mark_completed`는 시세 조회를 잠그기 전에 한다)
  - 가격 미스 캐시 조건
  - ISA 무효화
  - dashboard extras TTL·호출 범위
  - 딥링크 case
  - 배당 차트 null 인덱스
- A10에 해당하면 `uv run alembic check`(로컬 DB)를 실행한다. 모델은 바꾸지 않으므로 그 외에는 마이그레이션이 없다.
- 차트(C4)는 `make dev`로 백테스트·자산 추이·배당 차트의 범례 순서·기준선·키보드 Tab 이동을 직접 확인한다.
