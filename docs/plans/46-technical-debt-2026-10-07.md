# 46. 기술부채 감사·처리 (2026-10-07)

계획 45(PR #113) 이후 코드 변경은 `be5b32e`(dev.sh PATH 수정)뿐이었다.
그래서 45의 이관 목록을 다시 확인하고, 그동안 다루지 않은 축(날짜 기준, 캐시 무효화 대칭성, 고아 엔드포인트, 로컬/CI 도구 차이)으로 새로 스윕했다.
스윕 결과는 모두 코드를 직접 읽어 재확인한 뒤 반영했다.

- 고전적 부채: TODO 0건, noqa/type:ignore 9건, eslint-disable 15건. 거의 소진된 상태다.
- 브랜치: `fix/tech-debt-2026-10-07`
- 사용자 선택: 배치 A·B·C 전부. 고아 엔드포인트는 삭제(단, 종목별 배당월 설정은 이관).

## 배치 A — 실버그 (`798fed7`)

**A1. 사용자 기준 "오늘"을 UTC로 계산**
운영 서버는 UTC라 KST 00:00~09:00에 날짜가 전날로 잡힌다. `utils/kst.today_kst()`로 바꿨다.
- `rebalancing/plan_notifications.py`: 세금·시장신호 게이트 알림 dedup 키. 같은 파일의 일일한도 키는 이미 KST였다.
- `dca_service.py`: 목표 시작 후 경과 개월 수(매월 1일 새벽에 한 달 밀림)
- `tax_service.estimate_overseas_transfer_tax`: 기본 과세연도(1월 1일 새벽에 전년 세율)
- `goal_age_recommendation_service.age_group_from_birth_year`: 나이
- 테스트: `test_kst_today_boundaries.py`. `app.utils.kst.datetime`을 "UTC 12/31 20:00 = KST 1/1 05:00"으로 고정해 4건을 확인한다. 수정 전 코드에서는 4건 모두 실패한다.

**A2·A3. 계좌 캐시 무효화 함수 두 벌의 드리프트**
- `invalidate_asset_account_caches`(계좌 CRUD·포지션 수정·external 등록)는 월별 추이와 배분 이력을 지우지 않았다. 반면 sync용 `invalidate_account_caches`는 지웠다.
  - 결과: 계좌를 삭제(`is_active=False`)해도 월별 추이에 최대 5분, 배분 이력에 최대 하루 남았다.
- 두 함수를 합쳤다. `invalidate_asset_account_caches`가 합집합을 지우고, `invalidate_account_caches`는 계좌 상세 키 없이 위임하는 래퍼로 남겼다(호출부·patch 경로 보존).
- 수동 `/sync`는 `sync_account()`와 `sync_account_now()`에서 같은 캐시를 두 번 지우고 있었다(키 스캔 약 8회 중복). `sync_account_now`는 이제 계좌 상세 키만 추가로 지운다.

**A4. `GET /settings`가 저장된 0을 None으로 반환**
`float(x) if x else None` → `is not None`. 검증기는 0을 허용하고 같은 함수의 다른 필드는 이미 `is not None`이었다.
프론트는 0과 null을 모두 truthiness로 다루므로 화면 동작은 그대로다. 달라지는 점은 연수익률 0%가 빈칸 대신 0으로 보이는 것뿐이다.

**A5. 리밸런싱 계좌 그룹 실패 로그** (계획에서 축소)
- 처음 계획은 `exc_info`와 Sentry capture를 붙이는 것이었다.
- 그런데 Sentry는 기본으로 스택 지역변수를 전송하고, 이 경로의 프레임에는 복호화된 증권사 자격증명이 있다. `token_refresh`가 같은 이유로 Sentry를 쓰지 않는 것과 같은 판단이다.
- 그래서 예상 밖 예외(`HTTPException`·`AppError`·`SyncError`가 아닌 것)만 error 레벨로 올리고 `error_type`을 남기도록 축소했다.

## 배치 B — 고아 코드·도구 정합성 (`b3585d8`)

**고아 엔드포인트 삭제** (경로·함수명을 backend·frontend·android·scripts 전체에서 grep해 호출처 없음을 확인)
- `/backtest/portfolios` CRUD와 `BacktestPortfolio` 모델
  - 2026-05 `f9a8b7c6d5e4_add_unified_portfolios`에서 데이터를 통합 `portfolios`로 옮긴 뒤 남은 레거시였다.
  - 운영 DB `backtest_portfolios`는 0행이었다(읽기 전용 count, 2026-10-07).
  - 드롭 마이그레이션 `bt1_drop_backtest_portfolios`(down에서 테이블 재생성)를 추가했다.
- `/backtest/correlation`과 유일한 호출처 `correlation_service.py`, `correlation_key`
- `PATCH /assets/{id}/target-portfolio`. UI는 `batch-target-portfolio`를 쓴다.
  - 이 단일 PATCH와 batch 둘 다 `portfolio_id`가 본인 소유인지 확인하지 않았다. batch에 `get_owned_or_404`를 추가했다.
  - 읽는 쪽이 본인 포트폴리오 id와 비교만 해서 유출은 없었지만, 남의 id를 저장할 수 있었다.
- 미사용 `NotFoundError`

**프론트**
- `invalidateRebalancingHistoryData`는 "주문 실행 후"용으로 만들어 놓고 연결하지 않은 상태였다. 그래서 실행 직후 이력 탭이 최대 30초(staleTime) 동안 이전 목록을 보여 줬다. `handleExecute`에 연결했다.
- 테스트에서만 쓰던 export 3개(`SharesCell`·`fmtKrwNullable`·`getPortfolioHorizon`)와 고아 API 래퍼를 삭제했다.
- `usePortfolioTabFetching`의 하드코딩 프리픽스를 `QUERY_KEYS`에서 파생하도록 바꿨다. 아무 쿼리도 쓰지 않던 `"dart-disclosures"`는 제거했다.
- 미사용 타입 별칭(`*FormData`, `AssetManagementTab` 등)은 const 옆에 짝으로 두는 관례 패턴이고 런타임 비용이 없어 유지했다.

**도구**
- `make install-backend`: `uv pip install -e` → `uv sync --extra dev`(uv.lock 기준, CI와 동일)
- `make lint`: `ruff format --check`와 eslint `--max-warnings 0`을 추가했다. pre-commit eslint 훅에도 `--max-warnings 0`을 넣었다.
- `.PHONY` 보완, `format`이 `format-backend`를 재사용하도록 함
- CI 프론트 job에 `timeout-minutes: 20` 추가, 중복 `--run` 제거

## 배치 C — `GoalSettingWizard` 분해 (`c15ae18`)

- 560줄이던 파일을 본체 121줄 + `components/invest/goalWizard/` 6개 파일로 나눴다.
  - 훅: `useGoalWizardFeasibility`, `useRecommendationStepAutosave`
  - 단계 컴포넌트: `GoalWizardInputSteps`(1·2·5단계), `GoalWizardFeasibilitySteps`(3·4단계), `GoalWizardRecommendationStep`(6단계), `GoalWizardLoading`
- 단계 컴포넌트는 계획의 6파일 대신 3파일로 묶었다. 단계마다 파일을 두면 파일당 30~50줄이라 오히려 탐색이 늘어난다.
- 검증
  - 분해 전 1~6단계의 12개 상태(로딩·빈 상태·불가능 목표 포함) 렌더 DOM을 스냅샷으로 고정했다.
  - 분해 후 재생성한 스냅샷이 기준과 바이트 단위로 같았다.
  - 하네스는 DOM 스냅샷이 취약해 커밋하지 않았다(계획 43과 같은 방식).
  - 기존 테스트 14건은 수정 없이 통과했다.

## 이관

- 제품 판단이 필요한 항목
  - 자산추이 `CASH_STOCK` 잔차 라벨
  - `HIGH_CORR` 배당주기 예외
  - N6(`jobs/dca_cash_shortfall.py`. 사용자 단위 `monthly_deposit_amount`를 DCA 알림마다 비교)
- **종목별 배당월 override**(`/dividends/ticker-settings`)
  - 편집 UI는 없다. 그런데 저장된 `user_ticker_settings`는 배당 계산(`_dividend_queries.py`)에 여전히 우선 적용되고, "수동/자동" 배지 3곳에도 반영된다.
  - 편집 UI를 복원할지, 기능 전체(테이블·`is_manual` 배지)를 제거할지 판단이 필요하다.
- `settings.py`의 8중 `{enabled}` 토글 모델·엔드포인트 → 스펙 테이블화. API 스키마에 영향이 있어 단독 세션으로 한다.
- 메이저 업그레이드(React 19, recharts 3, tailwind 4), 2-leg 실패 leg 자동 재시도, 정기 자동매수

## 검증

```bash
cd backend && .venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80 -q   # 2487 passed, 90.87%
cd backend && .venv/Scripts/python.exe -m ruff check app tests && .venv/Scripts/python.exe -m ruff format --check app tests && .venv/Scripts/python.exe -m mypy app
cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src --max-warnings=0 && npx prettier --check src
cd frontend && npm run test -- --coverage && npm run build   # 1614 passed
cd backend && .venv/Scripts/python.exe -m alembic upgrade tx1_add_income_bracket:bt1_drop_backtest_portfolios --sql   # 오프라인 렌더(downgrade도 동일)
```

- 테스트 수 변화: 백엔드 2499 → 2487(삭제 엔드포인트 −20, 신규 +8). 프론트 1635 → 1614(죽은 코드·래퍼 테스트 삭제, 실행 후 무효화 +1).
- 로컬 `.env`의 DB가 운영 Supabase이고 Docker가 없어서 마이그레이션은 실 DB에 적용하지 않았다.
  - 오프라인 SQL 렌더로 upgrade와 downgrade 양방향을 확인했다. 현재 DB 리비전은 `tx1_add_income_bracket`이라 체인이 맞다.
  - 실제 적용은 Render preDeploy가 한다. CI는 자체 Postgres에서 `upgrade head`와 `downgrade -1` 왕복을 검사한다.
- 실브라우저 검증은 하지 않았다.
