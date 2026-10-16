# 자산 › 투자현황 › 종목 현황 탭 세로 스크롤 줄이기

## Context

사용자 불만: 모바일에서 종목 현황 탭의 세로 스크롤이 너무 깁니다. 360px 폭에서 종목 20개 기준으로 어림잡은 화면 구성:

| 영역 | 대략 높이 | 문제 |
|---|---|---|
| 상단 pill 탭 + 하위 underline 탭 + 간격 | ~140px | — |
| 요약 카드 (총평가액 + 투자기간별 3열) | ~280px | 투자기간별 블록만 ~110px |
| 비중 분석 카드 (기본 펼침) | 국내/해외 보기 ~300px, **종목 보기 ~700px** | 목록을 아래로 밀어냄. 종목 보기는 아래 목록과 정보가 겹침 (상위 10개 + 기타) |
| 보유 종목 목록 | 헤더+검색 ~120px + **카드 ~96px × N** (20개면 ~1,900px) | 접힌 카드가 3줄 구조 (이름/금액 · 티커/손익 · 비중 막대) |

**목표:** 보유 종목 목록이 첫 화면 가까이에서 시작하게 하고, 목록 자체 높이를 약 1/3 줄입니다. 정보는 빼지 않고 탭해서 펼치는 쪽으로 옮깁니다.

사용자 결정 사항:
1. 비중 분석 카드는 **모바일에서만 기본 접힘**으로 바꿉니다 (CLAUDE.md 콜랩스 규칙에 예외로 기록).
2. 비중 분석의 "종목" 보기는 **집중도 요약 + 상위 5개 + "전체 비중순 보기"** 로 줄입니다.

**상태: A1~A4·B1~B4 구현 완료(2026-10-16)** — 하단 "실행 결과" 참고.

---

## Phase A — 효과가 큰 변경 (구현 우선)

### A1. 보유 종목 모바일 카드를 3줄에서 2줄로 (목록 높이 약 -33%)
파일: [StockHoldingsTable.tsx](frontend/src/components/assets/StockHoldingsTable.tsx) `StockHoldingMobileCard`
- 1줄: 종목명 (왼쪽) | 평가금액 (오른쪽, 지금과 같음)
- 2줄: `티커 · 수량주 · 비중 12.3%` (왼쪽, truncate) | `+손익원 · 수익률` (오른쪽)
- 지금 3줄에 있는 비중 막대와 배당률 칩은 **펼침 영역**으로 옮깁니다. 펼침 `dl` 첫 행에 비중 막대 (`weightBarColor`, `clampPct` 재사용), 그 아래에 `배당률` DetailItem을 추가합니다.
- 펼침 상태를 알려주던 ChevronDown은 2줄 오른쪽 끝에 작게 둡니다 (`aria-expanded` 유지).
- 카드 패딩 `py-3` → `py-2.5`, `MOBILE_CARD_HEIGHT` 추정치 96 → 64로 바꿉니다 (실제 높이는 `measureElement`가 재므로 추정치만 수정).

### A2. 모바일에서 한 번에 카드 하나만 펼치기 (아코디언)
- 같은 파일의 `expandedSet`을 그대로 쓰되, 모바일 카드의 `onToggle`은 "다른 카드는 닫고 이것만 토글"합니다. 데스크톱 테이블의 다중 펼침 동작은 그대로 둡니다.
- 효과: 여러 카드를 펼친 채 내려가면서 목록이 계속 길어지는 문제를 막습니다.

### A3. 비중 분석 카드를 모바일에서 기본 접힘
파일: [AllocationCard.tsx](frontend/src/components/portfolio/AllocationCard.tsx)
- `useCollapsible(true, OPEN_KEY)` → `useCollapsible(() => isDesktopViewport(), OPEN_KEY)`.
  - `isDesktopViewport = () => typeof window.matchMedia !== "function" || window.matchMedia("(min-width: 640px)").matches` (Tailwind `sm` 기준. matchMedia가 없는 테스트 환경에서는 열림)
  - `useCollapsible`이 이미 함수 형태의 초기값을 받으므로 훅은 수정하지 않습니다. 사용자가 직접 토글해 저장된 값이 있으면 그 값을 따릅니다.
- 기존 `collapsedHint` ("최대 종목 OO 12.3%")가 접힌 상태에서 요약 역할을 합니다. 힌트에 `· 해외 OO%`를 덧붙일지는 데이터가 lite overview에 있으므로 (`domestic_stock_krw`/`foreign_stock_krw`) 함께 넣습니다 (상장시장 기준이라고 명시).
- 접혀 있으면 `enabled: isOpen && needsExposure`로 index-exposure 조회도 하지 않아 첫 로딩이 가벼워집니다 (이미 구현돼 있음).

### A4. 비중 분석 "종목" 보기를 상위 5개로
파일: [StockAllocationView.tsx](frontend/src/components/portfolio/allocation/StockAllocationView.tsx)
- 집중도 타일 2개 (최대 종목 / 상위 5종목 합계)는 유지합니다.
- 목록은 `ranked.slice(0, 5)`만 그리고, 나머지는 "기타 N종목 · X%" 한 행으로 합칩니다 (백엔드 `ETC` 항목 + 6~10위를 프론트에서 합산. `stock_allocation`은 [portfolio_service.py:119](backend/app/services/portfolio_service.py#L119)가 상위 10 + ETC로 반환).
- 하단 버튼 "보유 종목 전체 비중순 보기" 추가:
  - 새 prop `onShowAll?: () => void`. `AllocationCard` → `PortfolioPage`로 전달합니다.
  - `PortfolioPage`가 `StockHoldingsTable`에 `sortRequest` (예: `{ key: "weight_in_stock", nonce }`)를 내려주고 ref로 목록 헤더에 `scrollIntoView({ block: "start", behavior: "smooth" })`를 호출합니다. `StockHoldingsTable`은 `sortRequest` 변경을 `useEffect`로 받아 `setSort`합니다. 정렬 상태 끌어올리기보다 변경 범위가 작습니다.
- 테스트: [components.allocationCard.test.tsx](frontend/src/__tests__/components.allocationCard.test.tsx)에서 10행을 기대하는 단언이 있으면 5행 + 기타로 고칩니다.

---

## Phase B — 작은 정리 (같은 PR에 포함, 각각 독립)

### B1. 요약 카드의 "투자기간별 자산현황" 압축 (~110px → ~44px)
파일: [HorizonSummaryCard.tsx](frontend/src/components/dashboard/HorizonSummaryCard.tsx) (이 화면 전용으로 임베드됨)
- 모바일에서는 3열 미니 카드 (라벨/금액/막대/계좌수) 대신 **스택 바 1줄 + 범례 1줄** (`단기 1.2억 · 중기 3.4억 · 장기 5.6억`)로 그립니다. `sm:` 이상은 지금 레이아웃을 유지합니다.
- 계좌 수 정보는 범례 항목의 `title`/`aria-label`에 둡니다.

### B2. 국내/해외 보기 안내 문구 줄이기
파일: [RegionAllocationView.tsx](frontend/src/components/portfolio/allocation/RegionAllocationView.tsx)
- 2줄짜리 `BASIS_HINT`를 한 줄 요약 ("ETF가 실제로 투자하는 지역 기준" / "상장 거래소 기준")으로 바꾸고, 예시 문장 (TIGER 미국S&P500…)은 기존 `Tooltip` 공용 컴포넌트 (info 아이콘)로 옮깁니다.

### B3. 비중 카드와 목록 사이 간격 누락 수정
파일: [PortfolioPage.tsx:341-359](frontend/src/pages/PortfolioPage.tsx#L341-L359)
- `AllocationCard`와 `StockHoldingsTable`이 간격 없이 붙어 있습니다 (`ErrorBoundary` 안에 `space-y` 없음). `<div className="space-y-4">`로 감쌉니다. A3로 카드를 접으면 더 눈에 띄는 문제입니다.

### B4. 긴 목록 탐색: 검색/정렬 바를 모바일에서 sticky로
파일: `StockHoldingsTable.tsx` 검색 바 `div`
- `sm:static sticky top-0 z-10 bg-white dark:bg-gray-900`로 바꿔 스크롤 중에도 검색과 정렬에 바로 접근하게 합니다. 스크롤 길이를 줄이지는 않지만 체감이 큽니다.
- 주의: 부모 `.card-overflow`가 `overflow-hidden`이라 sticky가 동작하지 않습니다. 모바일에서는 `overflow-visible` + 모서리 처리가 필요합니다 (`sm:overflow-hidden`). 가상화 `scrollMargin` 측정에는 영향이 없습니다 (sticky는 레이아웃 위치를 바꾸지 않음). 구현 시 실제 기기 뷰포트에서 확인하고, 문제가 있으면 이 항목만 빼고 이관합니다.

---

## 손대지 않는 것
- 데스크톱 테이블 (`hidden sm:block`), 배당 탭, 계좌 선택/동기화 버튼.
- 백엔드 (`stock_allocation` 상위 10 응답 그대로. 프론트에서 5개로 자름).

## 문서 갱신
- [frontend/CLAUDE.md](frontend/CLAUDE.md) "콜랩스 기본값 일관성 규칙"에 예외 1줄 추가: `AllocationCard`는 모바일(<640px) 기본 접힘(`growlio:portfolio:allocationOpen`), 이유는 보유 종목 목록 위치 확보.
- 같은 파일 `AllocationCard` 설명에 "종목 보기는 상위 5 + 전체 비중순 보기 → 보유 종목 목록 정렬 연동" 추가.

## 검증
1. `cd frontend && npm run test -- src/__tests__/components.allocationCard.test.tsx src/__tests__/pages.portfolio.test.tsx src/__tests__/components.large.test.tsx` → 이어서 전체 `make test-frontend`.
   - 새 테스트: 모바일 카드 2줄 렌더 (비중 텍스트가 2줄에 있음), 아코디언 (두 번째 카드를 탭하면 첫 카드가 닫힘), matchMedia mock false → 비중 카드 접힘·true → 펼침, "전체 비중순 보기" 클릭 → 정렬 select 값이 `weight_in_stock`.
2. `make lint`, `make typecheck`.
3. 실제 브라우저 확인 (메모리의 테스트 계정 seed→검증→삭제 절차): Playwright 360×740 뷰포트에서 종목 15~20개 계정으로 `main.scrollHeight`와 "보유 종목 목록 헤더의 top 위치"를 변경 전후로 측정하고 스크린샷을 비교합니다. 기대치는 목록 시작 위치 ~900px → ~550px, 전체 높이 약 -35% 이상입니다. 다크 모드와 펼침 카드도 한 장씩 찍습니다.

---

## 실행 결과 (2026-10-16)

- A1~A4, B1~B4 전부 구현. 프론트 1665 tests, lint·typecheck·prettier 통과.
- 계획과 달라진 점:
  - A1: 펼침 영역 첫 행은 비중 막대 + 시장 코드(접힌 2줄에서 market을 빼 티커·수량·비중만 남김). 배당률 라벨은 데스크톱 열 이름과 같게 "투자배당율".
  - A3: 접힘 힌트는 "최대 종목 OO 12.3% · 해외상장 40%" (상장시장 기준이라 라벨에 "상장"을 붙임).
  - A4: 6위 이하 + 백엔드 `ETC`("기타 N종목", 이름에서 개수를 파싱)를 "기타 M종목" 한 행으로 합침. 전체 비중순 보기는 `StockHoldingsTable`의 `sortRequest`(nonce) prop으로 정렬하고 검색어도 비움.
  - B2: 공용 `Tooltip`이 absolute + max-w뿐이라 아이콘 폭에 갇혀 좁게 줄바꿈될 수 있어 `maxWidth="w-56"`(고정 폭)을 넘김.
  - B4: `.card-overflow`의 overflow-hidden을 모바일에서만 `max-sm:overflow-visible`로 풀고 검색/정렬 바를 `max-sm:sticky top-0`.
- 실브라우저 검증(Playwright 360×740, 일회용 계정 2계좌·17종목, 검증 후 삭제):
  - 접힌 보유 종목 카드 **62px**(종전 추정 96px), 비중 카드 접힘 상태에서 목록 헤더 시작 **582px**(비중 카드 "종목" 보기 펼침 시 1141px — 기본 접힘의 효과), 전체 스크롤 높이 1841px.
  - 실렌더링으로만 잡힌 것 2건 수정: sticky 검색 바가 `<main>` 위 패딩(py-4)만큼 아래에 붙어 틈으로 목록이 비침 → `max-sm:-top-4`. 해외 보유가 없을 때 접힘 힌트의 "해외상장 0%" 생략.
  - 툴팁(w-56)은 360px 화면 안(123~347px), 전체 비중순 보기는 정렬 "비중순" 전환 + 목록 헤더로 스크롤, 다크 모드 정상, 페이지 에러 0.
  - 후속 수정: 검색 placeholder "종목·티커 검색"이 360px에서 "종목·티커 검"으로 잘리던 기존 문제 — 모바일 정렬 라벨 "평가금액순"→"금액순", 검색창 오른쪽 여백(지우기 버튼 자리)을 검색어가 있을 때만 확보. 실측 placeholder 105px / 가용 130px.
