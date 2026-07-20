# 계획 11: `goal_recommendation_service.py` (1113줄) 책임 분리

**리스크: 중간 — 순수 이동/분리 리팩토링이지만 파일이 크고 목표 역산 추천(실제 자금 이동 없는 조회 전용 기능이라 리스크 자체는 낮음) 핵심 로직이라 신중히.**

## 배경 (Why)

`backend/app/services/goal_recommendation_service.py`가 백엔드에서 가장 큰 서비스 파일(1113줄)이다. 이미 `goal_return_solver.py`(목표 수익률 역산 순수 계산), `recommendation_universe.py`(큐레이션 ETF 유니버스)가 서브모듈로 분리되어 있는데도 이렇게 큰 이유는, 서로 독립적인 **3개 책임**이 한 파일에 남아있기 때문이다:

1. **MVO 최적화 엔진** (`_optimize_goal_portfolio`, 303–477줄) — SLSQP 최소분산 최적화. `portfolio_optimizer.py`의 골격을 재사용한다고 자체 주석에 명시. DB/Redis 의존 없는 순수 계산.
2. **후보 종목 관리/영속화** (`_apply_index_region_preference`, `_seed_candidate_tickers`, `_persist_added_candidates`, `_get_or_seed_candidates`, `existing_items_from_positions`, `_active_account_tax_types`, 156–219줄 + 480–601줄) — DB 락과 lost-update 방지를 포함한 CRUD성 로직.
3. **API 진입점 2종** (`get_goal_recommendation`/`_compute_goal_recommendation` 전체 자산 기준, 604–775줄 vs `get_horizon_recommendations`/`_compute_horizon_recommendations`/`_build_horizon_result` 투자기간별, 777–1114줄).

1·2번을 분리하면 3번(진입점)만 남아 파일당 300~400줄로 자연스럽게 줄어든다.

## 현재 코드 상태 (실행 전 라인 번호 재확인 필수 — 다른 세션이 먼저 수정했을 수 있음)

- `_optimize_goal_portfolio` 및 관련 헬퍼: 303–477줄
- 후보 관리 함수군: 156–219줄, 480–601줄
- 전체 자산 기준 진입점: 604–775줄
- 투자기간별 진입점: 777–1114줄

## 구현 단계

1. **`goal_portfolio_optimizer.py` 신규 생성**: `_optimize_goal_portfolio`와 이 함수만 참조하는 헬퍼를 이동. `portfolio_optimizer.py`와 이름이 유사하니 docstring에 "목표 역산 추천 전용 — 일반 효율적 프론티어 최적화는 portfolio_optimizer.py 참고"로 구분 명시.
2. **`goal_candidate_service.py` 신규 생성**: 후보 종목 관리/영속화 함수군 이동. DB 세션·락 관련 의존성 그대로 옮기고, 기존 함수 시그니처는 변경하지 않아 호출부(진입점 함수들) 수정을 최소화.
3. **`goal_recommendation_service.py`에는 API 진입점 2종만 남김**: `_optimize_goal_portfolio`/후보 관리 함수 호출부를 새 모듈 import로 교체.
4. **순환 참조 확인**: 세 파일 간 import 방향이 `goal_recommendation_service.py` → `goal_portfolio_optimizer.py`/`goal_candidate_service.py` 단방향인지 확인 (역방향 없어야 함).
5. **테스트 이동**: 기존 `tests/test_goal_recommendation_service.py`(또는 유사 파일)에서 최적화 로직/후보 관리 로직만 테스트하는 케이스를 파일 분리에 맞춰 재배치하거나, import 경로만 갱신(테스트 자체 로직은 변경 불필요).
6. **backend/CLAUDE.md 갱신**: `services/` 목록에 `goal_portfolio_optimizer.py`, `goal_candidate_service.py` 두 줄 추가, `goal_recommendation_service.py` 설명에서 책임 범위 수정.
7. **검증**: `cd backend && uv run pytest -k goal_recommendation -v && uv run pytest && uv run ruff check . && uv run mypy app/`.

## 주의사항

- 이 서비스는 `frontend`의 `RecommendationCard`/`GoalRecommendationPreviewCard`가 호출하는 API(`GET /rebalancing/goal-recommendation/by-horizon` 등)의 구현체다 — 함수 이동만 하고 라우터(`api/v1/rebalancing.py`)의 import 경로만 갱신하면 API 응답 스키마/동작은 전혀 변하지 않아야 한다. 순수 리팩토링이므로 API 응답을 diff해서 동일함을 확인하는 것을 권장.
- [08-invest-plan-tab-audit.md](08-invest-plan-tab-audit.md)가 같은 도메인(목표 역산 추천)의 프론트 카드를 다뤘으나 파일이 다르므로(프론트 vs 백엔드) 충돌 없음.
