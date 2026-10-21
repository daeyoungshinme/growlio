# 리밸런싱 탭 정보구성·프로세스 개선 계획 (계획 63)

## Context
요청: 리밸런싱 탭 전체에서 **중복 정보**와 **프로세스상 정보 구성·처리**의 개선점을 찾아 수정 계획 수립.
계획 62가 코드 레벨(버그·죽은코드·구조)을 다뤘다면, 이번 감사는 "사용자가 보는 숫자·흐름" 축이다. 2개 Explore(정보구조 맵 / 프로세스 플로우)로 조사했고 핵심 항목은 코드로 직접 재확인(✅).

핵심 결론: 같은 개념(이탈·예수금·시장신호·알림설정 여부)이 화면마다 **다른 소스·다른 기준·다른 라벨**로 계산돼 숫자가 어긋나고, 흐름 중간에 이미 고른 포트폴리오를 다시 고르거나 수동 sync→재분석을 해야 하는 끊김이 있다. 그리고 실주문 실버그 1건.

**산출물**: 실행 첫 단계로 이 계획을 `docs/plans/63-rebalancing-info-flow-2026-10-21.md`로 저장 + `docs/plans/README.md` 인덱스 추가. 계획 62의 C~F와 겹치는 항목은 "(62 Xn)"로 표기해 62에서 처리(중복 작업 금지).
브랜치: 현재 `fix/rebalancing-review-2026-10-21` 위에서 진행(62 A·B 커밋 포함, 미푸시). 착수 전 `git status`/`git diff` 확인(동시 세션 규칙).

## 진행 상황 (2026-10-21, 브랜치 `fix/rebalancing-review-2026-10-21`)
- **완료**: P0(4b239a29), P1-1(f59dddda), P1-2·P1-4(d5a7301b), P1-5(76dec312), P3 + P2-3(2b16a85c), P2-1·P2-2·P2-5(ba93d9d8), P4(7755d338).
- **P1-3 완료**(= 62 E1, 사용자 승인: 알림 기준으로 통일) — `filter_drifting_items`(임계치 **초과**)를 `service.py` 단일 정의로(order_builder는 재노출), 진단 요약 `compute_portfolio_drift_summary`가 `analyze_rebalancing(include_implicit_cash=True)` 결과로 판정, 수동 analyze API도 `include_implicit_cash=True`, 프론트 `getDriftStatus`·분석 진단카드도 `>` + 모든 항목. 계좌 범위는 AGGREGATE 기준 이미 동일(PER_ACCOUNT 알림은 계좌 1개 범위라 포트폴리오 단위 진단과 의도적으로 다름).
  - 바뀌는 숫자: TOTAL_ASSETS 포트폴리오의 목표 밖 예수금·목표에 없는 보유 종목이 이탈로 잡힘, 임계치와 정확히 같은 이탈은 더 이상 "필요"가 아님.
- 계획 대비 변경:
  - P0: 백엔드는 실행기가 아닌 `ExecutionRequest` 스키마 검증(422)으로 막음 — plan 경로는 스키마를 거치지 않아 영향 없음. 수동 모달 기본값은 FULL 유지, "(권장)" 라벨만 제거.
  - P1-1: `/broker-balance-all` 포트폴리오 계좌 필터는 생략 — 합계가 이미 `tradableAccounts`(포트폴리오 계좌)만 돌아 표시 불일치는 없음(과조회만).
  - P1-5: GET에서 확인 단계를 전진시키지 않도록 `get_last_composite_level`(저장값 읽기)만 사용.
  - P2-1: 세 "집중도"는 서로 다른 지표(자산 유형 비중 / 최대 종목 비중 / 종목 HHI)라 제거 대신 라벨 구분.
  - P2-4: `isDcaAutoBuyPreset`로 이미 단일 판정 + 고급 모드 칩 존재 → 변경 없음.
  - P3-4: 추가 발견 — 세금/시장/하루한도 보류·실행실패 푸시 4종이 딥링크 매핑이 없어 눌러도 첫 화면에 머묾 → 매핑 추가.
- 검증: 백엔드 2800 passed / 91.30%, ruff·mypy 클린. 프론트 1718 passed, tsc·eslint·prettier 클린.

---

## 배치 P0 — 실주문 실버그 (최우선)
| # | 문제 | 위치 | 수정 |
|---|---|---|---|
| P0-1 ✅ | 수동 실행 모달에서 "매수만" 선택해도 **매도 주문이 그대로 나감**. `strategy`는 상태·이력에만 저장되고 `buildOrders()`와 백엔드 `execute` 경로 모두 무시(BUY_ONLY 필터는 plan 경로 `order_builder.py:312`에만 존재). 기본값도 라벨("매수만 (권장)")과 달리 FULL | `hooks/rebalancingExecution/index.ts:140,286-330`, `components/rebalancing/RebalancingConfirmStep.tsx:54-73`, `services/rebalancing/execution_service.py:207-224,342` | ① 프론트: BUY_ONLY면 매도 행을 표/선택/현금계산에서 제외(매도 섹션 "매수만 전략 — 매도 없음" 안내) ② 백엔드 방어: `execute_rebalancing_orders`에서 `strategy=="BUY_ONLY"`면 SELL 주문 거부(400) 또는 SKIPPED 기록 ③ 기본값을 라벨과 일치(권장 표기 쪽으로 맞추거나 권장 문구 제거 — 둘 중 하나). 회귀 테스트: BUY_ONLY 요청 시 SELL 미발주 |

## 배치 P1 — 같은 개념, 하나의 소스 (숫자 불일치 해소)
- **P1-1 ✅ 예수금 기준 통일**: 분석 진입 경로별로 예수금이 다름 — 버튼 분석만 `/broker-balance/{id}` 실잔고 override, 자동분석(포트폴리오 선택·딥링크, `useAnalysisState.ts:91,102`)과 sync 후 재분석(`AnalysisPanel.tsx:209`)은 DB 예수금. → override 조회를 `triggerRebalancingAnalysis` 내부로 이동해 **모든 경로가 동일 기준**. 실행 모달의 `/broker-balance-all`은 포트폴리오 연결 계좌만 필터. 분석 요약카드 "예수금" 라벨에 기준(“동기화 시점”/“실시간”) 표기. (62 E3의 useQuery 전환과 함께 하면 자연스럽게 해소)
- **P1-2 이탈 라벨·임계치 통일**: 진단 행 "필요/점검 권장", 포트폴리오 카드 "X% 이탈/주의/안정", 분석 진단카드 "리밸런싱 필요/점검 권고/안정" → 공용 `driftStatusLabel()` 1개(utils/portfolio.ts)로. 분석카드 임계치(`AnalysisPanel.tsx:203` `rows[0].threshold_pct`, is_active 무시)를 백엔드 `_portfolio_queries.py:38`과 같은 "활성 알림 최소값"으로.
- **P1-3 이탈 계산 기준 통일** = 62 E1(드리프트 base·`>=`/`>`·암묵 CASH·계좌 스코프). **사용자 확인 필요 항목** — 이번 감사로 4경로(진단 summary / 수동 analyze / alert_check / plan 생성) 차이표가 확보됐으므로 62 E1을 이 표 기준으로 실행. 권장 기준: `compute_base_value_krw` + `>` + 알림과 동일한 CASH 처리.
- **P1-4 "알림 설정됨" 판정 통일**: 포트폴리오 카드/배너(`PortfolioManageTab.tsx:98`)와 `AutoInvestStatusBanner`가 `is_active` 미필터 → 꺼진 알림이 "알림"으로 보이고 진단·설정에선 "미설정". 공용 셀렉터 `getActiveAlertsByPortfolio()`(utils/portfolio.ts `mergeAlertsByPortfolio` 확장)로 통일, 비활성은 "꺼짐" 배지로 별도 표시.
- **P1-5 시장신호 등급 이원화 노출**: 진단 배너는 raw `/market-signals`, AUTO 게이트·전술은 hysteresis 확정 등급(`get_confirmed_composite_level`) → 배너는 RED인데 AUTO가 도는(또는 반대) 상황. 배너에 "자동실행 판단 기준: 확정 등급 X(N일 연속 확인)" 한 줄 추가(`/market-signals` 응답에 confirmed level 필드 추가), 전술 탭 매크로 배지에도 동일 라벨.

## 배치 P2 — 중복 정보 정리 (화면당 한 곳)
- **P2-1 진단 탭 "집중도" 3중 표시**: StatusCard 자산집중도 게이지 + RiskMetricsCard 최대비중·분산점수(같은 탭) + 분석 HHI. → 진단에서는 RiskMetricsCard 하나로(게이지 제거 또는 RiskMetricsCard에 흡수), 분석 HHI는 "포트폴리오 내" 문구로 구분.
- **P2-2 AutomationStatusBar 2회**: AnalysisPanel 리밸런싱 모드·전략 모드 각각 렌더 → 모드 토글 위 공통 1회.
- **P2-3 동기화 버튼 2개**: 결과 섹션(`RebalancingResultSection.tsx:25-32`, 재분석 없음) vs `RebalancingAccountSyncSection`(재분석 있음) → 하나로, 동기화 성공 시 **항상 재분석** (62 D3 `useSyncAccounts`와 합쳐서).
- **P2-4 빠른 적립(Quick DCA) vs 고급 설정**: 같은 row(MONTHLY+SCHEDULE_ONLY+AUTO+BUY_ONLY)를 두 UI로 만듦. 선택 화면은 유지하되 고급 모드에서 프리셋과 일치하면 "정기 적립식 프리셋" 칩 + "빠른 설정으로 보기" 전환 제공 → 개념은 "프리셋"으로 일원화(문구·`AutoInvestStatusBanner` 판정 공용 함수 `isQuickDcaPreset()`).
- **P2-5 "전략" 용어 3중 의미**: 실행 전략(BUY_ONLY/FULL/TWO_PHASE) / 전략 분석 카드(팩터·프런티어) / 전술. → 전략 분석 버튼·카드 명칭을 "효율 분석"(또는 "팩터·효율 분석")으로 변경, 실행 전략은 "주문 방식"으로. 라벨 상수 한 곳(`constants/rebalancingConfig.ts`).
- 기존 계획 중복은 62에서 처리: 실행결과 목록 2벌·CashSummaryBar 2벌·AccountPicker 2벌(62 D3), StatusCard variant(62 D1).

## 배치 P3 — 흐름 끊김 해소 (재선택·수동 단계 제거)
- **P3-1 실행 후 낡은 분석**: 실행 성공 후 모달 닫으면 실행 전 분석이 그대로(10분 후에야 "N분 경과"). → 실행 성공 시 analysis를 "실행됨 — 동기화 후 재분석" 상태로 표시하고 결과 화면에 "동기화하고 다시 분석" 단일 CTA(P2-3).
- **P3-2 새 포트폴리오 생성 후 미선택**: 추천→"새 포트폴리오 만들기"→저장 시 편집기만 닫힘(`PortfolioManageTab.tsx:212-215`). → 생성 응답 id로 `portfolioId` 설정 + 자동 분석(수정 적용 경로 `RebalancingPage.tsx:245`와 동일 동작).
- **P3-3 포트폴리오 선택 상태 공유**: 추천 탭 대상 포트폴리오(`RecommendationCard.tsx:193`)·전술 탭 select(`TacticalAllocationTab.tsx:360`)가 URL `portfolioId`를 무시/1회만 읽음 → 세 탭 모두 URL `portfolioId`를 단일 진실로 사용(62 E4 `useRebalancingUrlState`와 함께, 62 F "선택 포트폴리오 URL 반영" 포함).
- **P3-4 딥링크 목적지 정리**:
  - 복합신호 전용 푸시가 `type=REBALANCING + portfolio_id`로 특정 포트폴리오 주문 모달을 엶(`alert_check.py:162-168,197`) → 복합신호 발송은 `type=MARKET_SIGNAL`(포트폴리오 없음) → 진단 탭.
  - 이메일(진단)·푸시(포트폴리오+실행모달) 목적지 불일치 → 둘 다 `rtab=포트폴리오&portfolioId=..`(푸시만 openExecution 유지 여부는 P1-1 완료 후 재평가).
  - DCA 예수금 부족: 푸시는 `/invest-plan`, 홈 할일은 `/rebalancing?openAlert=1` → 한 곳으로(입금이 해결책이므로 계좌/입금 안내가 있는 쪽).
  - 설정의 `RebalancingAlertSummaryCard` 링크에 `portfolioId`+`openAlert=1` 부여(`settings/RebalancingAlertSummaryCard.tsx:38-57`).
- **P3-5 진단 빈 상태**: "포트폴리오 만들기" CTA가 탭만 전환 → 편집기까지 열기. 전술 탭 빈 상태에 CTA 추가.

## 배치 P4 — 알림/자동실행 설정의 정보 투명성
- **P4-1 ✅ 숨은 notify_time**: AUTO 모드에선 notify_time 입력이 숨겨지는데(`AlertModeSection.tsx:74`) 저장(기본 08:30)되고 `alert_check`가 AUTO에도 그 시각에 이탈 리포트를 발송(`alert_check.py:232-236`) → AUTO 사용자는 08:30 리포트 + `auto_execution_time` 계획 메일 2통. → AUTO에서도 "리포트 시각"으로 노출(또는 AUTO는 리포트 생략 옵션). 결정: **노출**(동작 불변, 투명성만 개선) 권장.
- **P4-2 "지금 계획 생성"이 저장/미저장 설정 혼합**(`AlertActionsSection.tsx:45-52`, `quick_execute_service.py:161`) → 폼이 dirty면 버튼 비활성 + "저장 후 실행" 안내.
- **P4-3 스코프 전환 시 기존 알림 삭제**(`alert_scope.py:52-62`) → 전환 확인 모달에 "기존 N개 설정이 삭제됩니다" 명시(동작은 유지).
- **P4-4 전술 적용 ↔ AUTO 알림**: 전술 적용 시 해당 포트폴리오에 AUTO 알림이 있으면 "다음 자동실행(시각)에 새 목표로 주문됩니다" 경고를 확인 모달에 표시(`TacticalAllocationTab.tsx:309-311` 문구 수정). 추천 적용 확인 모달도 동일.
- **P4-5 BUY leg 승인 표면 불일치**: 앱은 즉시 실행, 공개 이메일 페이지는 취소만 → 공개 페이지 안내 문구에 "앱에서 즉시 실행 가능" 명시(기능 확장은 보류).

## 이관/보류
- 추천 "전체" 기준 자산(전 계좌) vs 포트폴리오 계좌 범위 불일치(`rebalancing.py:178-191`) — 추천 모델 의미 변경이라 별도 검토.
- `/execute` vs `/quick-execute` 엔드포인트 명명, 목표비중 변경 출처(수동/추천/전술) 이력 기록 — 저가치/스키마 변경.
- 복합신호가 유저 단위라 모든 포트폴리오에 같은 배지 — 설계상 의도, 문구로만 보완(P1-5).

---

## 실행 순서·커밋
P0 → P1(P1-3은 사용자 기준 확정 후) → P3 → P2 → P4. 배치별 커밋 `fix:`/`refactor:` + `(plans/63 배치 Px)`. 62 C·D·E와 같은 파일을 만지는 항목(P1-1↔62 E3, P2-3↔62 D3, P3-3↔62 E4)은 62 항목과 묶어 한 커밋으로.

## 핵심 재사용 대상
`utils/portfolio.ts`(`mergeAlertsByPortfolio`, 기준 포트폴리오 헬퍼), `_portfolio_queries.py` 활성 알림 최소 임계치, `compute_base_value_krw`, `get_confirmed_composite_level`, `order_builder.py` BUY_ONLY 필터 로직, `MarketSignalLevelBadge`, `CashSummaryBar`, `constants/rebalancingConfig.ts`(STRATEGY_OPTIONS), `utils/queryInvalidation.ts`.

## 검증
- `make lint`, `make typecheck`, `make test-backend`(최종 `make test-backend-cov`), `make test-frontend`.
- 신규 테스트: P0-1(프론트 buildOrders BUY_ONLY 매도 제외 + 백엔드 BUY_ONLY SELL 거부), P1-1(자동분석 경로도 override 전달), P1-2/P1-4(라벨·활성필터 셀렉터 단위), P3-2(생성 후 portfolioId 설정), P3-4(복합신호 푸시 data type).
- 수동(`make dev`, 모바일 390px 포함): 진단 행 클릭 → 자동분석 예수금이 버튼 분석과 동일한지 / "매수만" 선택 시 확인화면에 매도 없음 / 실행 후 결과→동기화·재분석 1클릭 / 추천→새 포트폴리오 저장 후 자동 선택·분석 / 전술·추천 탭에서 고른 포트폴리오가 포트폴리오 탭에 유지 / 알림 비활성 시 모든 화면 "꺼짐" 일치.
- 문서: 파일 추가 시 `frontend/CLAUDE.md`·`backend/CLAUDE.md` 목록, `docs/plans/README.md` 상태 표 갱신.
