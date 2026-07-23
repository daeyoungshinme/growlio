# 계획 3: 추천 비중 변화 감지 — "추천이 달라졌어요" 배지

**리스크: 중간 (Phase A는 프론트 전용이라 낮음, Phase B는 백엔드 잡 추가라 중간)**

## 배경 (Why)

사용자가 원래 요청한 핵심 파이프라인은 "주기적으로 시장상황에 맞게 포트폴리오 비중을 추천"이다. 현재 `RecommendationCard.tsx`(리밸런싱 › 포트폴리오 탭)는 **화면을 열 때마다 최신 시장 데이터로 추천을 재계산**해서 보여주지만, "직전에 적용했던 추천과 비교해서 얼마나 달라졌는지"는 표시하지 않는다 — 사용자가 매번 화면을 열어봐야만 추천이 바뀌었는지 알 수 있다. "주기적으로 추천하고 알려준다"는 원래 요청의 마지막 조각이 빠져 있다.

## 현재 코드 상태 (2026-07-19 기준 — 실행 전 재확인 필수)

- `frontend/src/components/rebalancing/RecommendationCard.tsx` — "전체" 탭은 `fetchOverallGoalRecommendation()`(`overallData.recommended_items`), 기간별 탭은 `fetchHorizonGoalRecommendations()`(`horizonData.recommendations[].recommended_items`)로 매번 새로 계산된 추천을 받는다. "적용" 버튼(`applyOverallMutation`/`applyHorizonMutation`)을 누르면 `updatePortfolio(portfolioId, { items: normalizeWeights(...) })`로 **포트폴리오의 현재 목표 비중(`Portfolio.items`)을 추천값으로 그대로 덮어쓴다.**
- `backend/app/services/goal_recommendation_service.py::get_goal_recommendation()`/`get_horizon_recommendations()` — 호출될 때마다 최신 시장 데이터(기대수익률/배당수익률/CAGR)로 매번 재계산, 과거 계산 결과를 저장하지 않는다(stateless).
- `Portfolio` 모델(`backend/app/models/portfolio.py`)에는 "이 포트폴리오가 마지막으로 추천을 적용받은 시점의 비중"을 기록하는 필드가 없다.

## 설계 — Phase A (권장 우선 구현, 백엔드 스키마 변경 없음)

핵심 아이디어: **"포트폴리오의 현재 목표 비중"과 "지금 다시 계산한 추천 비중"을 프론트에서 직접 비교**한다. 별도 스냅샷을 저장할 필요 없다 — 사용자가 마지막으로 추천을 적용한 직후에는 두 값이 동일하고, 이후 시장 데이터가 바뀌어 추천이 달라지면 자연스럽게 차이가 발생한다(단, 사용자가 수동으로 포트폴리오 비중을 편집한 경우에도 차이가 생기는데, 이는 "추천과 다르게 운용 중"이라는 의미로도 유효한 신호이므로 오히려 자연스럽다).

1. 신규 유틸 `frontend/src/utils/recommendationDrift.ts`:
   ```ts
   // recommended: GoalRecommendationItem[], current: PortfolioItem[] (ticker/market 기준 매칭)
   // 반환: 매칭된 항목 중 최대 비중 차이(%p), 추천에는 있는데 현재 포트폴리오엔 없는 신규 후보 개수
   export function computeRecommendationDrift(recommended, current): { maxDeltaPct: number; newCandidateCount: number }
   ```
   `PORTFOLIO_WEIGHT_TOLERANCE`(`constants/validation.ts`)보다 유의미하게 큰 임계값(예: 3~5%p) 이상 차이 나면 "달라짐"으로 판단 — 정확한 임계값은 구현 세션이 실제 데이터로 튜닝.
2. `RecommendationCard.tsx`에서 "전체" 탭은 `overallConfirmTarget`(적용 대상 포트폴리오), 기간별 탭은 `horizonTargetPortfolio`의 `items`와 방금 받은 추천을 비교 → 차이가 임계값을 넘으면 추천 리스트 위에 배지(`"시장 상황이 바뀌어 추천 비중이 달라졌어요 · 최대 N%p 차이"`) 표시. 아이콘/색상은 `MarketSignalLevelBadge` 톤과 통일.
3. 목표 포트폴리오가 지정되어 있지 않은 경우(대상 자체가 없음)는 배지 자체를 숨김 — 지금도 "적용" 버튼이 대상 없으면 숨겨지는 것과 동일한 조건 재사용.
4. 테스트: `frontend/src/utils/__tests__/recommendationDrift.test.ts`(신규), `components.recommendationCard.test.tsx`에 배지 노출 케이스 추가.

## Phase B — 완료 (2026-07-23, "추천 비중 고도화" 세션)

Phase A는 사용자가 화면을 열어야만 보였다. 주간 알림 job으로 확장 완료:

- `backend/app/services/goal_recommendation_service.py::compute_recommendation_drift()` — Phase A의 `computeRecommendationDrift()`를 백엔드에 그대로 포팅한 순수 함수(임계값 3%p는 `_RECOMMENDATION_DRIFT_THRESHOLD_PCT`로 동일 유지).
- `backend/app/services/alerts/recommendation_drift_alert_service.py`(신규) — `_find_drifted_portfolios()`가 전체 자산 기준(연결 계좌 전부가 `target_portfolio_id`로 지정된 "full" 타겟 포트폴리오)과 투자기간별(포트폴리오에 `investment_horizon`+`tax_type`이 명시적으로 지정된 경우만, 계좌 태그 추론 폴백은 생략) 양쪽 경로에 대해 drift를 계산. `tax_reminder_service.py`와 동일하게 유저별 `AsyncSessionLocal` + `AlertHistory` 기반 dedup(주 1회 실행이라 "오늘 발송 여부"가 곧 주간 dedup) 패턴.
- `UserSettings.recommendation_drift_alert_enabled`(기본 OFF, 마이그레이션 `b1c2d3e4f5a6`) + `PUT /settings/recommendation-drift-alert` + 프론트 `useRecommendationDriftAlertToggle.ts` + `SettingsPage.tsx` "알림 설정" 섹션에 토글 추가.
- `backend/app/jobs/recommendation_drift_alert.py` + `app/scheduler.py`에 매주 월요일 09:15 KST 등록.
- 이메일 템플릿 `recommendation_drift_alert_template()`(`email_templates.py`) + `send_recommendation_drift_alert_email()`(`email_service.py`), 푸시 딥링크 `RECOMMENDATION_DRIFT` → `/rebalancing?rtab=포트폴리오`(`usePushNotifications.ts`).
- 검증: 백엔드 1885 tests 86.80%, 프론트 1376 tests, typecheck/lint/build 전부 클린.

## 주의사항

- `RecommendationCard.tsx`는 다른 계획 파일과 겹치지 않지만, 최근 다른 세션이 이 파일을 활발히 수정 중이었다(2026-07-19 세션 시작 시점 git status에 `M frontend/src/components/rebalancing/RecommendationCard.tsx` 존재) — 착수 전 `git log -p -- frontend/src/components/rebalancing/RecommendationCard.tsx`로 최근 변경 내역을 반드시 확인.
- 목표 역산 추천 기능은 "포트폴리오별 재계산은 부활시키지 않는다"는 과거 결정([[project_goal_recommendation_removal_2026-07-09]])이 있다 — 이 계획은 재계산 로직 자체를 건드리지 않고 "결과 비교·표시"만 추가하므로 그 결정과 충돌하지 않는다.
