# 계획 6: RebalancingExecutionModal → 공용 Modal.tsx 패턴 통합

**리스크: 낮음 (프론트 UI 리팩터링, 시각적 회귀 여부만 주의)**

## 배경 (Why)

2026-07-13 모바일 UX 감사([[project_mobile_readability_2026-07-13]])에서 "보류 항목"으로 남겨뒀던 것들을 2026-07-19 재조사한 결과:
- `FormInput.tsx` 미사용 문제 → **이미 해결됨**. 현재 `TransactionForm.tsx`, `InvestPlanPage.tsx`에서 실사용 중(다른 세션이 처리한 것으로 보임). 이 항목은 계획에서 제외.
- `Toaster` 스택 개수 무제한 → **이미 해결됨**. `frontend/src/components/Toaster.tsx:10` `const MAX_TOASTS = 3;`로 이미 캡이 걸려 있음. 이 항목도 제외.
- `RebalancingExecutionModal.tsx`가 공용 `Modal.tsx` 패턴을 쓰지 않고 독자 구현 → **아직 미해결**, 이번 계획의 유일한 대상.

## 현재 코드 상태 (2026-07-19 기준 — 실행 전 재확인 필수)

- `frontend/src/components/common/Modal.tsx` — 공용 모달. `useModalBehavior` 훅으로 body 스크롤 잠금/포커스 트랩/Escape 닫기 처리, `overlay`는 항상 `fixed inset-0`, 헤더에 `title` + X 아이콘 닫기 버튼, 모바일 드래그 핸들 바(44-46줄), `size` prop(sm/md/lg/xl)으로 너비 조절.
- `frontend/src/components/rebalancing/RebalancingExecutionModal.tsx:36-59` — 별도 구현. `useModalBehavior`는 동일하게 쓰지만, overlay가 `fixed inset-x-0 top-0 bottom-[calc(3.75rem+env(safe-area-inset-bottom))] sm:inset-0`로 **모바일에서 하단 네비게이션바 높이만큼 여백을 남긴다**(`Modal.tsx`에는 없는 동작 — `Modal.tsx`는 항상 `inset-0`). 헤더도 커스텀(`×` 텍스트 버튼 + `TOUCH_TARGET_MIN`, `Modal.tsx`는 `X` 아이콘 + `p-2.5`), 드래그 핸들 바 없음. `phase === "confirm"`일 때 헤더 아래 주문유형(MARKET/LIMIT) 토글 행이 추가로 붙음(62-75줄 부근) — 이건 `Modal.tsx`의 `title`/`children` 구조만으론 표현 안 되는 커스텀 서브헤더.

**핵심 차이 하나(중요)**: `RebalancingExecutionModal`이 모바일에서 `bottom-[calc(3.75rem+...)]`으로 하단 네비게이션 위 공간까지만 오버레이를 채우는 이유를 먼저 확인할 것 — 의도된 디자인(리밸런싱 실행 중 하단 네비 탭을 실수로 못 누르게? 혹은 반대로 네비를 가리지 않으려고?)인지, 아니면 `Modal.tsx`처럼 완전히 덮는 게 맞는데 놓친 것인지 git blame/커밋 이력으로 확인 후 진행 — 이 차이를 무시하고 단순 치환하면 시각적 회귀가 생길 수 있다.

## 구현 단계

1. **차이점 확인**: `git log -p --follow -- frontend/src/components/rebalancing/RebalancingExecutionModal.tsx | grep -B5 -A5 "bottom-\["`로 저 bottom offset이 언제·왜 추가됐는지 확인(의도적 설계인지).
2. **`Modal.tsx` 확장**: 만약 저 bottom offset이 의도된 것이라면, `Modal.tsx`에 옵션 prop 추가(예: `avoidBottomNav?: boolean` — true면 모바일에서 `bottom-[calc(3.75rem+env(safe-area-inset-bottom))]` 적용, 기본 false는 기존 `inset-0` 유지). 의도된 게 아니라면 이 단계 생략하고 그냥 `Modal.tsx` 기본 동작으로 통일.
3. **`RebalancingExecutionModal.tsx` 리팩터링**: 자체 overlay/dialog `<div>` 마크업(38-49줄)을 제거하고 `<Modal onClose={onClose} size="xl" title="리밸런싱 실행">`으로 감싸는 형태로 전환. `phase === "confirm"`일 때의 주문유형 토글 행은 `Modal`의 `children` 최상단에 그대로 유지(children은 자유 형식이므로 문제 없음).
4. **시각적 확인**: `npm run dev`로 실제 리밸런싱 실행 모달을 모바일 뷰포트(Chrome DevTools 375px 등)에서 열어 하단 네비게이션과의 겹침/여백이 리팩터링 전후 동일한지 스크린샷 비교.
5. **테스트**: 기존 `RebalancingExecutionModal` 관련 컴포넌트 테스트(`components.rebalancing2.test.tsx` 등, 최근 다른 세션이 수정 중이었으니 최신 내용 먼저 확인) — 마크업 구조 변경으로 깨지는 querySelector/role 기반 테스트가 있으면 갱신.
6. **검증**: `cd frontend && npm run test && npm run typecheck && npm run lint && npm run build`.

## 주의사항

- 이 리팩터링의 가치는 "유지보수 중복 제거"이지 기능 추가가 아니다 — 리스크 대비 효과가 크지 않다고 판단되면 스킵하고 README 상태에 "보류, 가치 낮음"으로 남겨도 무방하다.
- `frontend/src/components/rebalancing/RebalancingExecutionModal.tsx`는 git status상 최근 다른 세션이 건드리지 않은 것으로 보이나(2026-07-19 세션 시작 시점 diff 목록에 없었음), 착수 직전 재확인할 것.
