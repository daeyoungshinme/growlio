# 계획 7: 자산탭(`/assets`) 개선 — 기능 감사 + UX + 신규기능

**리스크: 낮음 (신규 UI 추가/버그 수정 위주, 라우팅·데이터 모델 변경 없음)**

## 배경 (Why)

2026-07-20 사용자 요청으로 자산탭(`AssetsPage.tsx` → "투자현황"/"계좌관리")을 전수 점검했다. 아래 항목은 서로 다른 파일을 건드리므로 원하는 것부터 골라 독립적으로 진행 가능하다.

## ⚠️ 실행 전 필수 확인사항

이 프로젝트는 여러 세션에서 동시에 작업되는 경우가 잦다. 아래 항목을 시작하기 전 `git status`/`git diff`로 대상 파일이 이미 다른 세션에 의해 수정 중이 아닌지 확인하고, 파일:라인이 실제 코드와 다르면 코드 현재 상태를 우선한다.

## 현재 코드 상태 (2026-07-20 기준)

- `frontend/src/pages/AssetsPage.tsx` — 상위 탭 "투자현황"/"계좌관리" 분기, `ASSETS_TOP_TABS`(`constants/tabs.ts`)
- `frontend/src/pages/PortfolioPage.tsx` — 하위 탭 "종목 현황"/"배당"/"세금" (`PORTFOLIO_TABS`)
- `frontend/src/pages/AssetManagementPage.tsx` — 하위 탭 "은행계좌"/"증권계좌"/"부동산"/"입출금·배당" (`ASSET_MANAGEMENT_TABS`)
- `frontend/src/components/assets/StockHoldingsTable.tsx` — 보유 종목 테이블(정렬/가상화 포함)

## 구현 단계 (항목별 독립 실행 가능)

### 1. [버그/UX] 정렬 방향 토글 부재

`StockHoldingsTable.tsx:15-46` (`SortTh` 컴포넌트) — `aria-sort`가 `sort === k ? "descending" : "none"`으로 고정(15-46행), 화살표도 `sort === k ? " ↓" : ""`로 항상 하향 표시. `sorted` 계산(110-113행)도 `b[sort] - a[sort]` 내림차순 전용. 같은 헤더를 다시 클릭해도 오름차순으로 바뀌지 않는다.

- `sort` state를 `{ key: AggSortKey; dir: "asc" | "desc" }`로 확장
- 같은 컬럼 재클릭 시 `dir` 토글, 다른 컬럼 클릭 시 `dir: "desc"`로 초기화(현재 동작 유지)
- `aria-sort`를 `dir`에 따라 `"ascending"`/`"descending"`으로 정확히 반영
- 테스트: `frontend/src/components/assets/__tests__/` 또는 관련 컴포넌트 테스트 파일에 토글 케이스 추가

### 2. [신규기능] 보유 종목 검색/필터

`StockHoldingsTable.tsx` — 종목명/티커로 필터링하는 입력창이 없음. 종목 수가 많은 사용자(여러 계좌 합산 시 수십 개 가능)를 위해:

- 테이블 상단(139-143행 헤더 영역)에 검색 입력 추가
- `aggregated`(109행) 이후 `sorted` 전에 이름/티커 부분 일치 필터 적용
- 모바일 카드뷰(148-198행)와 데스크탑 테이블(200-442행) 양쪽에 동일하게 반영 — 이미 `@tanstack/react-virtual`로 가상화되어 있어 필터링된 배열 길이만 바뀌면 자동 반영됨
- 검색 결과 0건일 때 `EmptyState`(이미 8행에서 import) 재사용

### 3. [기능감사] 부동산 탭에 요약 카드 없음

`AssetManagementPage.tsx:288-294`의 증권계좌 탭에는 `StockAccountSummaryCard`(전체 평가액/손익 요약)가 있지만, `AssetManagementPage.tsx:193-236`의 부동산 탭에는 대응하는 요약 카드가 없이 개별 `RealEstateAccountCard` 목록만 나열된다.

- `useStockAccountStats.ts`(`frontend/src/hooks/useStockAccountStats.ts`) 패턴을 참고해 부동산 계좌 전체 평가액/취득가 대비 평가손익 요약을 계산하는 훅 또는 인라인 `useMemo` 추가
- `RealEstateSection.tsx`(`components/assets/RealEstateSection.tsx`)에 `RealEstateSummaryCard` 추가하거나 기존 파일에 컴포넌트 추가
- 부동산은 `avg_price` 등 KRW 고정이므로(`CLAUDE.md` Key Constraints) 환율 변환 불필요 — 증권계좌 요약보다 단순함

### 4. [기능감사/확장성, 낮은 우선순위] 자산 구성 카드의 하드코딩된 3분류

`AssetManagementPage.tsx:111-128` `assetComposition` — `STOCK_TYPES`/`BANK_TYPES`/`REAL_ESTATE_TYPES` 3종류만 집계해 표시(142-180행 카드). `overview.total_assets_krw`(총액)에는 모든 자산유형이 포함되지만, 이 3종류 외 유형이 추가되면 브레이크다운 카드에는 안 잡힌다. 현재는 자산유형이 이 3종류뿐이라 문제 없음 — 향후 새 자산유형 추가 시 이 함수도 함께 갱신 필요하다는 점만 코드 주석 또는 이 문서로 남겨둔다. **즉시 코드 변경 불필요, 새 자산유형 추가 PR에서 체크리스트로 참고.**

### 5. [UX, 낮은 우선순위] "배당" 레이블 중복

"투자현황 › 배당"(`PortfolioPage.tsx:253-263`, `DividendTab.tsx` — 보유종목 기준 배당수익률 집계)과 "계좌관리 › 입출금·배당"(`AssetManagementPage.tsx:191`, `TransactionHistoryTab.tsx` — 실제 입출금/배당 거래내역)이 같은 "배당" 단어를 쓰지만 성격이 다르다(집계 뷰 vs 거래 이력). 실제로 헷갈린다는 피드백이 있으면:

- 레이블을 "배당 현황"(투자현황) / "입출금·배당내역"(계좌관리)처럼 구분하거나
- 두 화면 사이에 상호 링크("배당 거래내역 보기 →" 등) 추가

현재는 breadcrumb(`PortfolioPage.tsx:210-212`)로 구분되어 있어 **사용자 피드백 확인 후 진행 권장** — 선제적 변경보다는 관찰 후 판단.

## 확장 아이디어 (이번 계획 범위 밖, 참고용)

- 종목별 매입 이력(로트별 원가) 추적 — 현재는 계좌 합산 평단가만 표시, 세부 매매 이력 조회는 거래내역 탭에서 가능하나 종목 관점 통합뷰는 없음
- 보유 종목 CSV/엑셀 내보내기
