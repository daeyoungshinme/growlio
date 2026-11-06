# 114. 113 이관 기술부채 처리 (2026-11-06)

> **진행 상태**: A~D 구현 완료, 브랜치 `chore/tech-debt-2026-11-06b`. **B는 공유 Supabase에 수동 적용해야 한다**(아래 배포 순서).

## 배경

"남은 기술부채 수정 계획" 요청이다. 113(PR #237)이 머지된 뒤 main에 들어온 것은 Dependabot #238~#240(Tailwind v4 마이그레이션 포함)뿐이다. Tailwind v4 쪽은 깨끗했다. `tailwind.config`가 없고, v3 클래스명도 남지 않았고, frontend/CLAUDE.md에도 반영돼 있다. 그래서 113 "이관 / 보류" 목록을 main 코드와 대조해 처리했다.

사용자 결정은 두 가지다.
- 시세 파이프라인은 **내부 순서(국내 → Yahoo → KIS)로 통합**한다. KIS 폴백은 요청에 지정된 계좌로만 하고, 지정이 없으면 폴백하지 않는다.
- 마이그레이션 두 건(goal_start_date Date 전환, FK 인덱스)을 **이번에 포함**한다.

---

## 배치 A — 시세 파이프라인 통합 (동작 변경)

| # | 문제 | 수정 |
|---|---|---|
| A1 | `/stocks/price`·`prices-batch`는 Yahoo → 국내 → 지정 계좌 KIS 순서였고, `fetch_prices_batch`는 국내 → Yahoo → 아무 KIS 계좌 순서였다. 같은 일을 두 벌 구현했다 | `fetch_prices_batch(..., kis_accounts=)`에 티커별 소유 계좌를 넘기면 KIS 폴백은 그 계좌로, 매핑된 티커만 시도한다. `None`이면(내부 호출 4곳) 지금처럼 아무 KIS 계좌를 쓴다 |
| A2 | 라우터의 `_kis_price_fallback`·`_resolve_batch_prices` | 지우고 `_price_entries` 하나로 모았다. 단일 조회도 같은 경로를 탄다. 계좌 소유 검증(`get_owned_account`) 실패는 지금처럼 조용히 건너뛴다 |
| A3 | 표시용 JSON 캐시 `current_price_display_key`가 원시 캐시와 따로 있었다 | 제거했다. 라우터 결과도 원시 캐시(15분)를 내부와 공유하고, 환산은 매 요청 한다. 그래서 fallback 환율로 환산한 금액이 캐시에 남을 경로도 사라졌다 |
| A4 | **실버그**: `price_via_kis`가 시장 코드를 대소문자 구분으로 판정했다. 소문자 `kospi`가 KIS 폴백까지 가면 국내 종목을 해외 시세 TR로 조회했다 | 함수 입구에서 `market.upper()`. 라우터도 입구에서 정규화한다 |
| A5 | 배치 응답이 ticker 키라 같은 티커가 여러 시장으로 오면 충돌한다 | 계약을 유지하고 docstring에만 적었다 |
| A6 | **실버그(작업 중 발견)**: `CacheStore`에 `__len__`만 있어 빈 store가 falsy였다. 그래서 `if not cache: return`(`_write_cached_prices` 등)과 `if cache:`(배당 집계·포트폴리오 최적화·실행 후 무효화 등 약 10곳)가 콜드 스타트 직후, 곧 Render 슬립에서 돌아온 직후 캐시 쓰기를 통째로 건너뛰었다 | `__bool__ = True`. 회귀 테스트를 넣었다 |

**동작 변화**(PR 본문에도 적음):
- 국내 종목은 Naver/pykrx 값이 먼저 나온다. 그래서 거래 입력 화면 현재가가 Yahoo 값과 조금 다를 수 있다.
- 가격 0은 누락으로 본다.
- 지정 계좌가 없으면 KIS 폴백을 하지 않는다. 이전과 같다.

## 배치 B — 마이그레이션 (공유 Supabase 수동 적용)

| 리비전 | 내용 |
|---|---|
| `fk1_rebalancing_fk_indexes` | 111 E1 인덱스 3개(`rebalancing_plans.portfolio_id`, `rebalancing_executions.portfolio_id`, `rebalancing_plan_legs.execution_id`). `CREATE INDEX CONCURRENTLY IF NOT EXISTS`(autocommit_block). 모델 `__table_args__`에도 추가해 CI `alembic check`와 맞췄다 |
| `gd1_goal_start_date_to_date` | `user_settings.goal_start_date` timestamptz → date. `USING (goal_start_date AT TIME ZONE 'Asia/Seoul')::date`라서 UTC 자정(현재 저장)이든 옛 KST 자정(전날 15:00 UTC)이든 같은 날짜가 된다. downgrade는 UTC 자정으로 되돌린다 |

코드 변경:
- 모델은 `Mapped[date | None] = mapped_column(Date)`.
- 설정 저장은 `datetime.combine` 없이 다른 목표 필드처럼 `_GOAL_PLAIN_FIELDS`로 처리한다.
- `dca_service`에서 `.date()`와 isinstance 분기를 지웠다.
- `ExternalGoalSettings.goal_start_date: date`. nestlio 소비 측(`nestlio/app/schemas/financial_goal.py`)이 이미 `date`로 받는다. 응답 형식은 `"2024-01-01T00:00:00Z"` → `"2024-01-01"`.

**배포 순서**:
1. 읽기 전용 확인 쿼리를 돌린다: `SELECT goal_start_date::time, count(*) FROM user_settings WHERE goal_start_date IS NOT NULL GROUP BY 1`. 결과가 00:00과 15:00뿐이어야 한다. 다른 시각이 있으면 멈추고 값을 확인한다.
2. `backend/.env`의 `MIGRATION_DATABASE_URL`을 운영 DB로 지정하고 `uv run python scripts/bootstrap_alembic.py && uv run alembic upgrade head`를 실행한다.
3. **곧바로** 머지·배포한다. 2와 3 사이에는 옛 코드의 `goal_start_date.date()`(적립 분석)가 date 값에서 실패한다.

## 배치 C — 코드 정리 (동작 불변)

- **C1** private 이름 교차 import 4건을 공개 이름으로 바꿨다: `upsert_snapshot`, `cagr_lookback_years_from_settings`, `MARKET_NOTES`, `RECOMMENDATION_DRIFT_THRESHOLD_PCT`. 테스트 patch 문자열도 같이 고쳤다.
- **C2** `_stock_unrealized_from_rows`(4튜플, 첫 값만 사용) → `_overseas_unrealized_from_rows`(float). 국내 평가액·과세이연 계산은 죽은 코드라 지웠다. 해당 테스트는 해외만 검증하도록 바꿨다.
- **C3** `websockets`·`watchfiles`를 운영 의존성에서 dev extra로 옮겼다. 앱 import가 0건이고, 운영 CMD에 `--reload`도 WS 라우트도 없다. Docker 이미지는 extra를 설치하지 않는다.
- **C4** CI pytest `-x` 제거. 첫 실패에서 멈추면 나머지 실패가 가려진다.
- **C5** `components/common/ToggleSwitch.tsx` → `ToggleRow.tsx`. 내보내는 것은 `ToggleRow`뿐이다.

## 배치 D — 문서

- backend/CLAUDE.md: `price_service` 단일 경로와 `kis_accounts` 규칙, `CacheStore.__bool__` 함정.
- frontend/CLAUDE.md: `ToggleRow` 파일명.

---

## 검증

- 백엔드: ruff·ruff format·mypy 0건. pytest 전체 통과, 커버리지는 PR 본문에 기록.
- 프론트: tsc(앱·테스트)·eslint `--max-warnings 0` 0건, 관련 vitest 통과.
- 마이그레이션: `alembic upgrade dc2_drop_dead_columns:head --sql`와 downgrade `--sql`로 DDL을 확인했다. 실DB 판정은 CI(`alembic upgrade head`·`alembic check`, postgres 16)가 처음이다.
- **확인 못 한 것**:
  - KIS 실폴백(실계좌)
  - 공유 Supabase 적용(사용자 실행)
  - 거래 입력 화면 현재가 브라우저 확인

## 작업 시 함정

- worktree에는 `backend/.env`가 없다. 테스트는 CI와 같은 환경변수(`KIS_CRED_ENCRYPTION_KEY`·`DATABASE_URL`·`APP_ENV=development`)로 돌린다. 로컬 `.env`를 복사하면 공유 Supabase를 가리킬 수 있다.
- 셸에 `VIRTUAL_ENV`가 main 작업트리 venv로 잡혀 있으면 `uv run`이 경고하고 무시한다. `unset VIRTUAL_ENV`로 푼다.
- 빈 컨테이너 객체에 `if cache:`를 쓰지 않는다. `is None`으로 판정한다(A6).

## 계속 보류

- 600줄대 파일 4개(`goal_portfolio_optimizer` 678, `rebalancing/service` 649, `_goal_recommendation_common` 614, `tax_action_service` 609): 분할 변경량에 비해 얻는 게 적다.
- 테스트 폴더 배치 규칙, Dockerfile `PYTHONPATH`와 이미지 스모크: 유지한다.
- yfinance 1.x, React 19·recharts 3·TS 7 메이저: 기존 결정대로 둔다. Tailwind 4는 #240으로 끝나 목록에서 지웠다.
- 111 낮은 순위 보고 건과 사용자 확인 항목(KIS 실계좌, Render 로그, APK CI, 세법)은 그대로다.
- **사용자 실행**: 병합된 로컬 브랜치 삭제(`git branch --merged origin/main`, 34개).
