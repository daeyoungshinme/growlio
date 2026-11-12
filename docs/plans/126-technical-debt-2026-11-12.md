# 기술부채 계획 126 — 123~125 첫 감사 + 이관 재검증 (2026-11-12)

## Context
사용자 요청: "남은 기술부채 확인해서 수정 계획". 마지막 감사(계획 122, merge `e0eb0a5c`) 이후 PR #256~#261이 감사 없이 main에 들어왔다. 123파일, +4991줄이다. 내용은 추가 환전 `fx_extra_needs`, 보관 계좌 달러 제외(fx3), 환전 계획 로딩, 커넥션 반납, 모바일 성능 4차다.

이번에는 세 갈래로 조사했다. 백엔드 신규 코드, 프론트 신규 코드, 122·125 이관 항목의 코드 대조다. 실버그는 **캐시 무효화 판정**과 **화면에 안 보이는 값의 저장**에 몰려 있었다.

깨끗했던 영역(재조사 금지):
- fx_extra_needs IDOR(`get_owned_need`·`_check_scope_owned`), fx2/fx3 모델↔마이그레이션 일치, KST 날짜, USD/KRW 단위
- gather에서 세션 공유 없음, 세금 소스 캐시 무효화 범위, 캐시 scan 접두어 fast path
- 프론트↔백 API 계약, 새 persist 키의 계정 전환 정리(`claimCacheOwner`), lazy+Suspense, 무효화 병합 로직
- TODO·코드 없는 type:ignore·신규 eslint-disable 0건, 병합 안 된 로컬 브랜치 0개

## 배치 A — 실버그 (완료)
- **A1 일부 매도 후 해외 실현손익·리스크 캐시가 1시간 남음**
  - 원인: `asset_service.sync_account`의 `positions_changed`가 `(ticker, market)` 집합만 비교한다. AAPL 10→5주처럼 종목이 그대로면 False여서 `tax:overseas_realized:*`·`risk_key`가 남았다. 손실수확 매도 직후 세금 화면과 홈 절세 항목이 새 매도를 못 봤다.
  - 수정: `holdings_changed`(종목+수량, Numeric 4자리 정규화)를 따로 계산했다. 실현손익·리스크만 이 값으로 지운다. 목표 추천·팩터·배당은 기존대로 종목 구성(`positions_changed`)을 기준으로 둔다(plans/95·125 의도).
- **A2 하단 리밸런싱 배지가 최대 30분 동안 옛 값** (`BottomNav`)
  - 원인: `enabled:false` 관찰자는 무효화돼도 다시 받지 않는다. v5에서는 `isStale`도 항상 false다. 그래서 무효화된 drift 캐시가 action-items보다 우선했다.
  - 수정: 쿼리 캐시를 `useSyncExternalStore`로 구독한다. drift가 `isInvalidated`이면 지금 할 일로 폴백한다.
- **A3 환전 계획 알림 등록이 이전 기간·포트폴리오 구간을 저장** (`FxPlanCard`): `keepPreviousData` 중에는 등록·해제 버튼을 막는다(`isPlaceholderData`).
- **A4 삭제된 계좌가 추가 환전 보관 계좌로 남음**
  - 원인: 계좌는 소프트 삭제라 fx3의 FK `SET NULL`이 걸리지 않는다. 모달 select에는 그 계좌가 없어 "계좌 밖"으로 보이는데 저장하면 옛 id를 보냈다. 서버는 같은 id면 검증을 건너뛰었다.
  - 수정:
    - 계좌 삭제 라우트가 예약을 직접 해제한다.
    - 목록·응답은 활성 계좌만 조인하고, 비활성 계좌면 예약 없음으로 보인다.
    - PATCH는 같은 id도 다시 검증한다.
    - 모달은 목록에 없는 id를 해제해서 보낸다.
- **A5 공개 토큰 미리보기에서 WAITING_FX가 "이미 처리됨"으로 보임** (122 이관): reason을 `WAITING_FX`로 바꿨다. 확인 페이지에 환전 대기 안내와 매수 취소 버튼을 넣었다. 취소 엔드포인트는 이미 이 상태를 받는다.

## 배치 B — 커넥션 풀·캐시 리스크 (완료)
- **B1 KIS 실현손익**: 콜드 토큰의 DB 읽기 트랜잭션을 조회 HTTP(최대 20초) 전에 반납한다. 계좌 동시 조회를 3개로 묶었다. single-flight 락은 60초/대기 300회로 늘렸다(토큰 30초+조회 20초).
- **B2 전술 `evaluate_market`**: 확정 등급 durable 읽기 뒤, 차트·틸트 외부 조회를 기다리기 전에 반납한다. `save_strategy`처럼 저장 전 변경이 있으면 `release_read_connection`이 아무것도 하지 않는다.
- **B3 추가 환전**: 목록과 생성·수정 응답이 환율 1년 일봉을 기다리기 전에 반납한다. `fx_plan_service`의 직접 commit은 `release_read_connection`으로 통일했다.
- **B4 추가 환전 항목 수정**: 환율 알림 목록 캐시(5분, 항목 이름이 실림)를 무효화한다.
- **B5 배당 음성 캐시**: 국내 후속 소스(KIS·FDR) 장애 중의 "배당 없음"은 24시간이 아니라 10분만 캐시한다(`TTL_DIVIDEND_NO_DIVIDEND_UNCERTAIN`). DART는 실패와 무응답을 구분할 수 없어 대상에서 뺐다. 전부 실패면 지금처럼 캐시하지 않는다.

## 배치 C — 프론트 리스크·정리 (완료)
- **C1 무효화 누락**:
  - `invalidateAccountData`에 `fxExtraNeeds`를 넣었다(보관 계좌 이름·삭제 해제).
  - `invalidateAlertData`에 `actionItems`를 넣었다. 발동한 FX_PLAN 알림을 지우면 홈 행도 사라진다.
- **C2** 자산 › 투자현황의 당겨서 새로고침을 `refetchActiveData`로 바꿨다.
- **C3** `touchcancel`(시스템 제스처)은 임계값을 넘었어도 상태만 되돌린다.
- **C4** 챌린지 목록 조회가 실패하고 캐시도 없으면 "만들기" 카드 대신 숨긴다.
- **C5** goal-recommendation gcTime 24h를 persist하는 overall에만 적용한다(`setQueryDefaults` 프리픽스).
- **C6** 추가 환전 문구 모순을 정리했다(보관 계좌를 고르면 적립 계획에서 빠짐). 그 밖에 14일 상수화(백엔드 `FX_EXTRA_URGENT_DAYS` 주석 연결), 로딩 `SkeletonCard`, "추가" 버튼 `aria-label`.
- **C7** `invalidateFxExtraNeedData`·`invalidateAccountListData`·`refetchActiveData` 테스트를 추가했다.

## 배치 D — 문서·위생 (완료)
- **D1** CLAUDE.md:
  - backend: startup_warmup 예열 목록, 실현손익 `holdings_changed`·동시 3개, 보관 계좌 소프트 삭제 함정
  - frontend: 공용 쿼리 `actionItemsQuery`·`challengesQuery`, `api/retryPolicy.ts`, `fxPlanAlerts`
- **D2** README: 125 행에 B6·A5·E8 이관을 반영했다. 122의 "dateutil 2.9 고정"을 실제(pyproject `<5`, lock 2.9.0.post0 — `holidays`가 `<3`을 요구해 해석 결과로 묶임)로 정정했다.
- **D3** 이메일 HTML의 사용자 입력 이름(추가 환전 항목·포트폴리오·계좌)을 `html.escape` 한다. 제목은 평문이라 그대로 둔다.
- **D4** `ChallengeSummary.count`: 20일 전에는 조회하지 않아 0이다(plans/125 B6 의도). 스키마 주석을 실제 동작에 맞췄다.

## 이관(이번에 안 함)
- 125 B3 drift N+1, B4 기간별 매수 컬럼 select, `EXTRACT(YEAR)` 4곳(`dividend/aggregator`·`orchestrator`·`plan_service`, `asset_aggregator`), `period_purchase` 하한: 결과 동일성 검증 비용이 이득보다 크다
- 550줄 이상 백엔드 11개(신규 `fx_plan_service.py` 727 포함)와 500줄 이상 프론트 4개의 분할
- 해외 알림 `target_price_usd`(스키마), 반일장, 같은 계좌를 쓰는 두 포트폴리오의 정액 leg 달러 예약, 총자산 엔진 이중 구현(105), fx need 10개 상한 count-then-insert 경합
- BottomNav 폴백 배지 수: 이탈 포트폴리오가 2개 이상이면 action-items가 1행(`rebalance:all`)이라 "1개"로 센다. 숫자 정확도만의 문제다.
- 사용자 결정·작업 대기:
  - 외부 핑 등록 후 `keep-alive.yml` 제거
  - 두 포트폴리오가 같은 목표 환율일 때 FX_PLAN 알림이 2개가 되는 것이 의도인지
  - fx2·fx3 운영 적용 확인
  - 병합된 로컬 브랜치 14개와 worktree(`growlio-td116~118`) 정리
  - Dependabot pre-commit

## 검증
- 백엔드: ruff·format·mypy 0건, pytest 전체 통과(실 DB 5 skip — CI에서 실행).
  - 새 회귀 테스트: 수량 변화 sync, 소프트 삭제 예약 해제, WAITING_FX 미리보기, 토큰 뒤 반납 순서, 전술 반납 순서, 추가 환전 목록 반납·PATCH 무효화, 배당 음성 TTL, 이메일 이스케이프
- 프론트(`D:\project\growlio\frontend` 대문자 경로): eslint·prettier·tsc 클린, vitest 전체 통과.
  - 새 테스트: 배지 무효화 폴백(수정 전 실패 확인), placeholder 중 버튼 잠금, 삭제 계좌 해제 저장, 환전 대기 확인 페이지, touchcancel, 챌린지 실패, 무효화 헬퍼 3종
- 운영 확인 필요: 배포 후 Render에서 `/tax/*`·`/tactical/{id}`·`/invest/fx-extra-needs`의 QueuePool timeout 로그가 사라졌는지 본다.
