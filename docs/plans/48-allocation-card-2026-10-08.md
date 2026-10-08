# 48. 자산탭 비중 분석 카드 통합 (2026-10-08)

## 배경
자산 › 종목 현황의 비중 정보가 세 가지 형태로 흩어져 있었다.
- 국내/해외: 스택 바(`DomesticForeignBar`) — **상장시장 기준**이라 TIGER 미국S&P500이 "국내"로 잡혀, 바로 아래 지수별 카드의 "S&P 500"과 의미가 어긋남
- 종목별: recharts 트리맵 — 모바일 220px에서 작은 칸은 이름이 안 보이고 이름은 7자에서 잘림, 색은 순서 인덱스라 의미 없음
- 지수별: 별도 `IndexExposureCard`(47번) — 막대 목록, 접기 방식도 위 차트("비중 차트 접기" 텍스트 버튼)와 다름

## 결정 (사용자 확인)
1. 카드 1개("비중 분석") + 세그먼트 탭 [국내/해외 | 종목 | 지수], 세 뷰 모두 같은 막대 행 형식
2. 국내/해외는 **실제 투자지역(기본) / 상장시장** 토글, 투자지역을 판별 못 한 ETF는 "판별 불가"로 따로 표시
3. 트리맵 → 순위 막대 목록 + 집중도 요약(최대 종목, 상위 5종목 합계)

## 구현 (완료)
- 백엔드
  - `etf_index_classifier.py`: `IndexClass.region`(DOMESTIC/OVERSEAS/None) + `exposure_region()` — 해외상장→해외, 국내 개별주→국내,
    국내상장 ETF는 지수 키 접두어(`US_`/`KR_`, 커버드콜 내부 키 포함) → 종목명·기초지수명 키워드(해외 키워드 우선) 순.
    키워드 없는 국내 레버리지·인버스는 국내(코스피200 추종이 대부분)
  - `index_exposure_service.py`/`schemas/portfolio.py`: 응답에 `region_exposure{domestic,overseas,unknown}_krw`(합 = total_stock_krw), 멤버에 `region`
  - `portfolio_service._build_stock_allocation`: 항목에 `market`(기타는 None) — 종목 목록의 상장 배지용
  - **판별 버그 수정**(`recommendation_universe._TRACKING_INDEX_PATTERNS`): 한글 "고배당/전체시장/종합채권"이 무조건 미국 지수로 매핑돼
    PLUS 고배당주·KODEX 종합채권이 "미국 고배당"·"미국 종합채권"으로 묶이던 문제 → 한글은 "미국"이 붙을 때만(영문 패턴 불변).
    중복 분석·후보 dedup에도 같이 적용됨
- 프론트
  - `components/portfolio/AllocationCard.tsx`(lazy) + `allocation/`(`WeightBarRow`·`ListingBadge`·`SegmentedControl`·`Region/Stock/IndexAllocationView`)
  - index-exposure 쿼리는 "지수" 탭이나 "실제 투자지역" 기준일 때만 활성(종목 탭·상장 기준은 overview만 사용)
  - 선택 탭은 localStorage(`growlio:portfolio:allocationView`, try/catch) 기억, 카드 열림은 `growlio:portfolio:allocationOpen`
  - 상장시장 배지는 "국내상장/해외상장"으로 표기(투자지역과 혼동 방지)
  - 삭제: `DomesticForeignBar.tsx`, `IndexExposureCard.tsx`(본문은 `IndexAllocationView`로 이관). `TreemapChart`는 배당 탭이 계속 사용
- 테스트: classifier region 13케이스 + 한글 일반명 매핑 5케이스, `region_exposure` 합계·판별 불가, `_build_stock_allocation` market,
  `components.allocationCard.test.tsx`(14건, 기존 indexExposureCard 테스트 흡수)

## 남은 것 / 주의
- 상장시장 기준 금액은 overview(`domestic_stock_krw`/`foreign_stock_krw`), 투자지역 기준은 index-exposure(현금·현금성 제외) — 소스가 달라
  총액이 미세하게 다를 수 있으나 각 기준 내에서 비율로만 보여주므로 문제 없음
- "기타 N종목"은 펼치지 않고 아래 보유 종목 표로 안내 — 필요하면 백엔드가 rest 목록을 내려줘야 함
- 실브라우저 모바일 뷰포트 확인 미실시
