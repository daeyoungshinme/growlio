# 101 — 기술부채 재감사 (2026-10-31)

## 배경

100(PR #197, 머지됨) 직후 백엔드·프론트·인프라 3갈래로 다시 감사했다. 근거는 코드로 직접 확인했다.

- 브랜치: `chore/tech-debt-2026-10-31`
- 커밋: 클러스터마다 1개

감사 결과 문제없음으로 확인한 축은 다음과 같다.

- UTC/KST 날짜 처리
- 스냅샷·월별 추이의 `is_active` 필터
- 사용자 스코핑
- `app/services`의 fastapi import (0건)
- TODO 주석
- queryKey 표
- skip된 테스트
- Vercel rewrite

## 결과

### A. 실버그·리스크

| # | 항목 | 결과 |
|---|---|---|
| A1 | 전술 끄기 후 알림 캐시가 낡음 | 서버는 포트폴리오의 TACTICAL 알림을 **모두** DISABLED로 바꾼다. 그런데 프론트는 적립식 알림이 "모두 연동"일 때(`useDcaTacticalLink.linked`)만 알림·FX 캐시를 무효화했다. 그래서 일부만 연동된 경우 99 B2의 옛 모달 재저장 버그가 다시 났다. 이제 끌 때마다 `invalidateTacticalData(qc, { alertsReset: true })`를 호출한다. `dcaLinked`는 안내 문구에만 쓴다 |
| A2 | 국내 주문가 만원 축약 | `OrderResultList`와 `RebalancingWeightTable`이 주가에 `fmtKrw`를 써서 54,300원이 "5만원"으로 보였다. `utils/format`에 `fmtUsd`·`fmtUsdPrice`·`fmtNativePrice`를 추가했다. 인라인 USD 포맷 6곳(FxPlanCard·PositionsTable·StockAccountCard·holdings·FinalConfirmDialog)도 이 함수로 통일했다 |
| A3 | KIS 해외 미체결 조회 페이징 | `get_overseas_unfilled_qty`는 본문 연속키로 다음 페이지를 판정했고, 5페이지 상한에 걸리면 0("이미 체결")을 돌려줬다. 그 결과 열린 주문이 CANCEL_FAILED로 오기록될 수 있었다. 이제 `balance.py`와 같이 헤더 `tr_cont`로 판정한다. 상한 초과나 키 반복은 `BrokerOrderRejectedError`(CANCEL_FAILED, 재시도 가능)로 올린다. 새 테스트 3건은 수정 전 코드에서 실패했다 |
| A4 | 인사이트 부분 실패 1h 캐싱 | `_check_rebalancing_opportunity`에서 포트폴리오 단위로 실패하면 warning만 남겼다. `degraded`가 세워지지 않아 불완전한 목록이 1시간 캐싱됐다. 이제 `on_partial_failure` 콜백으로 짧은 TTL을 적용하고 `report_handled_failure`로 Sentry에 보고한다 |
| A5 | 로그인 직후 재설정 배너 누락 | `login()`이 `needs_password_reset`을 false로 고정했고, `/auth/me` 결과는 캐시에만 기록했다. 이제 store에도 반영한다. 응답 전에 사용자가 바뀌었으면 덮어쓰지 않는다 |
| A6 | 수동 주식계좌 생성 시 예수금 소실 | 생성 경로가 KRW와 USD를 합쳐 `manual_amount`로만 보냈다. 그래서 종목을 저장하면 `positions.py`가 `manual_amount`를 매입금액 합계로 덮어 예수금이 사라졌고, 달러는 환전 계획의 보유 달러에서 빠졌다. 이제 수정 경로처럼 `deposit_krw`·`deposit_usd`도 보낸다. `useCurrencyInput`은 `convertUsdToKrw`를 재사용한다 |
| A7 | Grafana 패널 "datasource not found" | 대시보드는 `uid: prometheus`를 참조하는데 datasource 프로비저닝에 uid가 없었다. 프로비저닝에 uid를 추가했다 |

### B. 백엔드 에러 계약·경계

| # | 항목 | 결과 |
|---|---|---|
| B1 | FX 계획 전용 예외 | `PortfolioNotFound`를 `NotFoundError`로 바꾸고, 라우터의 수동 404 매핑을 없앴다. 미사용 `FxPlanStatus`(`NO_RATE` 누락)도 삭제했다 |
| B2 | 전략 서비스 `{"error"}` 반환 | 이 반환을 `NotFoundError` raise로 바꾸고, 라우터의 분기를 없앴다 |
| B3 | 라우터의 `ValueError`→HTTP 3곳 | **유지.** 이유는 다음과 같다.<br>• `challenges.py`: `check_type_targets`가 pydantic validator에서도 쓰여 `ValueError`가 맞는 계약이다.<br>• `tactical` 백테스트: 503이라 맞는 AppError가 없고, 상태 코드를 바꾸면 계약이 바뀐다.<br>• `broker-balance`: 서비스가 gather 경로(`broker-balance-all`)에서도 쓰인다 |
| B4 | 전술 라우터의 비즈니스 로직 | `save_strategy`·`disable_strategy`·`check_apply_allowed`를 `tactical_allocation_service`로 옮겼다. 예외는 `BadRequestError`·`ConflictError`를 쓰고, 응답은 그대로다. 그룹 제안 실패는 `report_handled_failure`로 보고한다. `disable_strategy` 단위 테스트를 추가했다 |

### C. 프론트 정리

| # | 항목 | 결과 |
|---|---|---|
| C1 | `!` 단언 | `isTradableItem`을 type predicate로 바꿨다. goalChips·GoalTimelineCard는 판정과 값을 함께 좁히는 지역 변수로, RebalancingStatusCard·OrderResultList는 클로저 밖에서 값을 잡도록 고쳤다. 앱 코드에 남은 단언은 계약상 안전한 것뿐이다(`main.tsx` root, `api/client` 큐 토큰, `PortfolioGroupItemRow`의 `item.group`, `PortfolioAccountSelector`의 Map 조회) |
| C2 | eslint-disable 2건 | `useAnalysisState`(stable한 `triggerRebalancingAnalysis`를 deps에 추가)와 `useGoalWizardFeasibility`(updater가 이미 보호)를 정리했다 |
| C3 | 중복 쿼리 정의 | `exchangeRateQuery`·`exchangeRateAlertsQuery`를 `queryOptions`로 옮겼다. 프리페치가 staleTime 없이 환율을 받던 문제도 해결했다. `ExchangeRateAlertSection`은 `useAlertCrud`의 `queryFn` 타입(필수) 때문에 기존 키·함수를 그대로 둔다 |
| C4 | DeleteAccountModal의 수동 로그아웃 | **유지.** `logout()`은 이미 삭제된 사용자로 푸시 토큰 API를 부르고, 쿼리 캐시는 비우지 않는다. 탈퇴 경로가 의도적으로 다르다 |
| C5 | `frontend/CLAUDE.md` | 포맷 함수, 전술 끄기 무효화 조건, 주문 취소 무효화, 공용 쿼리 목록을 갱신했다 |

### D. 인프라·문서

| # | 항목 | 결과 |
|---|---|---|
| D1 | Node 드리프트 | CI·Android 빌드를 22에서 24로 올려 `frontend/Dockerfile`(node:24-alpine)과 맞췄다. 루트 CLAUDE.md도 갱신했다 |
| D2 | CI uv 버전 미고정 | **보류.** Dockerfile의 uv는 Dependabot이 올리는데, CI에 버전을 하드코딩하면 갱신 안 되는 사본이 하나 더 생긴다. `--locked` 동작은 버전 간 안정적이다 |
| D3 | nginx 서비스워커 30일 캐시 | `sw.js`·`registerSW.js`·`workbox-*.js`·`manifest.webmanifest`에 no-cache location을 asset 규칙보다 위에 추가했다. 자체 호스팅 대안 구성에만 영향이 있다 |
| D4 | README 인덱스 | 95/96 행 순서를 정정하고 101 행을 추가했다. 상태 표는 23에서 멈춰 있다는 것을 명시했다 |

## 검증

- 백엔드: ruff·format·mypy 클린, 3206 passed, 커버리지 92.23%(게이트 89%)
- 프론트: eslint `--max-warnings 0`·prettier·`npm run typecheck` 클린, 1913 tests 통과(신규 포함)
- **미검증**:
  - A3: 실계좌의 `tr_cont` 응답(KIS 실계좌 필요)
  - A7·D3: 이 환경에 docker가 없어 Grafana 패널 렌더링과 `nginx -t`를 돌리지 못했다
  - A6: 실기기에서 생성→종목 저장 흐름

## 이관

- `portfolios.py`의 item·account relink 로직을 서비스로 옮기기
- `deps.py:76`의 `type: ignore`(Protocol bound로 제거 가능)
- 신규 컴포넌트의 직접 테스트: `TacticalApplyConfirmModal`·`PortfolioGroupItemRow`·`RebalancingOrderRows`·`stockHoldings/*`·`useMediaQuery`·`useRebalancingUrlState`
- `httpx2` dev 의존성이 아직 필요한지 확인
- 그대로 두는 것:
  - 메이저 업그레이드
  - pyproject 상한에 닿은 의존성(cryptography <51 등, 네트워크 확인 필요)
  - vite-plugin-pwa low 4건
  - keep-alive 외부 핑
