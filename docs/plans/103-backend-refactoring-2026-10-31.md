# 103 — 백엔드 중복·구조 리팩터링 (2026-10-31)

## 배경

"백엔드에서 불필요한 코드·중복 코드 등 리팩터링할 부분 검토 + 수정 계획" 요청. 26~100의 반복 감사로 죽은 코드·미사용 의존성 같은 고전적 부채는 이미 소진돼 있어(이번에도 미사용 함수 0건), **중복 구현**과 **계층 위치(라우터 안 비즈니스 로직)** 두 축만 봤다. Explore 3개로 나눠 조사했다(API·core·utils·jobs / rebalancing·goal·tactical·portfolio / providers·notifications·tax·dividend·market_signal). 동작이 걸린 항목은 코드로 다시 확인했다.

중복을 걷어내다 보니 **같은 일을 하는 복사본끼리 동작이 갈라진 실버그**가 나와서 그것부터 고쳤다(배치 0). 사용자 선택에 따라 이번 세션 범위는 배치 0 + A이고, 배치 B는 아래 "다음 세션"에 남긴다.

## 결과 — 배치 0 (실버그)

| # | 문제 | 수정 |
|---|---|---|
| 0-1 | nestlio 입금(`POST /external/transactions`)이 수동 계좌의 오늘 스냅샷을 새로 쓸 때 포지션을 복사하지 않았다. 보유종목이 있는 수동 계좌라면 오늘 스냅샷의 포지션 행이 비어, 스냅샷 기준 종목 집계에서 보유종목이 빠졌다. 계좌 수정 경로(`assets.py`)는 복사하고 있었다 | 두 경로를 `snapshot_service.write_manual_deposit_snapshot`으로 합쳤다. `positions.py`의 두 경로는 새 포지션으로 원금까지 다시 계산하는 별개 로직이라 대상에서 뺐다. 회귀 테스트는 수정 전 코드에서 실패한다 |
| 0-2 | 배당 수집의 pykrx 호출이 프로세스 락 밖에서 동시에 돌았다. 락 docstring은 동시 호출이 크래시를 낸다고 적고 있다. 더해서, `sync_pykrx_etf_dividend_info`가 부르던 `get_market_dividend_by_date`는 **pykrx 1.2.9에 없는 함수**라, 이 폴백은 국내 종목마다 항상 실패 로그만 남기고 0을 돌려주고 있었다 | 락과 출력 억제를 `utils/pykrx_util.quiet_pykrx()` 하나로 묶었다(4곳). 죽은 pykrx 배당 폴백은 함수·호출·테스트째 지웠다. 락 회귀 테스트는 FDR 경로(실제로 pykrx 펀더멘털을 부름)로 걸었고, 수정 전 코드에서 실패한다 |
| 0-3 | 기간별·나이별 목표 추천은 필요 배당수익률을 부동산이 포함된 총자산으로 나눴다. docstring은 "전체 경로와 같다"고 했지만 전체 경로는 부동산을 뺀다. 그래서 부동산이 많을수록 필요 배당률이 낮게 나왔다 | 세 경로 모두 `_grc.investable_assets_krw(overview)`를 쓴다. 회귀 테스트 2건은 수정 전 코드에서 실패한다. 목표 추천 스냅샷 하네스는 바뀌지 않았다(부동산+배당목표 조합 픽스처가 없음) |
| 0-4 | 예외를 밖으로 던지는 잡(동기화·청소·플랜 실행 등 6개)의 실패가 Sentry로 가지 않았다. 스케줄러 리스너는 로그만 남겼다 | 계획은 잡 6개를 `run_alert_job`으로 옮기는 것이었는데, 리스너 한 곳에서 보고하는 쪽이 작고 모든 잡을 덮는다. 주문 실행 잡은 자격증명을 지역변수로 다루므로 스택 없는 `capture_message`로 보낸다 |

## 결과 — 배치 A (동작 불변 중복 제거)

| # | 내용 | 비고 |
|---|---|---|
| A1 | FRED 서킷 조회 래퍼 8벌 → `market_signal_indicators._fred_obs`. 20일 이평 2벌, CPI/PCE 같은 본문 → `_ma20`, `_yoy_inflation_signal` | 545→500줄. 테스트가 patch하는 `market_signal_indicators.fred_circuit`와 `economic_indicator_service.fred_get_observations`는 호출 시점에 읽는다. 임계값 사다리(if/elif)는 읽기 쉬워서 그대로 뒀다 |
| A2 | Naver 조회 클로저 3벌과 예외 분기 4벌 → `naver_retry.naver_get_json`, `log_naver_failure` | 0-2와 같은 커밋. 예전 `if exc.response`는 4xx 응답이 falsy라 status가 항상 None으로 찍혔다 → `is not None`으로 고쳤다 |
| A3 | 시장 게이트 판정 3곳 → `order_builder.is_alert_blocked_by_market_gate` | 자동 실행 잡은 차단 알림에 국면 값을 넘겨야 해서 그대로 뒀다. `get_confirmed_composite_level`이 이미 (GREEN, STALE)로 흡수해서 도달할 수 없던 try/except 2곳을 지웠다 |
| A4 | 알림+포트폴리오+수신자 조인 3벌 → `_alert_queries.alert_with_recipient_stmt`. 스코프 필터 2벌 → `alert_scope_filter`. 플랜 수신자 조회 2벌 → `_plan_recipient` | 환율·주가 알림의 같은 조인(2곳, 10줄)은 이득이 작아서 그대로 뒀다 |
| A5 | leg `FOR UPDATE` 4벌과 상태전이 7벌 → `_lock_leg`, `_decide_leg`. 마감 판정 2벌 → `plan_execution.is_leg_past_deadline` | `plan_service`가 다시 노출한다 |
| A6 | `OrderResult` 생성 7벌 → `OrderResult.for_order` | **작은 동작 변화**: 수량 가드의 SKIPPED 결과(보유 없음·예산 부족)도 이제 주문의 실제 `order_type`과 가격을 담는다. 예전엔 지정가 주문이 이력에 "시장가·가격 없음"으로 남았다 |
| A7 | 추천 3종의 캐시 → single-flight → 조건부 저장 골격 3벌, 캐시 조회 6벌 → `_grc.cached_recommendation`, `read_cached_model`. 최적화기 공분산 복붙 제거 | |
| A8 | KIS·키움 provider의 국내+해외 원화 합산 블록 → `providers/base.combine_domestic_overseas` | 테스트가 `kis_provider.decrypt`를 직접 patch하므로 `decrypt_*_credentials` 교체는 하지 않았다 |
| A9 | 수동 포지션 원화 재평가 2벌 → `utils/pnl.reprice_positions_krw` | |
| A10 | 배당 orchestrator의 종목별 조회·수집 클로저 2벌 → `_gather_position_dividends` | `get_position_dividend_yields`가 환율을 넘기지 않아 `estimated_monthly_usd=None`인 동작은 그대로다 |
| A11 | `_send_templated`의 `ok_event`/`fail_event` 21쌍 → `event=`. `send_test_email`도 같은 골격을 쓴다(발송 실패가 Sentry로도 간다). 리밸런싱 템플릿의 표 3개, 종목/티커 셀 3곳, 안내 배너 2곳 → `_shared` 헬퍼 | 템플릿 14종의 렌더 결과를 변경 전후로 비교해 **바이트 단위로 같다**. 리포트 표는 스타일이 달라서 그대로 뒀다. `_to_kst`는 사용처가 하나라 옮기지 않았다 |
| A12 | 한 줄짜리 금액 `field_validator` 15개 → `_validators.PositiveAmount`, `NonNegativeAmount` (Annotated) | settings의 다중 필드 검증자 2개, 챌린지 검증자 2벌, 자격증명 mixin, Goal 응답 base는 손대지 않았다 |
| A13 | `rebalancing_alerts`: 21필드 수기 응답 조립 → `model_validate(from_attributes=True)`. 14필드 할당 → `_ALERT_BODY_FIELDS` 루프. 테스트 발송 꼬리 2벌 → `_test_alert_response` | |
| A14 | 하드코딩 버전 4개 → `_XXX_VERSION` 상수(키 문자열이 변경 전과 같음을 확인). 빌더가 만든 키를 실제 `CacheStore`에 넣고 무효화한 뒤 사라지는지 보는 드리프트 테스트를 추가했다 | 계획은 SCAN 패턴을 빌더 호출로 바꾸는 것이었다. 하지만 `a:*`와 `a:*:*`는 매칭 범위가 달라 미묘하게 위험하므로, 포맷이 어긋나면 잡아내는 테스트로 대신했다. 모듈 밖에서 env prefix 없이 만드는 키 7곳은 **옮기지 않았다**. 키 문자열이 바뀌면 durable dedup 키가 어긋나 배포 당일 알림이 두 번 나갈 수 있다 |
| A15 | `month_key`/`month_label` 4벌 → `utils/kst`. 미참조 상수 3개 삭제. `alert_check`의 미사용 재노출 제거. `_account_deps.get_owned_or_404` 재노출 → `api.deps` 직접 import | 캐시 무효화 쌍 3곳의 합치기는 하지 않았다. 테스트가 개별 함수를 patch한다(10건) |

계획에서 뺀 것: `_upsert_snapshot` → `upsert_snapshot` 이름 변경. 테스트 patch 문자열 33개가 바뀌는데 얻는 게 거의 없다.

## 검증

- ruff, ruff format, mypy: 클린
- pytest: 3211 passed, 커버리지 92.63%(게이트 89%). 시작 시점은 3199 passed, 92.21%였다
- 배치 0의 회귀 테스트(0-1·0-2·0-3·0-4)는 수정 전 코드에서 실패하는 것을 확인했다
- A11: 리밸런싱 템플릿 14종의 렌더 결과가 변경 전후로 같다
- A14: 버전을 상수로 옮긴 4개 키 빌더의 출력이 변경 전후로 같다
- **미검증**: 실서버 동작. 0-1은 nestlio에서 실제로 입금한 수동 계좌의 다음 날 포지션 집계로 확인할 수 있다

## 다음 세션 (배치 B — 라우터 → 서비스 이동, 중위험)

- **B1 `api/v1/rebalancing.py`**: `analyze_portfolio`(파이프라인 전체)를 `services/rebalancing/`로 옮긴다. 캐시 → stale + 백그라운드 갱신 → 계산 3벌은 헬퍼로 묶는다. `:318`의 CAGR lookback 재구현은 `_cagr_lookback_years_from_settings`로 바꾼다. 테스트 13개의 patch 경로를 옮겨야 한다
- **B2 인라인 스키마**: `settings.py`(10클래스)와 `external.py`(9클래스) → `schemas/`. `float(x) if x is not None else None` 11곳, 기본값 40.0/10/80.0 3벌. 테스트가 `from app.api.v1.settings import GoalUpdate`를 쓰므로 다시 노출해 둔다
- **B3 `portfolios.py` CRUD**: 서비스로 옮기고, `target_portfolio_id` 채우기 2벌을 합친다. "소유 포트폴리오 + 관계 로드 + 404" 인라인 4곳 → `get_owned_or_404(..., options=)`
- **B4 "alert → overview → analyze → drift" 3벌** (`alert_check`·`alert_test`·`plan_generation`)과 주문 미리보기 복붙. `analyze_rebalancing`(29건), `build_portfolio_overview`(34건) patch가 lazy import에 기대므로 헬퍼도 함수 안에서 import한다
- **B5 최신 스냅샷+계좌+포지션 조회 5벌** → `accounts/_snapshot_queries.latest_snapshot_rows`. `get_tax_summary`는 같은 스냅샷을 두 번 읽는데 이것도 없앤다. 배당 orchestrator의 `like("STOCK%")`와 세금의 `POSITION_STOCK_ASSET_TYPES`가 다르니 먼저 테스트로 확인한다
- **B6** `execution_service`의 KIS·키움 계좌 주문 흐름(약 25줄) → `_broker_order_flow.execute_sell_then_buy`. executor 함수 이름은 유지한다(patch 55줄)

## 이관 (판단 또는 선행 작업 필요)

- **총자산 계산 엔진이 두 벌이고 규칙이 다르다.** `composition_calculator.build_asset_totals`(대시보드·DCA·챌린지)와 `portfolio_service._calc_account_amounts`(리밸런싱·목표). 스냅샷이 없는 주식계좌를 전자는 "포지션 + 예수금"으로, 후자는 `manual_amount`가 없으면 0으로 계산한다. 합치면 화면 숫자가 바뀌므로, 어느 규칙이 맞는지 정하고 동치 테스트부터 쓴다
- **해외 판정 기준이 다르다.** `overseas_realized_service`는 "국내가 아니면 해외", `tax_service`는 `OVERSEAS_MARKETS`에 있어야만 해외로 본다. 그래서 KONEX/OTHER가 갈린다. 세무 판단이 필요하며, `is_domestic_market()` 헬퍼(약 25곳)와 함께 처리한다
- goal `_compute_*` 분해(100~125줄짜리 3개). 하네스가 fetcher를 모듈 경로로 patch하므로, 공용 헬퍼는 fetcher를 인자로 받아야 한다
- `tactical_allocation_service.py`(672줄)를 국면 엔진과 포트폴리오 적용으로 나누기. `patch.object(tactical, …)` 23건
- `cache_keys.py`의 무효화 로직을 `cache_invalidation.py`로 분리하기
- 수동 포지션 재평가에서 해외 종목인데 환율이 None이면 USD 가격이 그대로 원화로 들어간다(`reprice_positions_krw`의 `elif raw_price`). `fetch_usd_krw`가 기본으로 fallback을 돌려주기 때문에 실제로 일어나기는 드물다. 기존 동작이라 그대로 뒀다
