# 54. 기술부채 감사 (2026-10-14)

## Context

"기술부채 확인 + 수정 계획" 요청. 오늘 이미 두 계획이 진행 중이라 그 범위는 다시 다루지 않았다.
- 계획52: 백엔드 구조. 배치 0·A는 완료, B~G는 미착수
- 계획53: 모바일 UX. Phase A는 완료, B~D는 미착수

이번 조사는 두 계획에 없는 축만 3개 병렬로 봤다(Explore 3개).
1. 프론트 코드 부채
2. 계획52에 없는 백엔드 항목과 계획51 이관분 재검증
3. CI·인프라·의존성·문서 드리프트

실버그 후보는 모두 코드를 직접 읽어 확인했다.
- 오보 1건: `RebalancingStrategyCard`의 null 역참조 "크래시". 백엔드(`strategy_service.py:265-298`)가 risk와 return을 항상 같이 null로 내려주므로 지금은 도달할 수 없다. 잠재적 타입 문제로 강등했다.

사용자 결정:
- 범위는 A+B+C 전부
- Docker 자체 호스팅 프론트 경로는 이번에 손대지 않고 이관한다
- 외부 API 멱등키는 처리 순서만 고치고 응답 규약(201·`duplicate=True`)은 유지한다

**실행 첫 단계**
1. 이 계획을 `docs/plans/54-technical-debt-2026-10-14.md`로 옮기고 `docs/plans/README.md`에 행을 추가한다.
2. 브랜치 `fix/tech-debt-2026-10-14`를 origin/main 기준으로 만든다. 현재 브랜치 `refactor/backend-plan52-batch0-a`는 머지된 상태다.
3. 시작 전에 `git status`/`git diff`로 동시 세션 변경이 있는지 확인한다.
4. 배치마다 커밋한다.

**계획52와의 충돌 회피**
- `external.py`의 스냅샷 재계산 블록은 52 B5 대상이다. A3에서는 그 블록을 건드리지 않는다.
- settings 무효화 헬퍼 6개는 52 D(`PATCH /settings`)에서 정리하므로 여기서 다루지 않는다.

---

## 배치 A — 실버그 (각각 회귀 테스트를 붙이고, 수정 전 코드에서 실패하는지 확인)

| # | 문제 | 수정 |
|---|---|---|
| A1 | **Android APK CI가 빌드되지 않는다.** `build-android.yml`의 `build-debug`/`build-release` 잡은 웹 dist만 내려받고 `npm ci`를 하지 않는다. 그런데 커밋된 `frontend/android/capacitor.settings.gradle`은 `../node_modules/@capacitor/android`를 가리키고, 플러그인 항목(app·haptics·push·biometric)도 없다. `capacitor-cordova-android-plugins`는 gitignore돼 있다. 이 워크플로의 유일한 실행 기록(2026-05-25)도 실패다 | 각 APK 잡이 직접 `setup-node`, `npm ci`, `npm run build`, `npx cap sync android`를 한 뒤 gradlew를 돌리게 한다. `build-web` 잡과 artifact 전달은 제거한다. 기존 SHA 고정 action을 그대로 재사용한다. 로컬 `make build-android-*`도 같은 순서다 |
| A2 | **프론트 "이번 달"이 UTC 기준이다.** `toISOString().slice(0,7)` 때문에 KST 매월 1일 00~09시에는 전월이 된다. 해당 위치: `ChallengeFormModal.tsx:35`, `DCAProjectionChart.tsx:31`, `MonthlyAchievementTable.tsx:10`, `InvestPlanPage.tsx:128` | `utils/format.ts`에 `localMonth()`를 추가해 `localToday().slice(0,7)`을 쓰고, 4곳을 교체한다. 테스트는 `vi.setSystemTime`으로 KST 1일 새벽을 재현한다 |
| A3 | **외부 API 멱등키 처리 순서.** `external.py:289` `_get_owned_account`(활성 계좌만)가 `find_by_external_ref`(:291)보다 먼저 실행된다. 그래서 계좌를 삭제한 뒤 nestlio가 재시도하면 duplicate 응답이 아니라 404가 난다. 같은 키에 다른 페이로드가 와도 아무 흔적이 없다 | 멱등 조회를 계좌 확인 앞으로 옮긴다. 기존 거래와 페이로드(account_id·amount·type·date)가 다르면 `logger.warning("external_tx_idempotency_payload_mismatch", …)`를 남긴다. 응답 규약은 유지한다. 테스트: 삭제 계좌 재시도 → duplicate, 페이로드 불일치 → duplicate + 경고 |
| A4 | **KIS 토큰 갱신 실패가 Sentry로 가지 않는다.** `jobs/token_refresh.py:56`은 `logger.error`만 남긴다 | `report_job_failure("kis_account_token_refresh_failed", e, account_id=…)`(`jobs/_job_helpers.py:30`)로 바꾼다. docstring의 자격증명 지역변수 주의사항은 이미 이 잡을 전제로 쓰여 있으니 따른다. 같은 계열의 "크래시 안 남"만 확인하던 약한 테스트(`test_token_refresh_job.py:66`, `test_alert_jobs.py:39,74,127`, `test_job_helpers.py:48`)에는 `report_job_failure` 호출과 루프 지속 assert를 추가한다 |

## 배치 B — 저위험 정리

**프론트**
- B1 **`useCollapsible` 안정화 + 스토리지 안전 래퍼**
  - `hooks/useCollapsible.ts`의 `toggle`/`setIsOpen`을 `useCallback`으로 감싼다.
  - `utils/safeStorage.ts`(`getItem`/`setItem`/`removeItem`, try/catch)를 신설한다. 기존 패턴은 `AllocationCard.tsx:29-53`에 있다.
  - raw `localStorage`를 쓰는 7개 파일을 전환한다: `useCollapsible`, `useGoalSettings`, `useBiometric`, `themeStore`, `App.tsx`, `useLogout`, `DeleteAccountModal`. `authStore`는 토큰 저장이라 동작을 바꾸지 않도록 개별 판단한다.
  - setter가 안정되면 `NotificationSettingsPage.tsx:177`의 `exhaustive-deps` 억제를 제거한다.
- B2 **쿼리 무효화 정리**
  - `invalidateTransactionData`/계좌 CUD 무효화(`queryInvalidation.ts:42,73`)가 `["transactions","all"]`만 지운다. 계좌별 키 `["transactions", accountId]`(`TransactionModal.tsx:75`)가 남으므로 `["transactions"]` prefix로 바꾼다.
  - `portfolioRiskBase` 키를 추가하고 `queryInvalidation.ts:24`의 `portfolioRisk()`(undefined 인자 매칭)를 교체한다.
  - CLAUDE.md가 금지하는 직접 `invalidateQueries` 7곳을 기존 헬퍼로 바꾼다: `PortfolioManageTab:64`, `RecommendationCard:241`, `useAutoRebalancingDailyCap:25`, `useRebalancingBalances:30`, `NotificationSettingsPage:194`, `SettingsPage:104`, `PortfolioPage:192`. 맞는 헬퍼가 없으면 신설한다. 재시도 버튼 2곳은 유지한다.
- B3 **죽은 Zod 스키마 삭제:** `schemas/auth.ts`·`assets.ts`·`portfolios.ts`(테스트만 import)와 `schemas.test.ts`의 해당 케이스.
- B4 **타입·상수 정리**
  - `RebalancingStrategyCard.tsx:63`의 `hasFrontier`에 `current_return`/`target_return` null 체크를 추가하고 `!` 4개를 제거한다.
  - `utils/accounts.ts:31`의 하드코딩 목록을 `constants/index.ts`에 `BROKER_BALANCE_ASSET_TYPES`로 옮긴다(`ORDER_EXECUTABLE_ASSET_TYPES` 옆).
  - `StockHoldingsTable.tsx:73`에 `.toUpperCase()`를 추가해 다른 3곳과 맞춘다.
- B5 **날짜시각 포맷 헬퍼**
  - `fmtDateTime()`을 `utils/format.ts`에 추가하고, 인라인 `toLocaleString("ko-KR")` 5곳을 바꾼다: `AlertSummarySection:33`, `RebalancingHistoryTab:65`, `RebalancingPlanConfirmPage:152,166`, `NotificationSettingsPage:86`.
  - 출력 문자열이 바뀌지 않는 곳만 교체한다. 각 위치의 옵션 인자를 비교하고, 다르면 남긴다.
  - 인라인 KRW 포맷과 pnl 색상 치환도 같은 기준(출력 동일)으로, 확인되는 것만 한다.

**백엔드**
- B6 `external_queries.py:45,57`과 `challenge_service.py:86`의 `to_char(date) >= 'YYYY-MM'`를 월 1일 `date` 비교로 바꿔 인덱스를 타게 한다. 결과가 같은지 기존 테스트로 확인하고, 경계(월말·월초) 테스트를 추가한다.
- B7 미사용 `python-multipart` 의존성을 제거한다(`Form`/`File`/`UploadFile` 0건). `uv lock` 후 앱이 기동하고 전체 테스트가 통과하는지 확인한다.

## 배치 C — 테스트·문서·도구

- C1 **훅 테스트 신규**(테스트 파일이 없는 것 중 위험도 순)
  - `useModalBehavior`: 53 A1에서 추가한 모달 스택·맨 위 모달만 Escape 처리 로직
  - `useCollapsible`: B1 이후 참조 안정성·스토리지 실패
  - `useSettingsToggle`: 토글 훅 6종의 공통 기반
  - `useChallengeMutations`
- C2 **`frontend/CLAUDE.md` 드리프트 수정**
  - 잘못된 기술: `tsconfig.app.json`(:77, 존재하지 않음), `dividendFreqInfo(months, isManual)`(:446), 없는 `fmtKrwNullable`(:348/351), Zod 레이어 설명(:241, B3 이후)
  - 누락: `fmtKrwPreview`/`parseYmd`/`daysUntilYmd`/`localMonth`/`fmtDateTime`/`safeStorage`
  - queryKey 표 누락 7개, `invalidateBrokerCredentialData`, accounts utils 3개, 시장 상수 3개
  - `backend/app/models/asset.py:286` `UserTickerSettings` docstring에 "기능 제거됨, 52 G 드롭 대상"을 명기한다.
  - `docs/plans/52`의 브랜치명(:37)을 실제 `refactor/backend-plan52-batch0-a`로 정정한다.
- C3 **도구 버전 정합**
  - `.pre-commit-config.yaml`의 ruff rev를 `uv.lock`(0.15.22)에 맞추고 `pre-commit-hooks`를 올린다.
  - `@typescript-eslint/parser`를 eslint-plugin(8.71)에 맞춘다.
  - 백엔드 dev 의존성(pytest·pytest-timeout·mypy·bandit·pip-audit·pytest-cov)에 상한을 추가한다(기존 런타임 의존성 상한 관례).

## 이관 (문서 54 "이관" 절에 기록, 이번 미구현)

- **Docker 자체 호스팅 경로**(사용자 결정)
  - `frontend/Dockerfile`의 컨텍스트 불일치: compose `context: ./frontend`인데 `COPY frontend/…`·`COPY nginx/…`를 한다.
  - nginx 최종 스테이지인데 compose는 `npm run dev`를 실행한다.
  - Node 20 사용, compose의 `VITE_API_BASE_URL`(실제로 읽는 것은 `VITE_API_DOMAIN`), nginx `/ws/` 죽은 블록
- `capacitor-native-biometric@4.2.2`(peer `@capacitor/core ^3`) vs core 8.5.2. 대체 플러그인 검토와 실기기 확인이 필요하다.
- 대형 컴포넌트·훅 분해
  - `StockHoldingsTable`(650), `InvestPlanPage`(568), `InvestmentGoalCard`(565, `order-*` WCAG 1.3.2)
  - `rebalancingExecution/index.ts`(528, 억제 4개), `RebalancingOrderTable`(모바일·데스크톱 마크업 중복)
  - `TradeFormModal`이 `FormInput`/`SuggestionDropdown`을 쓰지 않음
- 백엔드
  - N6: DCA 부족 판정이 알림마다 사용자 단위 `monthly_deposit_amount`를 쓴다. 알림별 금액 모델이 필요하다.
  - CASH_STOCK 잔차 라벨
  - action-items 세금 요약 캐시
  - `account_scoped_performance` N+1(52 C6과 같이)
  - 2-leg 실패 leg 재시도(기능)
- 테스트 인프라: conftest `make_user`·`auth_client` fixture 신설과 29/27개 파일 이관, private 이름 patch 157곳
- 옛 링크 리다이렉트 방식 통일(`AssetManagementPage` vs `AssetsPage`), `tenacity` 9·`firebase-admin` 상한 재검토
- Sentry DSN이 EU 리전이면 CSP `connect-src`(`vercel.json:22`) 보강. DSN 리전을 확인해야 한다.
- `render.yaml`에 `SENTRY_DSN`·`FIREBASE_CREDENTIALS_JSON` 등 대시보드 전용 env 목록을 주석으로 기록
- 메이저 업그레이드(React 19 / recharts 3 / Tailwind 4): 기존 이관 유지

## 검증

```bash
make lint && make typecheck
make test-backend-cov       # 기준선 2607 passed / 91.13%
make test-frontend          # 기준선 1683 passed(53 Phase A 머지 후), CI는 --coverage
cd frontend && npm run build
```

- A1은 로컬에서 워크플로를 돌릴 수 없다. 다음을 확인한다.
  - 수정한 잡과 같은 순서(`npm ci` → `npm run build` → `npx cap sync android` → `gradlew assembleDebug`)가 로컬에서 성공하는지
  - `cap sync` 후 `capacitor.settings.gradle`에 플러그인 4종이 생성되는지
  - PR 머지 후 `workflow_dispatch`로 실제 실행해 green인지(사용자 확인)
- A2~A4 회귀 테스트는 수정 전 코드에서 실패해야 한다.
- B6은 기존 테스트 통과에 더해, 월 경계 케이스의 결과가 전후 같아야 한다.
- B7은 의존성 제거 후 `uv run uvicorn app.main:app` 기동을 스모크로 확인한다.
- Windows pytest가 `N passed` 후 `-1073741819`로 끝나는 것은 실패가 아니다.
- 완료 후 README 상태와 메모리(`project_tech_debt_2026-10-14.md`)를 갱신한다.
