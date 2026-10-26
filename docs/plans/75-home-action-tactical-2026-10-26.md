# 홈 "지금 할 일"에 전술 배분 적용 항목 추가 (2026-10-26)

## Context
홈 "지금 할 일"에는 리밸런싱 이탈·예수금 부족·세금·챌린지만 있었다. 전술 배분 국면이 바뀌어 제안 비중을 적용해야 하는 상황은 07:40 잡의 푸시·이메일(`TACTICAL_REGIME`/`TACTICAL_DIP`)로만 알렸다. 알림을 껐거나 놓치면 홈에서 알 수 없었다. 그 상태에서 같은 포트폴리오에 "리밸런싱 필요" 행이 뜨면 **예전 목표 비중으로 리밸런싱하게 유도**했다.

## 결정
- 별도 행 `kind="TACTICAL"`을 둔다. 행동이 필요한 경우만 띄운다(전환 확인 중·적립 보류 같은 상태 안내는 넣지 않는다).
- 판정 `tactical_allocation_service.pending_action(strategy, portfolio)`는 전술 탭 `tacticalNextAction`의 action 톤과 같다.
  - `last_regime` 없음 또는 `pending_regime` 있음이면 할 일 없음
  - `partial_regime == last_regime`이면 `PARTIAL`(MEDIUM, "나머지 적용")
  - `applied_regime != last_regime` 또는 전술 자산 중 하나라도 현재 목표 ≠ 제안 비중이면 `APPLY`(HIGH, "적용하기")
  - 제안 비중은 저장된 틸트·웅덩이 단계로 계산한다(`proposed_weights_for(..., {})`, apply와 같다). 시세·매크로를 조회하지 않아 홈 로드 비용이 그대로다.
- 적립 연동 포트폴리오(활성 AUTO·BUY_ONLY·`market_condition_mode=TACTICAL`)는 제외한다. 비중을 바꾸지 않는 모드라 적용할 것이 없다.
- 전술 행이 생긴 포트폴리오는 REBALANCE 판정(묶음 개수 포함)에서 뺀다. 같은 HIGH면 전술 행이 먼저 온다(소스 순서: 전술 → 리밸런싱 → …). 전술 소스가 중간에 실패하면 리밸런싱 행은 그대로 보인다.
- 링크는 `/rebalancing?rtab=목표 조정&gmode=전술&portfolioId=…`이다. 국면 변경 이메일과 같은 목적지다.
- 프론트는 일반 링크 행으로 렌더링한다. 시장 신호 배지는 REBALANCE에만 붙는다. `invalidateTacticalData`가 `actionItems`도 무효화한다(켜기·설정·끄기 직후 반영).

## 감수할 점
- 국면 확정은 07:40 잡 또는 전술 탭 조회(GET)가 진행한다. 서버가 잠들어 잡을 놓친 날은 홈 판정이 늦을 수 있다. 홈 요청은 읽기 전용으로 유지한다.
- 전략이 여러 개면 포트폴리오별로 1행씩 생긴다(묶지 않음).
- 지수 그룹 항목(plans/74)이 SPY 대표로 들어간 포트폴리오는 비중 비교가 어긋나 APPLY로 보일 수 있다. 이런 포트폴리오는 전술 호환이 아니다(`is_tactical_managed`).

## 변경 파일
- 백엔드: `schemas/action_items.py`(kind), `services/tactical_allocation_service.py`(`pending_action`), `services/action_items_service.py`(`_tactical_items`·`_tactical_strategies`·`_dca_tactical_linked_portfolio_ids`, 리밸런싱 제외)
- 프론트: `api/dashboard.ts`(kind), `utils/queryInvalidation.ts`, `components/dashboard/ActionItemsCard.tsx`(docstring)
- 테스트: `test_action_items_service.py`(+9), `test_tactical_allocation.py`(`TestPendingAction` 5), `components.actionItemsCard.test.tsx`(+1)

## 상태
**완료**(미커밋). 백엔드 2934 passed, 프론트 1794 passed. ruff·mypy·tsc·eslint·prettier 통과. 실기기 확인은 하지 않았다.
