# 51. 기술부채 감사 (2026-10-10)

## 배경

직전 감사(계획 46, `c75acd1`) 이후 143개 파일이 바뀌었다. 계획 47~50(지수별 비중·비중 카드·기간별 매수·탭 재편·지금 할 일)과 nestlio 외부 API 강화가 들어왔고, 이 신규 코드는 아직 감사되지 않았다.

고전적 부채는 거의 남지 않았다. TODO 0, `# noqa` 0, 프로덕션 `any` 0, skip/xfail 0이다. 그래서 이번에는 신규 코드의 실버그·중복·문서 드리프트를 보고, 이관 항목은 재검증만 했다.

- 조사: 백엔드 신규 코드 / 프론트 신규 코드 / 이관 재검증 + 전역 스윕을 병렬로 진행했다. 실버그 후보는 모두 코드를 직접 읽어 확인한 뒤 수정했고, 수정 전 코드에서 테스트가 실패하는 것도 확인했다.
- 사용자 선택: 배치 A·B·C 전부. 종목별 배당월 override는 계속 이관한다.
- 브랜치: `fix/tech-debt-2026-10-10`(origin/main 기준)

## 배치 A — 실버그 (`35ca754`)

| # | 문제 | 수정 |
|---|---|---|
| A1 | **기간별 매수: 기간 밖 수기 기록이 추정 매수를 통째로 지움.** `manual_keys`를 [start, today] 전체 매매로 만들었지만, `lots_from_trades`는 기간 내 BUY만 lot을 만든다. 그래서 10월 추정 매수 + 11월 수기 매도만 있으면 10월 조회에서 종목이 사라졌다 | 추정 제외 기준을 `manual.keys()`(기간 내 수기 BUY lot이 있는 종목)로 바꿨다 |
| A2 | **기간별 매수: 수기 기록 market과 포지션 market 불일치.** 기록 market은 종목 검색(네이버 typeCode·Yahoo 거래소)에서 온다. 포지션 market은 브로커가 정한다(KIS·키움·토스 모두 국내는 코스닥도 `"KOSPI"`, 토스 해외는 `"US"`, Arca ETF는 NYSE/AMEX 혼재). 정확 일치로 매칭하니 코스닥 종목 기록은 **항상** 추정과 이중 집계되고 보유 0으로 잘렸다 | `_position_key_aligner`: ticker와 국내/해외 구분이 같으면 포지션 market으로 정렬한다. 뒤 스냅샷을 우선한다 |
| A3 | **`_merge_state` USD 평단 불일치.** 같은 스냅샷 안 동일 종목 행 중 한쪽에만 `avg_price_usd`가 있으면, 합산 수량에 한쪽 단가가 붙어 역산이 틀어졌다 | 이때는 `avg_price_usd=None`으로 두어 KRW 역산으로 폴백한다 |
| A3+ | (계획 이관분을 앞당김) `_load_series`가 가장 오래된 기준일 이후 **전 계좌** 포지션을 날짜 범위로 로드했다 | `Position.snapshot_id.in_(snap_meta)`로 바꿨다(`idx_positions_snapshot_id` 사용) |
| A4 | **데스크톱 보유종목 계좌별 하위 행이 한 칸 밀림.** 헤더는 9열인데 하위 행 맨 앞에 빈 `<td>`가 있어 계좌명이 "수량" 열 아래에 표시됐다 | 첫 셀을 sticky 계좌명 셀로 바꾸고 끝에 빈 셀을 맞췄다. 셀 수 = 헤더 수인지 jsdom 테스트로 확인한다 |
| A5 | **입출금·목표 시작일·백테스트 종료일 기본값이 UTC 날짜.** `toISOString().slice(0,10)` 때문에 KST 오전 9시 전에는 전날이 된다. `TransactionForm`은 모듈 최상위 상수라 자정을 넘긴 세션에서도 어제 날짜로 남았다 | `utils/format.localToday()`로 일원화했다(`TradeFormModal`의 로컬 함수를 이동). 폼을 열 때마다 계산한다 |
| A6 | **nestlio 순입금에 삭제 계좌 포함.** `monthly_net_deposits_by_account`에 `is_active` 조건이 없었다. 같은 모듈의 XIRR 쿼리에는 있었다 | `AssetAccount` join + `is_active`를 추가했다. 라우터 테스트가 이 함수를 통째로 mock하므로, 실제 SQL 조건은 PostgreSQL 방언 컴파일 문자열로 고정했다 |
| A7 | **대기 플랜 승인(즉시 체결) 후 홈·보유 stale.** 승인은 `_execute_leg`로 바로 체결하는데, 프론트는 플랜 목록·이력만 무효화했다. 수동 실행 경로는 `invalidateSyncData`를 호출한다 | `invalidateRebalancingPlanData(qc, { executed })` — 응답이 `EXECUTED`면 sync 무효화(보유·드리프트·지금 할 일)까지 한다. 앱 이력탭·이메일 승인 페이지 모두 적용했다 |

## 배치 B — 정리·중복 (`8ac6336`)

- ETF 기초지수명 → 지수 키(`RAW:` 정규화)를 `recommendation_universe.index_key_from_base_index`로 일원화했다. 원래 `etf_overlap_service`와 `etf_index_classifier`가 복제하고 있었다.
  - 두 서비스의 `resolve_*` 우선순위 차이(커버드콜 분기·`tracking_index` 명시값)는 의도된 차이라 남겼다.
  - 커버드콜을 overlap에서도 분리할지는 제품 판단이다.
- 매매 기록 수정에서 수수료·메모를 null로 비울 수 있게 했다(`TRADE_CLEARABLE_FIELDS`).
  - 프론트도 빈 값을 `null`로 보내게 바꿨다. `undefined`는 JSON에서 빠져 기존 값이 유지됐다.
  - 미래 날짜 매매 기록은 거부한다. 기간별 매수는 오늘까지만 집계하므로 이런 기록은 영영 보이지 않는다.
- `RebalancingStatusCard`의 `showHeaderBadge`·`showCombinedNote` prop을 제거했다. 호출처가 없고 `statusOnly`가 대체한다. 테스트는 `statusOnly` 기준으로 전환했다.
- 미사용 `TradeFormData`를 제거했다.
- 우선순위 타입이 3곳에 정의돼 있었다(`TaxActionPriority`·인라인 리터럴·`ActionPriority`). `utils/actionPriority.ActionPriority` 하나로 합쳤다.
- `RebalancingAlertModal`의 DCA 프리셋 setter 중복을 `applyDcaPresetValues`로 묶었다.
- `StockHoldingsTable` 정리
  - 로컬 국내시장 목록을 `DOMESTIC_MARKETS`로 바꿨다.
  - 수동 `+` 부호 조립을 `fmtPct`로 바꿨다.
  - `Math.min`을 `clampPct`로 바꿨다.
- `action_items_service` docstring을 정정했다. "각 소스가 자체 캐시"라고 적혀 있었지만 세금 요약은 캐시가 없다.

### 검토 후 손대지 않은 것 (종결)

| 후보 | 판단 |
|---|---|
| 인라인 `min-h-[44px]` 6곳 → `uiSizes` | 규칙이 금지하는 것은 `min-h`+`min-w` 쌍 재정의다. 6곳은 행 전체 폭 버튼의 `min-h`뿐이고, 상수로 바꾸면 `items-center`/`justify-center`가 들어와 정렬이 바뀐다. 위반이 아니다 |
| 신규 lazy import 상대경로 → `@/` | lazy `import()` 42곳이 전부 상대경로로, 굳어진 관례다. 3곳만 바꾸면 같은 파일 안에서 형식이 섞인다 |
| `SegmentedControl` / 필터칩 / 매수·매도 토글 통일 | 회색 세그먼트·파란 필터칩·44px 폼 토글로 시각 패턴이 서로 다르다. 합치면 디자인 변경이 된다 |
| `WeightBarRow`의 `DOMESTIC_MARKETS.includes` → `isOverseasMarket` | `isOverseasMarket`은 토스 `"US"`를 해외로 판정하지 못한다. 지금 방식이 맞다 |
| `ActionItemKind`·`PurchaseSource`·`RegionBadge` export 제거 | API 모델 타입·공용 배지의 export는 정상적인 공개 면이다. 실익이 없다 |
| 테스트의 `TreemapChart` mock 2곳 | `DividendTab`이 여전히 `TreemapChart`를 쓰고, 해당 페이지 테스트가 배당 탭을 렌더할 수 있다. 지우면 깨질 위험만 있다 |

## 배치 C — 테스트·CI·문서

- **테스트 신규**
  - `utils/__tests__/actionPriority.test.ts`(D-day 경계)
  - `utils/__tests__/legacyTabRedirect.test.ts`(`taxTabContainer.test.tsx`의 순수 함수 테스트를 관례 위치로 이동 + 케이스 1개 추가)
  - `api.trades.test.ts`
  - `schemas.test.ts`에 `tradeSchema` 추가
  - `TradeFormModal`: 수수료·메모 비우기와 수정 중 기록 삭제 흐름
- **CI**: `prettier --check`가 CI와 `make lint` 어디에도 없었다. pre-commit 훅은 `--write`라서, 훅을 건너뛴 커밋의 포맷 위반이 그대로 머지될 수 있었다. `npm run format:check`를 신설하고 `ci.yml` frontend job과 `make lint`에 추가했다.
- **문서**: `frontend/CLAUDE.md`
  - `/invest-plan` 탭 4개로 정정
  - IsaMaturityCard·TaxTabContainer 위치(계획 › 절세, `?taxAccount=`) 정정
  - `ASSET_MANAGEMENT_TABS`/`PORTFOLIO_TABS` 정정
  - queryKey 표 정정
  - `AllocationCard`·`allocation/*`·`AccountHistoryTab`(`?history=`)·`legacyTabRedirect`·`localToday`·`invalidateIncomeBracketData` 등재
  - `invalidateDcaData`·`invalidateRebalancingPlanData` 설명 갱신
  - `backend/CLAUDE.md`(기간별 매수 매칭 규칙·순입금 활성 계좌·`index_key_from_base_index`)와 루트 `make lint` 설명도 갱신했다.
  - 작업 트리에는 다른 세션의 미커밋 CLAUDE.md 정리가 있었다. 이번 커밋에는 HEAD + 이번 수정분만 스테이징했고, 그쪽 수정은 작업 트리에 그대로 남겼다.

## 이관

- **재검증 결과 그대로 유효**(계획 46 이관분)
  - 종목별 배당월 override: 편집 UI 없이 저장값만 배당 계산(`_dividend_queries.load_user_dividend_overrides`)과 "수동" 배지 3곳에 적용된다. 프론트 `updateTickerDividendMonths`/`deleteTickerDividendMonths`는 테스트만 호출한다. 복원할지 제거할지 제품 판단이 필요하다.
  - `settings.py` `{enabled}` 토글: 실측 **7개**(8개 아님, `:138~168`), PUT 7개(`:412~518`). 스펙테이블화한다. API 스키마 영향이 있어 단독 세션으로 한다.
  - N6: `jobs/dca_cash_shortfall.py:156`이 DCA 알림마다 사용자 단위 `monthly_deposit_amount` 합계와 비교한다.
  - CASH_STOCK 잔차 라벨(`portfolio_history_service.py`)
  - 메이저 업그레이드(React 19 / recharts 3 / Tailwind 4), 2-leg 실패 leg 재시도, 정기 자동매수
- **종결 제안**: HIGH_CORR 배당주기 예외. 지금 overlap은 정보 표시 전용이고(후보를 바꾸지 않음), 배당주기 예외는 SAME_INDEX에만 적용된다.
- **plans/50 Phase D**: M10 체결 → `TradeRecord` 자동 기록(모델에 `source` 컬럼 없음, 마이그레이션 필요), M9 알림 병합. 기능 작업이다.
- **신규**
  - action-items가 홈 로드마다 세금 요약을 다시 계산한다(`get_tax_summary` 캐시 없음). 지연이 문제되면 세금 요약 캐시와 무효화 키를 설계한다.
  - 외부 API 멱등키
    - 같은 키에 다른 페이로드(계좌·금액)가 와도 비교 없이 `duplicate=True`를 반환한다.
    - 계좌 삭제 후 재시도하면 중복 응답이 아니라 404가 된다(소유 계좌 확인이 멱등 조회보다 먼저다).
    - 중복도 201로 응답한다.
  - `account_scoped_performance`가 계좌별로 `get_latest_snapshot`을 N회 호출한다. 월 필터가 `to_char` 비교라 인덱스를 못 탄다.
  - 대형 컴포넌트
    - `InvestmentGoalCard.tsx` 565줄: CSS `order-*`로 시각 순서와 DOM 순서가 다르다(WCAG 1.3.2).
    - `StockHoldingsTable.tsx` 662줄
    - `TradeFormModal`이 `FormInput`/`SuggestionDropdown`을 쓰지 않는다.
  - `TradeFormModal`의 기록 삭제가 확인 없이 1탭으로 실행되고, 기록 목록 조회에 로딩·오류 상태가 없다.
  - `AssetManagementPage`(useEffect + setSearchParams)와 `AssetsPage`(`<Navigate>`)의 옛 링크 리다이렉트 방식이 다르다.

## 검증

```bash
cd backend && .venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80 -q
cd backend && .venv/Scripts/python.exe -m ruff check app tests && .venv/Scripts/python.exe -m ruff format --check app tests && .venv/Scripts/python.exe -m mypy app
cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src --max-warnings=0 && npm run format:check
cd frontend && npm run test -- --coverage && npm run build
```

- 결과는 아래 "검증 결과"에 기록한다.
- 실브라우저 검증은 하지 않았다. A4 하위 행 정렬은 jsdom에서 셀 수·열 위치로만 확인했다.

## 검증 결과

- 백엔드: **2610 passed, 커버리지 90.99%**(기준선 2589 → +21). ruff·format·mypy 클린.
- 프론트: **127 files / 1670 passed**(기준선 1648 → +22). 커버리지 lines 74.93% / statements 73.41% / branches 63.43% / functions 61.91%(`vite.config.ts` 임계값 통과). tsc·eslint(max-warnings 0)·prettier(`format:check`)·build 클린.
- 회귀 테스트(A1·A3·A4)는 수정 전 코드에서 실패하는 것을 확인했다.
