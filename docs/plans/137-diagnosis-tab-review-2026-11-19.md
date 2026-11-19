# 137. 리밸런싱 진단 탭 고도화 — 위험 지표 재검토 · 3대 지수 추세 종합 판단 (2026-11-19)

## Context

사용자 요청: 진단 탭의
1. 매크로 위험지표를 검토하고 고도화한다.
2. 그 아래 차트 추세(나스닥·S&P500·다우)를 위험지표와 **함께** 고려한다.
3. 잘 안 보게 되는 "내 포트폴리오 위험 지표"를 다시 검토한다.

사용자 결정:
- 지수 추세는 **표시용 "시장 종합 판단"만** 만든다. 복합 위험지수(27점)·자동 실행 게이트(`order_builder.is_market_signal_blocking_auto_mode`)·전술 국면 판정(`tactical_regime.classify_regime`)은 바꾸지 않는다.
- 포트폴리오 위험 지표는 **계산 수정 + 행동형 재구성**. 분산도 점수는 폐기하고 집중도로 대체한다 — `remaining-tasks.md` P4 "분산도 점수 체계 재설계(116)"를 이 계획이 흡수한다.

배치마다 PR 하나. 순서는 A → B → C(C는 A·B 응답 계약에 의존).

---

## 현재 상태 (코드 조사, 2026-11-19 `main` 8b83012a 기준)

진단 탭 구성 — `frontend/src/pages/RebalancingPage.tsx:203-246`:
`RebalancingStatusCard` → `MarketSignalBanner`(매크로 8지표 + 물가 + `ChartTrendList`) → `RiskMetricsCard`(기본 접힘).

### 포트폴리오 위험 지표 (`backend/app/services/risk_service.py`) — 실버그 포함

1. **날짜 미정렬(실버그)**: `market_data/market_data_fetcher.fetch_yf_daily_returns`(:51)가 종목별 `dropna()` 뒤 **날짜 없는 list**를 돌려준다. `_compute_risk_result`는 끝에서부터 순번으로 짝짓는다. 한국·미국 휴장일이 다르면 서로 다른 날의 수익률이 같은 날로 합쳐진다 — 포트폴리오 수익률·VaR·변동성·베타 모두 오염. plans/116 A2는 "앞에서 자르기 → 뒤에서 자르기"만 고쳤다.
2. **분산도 점수(실버그, 116 A2 보류분)**: `_calc_diversification_score`가 가중 상관합을 가중치 합이 아니라 쌍 개수로 나눈다 → 대부분 50점 근처. 진단 인사이트 `rebalancing/diagnosis_service.py:30` `RISK_DIVERSIFICATION_MIN`·`_risk_note`(:272)도 이 값을 쓴다.
3. **현금 제외**: `query_latest_position_map`의 포지션만 본다 → 예수금 비중만큼 VaR·변동성이 과대.
4. **환율 미반영**: 해외 종목은 USD 수익률을 그대로 원화 가중 → 원화 투자자의 실제 변동(환율 효과)이 빠진다.
5. **결측·짧은 이력**: `returns_map`에 없는 종목 가중치를 재정규화하지 않아 합이 1 미만(과소추정). `min_len`이 가장 짧은 종목(신규 상장) 길이로 전체 기간을 자른다.
6. **최대 종목 비중이 티커 단위**: QQQ와 TIGER 나스닥100처럼 같은 지수 ETF는 집중으로 잡히지 않는다.
7. **안 보게 되는 이유**: 변동성 10/20% 절대 임계(`frontend/src/utils/riskLevel.ts`)라 주식형 포트폴리오는 늘 "보통/높음". VaR95·VaR99·변동성·베타 4개가 사실상 같은 정보. 금액이 아니라 %라 체감이 없고, 접힌 상태 배너는 "안정/주의" 등급만 보여 줘서 열 이유가 없다.

응답은 스키마 없이 dict(`api/v1/portfolio_analysis.py:81`). 프론트 소비처: `api/risk.ts`, `utils/riskLevel.ts`, `api/rebalancing.ts`(DiagnosisContext), 테스트 3개. `portfolio-risk` queryKey는 persist 대상이 아니다(`constants/queryConfig.ts:19`) → 필드 삭제에 `PERSIST_CACHE_BUSTER` 불필요.

### 매크로 위험지표 (`market_signal/market_signal_indicators.py`, `market_signal_scoring.py`)

- 8지표 모두 **현재 수준만** 보는 계단식 점수다. 변화 방향(VIX 급등, 하이일드 스프레드 확대 속도)과 금리커브 **역전 해소(재가팔라짐)** 구간 — 역사적으로 침체 직전 — 을 보지 못한다.
- 월간 지표(CPI·PCE·실업률)는 기준일이 1~2개월 늦은데 행에서 기준일이 눈에 띄지 않는다.
- 점수를 바꾸면 AUTO 게이트가 바뀐다 → 이번 계획은 **표시 보강만**, 점수 변경 후보는 "결정 대기"로 기록.

### 차트 추세 (`market_signal/technical_indicators.py`, `components/rebalancing/ChartTrendList.tsx`)

- 추세 판정 = 종가 200일선 위 + 50일선 > 200일선(히스테리시스, `classify_trend` :111). 그런데 화면엔 **50일선 이격이 없다**(20/60/120/200만).
- DIA는 "참고 · 국면 판단 미반영"으로만 표시된다. 매크로와 추세를 엮은 해석이 없다 — 배너 헤더는 매크로 등급 문구(`MarketSignalBanner.tsx` `SHORT_IMPLICATION`)뿐.

---

## 배치 A — 포트폴리오 위험 계산 바로잡기 (백엔드, 중위험)

- **A1 날짜 정렬 + 원화 기준**: `market_data_fetcher.fetch_yf_close_series`(날짜 인덱스 Series, pykrx 폴백 포함)를 재사용해 종가 DataFrame을 만든다.
  - 해외 종목은 `USDKRW=X` 종가를 곱해 원화 종가로 바꾼다.
  - 휴장일은 `ffill(limit=3)`, 최근 252행, 그다음 일간 수익률.
  - `fetch_yf_daily_returns`는 다른 소비처(`portfolio_optimizer`, 목표 추천 스냅샷 테스트)가 있어 **건드리지 않는다**.
  - yfinance는 `run_yf_bounded`로, CPU 계산은 `asyncio.to_thread`로(현행 유지). `release_read_connection` 위치 유지.
- **A2 결측·짧은 이력**: 커버리지 60% 미만 종목은 빼고 남은 가중치를 재정규화한다. 응답에 `coverage_pct`(계산에 반영된 평가액 비중).
- **A3 현금 포함**: 활성 증권 계좌 최신 스냅샷 예수금을 수익률 0 자산으로 넣는다(`portfolio_service.prefetch_accounts_snapshot_positions`/`compute_total_assets_krw` 또는 `_snapshot_queries` 헬퍼 재사용 — 새 쿼리 금지). 응답에 `cash_weight_pct`.
- **A4 베타는 주간 수익률**: 한국·미국 장 시간차 때문에 같은 날 일간 상관은 과소 추정된다 → 금요일 기준 주간 수익률로 베타(벤치마크 `^GSPC` 원화 환산)를 계산한다.
- **A5 분산도 점수 폐기 → 집중도**: `etf/index_exposure_service.build_index_exposure`·`merge_holdings`로
  - `top_index_exposures`: 지수 기준 상위 3개(지수명·비중 %)
  - `top_holding_weight_pct`: 티커 병합 후(국내·해외 같은 티커 합산)
  - `effective_holdings`: 지수 기준 유효 보유 수(1/Σw²)
  - `diagnosis_service`의 분산도 문구·`RISK_DIVERSIFICATION_MIN`을 "한 지수 노출 60% 초과" 기준으로 바꾼다(`_risk_note`, `diversification_score` 인자를 받는 판정 함수 :244).
- **A6 신규 지표**:
  - `max_drawdown_pct`: 1년 최대 낙폭(원화)
  - `var_95_krw`: VaR95 × 총액(현금 포함)
  - `vol_ratio_vs_sp500`: S&P500(원화) 대비 연간 변동성 비율
  - `sp500_10pct_drop_krw`: 베타 × 10% × 주식 평가액
- **A7 응답 계약**: `diversification_score`·`var_99_pct` 제거, 위 필드 추가. 이번에 `schemas/`에 `PortfolioRiskMetrics` 응답 모델을 만들어 계약을 고정한다. `cache_keys.risk_key`에 버전을 붙여 옛 캐시 무시.
- **테스트**(`tests/test_risk_service.py` 확장, yfinance mock):
  - 한국 휴장일이 낀 국내·미국 2종목 — 같은 날짜끼리 합쳐지는지
  - 결측 종목 재정규화, 커버리지 60% 미만 제외
  - 환율 반영(USD 수익률 0이어도 환율 변동만큼 원화 수익률)
  - 현금 50%면 변동성 절반
  - 같은 지수 ETF 2개 → 지수 노출 합산
  - `diagnosis_service` 새 집중도 문구

## 배치 B — 시장 종합 판단: 매크로 × 3대 지수 추세 (표시 전용)

- **B1 순수 함수** `backend/app/services/market_signal/market_outlook.py`
  - 입력: 즉시 매크로 등급(raw `composite_level`) + QQQ·SPY·DIA의 `trend`·`drawdown_pct`.
  - 출력: `verdict`(FAVORABLE/STEADY/CAUTION/DEFENSIVE), 한 줄 행동 문구, 근거 목록, 추세 폭(상승 n/3), 조정 깊이(52주 고점 대비 가장 깊은 하락).
  - 매트릭스("상승 다수" = 판정 가능한 지수 중 과반 UP, "하락 다수" = 과반 DOWN):

    | 매크로 \ 추세 | 상승 다수 | 혼조 | 하락 다수 |
    |---|---|---|---|
    | GREEN | 우호 — 계획대로 | 신중 — 계획대로, 분할 고려 | 신중 — 분할 집행 |
    | YELLOW | 신중 — 분할 집행 | 경계 — 매수 속도 조절 | 경계 — 매수 속도 조절 |
    | RED | 경계 — 신규 레버리지 자제 | 방어 — 포지션 점검 | 방어 — 포지션 점검 |

  - UNKNOWN 추세는 폭 계산에서 뺀다. 판정 가능한 지수가 2개 미만이면 매크로만으로 판단하고 "추세 확인 불가" 근거를 단다. STALE 매크로면 추세만으로 판단 + "매크로 데이터 없음".
  - 조정 깊이 −10% 이하·−20% 이하는 근거 문구만 추가(판정 칸은 바꾸지 않음).
  - **게이트·전술 미사용**을 docstring과 테스트 이름에 명시한다.
- **B2 엔드포인트** `GET /market-signals/outlook`(`api/v1/market_signals.py`): 기존 캐시(`market_signal_service.get_market_signal` raw + `technical_signal_service.get_technical_signals`)를 조합만 한다. 새 외부 호출 없음. 홈 action-items 경로에는 붙이지 않는다(시세 지연 전파 방지). `frontend/vercel.json` rewrite는 `/api/*` 전체라 변경 없음 — 확인만.
- **B3 배너 헤더**: `MarketSignalBanner`의 `SHORT_IMPLICATION` 자리를 종합 판단 문구로 바꾼다(로딩·실패 시 기존 문구로 폴백). "위험지수 n/27"은 유지. 상세의 "차트 추세" 섹션 맨 위에 3지수 요약 칩(나스닥 상승 · S&P500 상승 · 다우 혼조)과 종합 판단 근거. 전술 국면과 다를 수 있다는 한 줄("전술 국면은 확정 등급·나스닥/S&P500 기준") — 기존 `confirmed_level` 줄 옆.
- **B4 ChartTrendList 보강**:
  - 행 제목 한글 병기: "나스닥100 (QQQ)", "S&P500 (SPY)", "다우 (DIA)".
  - **50일선 대비** 이격 추가 — `TechnicalSnapshot`에 `sma50` 노출(이미 계산됨, 스키마·타입만).
  - 추세 기준 `InfoTip`: "200일선 위 + 50일선이 200일선 위 = 상승".
  - DIA 문구: "전술 국면 미반영 · 종합 판단 반영".
- **B5 매크로 행 표시 보강(점수 무변경)**: 각 지표 행에 기준일(월간 지표는 "n월 기준")과 약 1개월 전 대비 방향(↑/↓). FRED 조회 `limit`만 늘려 같은 응답에서 계산하고 `signals.*`에 `prev_value`·`as_of`를 **optional로** 추가(`market-signal`은 persist 대상이라 필드 추가만, 삭제 없음).
- **테스트**: `tests/test_market_outlook.py`(매트릭스 9칸 + UNKNOWN·STALE·조정 깊이 근거), 라우트 테스트, `market_signal_indicators` prev_value 테스트, 프론트 배너·`ChartTrendList` 렌더 테스트.

## 배치 C — 진단 탭 화면 재구성 (프론트)

- **C1 `RiskMetricsCard` 재구성** — 6행 → 4행:
  1. **나쁜 날 예상 손실** — `var_95_krw`("20일 중 하루는 이보다 더 잃을 수 있어요")
  2. **1년 최대 낙폭** — `max_drawdown_pct`
  3. **시장 대비 흔들림** — `vol_ratio_vs_sp500`(1.0 = S&P500과 같음) + "S&P500 10% 하락 시 약 ○원"
  4. **쏠림** — 지수 기준 상위 노출 3개 + 자산탭 지수 비중 딥링크(`utils/tabUrl.portfolioUrl`)
  - 등급은 시장 대비로: 변동성 비율 <0.8 낮음 / ~1.2 시장 수준 / 초과 높음, 지수 노출 <40% / ~60% / 초과.
  - 접힌 상태 요약 배너를 금액·쏠림 한 줄로: "나쁜 날 −○원 · 나스닥100 쏠림 ○%".
  - 하단: 커버리지 90% 미만이면 "○% 종목은 데이터가 없어 제외", 현금 비중, 기준 설명.
- **C2 `utils/riskLevel.ts` 재작성** + `utils/__tests__/riskLevel.test.ts`·`diagnosisInsights.test.ts`·`__tests__/api.coverage.test.ts` 갱신. `api/risk.ts` 타입 교체.
- **C3 진단 요약 줄**(`DiagnosisSummaryStrip.tsx` 신규): `TabIntro` 아래에 칩 3개 — 이탈 포트폴리오 n개 · 시장 종합 판단 · 쏠림 최대 지수. 탭하면 해당 카드로 스크롤(위험 카드는 펼침). 데이터는 진단 탭이 이미 미리 발화하는 쿼리(`driftSummaryQuery`·outlook·`portfolioRisk`) 재사용 — 새 요청 없음. outlook 쿼리는 `api/queryOptions.ts`에 공용 정의, 키는 `QUERY_KEYS`.
- **C4 문서**: `frontend/CLAUDE.md`(콜랩스 예외·utils 목록에 `DiagnosisSummaryStrip`), `backend/CLAUDE.md`(market_signal 목록에 `market_outlook.py` "표시 전용, 게이트 미사용", risk_service 함정: 날짜 정렬·원화·주간 베타), `remaining-tasks.md` 분산도 항목 종결.

---

## 범위 밖 · 결정 대기

- **매크로 점수 변경 후보**(AUTO 게이트가 바뀌므로 사용자 결정 후 별도 계획):
  - 금리커브 역전 해소(최근 12개월 내 역전 → 현재 양수 전환) 가산
  - 하이일드 스프레드 4주 확대 폭 가산
  - VIX 5일 급등(+30% 이상) 가산
  - 각 후보는 VIX 근사 백테스트(`tactical_backtest`)처럼 과거 국면 대조 근거를 함께 낼 것
- **위험지수 30일 추이 그래프**: 일별 저장소(AppState 또는 테이블)가 필요하다. 136에서 뺀 이탈 추이 기록과 함께 다음 계획 후보.
- **"목표 비중대로 맞추면 위험이 어떻게 바뀌나" 비교**: 지수 그룹 행 펼치기(`group_expansion`)와 계좌 범위 문제가 있어 C1 안정화 뒤 후속.

## 검증

- 백엔드: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pytest tests/ -k "risk or outlook or diagnosis or market_signal"` → 마지막에 `make test-backend-cov`(91%).
- 프론트: `D:\project\growlio\frontend`(대문자 드라이브)에서 `npm run lint -- --max-warnings 0 && npm run format:check && npm run typecheck && npm run test`.
- 실화면: `bash dev.sh --keep-port` → `/rebalancing?rtab=진단`(390px 뷰포트)에서 배너 헤더 종합 판단, 3지수 칩·50일선, 위험 카드 4행·원화 금액·쏠림 딥링크, 요약 칩 스크롤.
- 실제 계정에서 A 전후 값(VaR·변동성·베타)을 비교해 이 계획서 하단 "구현 결과"에 기록한다.

---

## 구현 결과 (2026-11-19)

커밋: 계획 `6775b1c7` · A `eaacaee4` · B(백엔드) `c171450b` · B(프론트)·C는 이 문서와 같은 커밋.

계획과 달라진 점:
- **A3 예수금**: 새 쿼리 대신 `latest_snapshot_rows(with_positions=True)` 한 번으로 종목 평가액과 예수금(증권 계좌 `amount_krw` − 종목 합)을 같이 뽑는다. 예수금 티커 같은 합성 항목(`is_non_tradable`)은 종목에서 뺀다 — 예전엔 가격이 없어 가중치만 차지했다.
- **A5 집중도 알림**: 계획은 "지수 노출 60% 초과"를 진단·복합신호 사유로 쓰는 것이었지만 **넣지 않았다**. S&P500 한 지수에 60% 넣는 건 대개 의도된 인덱스 투자라, 복합신호 알림이 거의 모두에게 울린다. 분산도 사유만 지우고 단일 종목 40%·변동성 20% 기준은 그대로 뒀다. 쏠림은 위험 카드와 요약 칩에만 표시된다.
- **A7 캐시**: 위험 캐시는 프로세스 메모리(`cache_store`)라 배포 재시작 때 비워진다 — `risk_key` 버전은 올리지 않았다. `portfolio-risk` 쿼리는 persist 대상이 아니라 `PERSIST_CACHE_BUSTER`도 그대로다.
- **B5**: 1개월 전 값은 VIX·하이일드 스프레드(일간 시리즈)만 붙였다. 월간 지표(인플레이션·고용)는 방향 대신 "n월 기준"을 붙였다.
- **C3 앵커**: 요약 칩 앵커는 lazy 컴포넌트 밖에서도 쓰도록 `constants/rebalancingConfig.DIAGNOSIS_ANCHORS`에 뒀다. 위험 카드는 접혀 있어도 헤드라인(나쁜 날 손실액·쏠림)이 보이므로 칩은 스크롤만 하고 펼치지 않는다.

검증:
- 백엔드: `ruff check`·`ruff format`·`mypy app/` 통과, `pytest` 4015 passed(이후 B 테스트 22개 추가).
- 프론트: `lint --max-warnings 0`·`format:check`·`typecheck`·`vitest` 통과(2165개 중 실패 0 — 관련 파일 재실행 포함).
- **실화면·실계정 수치 비교는 하지 않았다** — 배포 후 진단 탭에서 위험 카드 값(특히 예수금 포함 후 VaR·변동성)과 종합 판단 문구를 확인해야 한다.
