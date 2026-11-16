# 134. 홈 환율과 환전 계획 환율 불일치 (2026-11-16)

## 증상
홈 `HeroSummaryCard`의 "환율(USD/KRW)"과 계획탭 › 적립 계획 › "달러 환전 계획" 카드의 현재 환율이 다르게 보인다.

## 원인
백엔드는 두 화면 모두 같은 전역 캐시 `usd_krw_rate`를 읽는다(홈 `GET /stocks/exchange-rate`, 계획 `GET /invest/fx-plan` →
`get_live_or_cached_usd_krw`). 캐시는 환율 알림 잡이 5분마다 갱신한다. 차이는 프론트에서 생겼다.

1. **홈 환율이 세션 내내 갱신되지 않음** — `exchangeRateQuery`는 앱 전역 `ExchangeRateProvider`가 한 번 마운트해 구독하고
   `refetchInterval`이 없다. focus 재조회도 5분 초과 + focus 이벤트가 있어야 해서, 앱을 켠 채 탭만 옮기면 부팅 때 값이 남는다.
   환전 계획은 카드를 열 때 새로 받아 더 최근 값이다.
2. **표시 자릿수** — 홈은 `Math.round` 정수(1,386원), 계획은 소수 1자리(1,385.6원).

실시간 환율이 없을 때 계획이 1년 종가를 쓰는 경우는 이미 "최근 종가 기준" 안내가 있어 대상 아님.

## 수정 (프론트만)
- `exchangeRateQuery`에 `refetchInterval: REFETCH_INTERVAL.EXCHANGE_RATE`(5분, 서버 갱신 주기와 같음).
- `utils/sharedUsdRate.syncSharedUsdRate` — 환전 계획·추가 환전 응답의 실환율이 전역 `exchange-rate` 캐시보다 새로우면
  그 값으로 맞춘다(`dataUpdatedAt` 비교, `rate_is_live=false`면 덮지 않음). `FxPlanCard`·`FxExtraNeedsSection`이 호출.
- `utils/format.fmtFxRate`(소수 1자리) — 홈·환전 계획 카드·은행 계좌 카드 환율 표시를 통일.
- 테스트: `sharedUsdRate.test.ts`, `format.test.ts`, `HeroSummaryCard.test.tsx` 소수 케이스.

## 상태
완료(코드). 실기기 확인 대기.
