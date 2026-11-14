# 133. 수기 계좌 달러 예수금 스냅샷 이중 합산 (2026-11-15)

## 증상
홈 '현금'이 계좌관리 예수금 합보다 크게 표시(9,252만원). 운영 DB 확인 결과 달러 예수금이 있는 수기 계좌(MANUAL)의
최신 스냅샷 `amount_krw`가 `manual_amount`(계좌관리 표시값)보다 `deposit_usd × 1,300`만큼 컸다.

## 원인
`asset_service` 동기화의 "해외 조회는 됐지만 달러 예수금만 미확인" 보정(계획 109)이 수기 계좌에도 적용됐다.
`ManualProvider`는 합계에 이미 `deposit_usd × 실환율`을 넣고, 사용자 입력 보호를 위해 `deposit_foreign`을 None으로 두며,
`usd_krw_rate`를 채우지 않아 기본값(fallback 1,300)으로 한 번 더 더해졌다. 홈 현금·총자산·월별 추이·수익률 모두 과다.

## 수정
- 보정 조건에 `account.data_source != DataSource.MANUAL` 추가 + 회귀 테스트(`test_manual_usd_deposit_is_not_added_twice`).
- 데이터: 배포 후 해당 계좌를 한 번 동기화하면 오늘 스냅샷·11월 월별 대표값이 정상화된다.
  2026-11-02~11-14 일별 스냅샷의 과다분은 일별 이력에만 남음(보정은 사용자 결정 시 별도).

## 상태
완료(코드). 운영 반영·재동기화 확인 대기.
