# 45. 계획 44 이관 기술부채 처리 (2026-10-06)

계획 44의 배치 A·B는 PR #112로 main에 머지됐다. 이 문서는 그때 이관한 **배치 C(중위험 구조 정리 3건)**와
**신규 관찰 항목** 가운데 저위험 항목을 처리한 기록이다.
착수 전에 3건 모두 코드에 그대로 남아 있는 것을 확인했다.

- 원칙: 동작은 바꾸지 않고 구조만 정리한다. 기존 테스트를 회귀 안전망으로 쓴다.
- 브랜치: `fix/tech-debt-2026-10-06b`

## 구현 완료

### 백엔드 (`c9a32f4`)

**C1. quick-execute 로직을 서비스로 이동**
- `api/v1/rebalancing_execution.create_rebalancing_execution_plan`(약 160줄)이 하던 일을 옮겼다.
  - 대상: 포트폴리오·알림 행 조회, PER_ACCOUNT 검증, pending·시장신호 게이트, 플랜 생성, 안내 발송
  - 위치: `services/rebalancing/quick_execute_service.quick_execute_plan()`
- 서비스는 `QuickExecuteStatus` enum과 `QuickExecuteOutcome`(메시지를 만드는 데 필요한 원자료)만 반환한다.
- 사용자에게 보여 줄 문구는 라우터의 `_QUICK_EXECUTE_MESSAGES`가 만든다. 문구는 바이트 단위로 기존과 같다.
- override 계좌의 소유권 검증(`get_owned_account`)은 라우터가 콜백(`verify_account_owned`)으로 넘긴다.
  서비스가 `app.api`를 import하는 선례가 없어서 계층이 거꾸로 의존하지 않게 했다.
- 입력 오류(404/422/400)는 `HTTPException`을 그대로 썼다.
  - 기존 테스트가 `HTTPException`을 기대한다.
  - 422 전용 `AppError`가 없다.
  - 서비스 쪽 선례도 있다(`execution_service`, `plan_execution`, `alert_scope`).
- 테스트: patch 경로 23곳을 서비스 모듈로 옮겼다. `get_owned_account` patch는 라우터 경로에 그대로 두었다(콜백이 호출할 때 조회하므로 유효하다).

**C2. 목표 달성 알림 3중 블록 통합**
- `jobs/goal_achievement`의 ASSET·DEPOSIT·DIVIDEND 블록을 `_GoalSpec` 테이블과 `_notify_goal`로 합쳤다.
- ASSET만 다른 점(현재 금액을 대시보드 총자산에서 가져옴)은 `current_from_total_assets` 플래그로 처리했다.
- 메시지, 로그 이벤트명, push `data`, 블록별 commit, 순서는 바꾸지 않았다. 기존 테스트 9건이 수정 없이 통과한다.

### 프론트 (`b9e2cb5`)

**C3. 추천 탭의 미설정·빈 상태 공통화**
- `RecommendationEmptyStates.tsx`(`RecommendationSetupCta`, `RecommendationNoItems`)를 새로 만들어 연령대·전체·기간별 탭에 적용했다.
  CTA 스타일은 `recommendationCardModel.SETUP_CTA_ACTION_CLASS`로 뺐다(react-refresh 규칙상 컴포넌트 파일에서 상수를 export할 수 없음).
- 요약문의 지표 조각은 `formatRecMetricParts(rec, includeExpected)`로 통합했다. 연령대·기간별 탭이 `" · "`로 이어 붙인다. 렌더되는 텍스트는 같다.
- 전체 탭은 문장형이라 요약문은 그대로 두고 빈 상태 컴포넌트만 적용했다.
- `RecommendationHorizonTab`의 `stockAccounts` 독스트링을 실제 동작에 맞게 고쳤다. 실제로는 전체 계좌를 받아 내부에서 기간·세제유형으로 필터한다.

**관찰 항목**
- Sentry
  - `reactRouterV7BrowserTracingIntegration`과 `withSentryReactRouterV7Routing(Routes)`를 적용했다.
  - 이제 트랜잭션이 raw URL이 아니라 라우트 패턴 단위로 묶인다.
  - DSN이 설정되지 않은 환경에서는 동작이 바뀌지 않는다.
- `useCandidateOverlap`
  - 편집 중인 목록은 400ms 디바운스한다. 첫 목록은 바로 조회한다.
  - `keepPreviousData`를 써서 기다리는 동안 이전 결과를 계속 보여 준다.
- 테스트: `formatRecMetricParts` 3건, 디바운스 1건을 추가했다.

**조치 불필요로 종결**
- `useBrokerCredentialVerify` 핸들 memo화
  - 소비처(`StockAccountModal`, `BrokerCredentialFields`)에 memo된 자식이 없다.
  - deps에 폼 키 필드가 들어가 매 입력마다 다시 계산된다.
  - 그래서 memo화해도 리렌더가 줄지 않는다.
- `virtualenv` PYSEC-2026-4014: `backend/uv.lock`에 없다. pre-commit이 자체 환경에서 쓰는 의존성이라 런타임과 무관하다.

## 이관 (변경 없음)

- `GoalSettingWizard`(560줄) 분해: 중위험이고 스냅샷 하네스가 없다.
- 제품 판단이 필요한 항목
  - 자산추이 `CASH_STOCK` 라벨 정확도
  - `HIGH_CORR` 배당주기 예외
  - N6(DCA 알림 `monthly_deposit_amount`)
- 메이저 업그레이드: React 19, recharts 3, tailwind 4
- 2-leg 실패 leg 자동 재시도, 정기 자동매수

## 검증

```bash
cd backend && .venv/Scripts/python.exe -m pytest --cov=app --cov-fail-under=80 -q   # 2499 passed, 90.73%
cd backend && .venv/Scripts/python.exe -m ruff check app tests && .venv/Scripts/python.exe -m ruff format --check app tests && .venv/Scripts/python.exe -m mypy app
cd frontend && npm ci && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/eslint src --max-warnings=0
cd frontend && ./node_modules/.bin/vitest run && npx prettier --check src && npm run build   # 1635 passed
```

- 로컬 `node_modules`의 `@sentry/react`가 11.0.0이었다. Dependabot PR #110으로 `^11.4.0`이 된 상태와 어긋나 있었다. `npm ci`로 맞췄다.
- 실브라우저 검증은 하지 않았다. 배포 후 Sentry Performance에서 트랜잭션 이름이 `/dashboard` 같은 라우트 패턴으로 나오는지 확인할 것.
