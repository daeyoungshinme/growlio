# 97 — 기술부채 감사 6차 (2026-10-30b)

## 배경

계획 95 뒤에 들어온 코드는 달러 환전 계획(96, `65db3bbb`) 하나다. 그 코드를 감사하면서 환전 계획이 쓰는 환율 경로까지 따라갔다. `get_usd_krw_rate`는 캐시가 비면 `settings.usd_krw_fallback_rate`(1300원)를 돌려준다. `fetch_usd_krw(force_refresh=True)`도 Yahoo가 실패하면(서킷이 열린 경우 포함) 같은 값으로 떨어진다. 캐시는 in-memory이고 TTL은 1시간이다. 그래서 Render 콜드스타트 직후나 Yahoo가 1시간 넘게 장애일 때 고정값 1300이 "현재 환율"로 쓰인다. 평가액 환산은 원래 그렇게 동작해 왔다. 문제는 **판정·발동**에 쓰는 곳이다.

브랜치: `feat/fx-exchange-plan`(PR #189) 위에 올렸다. 96 코드의 버그라서 같은 PR에 넣는다.

## 결과

| # | 항목 | 결과 |
|---|---|---|
| A1 | 환율 알림 잡 | 1300도 `> 0` 가드를 통과해서, 목표가 1300보다 높은 BELOW 알림이 전부 거짓 발동했다(메일·푸시가 나가고 알림이 비활성화됨). 96이 현재가 −σ(약 1380원대) BELOW 알림을 쉽게 만들게 해서 영향이 커졌다. `fetch_usd_krw`에 `allow_fallback=False`를 추가했다. 실시간과 캐시가 모두 없으면 0.0을 돌려주고, 잡은 그 회차를 건너뛴다 |
| A2 | 환전 계획 현재 환율 | fallback 1300일 때 "1년 중 낮은 편 · 하위 0%"가 나오고, "지금" 50% 환전과 1300 아래 목표 환율을 권했다. 이제 `get_live_or_cached_usd_krw`가 실값이 아니면 1년 일봉 마지막 종가로 대체한다. 응답에 `rate_is_live`를 추가했고, 카드에 "최근 종가 기준" 안내를 표시한다 |
| A3 | 시장 신호 환율 이격도 | 1300 − ma20이라 이격도가 항상 NORMAL로 나왔다. 실시간 캐시가 없으면 FRED 최신 관측값을 쓴다(네트워크 추가 호출 없음) |
| B1 | 분할 구간 목표 중복 | 1개월 σ가 약 20원 미만이면 0.5σ·1σ 목표가 10원 내림 후 같은 값이 됐다. 그러면 라벨·React key가 중복되고 같은 알림 생성 요청이 2번 갔다. 같은 목표는 한 구간으로 합치고, 목표는 현재 환율보다 최소 한 단계(10원) 아래로 둔다 |
| B2 | fx-plan 프론트 무효화 | 환전 계획은 목표 비중, 연결 계좌, `deposit_usd`, 적립 자동매수 알림을 읽는데 `invalidateDcaData`에서만 무효화되고 있었다. `fxPlanBase`를 sync·계좌·포트폴리오·리밸런싱 알림 무효화에 추가했다 |
| B3 | 삭제된 포트폴리오 선택 | 고른 포트폴리오가 삭제되면 404 문구가 카드가 마운트된 동안 계속 남았다. 오류가 나면 자동 선택으로 되돌린다. 구간 key는 `target_rate ?? label`로 바꿨다 |

## 검증

- 백엔드: ruff·ruff format·mypy 클린, 3179 tests, 커버리지 92.15%.
- 프론트: eslint `--max-warnings 0`, 변경 파일 prettier, `npm run typecheck`(앱+테스트) 클린, 1900 tests.
- 새 테스트: Yahoo 실패 + 캐시 미스면 0.0, 캐시 적중이면 캐시값. 환전 계획은 실값이 아니면 마지막 종가 기준이고 같은 목표는 합친다. 환율 신호는 FRED 최신값으로 대체한다. 카드는 종가 안내를 표시하고 404 뒤 자동 선택으로 돌아간다.

## 이관

- 95 이관 그대로: backend/Dockerfile(uv 핀·`--no-emit-project`)·`nginx:alpine` 태그 고정(Docker 빌드 검증 불가), `CashSummaryBar`의 `!` 단언, `rebalancingExecution` 수기 deps, TransactionForm 통화 로직 통합, `vite-plugin-pwa → workbox-build` low 4건.
- 평가액 환산용 `get_usd_krw_rate` 호출처(providers·price_service·stocks)는 기존 동작이라 유지한다.
