# 계획 12: 백엔드 도메인 경계 정리 (독립 실행 가능한 6개 소항목)

**리스크: 전체 낮음~중간 — 각 항목은 서로 다른 파일을 건드리므로 원하는 항목만 골라 독립적으로 진행 가능.**

## 배경 (Why)

전체 구조 감사 결과, `kis/`·`kiwoom/`·`providers/`·`jobs/`·리밸런싱 라우터 5개 분리는 이미 적절한 설계로 확인됐다(재설계 불필요). 대신 아래 6곳에서 "한 파일에 무관한 두 책임이 얹혀 있는" 패턴이 발견됐다. 각 항목은 서로 독립적이므로 이 문서 전체를 한 번에 처리할 필요 없이 하나씩 골라 진행해도 된다.

## 소항목

### (a) `schemas/asset.py` (369줄) — 무관한 스키마 분리

`Position`/`AssetAccount` 관련 스키마 외에 `TransactionCreate`/`Update`/`Response`(→ `api/v1/transactions.py` 전용), `DashboardResponse`(→ `api/v1/dashboard.py` 전용)가 섞여 있다. `schemas/rebalancing.py`(453줄)를 `schemas/rebalancing/` 패키지로 분리한 전례와 동일한 논리.

- **조치**: `schemas/transaction.py`, `schemas/dashboard.py` 신규 생성 후 해당 클래스 이동. import 경로 변경(`from app.schemas.asset import TransactionCreate` → `from app.schemas.transaction import TransactionCreate`)이 필요한 호출부(`api/v1/transactions.py`, `api/v1/dashboard.py`, 관련 서비스·테스트) 전부 grep으로 확인 후 갱신.
- **우선순위**: 중간.

### (b) `api/v1/stocks.py` (395줄) — 외부 API 호출 로직을 서비스로 추출

라우터 파일에 `_search_naver`/`_search_yahoo` 등 외부 API 직접 호출 로직이 그대로 박혀 있다. `backend/CLAUDE.md`의 "서비스→라우터" 계층 원칙(새 기능 추가 순서: 모델→스키마→서비스→라우터)에 어긋난다.

- **조치**: `services/stock_search_service.py` 신규 생성, `_search_naver`/`_search_yahoo` 및 관련 헬퍼 이동. 라우터는 서비스 함수 호출만 남김.
- **우선순위**: 중간.

### (c) `providers/kis_provider.py:105-114` vs `providers/kiwoom_provider.py:79-88` — 에러 매핑 중복

`httpx.HTTPStatusError`(5xx/4xx 분기 + json 파싱 폴백)·`ConnectError`/`TimeoutException` 매핑 로직이 거의 동일한 구조로 반복(브로커별 에러 메시지 키만 `msg1` vs `return_msg`로 다름). 이미 `providers/_retry.py`(토큰 재시도)·`base.py`(포지션 변환)는 공유되는데 이 부분만 안 됨.

- **조치**: `providers/http_client.py` 또는 신규 `providers/_error_mapping.py`에 공통 매핑 함수 추출, 브로커별 에러 메시지 키만 파라미터로 받도록 설계. 두 provider 파일에서 호출로 교체.
- **우선순위**: 낮음.

### (d) `backtest_service.py` (448줄) — 상관관계 분석 분리

`run_backtest`(백테스트 실행)와 `compute_correlation`(상관관계 분석)은 별도 스키마(`BacktestRunRequest/Result` vs `CorrelationRequest/Result`)를 쓰는 완전히 독립된 기능인데 한 파일에 공존한다.

- **조치**: `services/correlation_service.py` 신규 생성, `compute_correlation` 및 관련 헬퍼 이동. `api/v1/backtest.py`의 해당 엔드포인트 import만 갱신.
- **우선순위**: 중간.

### (e) `dividend/orchestrator.py` (426줄) — ticker 설정 CRUD 분리

배당 집계 오케스트레이션(`get_dividend_data` 등) 본류 외에 ticker 설정 CRUD(`get/upsert/delete_ticker_settings`, 357–427줄)가 별개 관심사로 붙어있다.

- **조치**: `services/dividend/ticker_settings_service.py` 신규 생성, 3개 CRUD 함수 이동. `orchestrator.py`가 이 함수들을 내부적으로 호출한다면 import로 교체.
- **우선순위**: 낮음~중간.

### (f) `tax_service.py` (442줄) — 연금 납입 현황 분리

양도세/배당세/손실수확 로직과 연금 납입 현황(`calc_pension_contribution_status`, `GET /tax/pension-contribution` 전용)은 무관한 도메인인데 혼재한다.

- **조치**: `services/pension_contribution_service.py` 신규 생성, `calc_pension_contribution_status` 및 관련 헬퍼 이동. `api/v1/tax.py`의 해당 엔드포인트 import만 갱신.
- **우선순위**: 낮음~중간.

## 공통 검증 절차 (항목별로 반복)

1. 이동 대상 함수의 모든 호출부를 `grep -rn "함수명" backend/`로 확인.
2. 새 파일 생성 → 함수 이동 → 원본 파일에서 삭제 → import 경로 갱신.
3. `backend/CLAUDE.md`의 `services/`(또는 `schemas/`) 목록 갱신.
4. `cd backend && uv run pytest && uv run ruff check . && uv run mypy app/`.

## 주의사항

- 6개 항목 모두 순수 코드 이동(로직 변경 없음)이므로 API 응답/동작에 변화가 없어야 한다 — 관련 기존 테스트가 그대로 통과하면 검증 완료로 간주.
- 서로 다른 파일을 건드리므로 여러 세션이 동시에 다른 항목을 진행해도 충돌 없음. 단, (a)와 (b)~(f)는 각각 완전히 무관한 파일이라 순서 무관.
