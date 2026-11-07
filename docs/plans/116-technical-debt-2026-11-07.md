# 116. 남은 기술부채 — 수익률·리스크·백테스트·연동·보유종목 표시 감사 (2026-11-07)

> **진행 상태**: A~D 구현 완료(B5 보류). 브랜치 `chore/tech-debt-2026-11-07`. 마이그레이션 없음.

요청은 "남은 기술부채 수정 계획"이다. 115(PR #243)는 머지됐고 main CI(Android 잡 포함)는 녹색이다.

이번 감사는 지금까지 감사하지 않은 영역을 대상으로 했다. 백엔드는 대시보드 수익률·리스크/프론티어·백테스트·배당·키움/토스·nestlio 연동, 프론트는 Tailwind v4 회귀·보유종목 표시, 그리고 인프라·문서 드리프트다.
실버그 가운데 아래 표시(✔)한 것은 코드를 직접 읽어 확인했다.

- Tailwind v4 회귀: 없음.
- 문서(CLAUDE.md 목록·plans 인덱스)·alembic(단일 head): 드리프트 없음.
- TODO/FIXME: 0건.
- 재조사 제외(115 "계속 보류"): 포지션 부분 unique 인덱스, keep-alive, 미사용 export 타입, advancedChunks, Sentry EU CSP, 메일 주소 인증.

## 배치 A — 백엔드 실버그 (수익률·리스크)

**A1 ✔ XIRR이 기초 잔액을 빼먹는다**
- 위치: `backend/app/services/portfolio/returns_calculator.py:136-145`
- 문제: 거래가 하나라도 있으면 현금흐름이 거래 + 오늘 총액뿐이다. 동기화 계좌의 기존 평가액이 유출로 잡히지 않는다. 현금 계좌 잔액을 수정하면 거래가 자동으로 생기므로(`assets.py:306-314`) 흔히 일어나는 경우다.
- 수정:
  - 첫 스냅샷일 S0의 총액(`is_active`·`include_in_total` 계좌 기준)을 `(S0, -total)`로 맨 앞에 넣는다.
  - 거래는 `transaction_date > S0`인 것만 넣는다. S0 스냅샷에 이미 포함된 입금은 이중으로 세지 않기 위해서다.
  - 거래 없음 분기(`:109-133`)와 같은 첫 스냅샷 조회를 함수로 뽑아 공유한다.
- 같은 결함: `services/external_queries.py:110-116`(`/external/account-performance`, 계좌 단위). 같은 헬퍼에 `account_id` 필터를 붙여 쓴다.
- 영향: `return_goal_gap_pct`, 챌린지, 월간 리포트, nestlio `/external/performance`·`/goal`. 캐시 무효화는 기존 경로를 그대로 쓴다.
- 테스트: 동기화 계좌 50M + 1개월 전 1M 입금일 때 XIRR이 합리적 범위인지, 거래 없음 분기와 결과가 일관적인지 확인한다.

**A2 ✔ 리스크·프론티어가 서로 다른 날짜 수익률을 짝짓는다**
- 위치:
  - `services/portfolio_optimizer.py:70,161`의 `[:min_len]`
  - `services/risk_service.py:138-149`와 베타·S&P 정렬(`:48-49,79-83`)
- 수정: 이미 고쳐진 `goal/goal_portfolio_optimizer.py:404-413`(plans/110 C1)과 같이 뒤쪽(최근) 구간 `[-min_len:]`으로 맞춘다. 그 로직을 `utils`(또는 `portfolio/estimation.py` 근처)의 `align_recent(returns_map, syms)`로 뽑아 3곳이 함께 쓴다.
- 테스트: 상장 6개월 종목이 섞여도 공분산이 최근 구간을 기준으로 계산되는지 확인한다.

**A3 ✔ 백테스트가 한쪽 시장 휴장일에 튄다**
- 위치: `services/backtest/backtest_metrics.py:115-127`
- 수정: 종목별로 직전 가격을 이월(forward-fill)해 휴장 종목이 빠지지 않게 한다. 첫 가격 전에는 지금처럼 제외한다.
- 테스트: KR 휴장일에 포트폴리오 값이 연속인지, MDD가 과대 계산되지 않는지 확인한다.

## 배치 B — 백엔드 실버그 (계좌·연동)

**B1 ✔ 브로커 키를 교체해도 옛 토큰을 쓴다**
- 위치: `api/v1/assets.py:257-261`
- 수정: 키를 교체한 브로커에 대해 `asset_credential_service.delete_credentials`가 쓰는 토큰 정리 로직(`:132-140`)을 함수로 분리해 호출한다. 토스 계좌번호 캐시(`toss/balance.py:51-54`)도 지운다.
- 테스트: 키 교체 후 토큰과 캐시가 삭제되는지 확인한다.

**B2 ✔ nestlio 입금이 수동 계좌 잔액을 덮는다**
- 위치: `api/v1/external.py:307-316`
- 문제: `manual_amount`로 잔액을 관리하는 부동산·은행·기타 계좌에서 오늘 스냅샷이 입금액만 남는다.
- 수정: 예수금 기반 계좌(보유종목·예수금을 쓰는 수동 주식 계좌)일 때만 `deposit_krw`를 조정하고, `manual_amount` 계좌는 `manual_amount += delta`로 처리한다. 판정은 `manual_provider`의 분기 기준과 같은 함수로 통일한다.
- 테스트: 부동산·은행 계좌에 입금하면 총액이 기존 값 + 입금액인지 확인한다.

**B3 배당 집계에 합산 제외 계좌가 들어간다**
- 위치: `services/dividend/aggregator.py:83`, `orchestrator.py:147`, `_collect_positions` 경로
- 수정: `include_in_total = TRUE`를 추가해 입출금·XIRR·월별 추이와 기준을 맞춘다. 단 배당 세금 집계는 기존 원칙(세금은 유지)을 따르므로 세금 쪽 쿼리는 건드리지 않는다.
- 먼저 할 일: 합산 제외 계좌를 배당 화면에서 볼 수 있어야 하는지 계정 단위 필터(`account_id`) 경로를 확인한다. 특정 계좌를 지정한 조회는 제외하지 않는다.

**B4 Sentry 누락 2곳**
- 위치: `external.py:226-228`(`/external/goal` 진행률), `dividend/orchestrator.py:213-215`(종목 배당 조회 전부 실패)
- 수정: `report_handled_failure`를 쓴다. 전부 실패하면 0을 1시간 캐시하지 않는다.

**B5 (저) 키움 해외 소수점 수량이 `int()`로 잘린다**
- 위치: `kiwoom/balance.py:283,293`, `providers/base.py:154`
- 수정: 키움 응답이 소수를 줄 수 있는지 API 문서로 먼저 확인한다. 가능하면 `float`로 바꾸고, 확인하지 못하면 보류한다.

## 배치 C — 프론트 실버그

**C1 ✔ 합친 보유종목 행의 평단가가 첫 계좌 값이다**
- 위치: `utils/portfolio.ts:24-40`
- 수정: 병합할 때 `Σ(avg_price·qty)/Σqty`로 다시 계산한다.
- 테스트: `utils/portfolio` 단위 테스트에 추가한다.

**C2 해외 단가가 반올림되고 통화 표시가 없다**
- 위치: `StockHoldingsDesktopTable.tsx:208,211,262,265`, `StockHoldingMobileCard.tsx:101,103`
- 수정: 기존 `fmtNativePrice(price, market)`(`utils/format.ts`)를 쓰고, 두 컴포넌트의 단가 포맷을 한 헬퍼로 묶는다.

**C3 ✔ 환율이 없으면 달러 예수금을 1:1로 더한다**
- 위치: `StockAccountSummaryCard.tsx:18`의 `usdRate ?? 1`
- 수정: `depositTotalKrw(account, rate): number | null`를 `convertUsdToKrw` 위에 만들어 `StockAccountSummaryCard`·`BankAccountCard:31`·`StockAccountCard:217-224`·`dcaAutoBuy:34`가 함께 쓴다. 환율이 없으면 "환율 조회 중"을 표시한다.

**C4 지정가 원화 환산이 환율 없을 때 USD를 그대로 원으로 표시한다**
- 위치: `rebalancingTradeMath.ts:8-10`
- 수정: `null`을 반환하게 하고, 3개 표시처(`RebalancingMobileCard:183`, `RebalancingPriceInput:76`, `RebalancingOrderTable:89`)에서 "—"로 표시한다.

**C5 검색창을 비운 뒤 이전 결과가 다시 뜬다**
- 위치: `hooks/useStockSearch.ts:20-25,47`
- 수정: 비우기·`clearSuggestions` 때 진행 중 요청을 무효화한다(요청 id 비교 또는 AbortController).

**C6 정리**
- `index.css`에서 쓰지 않는 `@theme` 색상 블록(5-29행)을 삭제한다.
- `fmtKrw`·`fmtKrwShort`가 억 경계에서 반올림되는 문제를 고친다(99,995,000 → "1.00억원").

## 배치 D — 인프라·의존성 (저위험)

- **D1** `ci.yml` backend 잡의 `pull-requests: write`를 커버리지 코멘트 전용 잡으로 분리한다. `coverage.xml`은 artifact로 넘긴다.
- **D2** `build-android.yml`의 tag 빌드에서 release APK를 GitHub Release에 첨부한다(`softprops/action-gh-release`, SHA 고정).
- **D3** `backend/pyproject.toml`에서 쓰지 않는 `pyyaml`을 제거하고 `uv lock`을 다시 만든다.
- **D4** `render.yaml:257`의 `startCommand`를 지워 Dockerfile `CMD`를 단일 출처로 삼는다. Render 대시보드 반영 확인이 필요하다.
- **D5** `tests/test_dividend_fetcher.py:90-91`의 조건부 skip을 assert로 바꾼다.
- **D6** `Makefile` `install-frontend`를 `npm ci`로 바꾼다.

## 보류·이관 (이번에는 하지 않음)

- `capacitor-native-biometric@4.2.2` 교체: Capacitor 3 시대 플러그인이 core 3.9.0을 같이 끌고 온다. 네이티브 생체인증 동작을 바꾸므로 실기기 검증이 필요한 별도 계획으로 돌린다.
- `factor_service.py:184`·`portfolio_optimizer.py:228`은 소유자 확인 없이 조회한다. 지금은 호출자가 확인하므로 안전하다. `acct_suffix` 중복 3곳과 함께 리팩터 때 처리한다.
- `period_purchase_service.py:306-313`의 하한 날짜가 가장 오래된 계좌 기준이다(성능, 저).
- 600줄대 파일 4개, 이전 deprecated transitive(glob·source-map), secret-scan의 force-push base는 계속 보류한다.

## 검증

- 백엔드(`backend/`):
  - `uv run ruff check . && uv run ruff format --check . && uv run mypy app`
  - `make test-backend-cov`(게이트 91)
  - worktree에서 `uv run`이 main venv를 잡으면 `.venv/Scripts/python -m pytest`에 CI 환경변수를 넣어 돌린다(115 함정).
- 프론트(`frontend/`):
  - `npm run lint`, `tsc`(앱·테스트), `npx vitest run --coverage`, `npm run build`
- 수동 확인(`bash dev.sh`):
  - 같은 종목을 두 계좌에 보유했을 때 평단가가 가중평균이고 해외 단가에 $가 붙는지
  - 환율 요청이 실패할 때 예수금에 "환율 조회 중"이 뜨는지
  - 대시보드 XIRR 값이 합리적인지
- 머지 후 확인:
  - Render `startCommand` 제거 반영
  - tag 빌드의 Release 첨부
- 마이그레이션: 없다.

## 커밋 단위

A(수익률·리스크) / B(계좌·연동) / C(프론트) / D(인프라)로 나누고, 마지막에 문서(계획서·README 인덱스·메모리) 커밋을 둔다. PR 하나로 올린다.

## 구현 결과 (2026-11-07)

커밋: A `5712cbec` · B `f0682d17` · C `7984b2ee` · D `54820840`.

계획과 달라진 점:
- **A1**: 기초 잔액은 사용자 단위 첫 스냅샷이 아니라 **계좌별 첫 스냅샷**으로 잡는다(`anchored_cashflows`).
  - 나중에 만든 계좌의 평가액이 수익으로 잡히지 않게 하기 위해서다.
  - 그 계좌에 첫 스냅샷보다 앞선 거래가 있으면 기초 잔액을 넣지 않는다(직접 기록한 과거 입금과 이중 계산 방지).
  - 거래 없음 분기도 같은 함수로 합쳤다.
  - nestlio `/external/account-performance`의 `net_invested_krw`에 기초 잔액이 포함된다(값이 커짐).
- **A2**: 추가로 발견한 문제가 있다. 분산도 점수(`_calc_diversification_score`)가 가중 상관합을 가중치 합이 아니라 쌍 개수로 나눠서, 상관을 과소평가한다(2종목 완전 상관도 25점).
  - 고치면 일반 포트폴리오 점수가 대부분 25점 전후로 내려간다. 그러면 진단 "분산도 낮음"(40 미만)과 화면 등급(70/40)이 거의 모두에게 뜬다.
  - 점수 체계를 다시 설계해야 하는 결정이라 **보류**한다.
- **B1**: 계좌번호는 수정 스키마에 없다. 키 교체 때만 토큰을 정리한다.
- **B2**: 부동산은 내역만 기록하고 잔액을 바꾸지 않는다. 금액 직접 입력 계좌는 `deposit_krw_adjusted=false`를 돌려준다.
- **B5**: 키움 응답의 소수 수량 여부를 확인할 근거가 없어 **보류**한다.
- **C2**: 감사 결과가 틀렸다. `avg_price`·`current_price`는 해외 종목도 원화다. 달러 반올림 문제는 없었고, 원화 포맷(`fmtKrwPrice`)으로 통일만 했다.
- **C3**: `BankAccountCard`·`dcaAutoBuy`는 이미 환율 없음을 0으로 다룬다. 의미가 달라서 그대로 두고, 증권 카드 두 곳만 `depositTotalKrw`로 통일했다.

검증:
- 백엔드:
  - ruff·format·mypy 0건.
  - pytest 3713 통과, 커버리지 93.28%.
  - yaml import를 막고도 `app.main`·`uvicorn.main` import 확인.
- 프론트:
  - eslint `--max-warnings 0`·prettier·tsc(앱·테스트) 0건.
  - vitest 188파일·2033 통과(coverage).
  - `npm run build` 성공.
- **확인 못 한 것**:
  - 새 `coverage-comment` 잡의 PR 첫 실행
  - tag 빌드의 Release 첨부
  - Render 대시보드에서 `startCommand` 제거 반영(Blueprint 동기화 후 대시보드 값이 남아 있는지)
  - 실데이터 XIRR 변화
