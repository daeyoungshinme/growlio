# 24. 기술부채 이관 항목 (2026-07-29 감사)

2026-07-29, "기술부채 있는지 검토해서 수정 계획 세워달라"는 요청으로 백엔드/프론트엔드/CI-인프라를 병렬 조사(Explore 서브에이전트 3개: docs/plans 백로그, 코드 전반 마커, 최근 커밋·CI 상태)한 결과. 저위험 항목(`goal_recommendation_service.py` 대형 함수 2개 분해, `RealEstateSection.tsx` 파일 분리, Dependabot 설정, GitHub Actions SHA 고정, 프론트 커버리지 임계값 실측 상향)은 같은 세션에서 바로 구현 완료 — 자세한 내용은 `docs/plans/20-technical-debt-2026-07-23.md` 갱신분 참고. 이 문서는 손이 많이 가거나 실거래 리스크가 있어 **다음 세션으로 이관**하는 항목만 기록한다.

## 이관 항목

### 1. `hooks/rebalancingExecution/index.ts` 분해 (528줄)
- `reducer.ts`는 이미 분리돼 있으나 `useRebalancingExecution` 훅 본체(100~519줄)는 여러 `useEffect`가 공유 state/ref를 통해 강하게 얽혀 있고(`eslint-disable react-hooks/exhaustive-deps`가 4곳), 실제 리밸런싱 주문 실행(실거래) 경로라 기계적 분해 시 회귀 위험이 큼.
- 다음 세션에서 시도할 경우: 먼저 effect별 책임 경계(잔고 로딩/선택 상태/실행 뮤테이션)를 명확히 정리하고, 기존 테스트로 커버되지 않는 분기가 있으면 분해 전에 characterization test부터 추가.

### 2. 신규 발견 대형 백엔드 서비스 파일
- `services/rebalancing/plan_service.py`(999줄) — AUTO 리밸런싱 2단계 플랜(계획 생성→매수 대기/매도 승인→실행) 생명주기 전체를 관리하는 실거래 경로. 리팩토링 시 세금/시장신호/일일한도 게이트 케이스별 회귀 테스트 선행 필요.
- `services/market_signal_service.py`(835줄) — AUTO 게이트·등급전환 알림의 신호원(8개 매크로 지표). 계산 로직 분해 시 hysteresis(`get_confirmed_composite_level`)와 raw 값 양쪽의 회귀 검증 필요.
- `services/email_templates.py`(847줄) — 상대적으로 저위험(HTML 템플릿 문자열 위주, 실거래 무관). 다음 세션 우선순위로 제안.

### 3. `portfolio_optimizer.py:170`의 `noqa: C901`
- 효율적 프론티어 계산 함수가 ruff 복잡도 상한을 넘어 예외 처리됨 — god-function 후보로 기록만, 이번 세션에서는 미착수.

### 4. 프론트엔드 500줄대 파일 워치리스트 (긴급하지 않음)
`GoalSettingWizard.tsx`(559), `StockAccountModal.tsx`(519), `InvestPlanPage.tsx`(516), `RebalancingOrderTable.tsx`(511), `StockHoldingsTable.tsx`(509), `InvestmentGoalCard.tsx`(507) — 500줄 기준을 소폭 초과한 수준. 참고용 기록만, 별도 조치 불필요.

### 5. Kiwoom 해외주식 주문 API-ID 실계좌 검증
- `docs/plans/20-technical-debt-2026-07-23.md` 1번에서 이월. 서드파티 오픈소스 클라이언트 소스 기반으로 API-ID/필드명을 확정했으나 공식 문서로 재확인한 것은 아님 — 실계좌 첫 해외 매수/매도 주문 시 응답 필드 실측 검증 권장. 실계좌 필요, 사용자 트리거 대기.

## 이번 세션에서 조사 후 "조치 불필요"로 종결한 항목 (참고용, 재작업 대상 아님)

- **의존성 취약점 스캔 블로킹 전환** — `pip-audit`(백엔드: pillow/pyasn1/pydantic-settings/python-multipart/soupsieve/starlette 등 다수 기존 취약점)과 `npm audit`(프론트: critical 1건 포함 9건, tar/js-yaml/postcss/react-router/fast-uri)이 모두 현재 클린하지 않아 `continue-on-error: true`를 유지. Dependabot이 이번 세션에 새로 설정됐으니 향후 주간 PR로 점진적으로 해소한 뒤 재검토.
- **GitHub Actions SHA 고정 여부** — 태그(`@v6` 등)만 고정돼 있던 것을 커밋 SHA로 전환 완료(이번 세션). 향후 Dependabot의 `github-actions` ecosystem이 SHA 갱신 PR을 자동 생성.

## 기존에 이미 문서화되어 보류 중인 항목 (재작업 대상 아님, 참고용 재확인만)

- 프론트엔드 메이저 버전 업그레이드 로드맵 (`docs/plans/20` 5번) — 변경 없음, 여전히 유효.
- 시장신호 방법론 Phase 2(AUTO 게이트 raw score 반영)/Phase 3(국내 리스크 지표 조사) — `docs/plans/21-market-signal-methodology.md`, 실자금 영향으로 의도적 보류.
