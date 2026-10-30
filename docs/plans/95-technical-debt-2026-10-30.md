# 95 — 기술부채 감사 5차 (2026-10-30)

## 배경

계획 94(PR #183) 머지 뒤 백엔드·프론트·인프라 세 축을 다시 감사했다. 데이터가 틀리게 보이는 실버그는 캐시 무효화 누락(백엔드 A, 프론트 F)과 USD 금액 환산 누락(F)이다. 나머지는 관측성 누락, 로컬 검증과 CI의 차이, 빌드 산출물 노출, 설정·문서 드리프트다.

브랜치: `chore/tech-debt-2026-10-30`. 클러스터마다 커밋 1개.

## 결과

| # | 항목 | 결과 |
|---|---|---|
| A | 백엔드 캐시 무효화 + 삭제 계좌 배당 | **실버그.** 리밸런싱 전략 캐시를 지워도, 재계산 때 읽는 포트폴리오 단위 팩터 분석(`factor_analysis:portfolio:{id}`)과 효율적 프론티어(`efficient_frontier:{user}:{pid}:*`) 캐시가 남아 있었다. 그래서 포트폴리오 수정·전술 적용 뒤 1시간 동안 목표 위치가 옛 비중으로 다시 조립됐다. 이제 `invalidate_rebalancing_analysis_cache`가 둘을 함께 지운다. 계좌 캐시 무효화는 보유 구성이 바뀐 경우(`positions_changed`) 보유 기반 팩터·프론티어도 지운다. 포트폴리오 생성·수정·삭제는 인사이트 캐시도 지운다. 배당 수령 집계 3곳(요약·종목별·연도별)이 삭제(soft) 계좌 배당을 빼도록 했다(사용자 확정: 입출금과 같은 기준). 세금 집계는 실제 소득이라 그대로 둔다 |
| F | 프론트 무효화·USD 환산 | **실버그.** `invalidateAccountData`에 drift·risk·insights가 빠져 있었다. 포지션 수동 저장·계좌 삭제 뒤 드리프트·리스크·인사이트 카드가 옛 값으로 남았다. 새 계좌의 첫 sync도 이제 `invalidateSyncData`를 쓴다. TransactionForm에서 USD 배당을 환율 없이 제출하면 이전 원화 금액이 그대로 저장됐다. 이를 막고, 통화를 바꾸면 금액을 비운다. StockPositionsModal은 환율이 로딩되기 전에 입력한 달러 평균단가(원화 0)를 422 대신 원인 메시지로 막는다. 예수금 반영 실패는 이제 토스트로 알린다. 모달과 부모 onClose가 겹쳐 두 번 돌던 무효화는 하나로 줄였다 |
| B | 관측성 | **관측성.** JWKS fetch가 실패하면 모든 인증이 401이 되는데 Sentry에 오지 않았다. 연결 실패는 `report_handled_failure`로 보고하고, 알 수 없는 kid(`PyJWKClientError`)는 토큰 문제로 보고 warning으로 남긴다. `PyJWKClient` 타임아웃을 30초에서 5초로 줄였다(동기 urllib이라 이벤트 루프를 막는다). Supabase 장애로 503/502를 돌려주는 3곳도 보고한다(HTTPException은 자동 수집 대상이 아니다) |
| C | 로컬 검증·산출물 | `make typecheck`가 CI처럼 `npm run typecheck`(테스트 tsconfig 포함)를 쓴다. Sentry 업로드 토큰이 없으면 소스맵을 만들지 않는다. 지금까지는 APK와 nginx 이미지에 `.map` 8MB가 실렸다(빌드 후 0개 확인). 사용처가 0이던 `generate:api-types`/`openapi-typescript`를 지웠다. overrides 하한을 올리고(js-yaml·undici) `npm audit fix`를 돌렸다. 전체 audit은 16건(high 7)에서 low 4건으로 줄었다. 남은 4건은 vite-plugin-pwa→workbox-build 체인이다. 매칭되는 URL이 없던 Workbox API `runtimeCaching`을 제거했다(매칭됐다면 사용자 간 응답 캐시가 샐 위험이 있었다). `frontend/Dockerfile`은 `VITE_*` ARG를 선언하고 compose nginx가 build args를 넘긴다 |
| E | 백엔드 정리 | `BROKER_API_ASSET_TYPES`·`BROKER_API_DATA_SOURCES`를 `app/constants.py`에 추가했다. 로컬 브로커 리스트 3곳(잔고 조회 게이트, `_account_queries`, asset_sync 잡)이 이 상수를 쓴다. `ORDER_EXECUTABLE_ASSET_TYPES`도 `order_builder`에서 constants로 옮겼다. 하드코딩돼 있던 주문 취소 게이트도 같은 상수를 쓴다. external 거래 반영의 중복 캐시 삭제를 지웠다. 배당 `STOCK%` 조건은 수기 주식 배당을 포함해야 해서 그대로 둔다. transactions의 `monthly_trend_key` 삭제도 방어적으로 유지한다 |
| G | 프론트 정리 | 재시도 버튼 3곳을 직접 무효화에서 `refetch`로 바꿨다. `dca-analysis`·`isa-status`를 `queryOptions`로 승격해 프리페치 staleTime 누락도 해소했다. 대시보드 챌린지는 `useChallenges`, TransactionModal 포지션은 `useAccountPositions`를 쓴다. 환율 실패 토스트는 소비 훅마다가 아니라 Provider에서 한 번만 띄운다. non-null 단언 2곳과 불필요한 export 2개, 죽은 `vi.mock` 2개, CLAUDE.md의 없는 queryKey 행을 정리했다 |
| D | 인프라·설정 | ci.yml에 최상위 `permissions: contents: read`와 PR `concurrency`를 넣었다. bandit·pip-audit는 pytest 앞으로 옮겼다(테스트가 실패하면 건너뛰던 문제). 커버리지 임계값은 pyproject `fail_under` 한 곳에만 둔다(플래그 없이 게이트가 동작하는 것 확인). Dependabot에 docker 생태계를 추가했다. Sentry release는 `RENDER_GIT_COMMIT`으로 폴백하고, render.yaml에 선택 env 3종을 적었다. 루트 `.env.example`은 compose 변수만 남겼다(가짜 앱 설정이 env_file로 backend/.env를 덮어써 기동에 실패했다). prometheus 인증 예시는 `credentials_file`로 바꿨다. 미사용 CSP 이미지 호스트 2개를 지웠고, 문서의 JDK 17+를 21+로 고쳤다 |

## 검증

- 백엔드: ruff·mypy 클린, 3141 tests, 커버리지 92.07%.
- 프론트: eslint `--max-warnings 0`·prettier·`npm run typecheck`(앱+테스트) 클린, 1889 tests 통과.
- `npm run build`에서 `.map` 0개, 전체 `npm audit` low 4건.
- **미검증**: Docker를 쓸 수 없는 환경이라 `frontend/Dockerfile`·compose nginx 이미지 빌드를 실제로 돌리지 못했다(YAML 파싱만 확인).

## 이관

- **backend/Dockerfile**(Render 배포 경로): uv 버전 고정(`COPY --from=ghcr.io/astral-sh/uv:<ver>`), `uv export --no-emit-project`, 빌더의 `COPY app/` 제거. 이미지 빌드를 확인할 수 없어 보류했다. `nginx:alpine` 태그 고정도 같이 보류.
- `CashSummaryBar`의 `!` 단언(불리언 플래그 때문에 좁혀지지 않음), `rebalancingExecution` 수기 deps, TransactionForm↔`useTransactionFormState` 통화 로직 통합.
- `vite-plugin-pwa → workbox-build` low 취약점(상위 수정 대기).
- **유지**: FCM FID, `PATCH /settings` 단일화, alembic squash, 대형 파일 분해, 프론트 메이저·pandas/yfinance 3, pandas resample deprecation, 사용자 작업(외부 keep-alive·APK Variables·실기기 확인).
