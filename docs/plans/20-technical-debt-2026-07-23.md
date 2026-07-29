# 20. 기술부채 이관 항목 (2026-07-23 감사)

2026-07-23, "기술부채 있는지 검토해서 계획 세워달라"는 요청으로 백엔드/프론트엔드를 병렬 조사(Explore 서브에이전트 3개: docs/plans 현황, 백엔드, 프론트엔드)한 결과. 저위험 항목(활성 계좌 헬퍼 적용 확산 6개 파일, 브로커 잔고·포지션 집계 서비스 테스트 추가, 의존성 버전 상한)은 같은 세션에서 바로 구현 완료 — 이 문서는 손이 많이 가거나 외부 의존성이 있어 **다음 세션으로 이관**하는 항목만 기록한다.

## 이관 항목

### 1. 해외주식 주문 Kiwoom API-ID placeholder — ✅ 완료 (2026-07-23)
- `backend/app/kiwoom/constants.py`, `backend/app/kiwoom/order.py`의 `"kt0XXXX"` placeholder를 실제 값으로 교체:
  - `API_ID_OVERSEAS_BUY = "ust20000"`, `API_ID_OVERSEAS_SELL = "ust20001"` (엔드포인트 `/api/us/ordr`)
  - 거래소 코드(`stex_tp`)를 `NY`/`ND`/`NA`로 수정 — 기존 placeholder `NYSE`/`NASD`/`AMEX`는 오기(誤記)였고, `balance.py`가 이미 실측으로 확정해둔 `_STEX_TP_MARKETS`(`ND`/`NY`/`NA`)와 어긋나 있었음
  - body 필드명도 국내주문의 `dmst_stex_tp`를 그대로 재사용하고 있었는데 해외주문은 `stex_tp`가 맞는 필드명이었고, `trde_tp`도 국내(1자리 `"0"`/`"3"`)와 달리 해외는 2자리(`"00"`/`"03"`)여야 함 — 둘 다 수정
- **근거**: 오픈소스 .NET 클라이언트 `dongbin300/KiwoomRestApi.Net`의 `Clients/UsStocks/KiwoomRestApiClientUsStockOrder.cs`/`Objects/ApiEndpoint.cs`/`Enums/UsStock/Order/*.cs`를 GitHub REST API로 직접 조회해 확인. 거래소 코드(`ND`/`NY`/`NA`)는 이 프로젝트의 `balance.py`가 별도로 실측 확정해둔 값과 정확히 일치해 교차검증됨.
- **주의**: 공식 문서 원문으로 재확인한 것은 아니므로(3rd-party 라이브러리 소스 기반), 실계좌 첫 해외 매수/매도 주문 시 응답 필드(`ord_no` 등 파싱 부분)는 실측으로 한 번 검증 권장.

### 2. `goal_recommendation_service.py` 대형 함수 분해 — ✅ 완료 (2026-07-29)
- `_compute_goal_recommendation`에서 `_fetch_overall_candidate_data`/`_filter_candidates_with_cagr`를, `_build_horizon_result`에서 `_build_horizon_candidate_universe`/`_single_candidate_horizon_result`를 순수 extract-method로 분리(로직/분기/상수 변경 없음). 공개 진입점(`get_goal_recommendation`/`get_horizon_recommendations`/`get_age_based_recommendation`) 시그니처는 그대로 유지.
- 검증: `pytest -k goal_recommendation`(167개) + 백엔드 전체 스위트(1974 passed, 87.78% coverage), ruff/mypy 클린.

### 3. Join/집계/컬럼-select 쿼리용 "활성 계좌 조건" 헬퍼 확장
- 이번 세션에 `_account_queries.active_accounts_stmt()`를 적용한 6개 파일은 전부 `select(AssetAccount).where(user_id==, is_active==True, ...)` 형태였음.
- 반면 `dca_service.py`, `tax_service.py`, `backtest_service.py`, `pension_contribution_service.py`, `position_aggregator.py`, `dividend/orchestrator.py`, `returns_calculator.py`, `goal_candidate_service.py`, `goal_recommendation_service.py:716` 등은 `AssetSnapshot`과의 join 또는 컬럼-select(`select(AssetAccount.tax_type, ...)`) 형태라 `Select[tuple[AssetAccount]]`를 반환하는 현재 헬퍼가 맞지 않음. **필터 자체는 이미 정확히 존재하므로 버그는 아님** — 다만 조건이 각 파일에 반복 작성되어 있음.
- 검토 필요: 재사용 가능한 WHERE절 fragment(`ACTIVE_ACCOUNT_CONDITION = AssetAccount.is_active == True` 같은 단순 상수)를 만들지, 아니면 현재처럼 파일별로 명시하는 게 오히려 가독성이 나은지 — 후자라면 이 항목은 "조사 완료, 조치 불필요"로 종결해도 됨. 다음 세션에서 실제 가치가 있는지부터 재확인.

### 4. 프론트엔드 대형 컴포넌트 재분해 — 재검증 결과 부분 종결 (2026-07-29)
- `src/pages/SettingsPage.tsx`(593줄) — ✅ 이미 해결됨. 2026-07-26 세션에서 `/settings/notifications`(`NotificationSettingsPage`)로 알림 설정 상세가 분리되며 339줄로 축소(`frontend/CLAUDE.md` 참고).
- `src/components/rebalancing/RecommendationCard.tsx`(741줄, 재검증 시점 778줄) — ✅ 의도적 설계로 종결. 2026-07-26 세션에서 3탭 공통 렌더(드리프트 배지·비중 목록·안내문구·적용 섹션)가 `RecommendationResultPanel.tsx`로 이미 분리됨. 남은 부분(탭별 `useMutation`·탭 전환 상태머신)은 3탭이 공유하는 파생 상태(activeTab/selectedTaxType/taggedAccounts/cashEquivalentMatches/horizonTargetPortfolio 등)가 강하게 얽혀 있어 `frontend/CLAUDE.md`에 "이 파일에 그대로 유지"라고 명시된 의도적 설계 — 추가 분해 대상 아님.
- `src/components/assets/RealEstateSection.tsx`(611줄) — ✅ 완료 (2026-07-29). 이미 독립적이던 4개 named export(`RealEstateAccountModal`/`RealEstateEditModal`/`RealEstateSummaryCard`/`RealEstateAccountCard`)를 `components/assets/realEstate/` 하위 개별 파일로 분리, 원 경로는 barrel re-export로 유지(기존 import 불변). 로직 변경 없음 — typecheck/lint/test(20개) 통과.
- `src/hooks/rebalancingExecution/index.ts`(528줄) — 미착수, `docs/plans/24-technical-debt-2026-07-29.md`로 이관. effect 간 상태 공유가 강하고 실거래 실행 경로라 신중한 별도 세션 필요.

### 5. 프론트엔드 메이저 버전 업그레이드 로드맵
`npm outdated` 기준 뒤처진 메이저 버전:
- `@sentry/react` 8.x → 10.x, `recharts` 2.x → 3.x, `react-router-dom` 6.x → 7.x, `tailwindcss` 3.x → 4.x, `zustand` 4.x → 5.x, `lucide-react` 0.x → 1.x, `vite` 6.x → 8.x, `react`/`react-dom` 18.x → 19.x.
- 각각 breaking change가 있어(Tailwind 4는 설정 파일 구조 전면 변경, Recharts 3/Router 7은 API 변경) 한 번에 다 올리면 회귀 위험이 큼. 다음 세션에서 항목별로 리스크/이득을 따져 우선순위를 정하고, 하나씩 별도 PR로 검증 권장.

## 이번 세션에서 조사 후 "조치 불필요"로 종결한 항목 (참고용, 재작업 대상 아님)

- **프론트 `exhaustive-deps` 억제** — `useAnalysisState.ts:78`, `StockPositionsModal.tsx:77` 모두 이미 근거 주석 있음(Set→문자열 직렬화 의존성 추적 / `editor.setRows`·`enrichRows`가 매 렌더 새 참조라 의존성 포함 시 무한루프). 실제 버그 아님.
- **백엔드 dead code** — 뚜렷한 죽은 코드 없음. `alerts/alert_service.py`의 `__getattr__` shim, `FMP_API_KEY` 예약 설정 등은 CLAUDE.md에 이미 "의도된 설계"로 문서화됨.
- **프론트 dead code / a11y** — import 미참조 컴포넌트 없음, 아이콘 전용 버튼 `aria-label` 누락 없음.

## 기존에 이미 문서화되어 보류 중인 항목 (재작업 대상 아님, 참고용 재확인만)

이번 감사에서 다시 발견되었으나 이미 `docs/plans/README.md`에 의도적 보류로 기록되어 있어 재작업하지 않음:
- 통합 알림 센터 전용 화면 (계획 4번, 9번 3소항목)
- 자산유형 3분류 하드코딩 / "배당" 레이블 중복 (계획 7번 4·5소항목)
- 연금저축/IRP/ISA 절세 실행 타이밍 추천, 시장신호 임계값 백테스트 검증 (계획 14번 A3·A4)
- 캐시 prefix 인덱스 (계획 18번 3소항목 잔여분)
- 정기 자동매수, ETF TER 투명성 (경쟁앱 기능격차 로드맵)
