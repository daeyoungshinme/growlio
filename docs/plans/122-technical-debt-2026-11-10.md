# 122. 남은 기술부채 — 휴장일·환전 대기 판정·월간 잡 중복 발송·환전 계획 카드 (2026-11-10)

> **진행 상태**: A~D 구현 완료. 브랜치 `chore/tech-debt-2026-11-10`. 마이그레이션 없음. 새 의존성 `holidays`.

요청은 "남은 기술부채 확인 후 수정 계획"이다. 119 이후 머지된 120(정액 적립·환전 대기, PR #253)·121(환전 계획 알림, PR #254)은 감사를 거치지 않았고, Dependabot #249~#252는 무검토 머지됐다. 감사는 세 갈래로 했다.
1. 백엔드 120/121
2. 프론트 120/121
3. 인프라·의존성·119 이관

실버그는 대부분 **120의 환전 대기(WAITING_FX) 흐름**과 **월간 잡 중복 발송**에 몰려 있었다. 실계좌 주문이 FAILED로 끝나 그달 해외 적립이 사라지는 경로가 3개였다.

깨끗했던 영역(재조사 금지):
- 120/121 IDOR(`_get_owned_leg`·포트폴리오 소유 확인), WAITING_FX 전이 락·재확인(이중 주문 경로 없음), 자동화 끄기 시 WAITING_FX 취소
- dca1·fx1 모델 일치, 30분 잡 등록, DST, 정액 배분 floor·총액 상한, 실시간 달러 캐시 키·동기화 무효화
- 프론트↔백 API 계약, 푸시 딥링크 타입, 모바일 레이아웃
- CLAUDE.md 파일 목록 드리프트 없음, TODO·무코드 type:ignore·신규 eslint-disable 0건
- Dependabot #249(액션 SHA)·#250(마이너)·#252(uv.lock, 상한 안) 저위험

## 배치 A — 백엔드 실버그 (실계좌 영향)

- **A1 휴장일 미반영**
  - 원인: `utils/market_hours.py`가 평일이면 장이 열린 것으로 봤다. 추수감사절 같은 날 마감 US leg가 닫힌 거래소로 발주돼 FAILED. 30분 재확인도 휴장일을 장중으로 보고 WAITING_FX를 PENDING으로 되돌려 FAILED.
  - 수정: `holidays` 패키지의 거래소 달력(`financial_holidays("NYSE")`, `"XKRX"`)으로 `is_krx_trading_day`·`is_nyse_trading_day`를 만들고, 개장 판정·다음 개장·환전 대기 기한(거래일 5일)이 휴장일을 건너뛴다. 반일장·KRX 연초 10시 개장은 범위 밖(주석).
  - 연쇄 수정: AUTO 스케줄일 이월(`alerts/calculator._roll_to_trading_day`)도 KRX 휴장일을 건너뛴다. 안 그러면 "매월 25일"이 추석인 달은 AUTO 잡이 장이 닫혀 돌지 않아 그달 실행이 통째로 빠진다.
  - **의존성 함정**: `holidays`가 `python-dateutil<3`을 요구해 dateutil이 4.0.0(Dependabot 11-01) → 2.9.0으로 내려갔다. 코드는 `relativedelta`만 쓴다. lock은 CI와 같은 uv 0.13.7로 생성(로컬 0.11은 revision 5→3으로 낮춘다).
- **A2 달러 판정 불가를 "충분"으로 취급**
  - 원인: `usd_buying_power.check_usd_shortfall`이 잔고·시세 조회 실패도 `None`(=충분)으로 돌려줘, 30분 재확인이 leg를 재개하고 달러 없이 발주돼 FAILED.
  - 수정: 결과를 부족(`UsdShortfall`)·미확인(`USD_UNKNOWN`)·충분(`None`) 3상태로. 재확인은 미확인이면 대기를 유지한다. 1분 실행 경로와 "다시 매수"는 미확인이면 기존처럼 진행(증권사 판정, 다시 매수는 사용자가 환전했다고 누른 것).
- **A3 재개된 leg가 장 닫힘에 영구 만료**
  - 원인: `_run_due_buy_leg`가 PENDING이면 장 닫힘 시 무조건 EXPIRED. 서버 슬립·16:00 경계·시장 게이트로 `fx_retry_until`이 남았는데 끝났다.
  - 수정: `fx_retry_until`이 남은 leg는 EXPIRED 대신 WAITING_FX로 되돌린다(알림 없음). 일반 leg는 그대로 만료.
- **A4 월간 잡 중복 발송(119 이관)**
  - 원인: `monthly_report`·`challenge_monthly_wrap`·`challenge_deposit_reminder`가 확인 → 발송 → 기록. catch-up 잡과 겹치면 2통.
  - 수정: 발송 전에 `claim_durable`로 선점한다.
    - 챌린지 둘은 챌린지 savepoint 안에서 선점(`commit=False`). 같은 키의 미커밋 INSERT는 상대 트랜잭션이 끝날 때까지 기다리므로 락 역할을 한다. 발송 못 하면(채널 없음·실패) 선점을 지워 다음 실행이 재시도한다.
    - 월간 리포트는 세션 밖에서 발송하므로 30분짜리 선점 후, 성공하면 전체 TTL로 덮고 실패·예외면 지운다. 발송 중 프로세스가 죽어도 그달이 영영 막히지 않는다.

## 배치 B — 백엔드 리스크

- **B1** 환전 대기 재진입마다 메일·푸시 반복 → 첫 진입에서만 알린다. 기한이 지난 뒤 돌아온 예약 매수가 또 부족하면 지난 기한을 알리지 않고 만료.
- **B2** 미국장이 닫힌 동안 US 정액 leg에 "지금 매수 실행"이 하루 종일 보였고, 누르면 닫힌 장 지정가 → FAILED → `approve_buy_leg`가 그 시장이 닫혀 있으면 409(leg는 그대로). `actionable`은 취소 버튼도 겸해서 바꾸지 않았다.
- **B3** 다시 매수 경합: 재개를 commit한 뒤 선점하는 사이 1분 잡이 끼어들어 사용자는 "이미 처리" 409 → commit 대신 flush로 락을 쥔 채 바로 선점.
- **B4** 실시간 달러 조회 실패를 캐시하지 않아 화면을 열 때마다 증권사 재조회·Sentry → 실패도 2분 음성 캐시.
- **B5** FX_PLAN 알림 누적·고아:
  - 계획 맞추기가 "지금 할 일" 기간(`FX_PLAN_ACTION_DAYS`, `constants`로 이동)이 지난 발동 계획 알림을 지운다. 쌓이면 상한 50에 걸려 맞추기·직접 등록이 모두 409.
  - 일시정지한 미발동 계획 알림도 계획 알림으로 보고 같은 목표면 다시 켠다(같은 환율 알림 중복 방지).
  - 포트폴리오 삭제 시 그 FX_PLAN 알림을 함께 지운다(FK SET NULL이라 계획 없이 계속 발동했다).
- **B6 정리**: `is_dca_amount_mode`를 적립식 프리셋 전체(MONTHLY·SCHEDULE_ONLY·AUTO·BUY_ONLY)로 판정. 매수 메일 실행 시각이 오늘이 아니면 날짜도 표시.

## 배치 C — 프론트

- **C1** `#fx-plan` 진입이 `useCollapsible` 저장값을 `true`로 덮어 푸시 한 번에 카드가 영구히 펼쳐졌다(121 명세 위반) → 이번 진입(`location.key`)에만 강제로 펼치고 저장하지 않는다. 사용자가 접으면 그 진입의 강제 펼침을 끈다.
- **C2** 목표 구간이 없어진 상태(1년 시세 실패·환전 대기가 전액·달러 충분·월 적립액 없음·해외 종목 없음)에 옛 계획 알림을 지울 버튼이 없었다 → 계획 알림이 있으면 어느 상태든 "이 계획으로 등록한 알림 N건 해제".
- **C3** 동기화 판정이 금액 차 1달러라 실시간 재계산(환율·보유 달러)마다 "바꾸기"로 깜빡였다 → 5%(최소 1달러).
- **C4** 다시 매수·건너뛰기 후 홈 "다시 매수" 행·환전 계획 "지금" 구간이 최대 5분 stale, 실패(만료 후 409) 시 목록 미갱신 → `invalidateRebalancingPlanData`가 항상 `actionItems`·`fxPlanBase`도 무효화, 실패해도 무효화, WAITING_FX가 있으면 2분 폴링.
- **C5** "환전했어요, 다시 매수"가 확인 없이 실거래 주문 → 승인과 같은 `ConfirmModal`.
- **C6** 같은 링크 재탭 시 펼침·스크롤이 다시 안 됐고, 늦게 그려지는 배너·차트가 카드를 밀어냈다 → effect를 `location.key`에 묶고 600ms 뒤 한 번 더 스크롤.
- **C7** 발동한 계획 알림을 설정에서 다시 켜면 `triggered_at`이 남아 맞추기가 못 건드리는 고아가 됐다 → 백엔드 재활성화가 FX_PLAN이면 `triggered_at`을 지워 미발동 계획 알림으로 돌린다(계획의 "재활성화 숨김·422"보다 단순해 바꿨다).
- **C8** 맞추기 토스트 0건 문구, 배너 달러 `$1,234.5` → `fmtUsdPrice`.

## 배치 D — 인프라·문서

- **D1** jsdom 31이 Node `^24.15.0`을 요구 → `engines` `>=24.15.0 <25`(lock 루트 포함), 루트 CLAUDE.md Prerequisites.
- **D2** 금액 포맷 잔여(119 이관): `PriceCell` → `fmtUsdPrice`, `BankAccountCard` → `fmtUsd`·환율 소수 1자리, `MonthlyDividendChart` 축 → `fmtKrwShort`.
- **D3** README 121 행 fx1 적용됨, backend/CLAUDE.md `market_hours.py` 한 줄.

## 이관(이번에 안 함)

- 600줄대 백엔드 6개(`plan_execution`·`plan_generation` 신규 포함)·500줄대 프론트 4개 분할
- `period_purchase` 하한, 해외 알림 `target_price_usd`(스키마), Dependabot pre-commit, 외부 핑 등록(사용자)
- 같은 계좌를 쓰는 두 포트폴리오 정액 leg 간 달러 예약 없음(두 번째는 FAILED, 드문 구성), 반일장
- 공개 토큰 미리보기에서 WAITING_FX가 "이미 처리됨"으로 보임(메일 취소 엔드포인트는 받는다) — 응답 reason·공개 페이지 문구가 함께 바뀌어야 해서 보류
- 배너의 환율이 fallback일 수 있음(`DcaAmountField`는 제외) — 표시 차이뿐
- 두 포트폴리오가 같은 목표 환율이면 FX_PLAN 알림 2개·홈 금액 합산 — 의도인지 사용자 확인 필요

## 검증

- 백엔드:
  - ruff·format·mypy 0건
  - pytest 3843 통과(4 skip), 커버리지 93.4%
  - 새 실버그 테스트(A2·A3·B1 6건)는 수정을 빼면 실패하는 것을 확인했다.
- 프론트:
  - eslint `--max-warnings 0`·prettier·tsc(앱·테스트) 0건
  - vitest 195파일·2072 통과(coverage 임계값 통과)
  - `npm run build` 성공
- **확인 못 한 것**: 실계좌 휴장일 발주·환전 대기 재개, 실제 메일·푸시 왕복, 실기기 해시 진입 스크롤.
