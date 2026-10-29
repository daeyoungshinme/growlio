# 94 — 남은 기술부채 처리 4차 (2026-10-29d)

## 배경

계획 93(PR #182)의 이관 항목은 대부분 외부 조건에 묶여 있다(FCM FID·`PATCH /settings`는 APK 재배포 뒤, alembic squash는 단독 PR). 브랜치 정리 이관은 이미 해소됐다(머지된 원격 브랜치는 `chore/tech-debt-2026-10-29c` 하나). 그래서 백엔드·프론트·인프라 세 축을 다시 감사했다. 데이터 오류 실버그는 없었다. 93 A와 같은 관측성 누락, 공용 쿼리 정의 분산, 빌드되지 않는 compose 서비스가 나왔다.

브랜치: `chore/tech-debt-2026-10-29d`. 클러스터마다 커밋 1개.

## 결과

| # | 항목 | 결과 |
|---|---|---|
| A | 처리된 실패 Sentry 누락 | **관측성.** 네 곳은 `logger.error`/`critical`만 하고 있었다. 이를 `report_handled_failure`로 바꿨다. (1) `_send_templated`: Resend 키 만료나 4xx/5xx가 나면 모든 알림 메일이 조용히 `False`가 됐다. (2) 탈퇴: Supabase 삭제 후 로컬 정리에 실패하면 고아 데이터가 남는다. 로그 이메일도 마스킹한다. (3) Firebase 초기화 실패: 플래그가 이미 서 있어 재기동 전까지 푸시가 꺼진다. (4) 주문 취소 응답 유실: 주문 상태를 알 수 없게 된다. 손으로 쓴 capture 2곳(dca 현금부족 평가, 실행 이력 저장)도 헬퍼로 바꿨다. `drift_summary` 항목 격리는 이웃처럼 warning으로 맞췄다. `test-email`은 사용자가 결과를 직접 보므로 그대로 둔다. `token_refresh`는 Sentry 태그를 써서 유지한다 |
| B | 공용 쿼리 `queryOptions` 승격 | accounts(12곳), portfolioOverviewLite(6곳), rebalancingAlerts(6곳), goalRecommendationOverall(5곳)을 `api/queryOptions.ts`로 옮겼다. 화면마다 staleTime이 30s~1h로 섞여 있었다. 덮어쓰기는 위저드 `staleTime: NONE`과 대시보드 폴링만 남겼다. accounts `setQueryDefaults`(main.tsx)는 흡수했다. App·LoginPage의 프리페치 목록은 `api/prefetch.ts` 하나로 합쳤다(로그인 쪽 settings 누락 해소). TradeFormModal은 환율 컨텍스트를 직접 읽어 오류 토스트를 건너뛰고 있어서 `useExchangeRate`로 바꿨다 |
| C | 저위험 정리 | KST 수동 계산 2곳을 헬퍼로 바꿨다. `type: ignore`는 앱 8→2(`main.py` slowapi, `deps.py` 제네릭)로 줄였고, tests의 13개는 mypy 비대상이라 지웠다. `order_builder`의 `filter_drifting_items` 재노출을 지웠다(감사 보고는 사용처 1곳이었지만 실제 3곳). 프론트에서는 죽은 `groupKeys`와 `QUERY_KEYS.alertHistory`, eslint-disable 2개(settings/shared, WidgetPlugin)를 지웠다. 테스트 setup은 한 파일로 합쳤다. CLAUDE.md 목록 드리프트도 고쳤다 |
| D | 인프라 | compose `frontend` 서비스를 지웠다(사용자 확정). 빌드 컨텍스트와 Dockerfile 경로가 어긋나고 최종 이미지가 nginx라 실행할 수 없었다. nginx `production` 프로필은 빈 `frontend_dist` 볼륨 대신 `frontend/Dockerfile`을 루트 컨텍스트로 빌드한다(`Dockerfile.dockerignore`). nginx `/ws/` 블록을 지웠고, Dockerfile node를 20→22로 올렸다 |

검증: 백엔드 3133 tests, 커버리지 92.07%, ruff/format/mypy 클린. 프론트 1886 tests, tsc(앱·테스트)/eslint/prettier/build 클린. compose는 이 머신에 Docker가 없어 YAML 파싱으로만 확인했다. 서버 기동 스모크는 하지 않았다(로컬 `.env`가 공유 Supabase를 가리킴, 93과 같은 이유).

## 계획과 달라진 점

- **`ExchangeRateContext`의 eslint-disable은 유지했다.** 훅을 다른 파일로 옮기려면 `vi.mock("@/context/ExchangeRateContext")` 8곳을 고쳐야 한다. 지금 disable에는 주석으로 이유가 달려 있다.
- **recharts 3·tailwind 4는 Dependabot `ignore`로 막지 않았다.** 닫힌 PR은 그 버전만 건너뛰고 다음 major 릴리스에서 다시 열린다. "건별 검증" 의도를 유지하고 현황만 주석에 남겼다.
- **accounts 1h override 2곳(TaxTabContainer·PortfolioPage)은 지웠다.** 이유 주석이 없었고, 계좌는 CRUD·sync 때 명시적으로 무효화된다.

## 이관

- **pandas resample의 numpy `timedelta` deprecation**(새로 발견): `test_etf_overlap_service.py`에서 10건이 난다. pandas 내부(`resample.py`)에서 나므로 pandas 업그레이드 때 확인한다.
- **유지**: FCM `Message.token` → FID(클라이언트 FID 경로 없음, APK 재배포), `PATCH /settings` 단일화(고아 PUT 0, APK 재배포 뒤), alembic squash 52 G2(리비전 123, `_BASELINE_REVISION`·`xr1` external_ref 부분 유니크·`ix1`·`_DESC_INDEXES` 보존, 단독 PR), 400줄 초과 프론트 파일 12개와 600줄 초과 백엔드 3개(기능 작업 때), 프론트 메이저·yfinance·pandas 3, 사용자 작업(외부 keep-alive·APK Variables·실기기 확인).
