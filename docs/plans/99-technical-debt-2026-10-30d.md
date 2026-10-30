# 99 — 기술부채 감사 8차 (2026-10-30d)

## 배경

98(PR #191)이 머지된 직후 main(df774466)을 다시 감사했다. 98에서 이관된 항목은 vite-plugin-pwa 쪽 low 4건뿐이고, 이건 상위 수정을 기다리는 중이다. 그래서 이번에는 96~98에서 새로 들어온 코드와 인프라·문서를 백엔드·프론트·인프라 3갈래로 병렬로 훑었다.

정적 검사는 시작 시점에 이미 깨끗했다(ruff·format·mypy·eslint·tsc 0건, pip-audit·npm audit(prod) 0건). 테스트 경고만 2건 남아 있었다.

브랜치: `chore/tech-debt-2026-10-30d`. 클러스터마다 커밋 1개.

## 결과

| # | 항목 | 결과 |
|---|---|---|
| A1 | KIS 해외 환산 | **실버그, 최초 커밋부터 있었음.** `HHDFS00000300`의 `output.rate`는 전일 대비 등락률(%)이다. 그런데 이 값을 USD/KRW 환율로 읽어서 KIS 동기화의 해외 평가금·예수금·평단을 환산했다. 0보다 크면 `cache_usd_krw_rate`로 전역 환율 캐시까지 덮어썼다. 그 결과 환전 계획의 "실시간 환율", 시장신호 FX 지표, 환율 알림 fallback까지 오염될 수 있었다. 테스트 픽스처조차 `rate: "1400"`으로 같은 오해를 하고 있었다. 수정: 키움·토스와 같은 `get_usd_krw_rate(cache)`를 쓴다. `get_overseas_price`는 `price_usd`만 돌려준다. `cache_usd_krw_rate`에는 500~3000 범위 가드를 두었다. 회귀 테스트는 수정 전 코드에서 실패하는 것을 확인했다 |
| A2 | 전술 적용 후 인사이트 | 전술 비중을 적용해도 `insights_key`가 무효화되지 않았다. 그래서 홈 "리밸런싱 기회"가 최대 1시간 동안 옛 목표 비중 기준으로 나왔다. 포트폴리오 CRUD와 같이 무효화하도록 고쳤다 |
| A3 | 인사이트 부분 실패 | 대시보드나 체커가 실패하면 줄어든 목록이 1시간 캐싱됐다. 이제는 실패가 있으면 `TTL_MARKET_SIGNAL_DEGRADED`로 짧게만 캐싱하고, `report_handled_failure`로 보고한다 |
| A4 | confirmed 시장신호 폴백 | 폴백이 Sentry에 보고하지 않았고, DB 오류 뒤에도 세션을 aborted 상태로 남겼다. 그러면 호출자(전술 GET·국면 잡)의 다음 commit이 깨진다. 지금은 보고하고, DB 오류(`SQLAlchemyError`)일 때만 rollback한다. 그 외 예외에서는 rollback하지 않는다. 계획 실행처럼 호출자에게 미커밋 변경이 남아 있을 수 있기 때문이다. 전술 쪽 죽은 이중 except도 지웠다 |
| A5 | 추천 백그라운드 갱신 | 실패하면 warning만 남았다. stale 결과가 남아 있어 사용자는 실패를 알 수 없으므로 Sentry로 보고하게 했다 |
| A6 | 환율 없는 환전 계획 | 실시간 환율도 1년 종가도 없으면 fallback 1300원으로 달러를 계산하고 있었다. 이제 `status="NO_RATE"`를 반환하고 프론트가 안내 문구를 보여 준다 |
| A7 | firebase 경고 | `Message.token` DeprecationWarning의 대체 인자 `fid`는 Firebase 설치 ID다. 저장된 값은 Capacitor `registration` 리스너가 준 FCM 등록 토큰이라 **fid로 바꾸면 발송이 깨진다.** 이 경고 하나만 억제하고 이유를 주석으로 남겼다 |
| B1 | FxPlanCard | 고른 포트폴리오가 NO_OVERSEAS가 되면 선택기가 사라져 다른 후보로 옮길 수 없었다. 이제 선택기는 상태와 관계없이 보이고, 후보에서 빠진 현재 선택도 함께 보여 준다. 일시적인 5xx에도 선택이 지워지던 것은 404일 때만 지우도록 바꿨다. 월 탭을 바꿀 때 스켈레톤으로 깜빡이던 것은 `keepPreviousData`로 막았다. `SELECT_SM`·`STALE_TIME`·범위 바 `role="img"`도 적용했다 |
| B2 | 전술 연동 자동매수 해제 | `dcaLinked`일 때 목록 키만 무효화하고 있었다. 그래서 `["rebalancing-alert", pid]`와 계좌별 캐시가 60초 동안 옛 TACTICAL 값으로 남았고, 그 사이 모달에서 저장하면 TACTICAL을 되저장할 수 있었다. `rebalancingAlertBase`와 `fxPlanBase`를 추가했다 |
| B3 | 지수 그룹 제안 | 계좌를 모두 해제하면 빈 배열이 파라미터 없이 전송돼 전체 계좌 기준 제안이 왔다. 이 경우에는 조회하지 않는다 |
| C | 정리 | 백엔드: `DCA_AUTO_BUY_PRESET`·`load_executable_account`·`load_kis/kiwoom_credentials`를 공개 이름으로 바꿨다. 다른 모듈이 사설 이름을 import하고 있었다. 프론트: 통화 토글에 `aria-pressed`를 달았고, 모달 통화 토글이 `h-5`에 갇혀 입력칸을 덮던 것을 `min-h-5`로 고쳤다. 그 밖에 매수 종목 select의 `!` 제거, `AmountCurrency` 미사용 export 제거, inline `import()` 타입을 일반 import로 바꿨다 |
| D1 | 프론트 이미지 Node | `node:25-alpine`(홀수, 2026-06 EOL)를 `node:24-alpine`(LTS)으로 바꿨다. Dependabot docker의 node major는 ignore로 두었다(홀수 버전 재유입 방지) |
| D2 | CI·의존성 설정 | coverage comment를 Dependabot·fork PR에서 건너뛰게 했다(읽기 전용 토큰). release 빌드는 Secrets가 비어 있으면 명확한 메시지로 실패한다. Dependabot `docker-compose`(prometheus·grafana 핀) 추가, `.dockerignore`에 커버리지 산출물 추가, ruff 하한 0.17, `@typescript-eslint/parser` 범위를 plugin과 맞췄다 |
| D3 | 문서 드리프트 | 새 모델 등록 위치를 `app/models/__init__.py`로 바로잡았다(문서 3곳이 `alembic/env.py`라고 적고 있었다). `fx-plan` queryKey 행과 무효화 경로를 추가했다. `useExchangeRate` 안내, ci.yml 잡 구성, android 타깃이 Windows 전용이라는 점도 반영했다. README 22행 리스크 칸도 정정했다 |

## 검증

- 백엔드:
  - ruff·format·mypy 클린, 전체 3187 passed.
  - A1·A3·A4·A6 테스트를 추가했다. A1 회귀 테스트는 수정 전 코드에서 실패하는 것을 확인했다.
  - firebase 경고는 사라졌다. 남은 pandas resample 경고는 라이브러리 내부에서 나온다.
- 프론트:
  - eslint `--max-warnings 0`, `npm run typecheck` 클린, 1907 tests.
  - 새 테스트 4건(5xx 선택 유지, NO_OVERSEAS 선택기, NO_RATE, dcaLinked 무효화)은 모두 수정 전 코드에서 실패하는 것을 확인했다.
- **미검증**:
  - node:24 프론트 이미지 빌드는 PR CI `docker-build`에서 처음 돈다.
  - KIS 해외 보유 계좌를 동기화한 뒤 해외 평가금이 Yahoo 환율 기준과 맞는지는 운영에서 확인해야 한다.

## 이관

> 2026-10-30: 아래 항목은 [100](100-technical-debt-2026-10-30e.md)에서 처리하거나 다시 분류했다.

- `order_cancel_service`·`execution_service`가 `fastapi.HTTPException`을 직접 던진다. 도메인 에러로 바꾸는 일은 실행 경로 전체에 걸쳐 있어 따로 한다.
- KIS 해외 취소 수량: 부분 체결 시 원수량을 보내는데, KIS가 이를 허용하는지 문서로 확인해야 한다.
- 이번에 하지 않은 것:
  - `fmtUsd` 공용화: FxPlanCard는 소수 0자리, OrderResultList는 2자리라 같은 함수가 아니다.
  - `exchangeRateAlertsQuery` 공용화: 설정 화면의 `useAlertCrud`는 queryKey·queryFn을 따로 받는다.
  - `PortfolioGroupItemRow`의 `item.group!` 타입 좁히기: 호출부의 속성 검사로는 객체 타입이 좁혀지지 않는다.
- `stores/authStore.ts`가 api 모듈을 우회하는 곳이 8곳 있다. 오래된 `!` 단언(StockAccountCard 등)도 남아 있다.
- 메이저 업그레이드(React 19, recharts 3, tailwind 4, TS 7, plugin-react 6)는 Dependabot ignore 정책대로 따로 진행한다.
- keep-alive 크론: 외부 핑 서비스를 정해야 정리할 수 있다.
- 마이그레이션 docstring 오기(aa2 `Revises`, 104aa75dc751 이름): 동작에 영향 없음.
- `vite-plugin-pwa → workbox-build` low 4건(98 이관 그대로).
- 로컬 `node_modules`의 `@typescript-eslint/*`가 8.72.0이다. lock은 8.72.1이므로 `npm ci`로 맞추면 된다.
