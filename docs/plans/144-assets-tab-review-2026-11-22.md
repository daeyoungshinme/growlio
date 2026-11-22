# 계획 144 — 자산탭(/assets) 감사·고도화 (2026-11-22)

## Context
자산탭(투자현황 / 계좌관리)은 계획 07·47·48·58·67·102를 거치며 기능이 늘었지만 전체를 한 번에 감사한 적은 없다. 코드를 읽어 보니 다음 세 가지 문제가 있다.
- **실버그 2건(코드로 확인함)**
  - 연동 계좌의 오늘 스냅샷을 수기 값으로 덮어쓴다.
  - '합산 제외' 계좌가 주식 집계에 섞여 비율이 100%를 넘을 수 있다.
- **UX 결함**: 에러가 나도 빈 상태로 보인다, 모바일 그리드가 깨진다, 같은 정보가 여러 번 나온다, 포맷이 화면마다 다르다.
- **기능 공백**: 순자산 구성 요약·자산 추이가 없다. 계좌별 수익이 입금 흐름을 반영하지 않는다. 은행 탭이 빈약하다.

사용자가 정한 것:
- 고도화 범위는 C1 순자산 구성·추이, C2 계좌별 입금 대비 수익, C3 은행계좌 요약·정렬이다. CSV 내보내기는 제외한다.
- 합산 제외 계좌는 "전부 제외로 통일"한다.

작업은 PR 3개로 나눈다(실버그 → UX 정리 → 고도화). 시작할 때 `docs/plans/144-assets-tab-review-2026-11-22.md`와 README 인덱스 행을 먼저 쓴다.

---

## PR1 — 실버그 (A)

### A1. 연동 계좌에서 "전체 현재가 갱신"이 스냅샷을 MANUAL로 덮어쓴다
- `backend/app/api/v1/positions.py:177` `sync_position_prices`에는 `data_source` 검사가 없다.
  - 브로커 계좌도 `snapshot_id IS NULL` 현재 포지션이 있어서 `fetch_manual_positions`가 그것을 그대로 반환한다.
  - 그 결과 `account.manual_amount`가 설정되고, 오늘 스냅샷이 `source="MANUAL"`로 upsert된다.
- 프론트 `frontend/src/components/assets/StockPositionsModal.tsx:239`의 버튼은 `readonly`(연동 계좌)일 때도 보인다. 저장 버튼만 `!readonly`로 가려져 있다.
- 수정
  - 백엔드: `get_owned_account` 다음에 `account.data_source != DataSource.MANUAL`이면 400을 반환한다(같은 파일 PUT의 MANUAL 검사(:106)와 같은 문구·방식).
  - 프론트: 버튼을 `!readonly`로 감싼다.
  - 테스트: 브로커 계좌로 요청하면 400이고 `upsert_snapshot`이 호출되지 않는지 확인한다.

### A2. 합산 제외(`include_in_total=False`) 계좌를 투자현황 집계에서 뺀다
- `backend/app/services/portfolio/portfolio_service.py:181` `_accumulate_account_totals`는 투자원금·손익을 `include_in_total`과 상관없이 더한다.
  - 그래서 `total_stock_krw`(:312)가 총자산보다 커지고, `total_non_stock_krw`(:334)가 음수가 된다.
  - `all_positions`와 `stock_allocation`에도 이 계좌가 들어간다.
- `build_portfolio_overview`는 리밸런싱·세금·인사이트·external 같은 다른 소비자도 쓴다. 핵심 집계를 바로 바꾸면 영향이 넓다.
  - 그래서 키워드 인자 `exclude_out_of_total: bool = False`를 새로 둔다.
  - True이고 `account_ids`가 없을 때(전체 보기)만 다음처럼 동작한다.
    - 제외 계좌의 투자원금·손익을 더하지 않는다.
    - 제외 계좌는 `all_positions`·`lite_stock_items`에 넣지 않는다.
    - `accounts` 행은 그대로 둔다(`include_in_total` 필드로 프론트가 구분할 수 있다).
  - 계좌를 지정해서 조회하면 지정한 계좌는 항상 포함한다.
  - 캐시 키 suffix에 플래그를 넣는다(`portfolio_overview_acct_suffix` 또는 키 빌더). `cache_invalidation`의 SCAN 패턴과 맞는지는 드리프트 테스트가 확인한다.
- 플래그를 켜는 곳
  - `/portfolio/overview` 라우터(`portfolio_analysis.py:45`)
  - `index_exposure_service`(:131)의 overview 재사용 경로. 비중 분석 카드가 투자현황과 같은 기준이 되어야 하기 때문이다.
  - 그 외 소비자는 바꾸지 않는다. 세금은 삭제 계좌까지 포함하는 것이 원칙이고, 리밸런싱은 계좌를 지정해서 조회한다.
- 대시보드도 같은 queryKey(`portfolio-overview` lite)를 공유한다. 홈에서 lite overview의 어느 필드를 쓰는지 확인하고, 홈 숫자가 의도대로 바뀌는지 본다. 총자산은 이미 제외하고 있었으므로 주식 손익만 바뀐다.
- 프론트: 제외 계좌가 있으면 상단에 "합산 제외 계좌 N개는 빠짐" 한 줄을 보인다(`overview.accounts`의 `include_in_total`로 판단).
- 응답 형태는 그대로라 `PERSIST_CACHE_BUSTER`는 올리지 않는다. 값 의미만 바뀐다.
- 테스트: 제외 계좌가 섞였을 때 `total_stock_krw <= total_assets_krw`, positions 미포함, 계좌 지정 시 포함, 플래그가 꺼지면 기존 동작 그대로인지 확인한다.

---

## PR2 — UX·코드 정리 (B)

| # | 내용 | 위치 |
|---|---|---|
| B1 | 배당 탭이 조회에 실패해도 "배당 데이터가 없습니다"로 나온다. `divError`를 넘기고, 실패하면 `PageLoadError`형 에러와 다시 시도를 보인다 | `pages/PortfolioPage.tsx:380`, `components/portfolio/DividendTab.tsx:385` |
| B2 | 계좌관리 overview·txTotals의 로딩과 실패가 0원으로 보인다. `useAssetManagementData`에 `isLoading`/`isError`를 노출한다. 카드는 로딩이면 `SkeletonStatBox`, 실패면 "평가액을 불러오지 못했어요 · 다시 시도"를 보인다(`hasStats` false로 영역이 사라지지 않게) | `hooks/useAssetManagementData.ts:22-32`, `components/assets/StockAccountCard.tsx:65` |
| B3 | 모바일 2열 그리드에서 펼침 버튼이 `col-span-3`라 3열이 생긴다. `col-span-2 sm:col-span-3`로 바꾼다 | `StockAccountCard.tsx:259` |
| B4 | 은행 카드 제목 줄이 넘친다. `flex-wrap`과 `min-w-0 truncate`를 넣는다 | `components/assets/BankAccountCard.tsx:38` |
| B5 | 은행 카드가 환율이 없으면 달러 예수금을 말없이 뺀다. 증권 카드처럼 "환율 조회 중"을 표시한다 | `BankAccountCard.tsx:29-32` |
| B6 | 카드가 각자 `useExchangeRate()`를 부른다. 부모의 `usdRate`를 prop으로 받는다 | `StockAccountCard.tsx:69`, `BankAccountCard.tsx:25` |
| B7 | 계좌 필터 배열을 렌더마다 새로 만들어 하위 memo가 무력화된다. `useMemo`로 감싼다. `RealEstateSummaryCard`·`HorizonSummaryCard`의 reduce도 memo한다 | `pages/AssetManagementPage.tsx:144-146` |
| B8 | 기간 버튼을 직접 만든 pill 대신 `SegmentedControl`로 바꾼다. 에러 시 다시 시도를 넣는다 | `components/assets/PeriodPurchasesTab.tsx:89-104,162` |
| B9 | 거래 내역 로딩을 `EmptyState "불러오는 중"`에서 `SkeletonCard`로 바꾼다 | `TransactionHistoryTab.tsx:281` |
| B10 | 금액 포맷을 통일한다. DividendTab 본문의 `fmtKrwShort()+"원"`을 `fmtKrw`로 바꾼다(차트 레이블은 그대로) | `DividendTab.tsx:233,304` |
| B11 | 중복을 정리한다. 배당 계획 링크 2개를 1개로 줄이고, 배당 맵 재구성(`DividendTab.tsx:104`)은 부모의 `dividendMap`을 prop으로 재사용한다 | `DividendTab.tsx:104,277,412` |

카드 제목·배지 크기를 맞추는 일은 B4와 함께 은행·증권 카드에서 같은 클래스로 정리한다.

---

## PR3 — 고도화 (C)

### C1. 순자산 구성 요약 + 자산 추이
홈에는 이미 `HeroSummaryCard`(총액)와 `AllocationHistoryCard`(월별 누적 막대)가 있다. 자산탭은 이와 겹치지 않도록 **계좌 유형별 구성과 계좌 단위 추이**를 맡는다.
- **계좌관리 상단 `NetWorthSummaryCard`(신규, `components/assets/`)**
  - 서브탭 위에 1장을 둔다.
  - 행: 증권(주식+예수금), 은행·현금, 부동산(시세), 부채(담보대출), 순자산. 각 행을 누르면 해당 `atab`으로 이동한다(`assetManagementUrl`).
  - 데이터: 이미 조회 중인 overview lite 하나로 계산하고 새 API는 만들지 않는다.
    - 부동산 `market_value_krw - amount_krw`가 부채다. 부동산 `amount_krw`는 이미 담보대출을 뺀 순액이다.
    - 순자산은 `total_assets_krw`다.
  - B2와 같은 로딩·에러 처리를 적용한다. 계좌관리 overview 조회가 증권 탭 전용(`enabled`)이면 모든 탭에서 켠다. lite라 가볍다.
- **투자현황에 계좌별 추이 카드**
  - `components/dashboard/AllocationHistoryChart.tsx`는 이미 `accountId`와 `storageKey` prop을 지원한다.
  - 종목 현황 탭 아래에 `useInView`로 지연 마운트한다. 상단 계좌 select의 `selectedAccountId`를 넘기고, storageKey는 `growlio:assets:allocationHistoryOpen`, 기본은 접힘으로 둔다.
  - 홈 카드와 달리 선택한 계좌를 따라간다. 이것이 자산탭 카드를 따로 두는 이유다.
  - `portfolio_history_service`는 `account_id`를 지정해도 `include_in_total=False`이면 빈 응답을 준다. A2의 "지정 계좌는 포함" 원칙에 맞게, account_id를 지정했을 때는 `include_in_total` 필터를 건너뛴다(`portfolio_history_service.py:108-113`).

### C2. 증권계좌 카드에 입금 대비 수익
- `hooks/useStockAccountStats.ts`는 지금 DEPOSIT만 합산한다. WITHDRAWAL도 모아 `net_deposit = deposit - withdrawal`을 `AccountStats`에 추가한다.
- 카드 통계에 "입금 대비 +X원 (Y%)"를 넣는다: `(amount_krw - net_deposit) / net_deposit`.
  - 배당은 예수금에 들어와 `amount_krw`에 이미 반영되므로 다시 더하지 않는다.
  - `net_deposit <= 0`이거나 입금 기록이 없으면 숨긴다. 기록 전 자금이 있는 계좌에서 오해를 부르지 않기 위해서다.
  - InfoTip으로 "기록된 입출금 기준, 기간 수익률 아님"을 설명한다.
- 기존 "평가손익(투자원금 기준)"은 그대로 두고, 입금 대비 수익은 펼침 영역의 누적 입금·배당 옆에 둔다.
- 요약 카드(`StockAccountSummaryCard`)에도 전체 합계를 같은 식으로 1행 넣는다.
- 순수 계산은 `utils/accountReturn.ts`(신규)로 빼고 테스트한다.

### C3. 은행계좌 요약·정렬
- `components/assets/BankAccountSummaryCard.tsx`(신규)를 둔다.
  - 내용: 총 잔액(원화+달러 환산), 계좌 수, 유형별(입출금·예적금·기타현금) 소계.
  - 증권·부동산 요약 카드와 같은 레이아웃으로 만든다.
- 정렬은 `SegmentedControl`로 기본(`sort_order`)/잔액순/이름순 중에서 고른다.
  - 증권 탭에도 같은 컨트롤을 둔다.
  - 선택은 `utils/safeStorage.ts`로 `growlio:assets:accountSort`에 저장한다.

---

## 범위 밖(계획서에 이관 기록)
- 거래 내역에 삭제 계좌 행이 보이는 문제의 처리 방침
- 기간별 매수(연) 캐시
- TransactionHistoryTab 데스크톱 중첩 스크롤(67에서 이관)
- 47 수동 지수 지정·49 KIS 체결내역(보류 유지)
- CSV 내보내기(사용자 제외)

## 갱신할 문서
- `frontend/CLAUDE.md`: hooks·컴포넌트 목록에 새 파일을 한 줄씩 추가한다.
- `backend/CLAUDE.md`: `portfolio_service` 항목에 `exclude_out_of_total`의 함정을 한 줄 적는다.
- `docs/plans/README.md`: 144 행을 추가한다.

## 검증
- 백엔드: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pytest --cov=app` (91% 게이트)
  - 새 테스트: positions sync-prices 브로커 거부, overview 제외 계좌, allocation-history 지정 계좌
- 프론트: `D:\project\growlio\frontend`(대문자 드라이브)에서 `npm run lint -- --max-warnings 0 && npm run format:check && npm run typecheck && npm run test`
  - 새 테스트: `accountReturn` 유틸, `NetWorthSummaryCard`·`BankAccountSummaryCard` 렌더, DividendTab 에러 상태
- 수동: `bash dev.sh`로 띄우고 390px 폭에서 확인한다.
  - 연동 계좌 보유종목 모달에 갱신 버튼이 없는지
  - 합산 제외 계좌를 하나 만들어 투자현황 %가 100% 이하인지
  - 순자산 카드 합이 홈 총자산과 같은지
  - 계좌 select 변경 시 추이 차트가 따라가는지
  - 은행 정렬이 새로고침 후에도 유지되는지
- 마이그레이션 없음. 모델 변경이 없다.
