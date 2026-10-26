# 홈 "지금 할 일" + "리밸런싱 점검" 카드 통합 (2026-10-26)

## Context
홈 탭에서 같은 drift-summary가 두 카드에 연달아 보였다.
- `ActionItemsCard`("지금 할 일"): 백엔드 `action_items_service._rebalance_items`가 이탈 포트폴리오마다 "OOO 리밸런싱 필요" 행(HIGH)을 넣는다.
- 바로 아래 `RebalancingStatusCard statusOnly`("리밸런싱 점검" 한 줄 행): "포트폴리오 N개 중 M개 이탈"(빨간 글씨) + 시장 신호 배지.

이탈이 있으면 같은 사실을 두 번 말했고, 이탈이 없으면 "지금 할 일이 없어요"와 "모두 목표 비중 이내"가 카드 2장으로 따로 떴다(plans/67 P1-3이 4번→2번까지 줄였던 중복의 잔여).

## 결정
홈에서 리밸런싱을 다루는 카드를 `ActionItemsCard` 1장으로 합친다. "리밸런싱 필요" 신호는 행동 항목(REBALANCE 행)에만 둔다.

- 카드 하단에 리밸런싱 상태 줄(`RebalancingStatusFooter`, `/rebalancing` 링크)을 둔다: "리밸런싱 · {상태}" + 시장 신호 배지.
  - 이탈 0개: "포트폴리오 N개 모두 목표 비중 이내"
  - 이탈이 위 REBALANCE 행에 다 있음: "포트폴리오 N개 현황 보기"(개수를 반복하지 않음)
  - 이탈이 행으로 다 보이지 않음(지금 할 일 조회 실패·5건 상한): "포트폴리오 N개 중 M개 이탈"(빨간 글씨)
  - 포트폴리오 없음(drift-summary 빈 배열)·로딩 중: 줄을 그리지 않는다
- 항목 있음/0건/조회 실패 세 상태 모두 같은 카드 안에 상태 줄을 둔다. drift-summary는 별도 쿼리(`QUERY_KEYS.driftSummary`, 리밸런싱 탭과 캐시 공유)라 action-items가 실패해도 보인다.
- `RebalancingStatusCard`의 `statusOnly` 모드는 삭제한다. 이제 리밸런싱 진단 탭 전용이다.
- 시장 신호 알약 배지 상수는 `utils/marketSignalBadge.ts`로 옮겨 두 카드가 공유한다.
- 백엔드는 바꾸지 않았다.

## 변경 파일
- `frontend/src/components/dashboard/ActionItemsCard.tsx`: `marketSignal` prop, 하단 상태 줄
- `frontend/src/pages/DashboardPage.tsx`: 홈 `RebalancingStatusCard` 섹션 제거
- `frontend/src/components/dashboard/RebalancingStatusCard.tsx`: `statusOnly` 제거
- `frontend/src/utils/marketSignalBadge.ts`: 신규
- 테스트: `components.actionItemsCard.test.tsx`(상태 줄 6케이스), `components.large.test.tsx`(statusOnly 3케이스 삭제), `pages.dashboard.test.tsx`

## 상태
**완료**. 프론트 테스트 1792개 통과, tsc·eslint·prettier 통과. 실기기 확인은 하지 않았다.

## 후속: 리밸런싱 항목 묶기 + "자세히 보기" 펼침
포트폴리오별 "OOO 리밸런싱 필요" 행이 서버 상한 5건을 차지해 다른 할 일(예수금 부족·절세·챌린지)이 밀려났다. 이탈 4개 + 세금 + 적립 + 챌린지면 적립·챌린지가 잘렸다.

- 백엔드 `_rebalance_items`: 이탈 포트폴리오가 2개 이상이면 행 1개로 묶는다. `id=REBALANCE_GROUP_ID("rebalance:all")`, 제목 "리밸런싱 필요 · 포트폴리오 N개", 상세 "{최대 이탈 포트폴리오} 최대 x%p 이탈 외 N-1개", CTA "자세히 보기", 링크 `/rebalancing`(대체 경로). 1개면 묶지 않고 해당 포트폴리오로 바로 가는 기존 행을 유지한다(묶으면 탭 한 번이 늘어날 뿐이라서). 스키마는 그대로다.
- 프론트 `RebalanceGroupRow`: 이 id의 행은 링크가 아니라 펼침 버튼이다(`aria-expanded`, CTA 문구 표시). 펼치면 drift-summary에서 `needs_rebalancing`인 포트폴리오만 이탈 큰 순으로 보이고, 각 행은 `rebalancingUrl({tab:"포트폴리오", portfolioId})`로 간다. drift-summary가 없으면 "리밸런싱 탭에서 보기" 한 줄을 둔다. 하단 상태 줄은 묶음 행이 있으면 이탈 개수를 반복하지 않는다.
- 펼침은 다른 화면으로 이동하지 않고 카드 안에서 한다. 진단 탭으로 가는 길은 하단 상태 줄이 맡는다.

## 후속 2: 하단 상태 줄 삭제 + 시장 신호 배지를 리밸런싱 행으로
묶음 행이 생긴 뒤 하단 상태 줄에 남은 것은 행동이 필요 없는 상태 정보("N개 현황 보기"/"모두 목표 비중 이내")와 시장 신호 배지뿐이었다.

- `RebalancingStatusFooter`를 삭제했다. 0건/실패 카드는 다시 한 줄이다.
- 시장 신호 배지(`MarketSignalPill`)는 REBALANCE 행(단일·묶음)의 제목 옆에만 붙인다. 이탈을 지금 처리할지 판단할 때 함께 보는 정보이기 때문이다.
- drift-summary는 묶음 행이 있을 때만 그 행이 조회한다. 홈 첫 로드에서 요청 1건이 줄었다.
- 감수할 점: 리밸런싱 행이 없으면 홈에 시장 신호가 보이지 않는다. 등급 전환은 즉시 알림(`market_signal_alert`)과 진단 탭이 담당한다.
