# 31. 기술부채 감사 (2026-09-09)

`docs/plans/30`(2026-09-06) + 라운드 #2 이후 HEAD 전진분은 tech-debt 커밋 3개
(`3170daa`/`4ab5c65`/`91eea56`) + `b60aa0f`(키움 해외 거래소 프로빙 폐기 → Yahoo 조회 기반
시장 판별) + `e369156`(yfinance quoteSummary 404 로그 필터)뿐. Explore 2개(백/프) 병렬 재조사.

30라운드 넘는 감사로 고전적 부채(죽은 코드, 미사용 의존성, TODO 마커, `any`, `@ts-ignore`)는
여전히 소진 상태. 신규 부채는 (1) `b60aa0f` 전환 잔여물, (2) 토스 연동(`b8a3d37`)이
"동기화 가능"/"주문 실행 가능" 두 개념을 분리시키며 표면화한 프론트 인라인 중복, (3) `e369156`
필터 과다 스코프뿐.

브랜치 `tech-debt-2026-09-09`.

## 같은 세션에 구현 완료

### 배치 A — 백엔드 저위험 (커밋 예정)
- `resolve_english_name()` 죽은 위임 래퍼 제거 — 프로덕션 호출부 0
  (`_overseas_name_enrichment.py`는 이미 `resolve_ticker_meta` 사용). 중복 테스트 클래스
  `TestResolveEnglishName` 삭제(`TestResolveTickerMeta`가 name+market 튜플 커버).
- `_STEX_TP_MARKETS`(b60aa0f에서 삭제) 참조하던 stale 주석 2곳 리워드
  (`kiwoom/constants.py`, `kiwoom/order.py`) — 상수 `KIWOOM_OVERSEAS_MARKET_CODES` 자체는
  `order.py`가 여전히 사용, 주석만 무효였음.
- `core/logging.py` yfinance 404 필터에서 맨몸 `"HTTP Error 404"` 패턴 제거 —
  `"No fundamentals data found for symbol"` 단일 패턴으로 quoteSummary 404만 특정
  (상장폐지 티커의 `.history()` 404 등은 다시 통과). `test_core_logging.py`에 통과 케이스 추가.
- 키움/토스 타임아웃 메시지 `"50초"` 하드코딩 → `int(SYNC_TIMEOUT_SECONDS)` f-string.

### 배치 B — 프론트 저위험 (커밋 예정)
- `ORDER_EXECUTABLE_ASSET_TYPES` 상수(`constants/index.ts`) + `isOrderExecutableAccount()`
  헬퍼(`utils/accounts.ts`) 신설 — 백엔드 `order_builder.ORDER_EXECUTABLE_ASSET_TYPES` 대응.
  인라인 `asset_type === "STOCK_KIS" || "STOCK_KIWOOM"` 6곳 치환
  (`rebalancingExecution/index.ts` ×3, `RebalancingTable.tsx`, `useRebalancingAlertForm.ts` ×3).
- F2 일부: `computeInitialBuyAndSelected`의 `getPrimaryAccountId`·매도행 프리선택이
  `STOCK_KIS`만 보던 것도 헬퍼로 교체 — KIWOOM 단독 보유 종목의 주 매수계좌 추론·매도행
  자동선택이 안 먹던 불일치 해소.
- `frontend/CLAUDE.md`의 존재하지 않는 `DiagnosisSummaryHeader.tsx` 참조 제거.
- `@vitest/ui` 미사용 devDependency 제거(라운드 #2 `@vitest/coverage-istanbul` 제거와 동일 성격).

### 배치 C — 테스트 커버리지 (커밋 예정)
- `utils/riskLevel.ts` 단위 테스트 신규(`utils/__tests__/riskLevel.test.ts`) — 커버리지 0%였음.

검증: 백엔드 관련 190 tests(provider/kiwoom/toss/overseas/logging/stock_search) + ruff/mypy 클린,
프론트 1483 tests / lint·tsc·build 클린.

## 이관 항목 (이번 세션 미착수)

### 1. 대형 `_compute_*` near-clone 분해 — 구 plan 30 #2 (C2)
C1(`91eea56`)은 공유 *헬퍼*만 `_goal_recommendation_common.py`로 추출했고 `_compute_*` 스켈레톤
중복은 그대로:
- `goal_portfolio_optimizer._optimize_goal_portfolio` ~212줄
- `goal_age_recommendation_service._compute_age_based_recommendation` ~199줄
- `goal_horizon_recommendation_service._compute_horizon_recommendations` ~197줄
- `goal_horizon_recommendation_service._build_horizon_result` ~182줄
- `goal_recommendation_service._compute_goal_recommendation` ~170줄

공통 스켈레톤(후보 유니버스 → 배당 attach → MVO → 결과 빌드 → 배당후보 제안)을 1번 공통 모듈에
헬퍼로. **characterization 스냅샷 테스트 하네스 선행 필수** — 실추천 결과 회귀 표면 큼. 멀티 세션.

### 2. `assets.py` 브로커 분기 스펙테이블화 — 구 plan 30 #3 (B4)
`api/v1/assets.py` `create_account`(:186-219)·`update_account`(:273-283)에 KIS/키움/토스
near-identical 분기 3벌(존재검증 → `model_dump(exclude=_CREDENTIAL_FIELDS)` → encrypt 2필드 →
asset_type). **KIS 분기만 `asset_type` 미설정 quirk** 먼저 확인(스키마 validator가 채우는 듯).
`{data_source: (asset_type, required_fields, encrypt_fields, error_msg)}` 스펙 + 루프로 축약.
계좌 생성 경로 — 회귀테스트 필수. ~2-3h.

### 3. `market_signal_service.py`(835줄) 분해 — 구 plan 24 #2 / 29 #3 / 30 #5
`fetch_*_signal` ~12개 + `compute_composite_signal` + 캐싱 + confirmed-level durable state 머신.
패키지 분리(fetchers / composite / state). AUTO 게이트 신호원이라 hysteresis/raw 양쪽 회귀. 저긴급.

### 4. 키움 해외 주문 폴백 라우팅 (신규)
`_overseas_name_enrichment.py`의 시장 판별이 Yahoo 조회 실패 시 `_FALLBACK_MARKET = "NASDAQ"`로
폴백되고 `overseas_stock_meta_key`에 **7일 캐시**된다. 그 창 동안 NYSE/AMEX 상장 종목의
리밸런싱 매수/매도 주문이 `kiwoom/order.py`에서 `stex_tp="ND"`로 라우팅됨. 과거 프로빙 방식도
SPY류를 못 맞췄으므로 순회귀는 아니나, 실자금 경로에서 외부 조회 실패가 조용히 오라우팅으로
이어지는 구조. 권위 있는 거래소 소스가 없어 완전 수정 불가 — 최소안: 폴백 시 경고 로그 +
`backend/CLAUDE.md` 문서화. ~30분+.

### 5. 토스 `market` 판별 필터 불일치 (신규, 잠재)
`toss/balance.py:129`는 `marketCountry != "KR"` → `"US"` 센티널로 설정하지만
`toss_provider.py:117`은 `currency == "USD"` 포지션만 enrich한다. 비-KR·비-USD 보유
(토스가 향후 도쿄/홍콩 지원 시)는 `"US"` 센티널이 Position까지 흘러가
`is_overseas_market("US")` == `False` → 세금/리밸런싱에서 국내로 오분류. 현재 토스는 KR+US만
지원해 잠재 상태. 필터 기준 통일(`_needs_market_resolution` 기반) 또는 `raw_to_position`에서
센티널 방어 매핑. ~30분.

### 6. `useRebalancingPrices.ts` 가격 폴백이 `STOCK_KIS`만 (신규)
`useRebalancingPrices.ts:21` `findKisAccountId`(가격 폴백)가 `STOCK_KIS`만 필터. 실행 경로는
KIWOOM을 포함하므로 KIWOOM 단독 종목의 가격 폴백이 안 먹을 수 있음. 주석은 "KIS 연동 계좌"라
의도적일 가능성 — 키움 가격 조회 API 도메인 확인 후 판단(배치 B에서 F1 헬퍼 치환 범위에서 제외함).

### 7. plan 27 이관분 — 구 plan 30 #7
(2-leg 부분실행 가시성, AUTO 매수 leg 실행 직전 잔고 clamp) 실자금 리스크. 별도 설계 세션.

### 8. lucide-react 1.x deprecated alias 스윕 미완
라운드 #2 배치 B가 5파일(`CheckCircle→CircleCheck` 등)만 처리. 나머지 ~20파일:
`AlertTriangle→TriangleAlert`, `LineChart→ChartLine`, `BarChart2→ChartNoAxesColumn`,
`BarChart3→ChartColumn`, `MoreVertical→EllipsisVertical`, `Edit2→Pen`, `Wand2→WandSparkles`.
lucide 1.39도 계속 export하고 `@deprecated` JSDoc 없어 빌드 경고 0 — 순수 네이밍 일관성.
기계적 치환 + `no-restricted-imports`로 alias 차단 재발방지 규칙 동반 검토.

### 9. `useRebalancingExecution` 훅 커버리지 보강
`rebalancingExecution/index.ts` ~525줄, 라인 커버리지 45%(268-493 대량 미커버). `reducer.ts`(98%)
`types.ts`는 이미 분리(의도된 패키지 구조). 추가 분해보다 커버리지 보강 쪽.

### 10. 프론트 커버리지 임계값 실측 대비 여유 과다
임계값(`vite.config.ts`): lines 65 / functions 51 / branches 51 / statements 63.
실측(2026-09-09): lines ~68.9 / functions ~55.7 / branches ~54.7 / statements ~67.5.
갭 3.7~4.5%p. functions/branches는 51로 살짝 낮게 고정 — 이번 배치 C 반영 후 재측정해 소폭 상향 여지.

### 11. advancedChunks `vendor-query` 그룹이 transitive dep 미포함
`vite.config.ts`의 `test: /[\\/]node_modules[\\/]@tanstack[\\/]react-query[\\/]/`가
`@tanstack/query-core`(react-query 런타임 의존)를 안 잡음. 빌드 정상, 영향 미미
(query-core가 엔트리/페이지 청크로 흡수). 필요 시 regex를 `/@tanstack[\\/](react-)?query/`로. 불급.

## 검증

```bash
cd backend && uv run pytest -q && uv run ruff check . && uv run mypy app/
cd frontend && npm run test && npm run lint && npx tsc --noEmit && npm run build
```
