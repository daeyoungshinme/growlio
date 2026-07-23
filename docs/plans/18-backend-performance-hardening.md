# 계획 18: 백엔드 성능 개선 (쿼리 병렬화 + 캐시 계층 경량화 + job 보일러플레이트 통일)

**리스크: 낮음~중간 — 1·4번은 순수 리팩터(로직 불변), 2번은 계산 결과가 동일해야 하는 리팩터(회귀 테스트 필수), 3번은 캐시 계층 내부 구조 변경(무효화 동작 재검증 필요).**

## 배경 (Why)

2026-07-23 "전반적 성능개선" 감사(3개 병렬 조사 에이전트, 프론트 성능/백엔드 성능/구조)에서 백엔드 API 응답속도에 영향을 주는 지점이 발견됨. 기존 감사(계획10~12, "백엔드 성능 개선 2026-06-22")는 인덱스·캐시키·SCAN 패턴을 다뤘고, 이번엔 그 이후 새로 추가된 기능(목표 역산 추천, Redis 제거 후 in-memory 캐시)에서 드러난 지점.

## 1. `composition_calculator.fetch_position_maps` 순차 쿼리 → 병렬화 (Quick win)

**현재 상태:** `backend/app/services/composition_calculator.py:80-84` 부근 `fetch_position_maps()`가 `_fetch_snapshot_positions()`와 `_fetch_current_positions()`를 순차 `await`. 같은 파일의 `build_asset_totals()`는 동일한 두 쿼리를 이미 `asyncio.gather`로 병렬화했는데, `build_portfolio_overview()` 경로(포트폴리오 탭에서 자주 호출되는 화면, 10/min 레이트리밋)만 순차 버전을 그대로 사용 중.

**구현:**
1. `fetch_position_maps()` 내부를 `asyncio.gather(_fetch_snapshot_positions(...), _fetch_current_positions(...))`로 교체 — `build_asset_totals()`의 기존 패턴 그대로 재사용.
2. 관련 테스트(`test_composition_calculator.py` 등) 통과 확인.

## 2. `goal_recommendation_service.py` 기간별 추천 순차 DB 라운드트립 축소

**현재 상태:** `backend/app/services/goal_recommendation_service.py:706-753` 부근, 기간별(`by-horizon`) 추천 계산이 `for horizon in InvestmentHorizon: for tax_type in AccountTaxType:` 이중 루프 안에서 조합마다 `build_portfolio_overview(...)`를 순차 호출(최대 5×3=15조합). 주석에 "DB 세션 동시접근 불가 + 조합 간 상태 의존"으로 병렬화를 명시적으로 포기한 상태. `build_portfolio_overview`는 캐시 미스 시 쿼리 4개를 실행하므로, 캐시 미스 상황(목표 설정 변경 직후, 신규 유저 최초 진입)에서 이 요청 하나가 최대 ~60회 DB 왕복을 순차로 발생시킴. 결과는 `TTL_GOAL_RECOMMENDATION`(10분)로 캐시되지만, 최초/무효화 직후 진입 시 화면 지연이 수 초 단위로 체감될 수 있음.

**구현:**
1. 루프 진입 전에 유저의 전체 계좌 스냅샷/포지션을 **1회**만 조회(계좌 ID 전체 범위로 `_fetch_snapshot_positions`/`_fetch_current_positions` 호출).
2. 조합별(horizon, tax_type) 필터링은 조회된 결과를 메모리에서 계좌 태그(`investment_horizon`/`tax_type`) 기준으로 슬라이싱하는 방식으로 변경 — DB 재조회 없이 순수 계산만 반복.
3. "조합 간 상태 의존" 주석이 정확히 무엇을 가리키는지 먼저 git blame/코드 흐름으로 확인 — 만약 각 조합이 이전 조합의 결과(예: 이미 배정된 후보 종목 제외)에 의존한다면, 그 의존관계는 유지하되 **DB 조회만** 1회로 줄이는 선에서 범위를 제한할 것(최적화 로직 자체는 건드리지 않음).
4. 리팩터 전후 결과가 동일한지 확인하는 회귀 테스트 필수 — 기존 `test_goal_recommendation.py`의 기간별 추천 케이스가 리팩터 후에도 동일 출력을 내는지 스냅샷 비교.

## 3. `app/core/cache_store.py` — 캐시 계층 경량화

**현재 상태:**
- `scan()`이 전체 `self._data` dict를 순회하며 정규식 매칭(O(n)), get/set/scan이 전부 단일 `self._lock`(`cache_store.py:73-80`) 공유. `invalidate_portfolio_overview_cache` 등 무효화 헬퍼가 계좌 동기화·거래 입력마다 `scan()`을 여러 번 호출.
- 만료(expiration)는 접근 시에만 지워지는 lazy 방식이라, 재방문하지 않는 유저의 캐시 엔트리는 TTL이 지나도 dict에 계속 남아 메모리와 `scan()` 비용을 함께 키움.
- Redis 제거 후 단일 프로세스 전제(`render.yaml`에 `--workers` 미지정, free plan 단일 인스턴스)로 현재는 정합하나, 워커/인스턴스를 늘리면 캐시 적중률이 인스턴스 수에 반비례로 급락하고 무효화도 프로세스 로컬이라 다른 워커가 stale 데이터를 계속 반환하는 구조적 리스크가 있음.

**구현 (이번 세션 범위 — 1·2번만):**
1. **주기적 sweep**: `app/scheduler.py`에 10~15분 간격 job 추가해 만료된 키를 능동적으로 청소(`cache_store.py`에 `sweep_expired()` 메서드 추가). 기존 `jobs/_job_helpers.py` 패턴 참고.
2. **prefix 인덱스(선택, 여유 있으면)**: 무효화 헬퍼들이 실제로 필요로 하는 건 "특정 prefix로 시작하는 키 목록"뿐이므로, `scan()`의 정규식 풀스캔 대신 prefix→key-set 인덱스(dict of sets)를 유지해 무효화 시 인덱스 조회만으로 대상 키를 찾도록 개선. `set()`/`delete()` 시 인덱스도 함께 갱신.
3. **범위 밖(다음 세션 또는 확장 시점에 별도 진행)**: 다중 워커/인스턴스 확장 시 Redis(또는 Postgres LISTEN/NOTIFY 기반 무효화) 재도입 여부는 별도 아키텍처 결정 사항 — 이번엔 "확장 시 이 트레이드오프가 있다"는 것만 `backend/CLAUDE.md`의 `cache_store.py` 설명에 한 줄 추가해 문서화.

## 4. 알림 job 보일러플레이트 통일

**현재 상태:** `jobs/` 13개 중 7개 알림성 job 가운데 5개(`market_signal_alert`, `market_signal_daily_digest`, `year_end_tax_reminder`, `recommendation_drift_alert`, `rebalancing_alert`, `stock_price_alert`, `exchange_rate_alert` 중 다수)는 이미 `jobs/_job_helpers.py`의 `run_alert_job` 패턴으로 통일됐지만, `jobs/goal_achievement.py`와 `jobs/monthly_report.py`는 "유저 조회 → `asyncio.Semaphore(3)` → per-user 세션 → `get_dashboard_summary` → 발송 → `AlertHistory` 저장" 패턴을 각자 ~80줄씩 재구현.

**구현:**
1. `_job_helpers.run_alert_job`에 "유저별 동시성 제한(세마포어) + per-user 세션" variant를 추가(기존 시그니처와 호환되게 옵션 파라미터로).
2. `goal_achievement.py`/`monthly_report.py`를 이 공통 헬퍼를 쓰도록 리팩터 — 발송 조건 판단 로직(순수 함수)은 그대로 두고 boilerplate만 교체.
3. 두 job의 기존 테스트가 리팩터 후에도 통과하는지 확인.

## 검증

```bash
cd backend && uv run pytest && uv run ruff check . && uv run mypy app/
```

각 항목은 독립적으로 진행 가능(서로 다른 파일) — 1번이 가장 빠르고 안전한 착수 지점, 2번이 체감 효과가 가장 큼, 3-1번(sweep)은 낮은 리스크로 바로 가능, 3-2번(prefix 인덱스)은 여유 있을 때, 4번은 순수 유지보수성 개선.
