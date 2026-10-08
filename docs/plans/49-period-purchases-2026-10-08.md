# 49. 기간별(월/연) 매수 종목·수익률 (2026-10-08)

## 배경
"이번 달/올해 산 주식이 무엇이고 그 매수분이 지금 얼마나 벌고 있나"를 볼 수 있는 화면이 없었다.
매수 기록 자체가 없어서다:
- `Transaction`은 현금흐름(입출금·배당·이자) 전용이다. 수량·단가 컬럼이 없다.
- KIS/키움/토스 sync는 잔고·보유종목만 가져온다. 체결내역 API는 쓰지 않는다(KIS `TTTC8001R` 상수만 정의돼 있음).
- 대신 일별 스냅샷 포지션(`AssetSnapshot` + `Position.snapshot_id`)이 있다.

## 결정 (사용자 확인)
- 기본은 **스냅샷 비교 추정**이다.
- 사용자가 **매수/매도를 직접 기록**하면 그 (계좌, 종목)은 기록으로 정확히 계산한다.
- 화면은 자산 › 계좌관리 › **"기간별 매수"** 하위탭에 둔다.

## 구현 (완료)
- 백엔드
  - `models/trade.py` `TradeRecord`(`trade_records`)를 신설했다. 마이그레이션은 `tr1_add_trade_records`다.
    - `Transaction`과 의도적으로 분리했다. BUY/SELL을 섞으면 유형 필터 없는 입출금 집계가 오염되기 때문이다.
    - 보유 포지션은 자동 수정하지 않는다.
    - `price_krw`는 항상 KRW다. 해외 종목은 프론트에서 USD×환율로 환산한다.
  - `services/period_purchase_service.py`
    - `estimate_lots()`(순수)는 기준 스냅샷(기간 시작 직전) 이후 연속 스냅샷의 수량 변화를 매매로 본다.
      - 매수 단가는 이동평균 평단을 역산해 구한다.
      - **해외는 USD 평단으로 역산**한다. 원화 평단이 당일 환율로 매일 재환산되기 때문이다(`providers/base.py`). 그다음 그 스냅샷의 `usd_rate`로 환산한다.
      - 역산값이 ±50% 밖이면 현재가로 대체하고 `price_estimated`로 표시한다.
      - 매도는 보유분 대비 이번 기간 매수분 비율만큼 차감한다. 매도 단가는 그 스냅샷 현재가로 추정한 실현손익이다.
      - 매수는 기간 안에서만 세고, 매도는 오늘까지 반영한다.
    - `lots_from_trades()`(순수)는 수기 기록으로 계산한다. 수기 매도는 이번 기간 매수분에서 차감한다. 기록상 잔량이 현재 보유보다 많으면 현재 보유로 상한을 둔다.
    - 기준 스냅샷이 없는 계좌(기간 중 등록)는 첫 스냅샷을 기존 보유로 본다. 이 계좌는 `tracking_started`로 반환한다.
    - 대상 계좌는 `POSITION_STOCK_ASSET_TYPES`의 활성 계좌다(토스 포함).
  - `api/v1/trades.py`
    - `GET /trades/period-summary?period=month|year&year=&month=&account_id=`: 기본은 KST 이번 달이고, 미래 기간은 400이다.
    - `GET/POST/PUT/DELETE /trades`: 계좌 소유권을 검증한다.
- 프론트
  - `components/assets/PeriodPurchasesTab.tsx`(lazy)
    - 월/연 토글, ◀▶ 기간 이동, 계좌 필터
    - 요약(매수금액·평가금액·손익·수익률)
    - 종목 카드: `추정`/`기록` 배지, 일부·전량 매도 표시
  - `components/assets/TradeFormModal.tsx`
    - 종목 검색, 해외 USD 단가→KRW 환산
    - 해당 종목 기록 목록과 삭제
  - `api/trades.ts`, `schemas/trade.ts`, `QUERY_KEYS.periodPurchases`/`periodPurchasesBase`/`trades`/`tradesFor`
  - `invalidateTradeData()`를 신설했다. `invalidateSyncData`/`invalidateAccountData`에 `periodPurchasesBase`를 추가했다.
- 테스트
  - `test_period_purchase_service.py`(17), `test_trades_api.py`(11)
  - `components.periodPurchasesTab.test.tsx`(6), `components.tradeFormModal.test.tsx`(3), `queryInvalidation.test.ts`
  - 결과: 백엔드 2576 passed, 프론트 전체 통과

## 한계 (UI 안내 문구로 노출)
- 추정은 스냅샷 사이 순변화다. 같은 날 왕복매매나 동기화가 없던 날(Render 슬립)의 매매는 보이지 않는다.
- 수수료·평단 조정이 있으면 추정 단가에 오차가 생긴다.
- 기록 수정은 삭제 후 재입력으로만 할 수 있다. `PUT /trades/{id}`는 있으나 UI는 아직 없다.

## 후속 (보류)
- KIS 체결내역(`TTTC8001R` 국내 / 해외 체결 조회) 자동 연동으로 KIS 계좌는 추정 없이 정확히 계산하기. 키움·토스는 API 확인이 필요하다.
- 실브라우저 모바일 뷰포트 검증. 마이그레이션 적용 후 실제 스냅샷 데이터로 확인해야 한다.
