# 47. 추종 지수별 ETF 비중 합산 (2026-10-07)

## 배경
자산 › 투자현황 › "종목 현황"은 국내/해외 바 + ticker 단위 트리맵뿐이라, SPY(미국상장)와 TIGER 미국S&P500(국내상장)처럼
같은 지수를 추종하는 상품이 계좌·상장시장별로 흩어져 있으면 "S&P500에 실제로 몇 %가 들어가 있나"를 알 수 없었다.

## 결정 (사용자 확인)
- 분모: 기본 주식 총평가액 대비(개별주는 "개별주" 묶음으로 합 100%) + "ETF만" 토글
- 환헤지(H)·합성·선물형은 원 지수에 합산하고 "(H) 포함" 배지. 커버드콜은 별도 지수 그룹. 레버리지·인버스는 별도 묶음(배수 노출 미반영)
- 자동 판별 실패 ETF는 "기타 ETF". 사용자 수동 지정은 2단계(아래 보류)

## 구현 (완료)
- 백엔드
  - `services/etf_index_classifier.py`(신규, 순수): `classify_holding()` → `INDEX`/`LEVERAGED`/`OTHER_ETF`/`STOCK` + 지수 키·라벨·hedged
  - `services/index_exposure_service.py`(신규): `build_portfolio_overview`(비-lite, 캐시 공유) 포지션 → ticker+market 합산 →
    `get_etf_profiles_with_status`로 프로필 → 분류 → 그룹 집계. 응답 캐시 없음(프로필은 7일 전역 캐시)
  - `GET /portfolio/index-exposure?account_id=` (`portfolio_analysis.py`, 10/min, 계좌 소유권 404)
  - `etf_profile_service.get_etf_profiles_with_status()` — 조회 실패 키를 따로 반환(“ETF 아님”과 “이번엔 모름” 구분) → `profiles_complete`
  - `recommendation_universe.py` 판별 보강 (중복 분석·후보 dedup에도 같이 적용되는 버그 수정):
    - 해외상장 ticker 단독 맵 `_US_ETF_INDEX_BY_TICKER` + `overseas_ticker_tracking_index()` — QQQ(정식명에 Nasdaq-100 없음)·
      SPY(NYSE Arca라 NYSE/AMEX/"US"로 저장됨)가 `(ticker, market)` 키로 매칭 안 되던 문제. `resolve_tracking_index`가 사용
    - DIA("Dow Jones Industrial Average")가 배당다우존스로 묶이던 문제 → `US_DJIA` 패턴을 앞에
    - "TIGER 미국나스닥100커버드콜"이 나스닥100으로 묶이던 문제 → 커버드콜 패턴 우선, 기초지수 불명 커버드콜은 None
    - "S&P500 동일가중/배당귀족/성장" 등 파생 지수가 원 지수로 묶이던 문제 → `_INDEX_VARIANT_RE`
    - 코스닥150·필라델피아 반도체 패턴 추가
- 프론트: `components/portfolio/IndexExposureCard.tsx`(lazy, 종목 현황 탭 비중 차트 아래 — 48번에서 `AllocationCard`의 "지수" 탭으로 흡수), `QUERY_KEYS.indexExposure(accountId)`
  + `indexExposureBase`를 `invalidateSyncData`/`invalidateAccountData`에 추가
- 테스트: `test_etf_index_classifier.py`, `test_index_exposure_service.py`, `test_api_routes.py`(라우터 2건),
  `test_etf_profile_service.py`(unresolved 키), `components.indexExposureCard.test.tsx`. 추천 스냅샷 테스트 변경 없음 통과.
  백엔드 2527 passed(90.84%), 프론트 1620 passed

## 보류 (2단계)
- **사용자 수동 지수 지정**: 테마·섹터 ETF처럼 자동 판별이 안 되는 종목을 사용자가 직접 지수 그룹에 넣는 기능.
  `user_ticker_settings`에 `tracking_index` 컬럼 추가(마이그레이션) → `classify_holding`의 최우선 입력으로 전달,
  카드의 "기타 ETF" 구성 종목 행에 "지수 지정" 액션. 지정 키는 기존 키 목록(`INDEX_LABELS`) + 자유 라벨 허용 여부 결정 필요
- 레버리지 배수 반영(예: TQQQ를 나스닥100 3배 노출로 환산)은 사용자 결정으로 제외 — 필요해지면 배수 메타데이터 소스부터 확보
- 실브라우저 검증(테스트 계정 시딩→스크린샷→삭제)은 이번 세션 미실시
