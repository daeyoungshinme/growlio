# 고도화 계획 인덱스 (2026-07-19 감사 기반)

2026-07-19 전체 기능 감사(`docs/mobile-ux-audit-2026-07.md`와 별개 세션, 같은 시기 병행 진행)에서 도출된 고도화 항목을 세션별로 독립 실행 가능하도록 분리했다. 각 파일은 자기완결적(self-contained)이며, 서로 다른 파일이 건드리는 코드 영역이 최대한 겹치지 않도록 설계했다.

## ⚠️ 실행 전 필수 확인사항

이 프로젝트는 **여러 터미널/세션에서 동시에 작업되는 경우가 잦다** (git status에 낯선 미커밋 변경이 자주 나타남 — 다른 세션의 진행 중 작업일 수 있음). 아래 계획 중 하나를 집어 실행하기 전에 반드시:

1. `git status` / `git diff`로 계획이 언급하는 파일들이 이미 다른 세션에 의해 수정되지 않았는지 확인
2. 계획서에 적힌 "현재 코드 상태"(파일:라인)가 실제 코드와 다르면, 계획서 내용보다 **현재 코드를 우선** — 계획서는 작성 시점의 스냅샷일 뿐
3. 완료 후 이 README의 상태 표를 갱신하고, 만약 다른 계획 파일이 영향받는 코드를 건드렸다면 해당 파일에도 메모 남기기

## 계획 목록

| # | 파일 | 요약 | 영역 | 의존성 | 리스크 |
|---|---|---|---|---|---|
| 1 | [01-auto-gate-tax-impact.md](01-auto-gate-tax-impact.md) | AUTO 자동매매 게이트에 세금영향(양도세 추정치) 반영 | 백엔드(rebalancing) | 없음 | 높음 (실제 자금 이동 로직) |
| 2 | [02-threshold-recommendation-dedup.md](02-threshold-recommendation-dedup.md) | 드리프트 임계값 추천 로직 백엔드 dead code 제거 | 백엔드(rebalancing) | 없음 (①과 같은 파일 `order_builder.py`를 건드리므로 **①과 동시 진행 시 순서 조율 필요**) | 낮음 |
| 3 | [03-recommendation-diagnosis-linkage.md](03-recommendation-diagnosis-linkage.md) | 추천 비중 재계산 시점을 추적해 "추천이 바뀌었어요" 알림/배지 추가 | 백엔드+프론트(goal_recommendation) | 없음 | 중간 (스키마 추가) |
| 4 | [04-notification-center-unification.md](04-notification-center-unification.md) | 알림 관리 화면 분산(설정 페이지 vs 리밸런싱 알림 모달) 완화 | 프론트(신규 화면) | 없음 | 중간 (신규 라우트/화면) |
| 5 | [05-backtest-tab-relocation.md](05-backtest-tab-relocation.md) | RebalancingPage "백테스팅" 최상위 탭 → 하위로 격하 | 프론트(RebalancingPage) | 없음 | 낮음 |
| 6 | [06-mobile-ux-carryover.md](06-mobile-ux-carryover.md) | 2026-07-13 감사 보류 항목 잔여분 처리 (RebalancingExecutionModal 공용 Modal화, Toaster 스택 제한) | 프론트(common) | 없음 | 낮음 |

**동시 진행 가능 조합**: 1·3·4·5·6은 서로 다른 파일을 건드려 병렬 진행 가능. **2번은 1번과 같은 파일(`order_builder.py`)을 건드리므로, 두 세션이 동시에 잡으면 머지 충돌 가능성이 있다** — 가능하면 순차 진행 권장(1 → 2), 병렬로 할 경우 2번 세션이 먼저 커밋하고 1번 세션이 rebase하는 편이 안전(2번은 삭제만 하는 작은 diff).

## 상태

| # | 상태 | 완료일 | 비고 |
|---|---|---|---|
| 1 | 미착수 | | 사용자가 "세금 영향 추가 반영"으로 방향 확정(리스크 지표는 반영 안 함) |
| 2 | 미착수 | | |
| 3 | 미착수 | | |
| 4 | 미착수 | | |
| 5 | 미착수 | | |
| 6 | 미착수 | | |

## 이번 감사에서 "이미 구현되어 있어 재작업 불필요"로 확인된 것 (참고용, 계획 없음)

- 단기/중기/장기 × ISA/연금저축/IRP/일반/해외전용 계좌 특성별 목표 역산 추천 — `GET /rebalancing/goal-recommendation/by-horizon` + `RecommendationCard.tsx`(리밸런싱 › 포트폴리오 탭)
- drift + 시장신호(거시 8종) + 리스크지표(VaR/베타/분산도) + 세금영향 복합 진단 — `rebalancing/diagnosis_service.py`
- 포트폴리오별/계좌별(AGGREGATE/PER_ACCOUNT) 독립 알림 + AUTO 2단계 실행(매수 자동/매도 승인)
