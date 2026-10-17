# 60. 기술부채 감사 (2026-10-17)

## Context

계획59(A·B·D)를 막 끝냈다. 이번 감사는 55~59에서 다루지 않은 영역을 본다. 대상은 수익률 계산, 스케줄러 잡, 목표 설정, 프론트 쿼리 무효화, 저장소 접근, 에러 상태다. 구조 지표는 건강하다(`type: ignore` 11, `any` 0, eslint-disable 13, 실제 TODO 없음, CI 액션 SHA 고정, timeout 전부 설정, ORM↔마이그레이션 드리프트 없음). 그래서 이번 범위는 **사용자에게 틀린 값이나 오래된 화면을 보여주는 실버그**가 중심이다. 아래 A·B 항목은 Explore 보고를 받은 뒤 해당 코드를 직접 읽어 확인했다.

상태: **A·B·D 완료, C 미착수**(아래 "실행 결과"). 브랜치 `fix/tech-debt-2026-10-17`(계획59 브랜치에서 분기).

## 배치 A — 백엔드 실버그 (최우선)

| # | 문제 | 수정 |
|---|---|---|
| A1 | **XIRR이 삭제·제외 계좌의 입금을 포함한다.** `services/returns_calculator.py:92-99` `calc_xirr`의 Transaction 쿼리는 `user_id`만 거른다. 반면 종료값 `current_total`은 활성이면서 `include_in_total`인 계좌만 합산한다. 계좌를 삭제하면 입금은 남고 평가액은 빠져서 XIRR이 크게 음수로 나온다. 영향: 대시보드 수익률, RETURN_PCT 챌린지(XIRR 우선), 월간 리포트 | 계획59 A1과 같은 패턴을 쓴다(`asset_aggregator.py:~88`). `LEFT JOIN asset_accounts a ON a.id = t.account_id`로 붙이고 `(t.account_id IS NULL OR (a.is_active AND a.include_in_total))` 조건으로 거른다. 회귀 테스트: 삭제 계좌의 입금이 cashflow에서 빠지는지 확인한다(SQL 텍스트 고정 + pglast 문법 확인) |
| A2 | **15:30 intraday 동기화가 토스 계좌를 빠뜨린다.** `jobs/asset_sync.py:15` `_STOCK_SOURCES = ("KIS_API", "KIWOOM_API")`. 그래서 토스 계좌는 18:00 일일 동기화 때만 갱신되고, 15:30~18:00 사이의 알림·분석 잡은 토스 포지션을 오래된 값으로 본다 | `"TOSS_API"`를 추가한다. 주문 경로의 목록(`ORDER_EXECUTABLE_ASSET_TYPES`, `_AUTO_EXECUTION_ASSET_TYPES`)은 일부러 토스를 뺀 것이니 그대로 둔다. 테스트: intraday 잡이 TOSS 계좌를 조회 대상에 포함하는지 |
| A3 | **목표 필드를 비울 수 없다.** `api/v1/settings.py:331-351`은 필드마다 `if req.X is not None:`이다. 프론트(`useGoalSettings.ts`, `useDividendPlanSettings.ts`)는 빈 입력을 `null`로 보낸다. 그래서 "저장됨" 토스트가 뜨지만 이전 값이 그대로 남는다 | `req.model_fields_set`을 기준으로 바꾼다. 명시적으로 `null`을 보낸 필드는 지우고, 생략한 필드는 유지한다. `birth_year=None`이면 `age_group`도 None으로 지운다(컬럼 nullable 확인). **확인할 것:** 목표 마법사가 폼을 기존 설정값으로 채우는지. 화면에 없는 필드를 null로 보내면 의도치 않게 지워진다. 마법사 단계에서 편집하지 않는 필드는 payload에서 빼도록 프론트를 고친다. 테스트: null이면 삭제, 생략하면 유지 |
| A4 | **월간 리포트의 전월 대비 값이 엉뚱한 달을 비교할 수 있다.** `jobs/monthly_report.py:84-85`가 `monthly_trend[-2]`·`[-1]`을 위치로 집는다. 1일 09:00 실행 전에 당월 스냅샷(계좌 수정·수동 sync)이 생기면 `[-1]`이 당월 부분합이 되어 "지난달 급락"으로 보인다 | `month == month_key`(전월)인 항목과 그 직전 항목을 키로 찾는다. 없으면 None으로 둔다. 테스트: 당월 항목이 섞인 trend에서도 전월 대비 값이 맞는지 |
| A5 | 캐시 무효화 누락(TTL 5분~1시간): ① `invalidate_asset_account_caches`(`utils/cache_keys.py:~509`)에 `challenge_progress_key`가 없다. 현금계좌 잔액 수정으로 Transaction이 생기거나 계좌를 삭제해도 챌린지 캐시가 남는다. ② `jobs/challenge_monthly_wrap.py:133`에서 COMPLETED로 바꾼 뒤 `invalidate_challenge_cache`를 부르지 않는다. ③ `insights_key`·`risk_key`가 어떤 invalidate 헬퍼에도 없다. 계좌 삭제·sync 뒤 1시간 동안 삭제 계좌 포지션이 인사이트·리스크에 남는다 | ①은 키 목록에 추가한다. ②는 status를 바꾼 뒤 무효화한다. ③은 `invalidate_asset_account_caches`에 두 키를 추가한다(sync 경로에서 이 헬퍼를 쓰는지 확인하고, 안 쓰면 sync 무효화 헬퍼에도 추가). 기존 무효화 테스트 패턴으로 키 포함 여부를 고정한다 |
| A6 (저) | `jobs/goal_achievement.py:31`의 `month_start`가 UTC 자정이다(현재 18:45 실행이라 무해). `api/v1/external.py:216`의 `manual_updated_at.date()`는 UTC 날짜라 00~09시 KST 수정이 전날로 보인다 | 둘 다 KST로 바꾼다(`utils/kst.py`). `challenge_service.py:300-303` ACTIVE 복귀 시 `completed_at=None`도 함께 처리한다 |

보류(설계 판단): 배당·이자·수수료 합계(`tax_service.py:427-445`, `dividend/aggregator.py:66-74`)는 `is_active`로 거르지 않는다. 세금 관점에서는 삭제 계좌의 수령 배당도 실제 소득이므로 의도된 동작으로 보고 README에 근거만 기록한다.

## 배치 B — 프론트 실버그

| # | 문제 | 수정 |
|---|---|---|
| B1 | **배당 거래를 저장·삭제해도 배당 화면이 최대 1시간 오래된 값을 보인다.** `utils/queryInvalidation.ts:71` `invalidateTransactionData`에 `dividendSummaryBase`·`dividendPlan`이 없다(백엔드는 무효화한다) | 두 키를 추가한다 |
| B2 | 배당 목표만 저장하면 `invalidateDividendPlanData`만 부른다(`hooks/useDividendPlanSettings.ts:48`). 백엔드는 dashboard·dca·challenge·goal 추천 캐시를 지우므로 홈 InvestmentGoalCard와 설정 "목표 N개"가 1시간 동안 오래된 값을 보인다 | `invalidateDcaData`(dividendPlan 포함) + `invalidateGoalRecommendationData`로 바꾼다 |
| B3 | 마법사가 아닌 편집 모달에서 목표를 바꾸면 goal 추천을 무효화하지 않는다(`hooks/useGoalSettings.ts:~184`, `if (wizardMode)` 안에만 있다). 게다가 localStorage에 persist되는 키라 재시작 후에도 남는다 | 무효화를 wizardMode 블록 밖으로 뺀다 |
| B4 | 계좌별 전환 뮤테이션(`RebalancingAlertModal.tsx:157-160`)이 `invalidatePortfolioData`만 부른다. 그래서 삭제된 AGGREGATE 알림 배지·AUTO 배너가 남는다. 반대 방향(`PerAccountRebalancingAlertList.tsx`)은 제대로 무효화한다 | `invalidateRebalancingAlertData(qc, portfolioId)`를 함께 부른다 |
| B5 | `sessionStorage`·`localStorage`를 직접 접근한다: `hooks/useBiometric.ts:15,55,72`(렌더 중에 throw하면 가드가 크래시하고, 인증 성공이 에러로 표시된다), `stores/authStore.ts:54,99`(로그인 성공인데 실패로 표시될 수 있다), `main.tsx:30`(사이트 데이터 차단 시 앱 부팅 실패) | `utils/safeStorage.ts`에 session 변형을 추가하거나 try/catch로 감싼다. `main.tsx`는 `localStorage` getter 접근을 try로 감싸고, 실패하면 persister 없이 부팅한다 |
| B6 | 실패를 빈 상태로 표시한다: `TransactionHistoryTab.tsx:56`(실패하면 "등록된 내역이 없습니다"), `PortfolioExecutionTab.tsx:34`, `NotificationSettingsPage.tsx:58-69`, `RebalancingAlertSummaryCard.tsx:14-28` | 기존 에러카드+재시도 컴포넌트(리밸런싱 분석 UX 때 만든 패턴, 착수 시 grep)를 `isError` 분기에 쓴다 |
| B7 (저) | `StockPositionsModal.tsx:162`의 "KIS/키움 계좌는…" 문구가 토스를 빠뜨린다. 자기 파일에서만 쓰는 export 3개(`CANDIDATE_OVERLAP_DEBOUNCE_MS`, `DEFAULT_OVERSEAS_TAX_RULE`, `RegionBadge`) | 문구를 고치고 export를 제거한다(테스트 import 여부 확인) |

## 배치 D — 문서·위생 (저위험)

- 루트 `.env.example`에서 죽은 변수 `REDIS_URL`, `JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, `JWT_REFRESH_TOKEN_EXPIRE_DAYS`를 제거한다(`POSTGRES_PASSWORD`는 유지).
- `backend/CLAUDE.md` schemas 트리에 `schemas/action_items.py`를 추가한다.
- `.github/dependabot.yml`의 stale 주석 2건을 고친다(structlog/pytest는 이미 상한이 있음, zustand 5는 이미 적용됨). tenacity·pandas major ignore는 유지 근거를 재확인해 주석으로 남긴다.
- `docs/plans/10-…`의 Redis 언급에 "Redis 제거됨(2026-07-22)" 주석을 단다.
- 실시계 의존 테스트를 고정한다: `test_alert_calculator.py:168-190`, `test_alert_service_extended.py:50-84`, `TransactionHistoryTab.test.tsx`, `constants.test.ts:116`. 자정 경계에서 flaky할 수 있으므로 시각을 고정한다(백엔드는 기존 `today_kst` patch 패턴, 프론트는 `vi.setSystemTime`).

## 배치 C — 계획59 이관 (중위험, 실주문)

59의 C1(AUTO 잡 app_state 원자적 claim: `INSERT … ON CONFLICT DO NOTHING RETURNING`)과 C2(국내 지정가 호가단위 `utils/krx_tick.py`)는 그대로 유효하다. 상세는 `docs/plans/59` 표를 따른다. A·B·D와 분리해 별도 커밋으로 진행하고, 착수 전에 현행 KRX 호가표와 ETF 판별 소스를 확인한다.

## 이관 유지

계획59 "이관" 목록은 전부 유효하다(스케줄러 워커 분리, 데이터 보존, FK 인덱스, 52 B~G, biometric 플러그인, `noUncheckedIndexedAccess`, 대형 컴포넌트, 프론트 major 업그레이드). 이번에 새로 추가할 항목은 없다.

## 재사용할 기존 코드

- `asset_aggregator.py`의 삭제 계좌 필터 SQL(59 A1), `active_accounts_stmt`
- `utils/kst.py`(`today_kst`, KST tz), `utils/cache_keys.py` invalidate 헬퍼, `invalidate_challenge_cache`
- `frontend/src/utils/queryInvalidation.ts` 헬퍼(`invalidateDcaData`, `invalidateRebalancingAlertData`, `invalidateGoalRecommendationData`), `utils/safeStorage.ts`

## 검증

```bash
make lint && make typecheck
make test-backend-cov   # 80% 게이트, Windows 종료코드 -1073741819는 실패 아님
make test-frontend
cd backend && uv run alembic check   # 스키마 변경 없음 확인
```
- 실버그 회귀 테스트(A1~A5, B1~B6)가 수정 전 코드에서 실패하는지 먼저 확인한다(59와 같은 절차)
- A1·A4 SQL/로직: SQL 텍스트 고정 + `uvx --with pglast`로 문법 확인(로컬 Docker 없음)
- A3: 마법사·편집 모달·배당 목표 세 경로에서 다른 필드가 지워지지 않는지 테스트한다
- 배포 후 확인: 삭제 계좌가 있는 사용자의 대시보드 XIRR 변화, 15:30 로그에서 토스 계좌 `account_synced`

---

## 실행 결과 (2026-10-17, 브랜치 `fix/tech-debt-2026-10-17`)

**A·B·D 완료. C는 미착수(59 표 그대로 유효).** 백엔드 2704 tests 91.21%, 프론트 1677 tests. ruff·ruff format·mypy·tsc·eslint(`--max-warnings 0`)·prettier(`src`) 모두 클린. 실버그 회귀 테스트(A1·A2·A3·A5·A6, B1·B2·B5·B6)는 수정 전 코드에서 실패하는 것을 확인했다(A4는 헬퍼 신설이라 동작 테스트로 고정).

계획 대비 정정·추가:
- **A3 설계 보강**: 백엔드만 `model_fields_set`로 바꾸면 위험하다. `useGoalSettings.buildCurrentForm`은 DCA 분석(`data`)이 없을 때 빈 폼을 만들고, 그 상태로 저장하면 모든 목표가 null로 지워진다. 그래서 프론트에 `numberFieldPayload(value, initial)`(`hooks/useEditableSettingsForm.ts`)를 두었다. 값이 있으면 숫자, 원래 있던 값을 지우면 null, 처음부터 비어 있으면 키를 생략한다. 저장할 때 초기 폼과 비교해 사용자가 지운 필드만 null로 보낸다. `useEditableSettingsForm`이 `initialForm`을 노출한다. 출생연도를 비워도 `age_group`은 유지한다(추천 옵션에서 직접 고를 수 있으므로). `goal_start_date`는 기존대로 빈 칸이면 오늘 날짜로 채운다.
- **B2**: `invalidateDividendPlanData`의 유일한 호출부가 바뀌어 헬퍼가 죽은 코드가 됐다. 헬퍼와 테스트, 테스트 mock 2곳, `frontend/CLAUDE.md` 항목을 함께 제거했다.
- **A5**: sync 경로(`asset_service.sync_account`)도 `invalidate_asset_account_caches`를 쓰므로 키 3개(challenge·insights·risk)를 추가한 것으로 계좌 CRUD·잔액 수정·sync를 모두 덮는다. 챌린지 결산 잡은 유저 단위 루프 끝에서 한 번 무효화한다.
- **B4**: 1줄 수정. 전환 버튼이 AUTO 모드 하위 섹션에 있어 렌더 테스트 비용이 커서 회귀 테스트는 생략했다.
- **B5**: `authStore.ts:54`는 이미 try 안이라 수정하지 않았다. `safeStorage`에 `sessionGet`/`sessionSet`/`getLocalStorageOrUndefined`를 추가했다. 저장소 차단 테스트는 `vi.spyOn(window, "sessionStorage", "get")`이 SecurityError를 던지게 해서 작성했다.
- **B6**: `TransactionHistoryTab`·`PortfolioExecutionTab`·알림 이력은 `EmptyState` + "다시 시도"를 쓰고, `RebalancingAlertSummaryCard`는 링크 행 안의 문구로 바꿨다(설정 화면 요약 행이라 재시도 대신 리밸런싱 탭으로 이동).
- **D 실시계 테스트**: 백엔드 2파일(발송일 판정)은 `calculator.today_kst`를 고정 날짜로 monkeypatch했다. 프론트 2파일은 **보류**했다. 연도만 비교해서 경합 창이 새해 자정의 수 ms뿐이고, fake timer는 react-query·`waitFor`와 간섭할 위험이 더 크다.
- **D dependabot**: tenacity 9 ignore는 유지하되 근거 주석을 달았다(재시도 데코레이터 5개 모듈 사용 → 상한 확장 + 재시도 테스트 확인을 별도 PR로). pandas ignore 근거(pykrx <2.0이 pandas<3 요구)는 그대로 유효하다.

배포 후 확인:
- 삭제·합산 제외 계좌에 입금 이력이 있는 사용자의 대시보드 XIRR이 정상 범위로 돌아오는지
- 15:30 Render 로그에서 `job=intraday_sync`의 토스 계좌 `account_synced`
- 다음 달 1일 월간 리포트의 전월 대비 값
