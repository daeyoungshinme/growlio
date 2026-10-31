# 106. 메뉴·하위메뉴 구성 재점검 (2026-10-31)

> 상태: 진행 중


## Context

사용자 요청: 앱 전체의 메뉴/하위메뉴 구성을 점검하고 개선 계획을 세운다.
IA는 계획 50·53·64·67·82·102를 거치며 큰 틀이 정리된 상태다(하단 5탭: 홈/자산/리밸런싱/계획/설정).
이번 점검에서는 큰 재편보다 **세 가지 문제**가 남아 있음을 확인했다.

- 이름과 다른 곳으로 가는 딥링크·라벨이 있다.
- 탭 이름이 여러 파일에 흩어져 정의돼 있고, 컴포넌트 폴더 위치가 실제 화면과 맞지 않는다.
- 같은 기능으로 들어가는 진입점이 겹친다.

사용자 결정:
- 범위는 ①+②+③ 전부. 단계는 위험이 낮은 것부터 진행한다.
- 자산 › 계좌관리의 기본 하위탭을 **증권계좌**로 바꾼다.


### 현재 구조

```
홈 /dashboard          지금 할 일 · 목표 · 챌린지 · 주식 현황 · 자산 추이
자산 /assets           [투자현황: 종목 현황|배당] [계좌관리: 은행계좌|증권계좌|부동산|내역]
리밸런싱 /rebalancing   [진단|포트폴리오|목표 조정(추천|전술)|이력]
계획 /invest-plan      [적립 계획|배당 계획|절세(한도 현황|세금 추정)|챌린지]
설정 /settings (+ /settings/notifications)
```

---

## Phase A — 잘못된 딥링크·라벨 (실버그, 저위험)

**A1. 절세 CTA가 계좌관리 기본 탭(은행계좌)으로만 간다**

`backend/app/services/tax/tax_action_service.py:82`의 `_LINK_ACCOUNTS = "/assets?tab=계좌관리"`를 쓰는 곳이 3곳이다.

| 액션 | 지금 | 바꿀 곳 |
|---|---|---|
| "입금 내역 기록"(연금 공제 L221, ISA 납입 L293) | 계좌관리 기본 탭 | `/assets?tab=계좌관리&atab=내역&history=현금 흐름` → `_LINK_CASH_FLOW` |
| "ISA 현황 보기"(L261) | 계좌관리 기본 탭 | `/invest-plan?tab=절세&taxTab=한도 현황` → `_LINK_TAX_LIMITS` |

- 이 CTA는 홈 "지금 할 일"(`action_items_service`)에서도 그대로 쓰인다.
- `tests/`에 있는 tax_action·action_items 테스트의 링크 기대값을 갱신한다.

**A2. 설정 "투자·입금·배당 목표" 행이 적립 계획으로만 간다**

`frontend/src/pages/SettingsPage.tsx:212-214`
- "투자·입금 목표" → 적립 계획
- "배당 목표" → `/invest-plan?tab=배당 계획`

이렇게 2행으로 나누거나, 라벨을 "투자·입금 목표"로 줄이고 배당 행을 추가한다. `pages.settings.test.tsx`를 갱신한다.

**A3. "시장 신호 알림"이라는 메뉴가 화면에 없다**

- 알림 설정 화면의 실제 카드 제목은 "시장 모니터링"이다. `MarketSignalAlertSection`은 `embedded`라 자체 제목이 없다.
- 그런데 이메일 3곳은 "설정 > 알림 설정 > 시장 신호 알림"이라고 안내한다.
  - `email_templates/market_signal.py:34,53`
  - `email_templates/rebalancing.py:161`
- 수정: 이메일 문구를 "설정 > 알림 설정 > 시장 모니터링"으로 바꾸고 `test_email_templates.py:130,171`을 갱신한다.
- 링크 `?atab=시장 신호 알림`(`MarketSignalBanner.tsx:187`)은 이미 발송된 알림과의 호환 때문에 **값을 유지한다**.
  - 대신 탭이 아닌 "섹션"을 여는 파라미터라는 점을 `NotificationSettingsPage.tsx:183`에 주석으로 남긴다.

**A4. 알림 설정 하위탭이 URL과 동기화되지 않는다**

- `NotificationSettingsPage`는 `?atab`을 최초 1회 `useState`로만 읽는다. 그래서 탭을 바꿔도 URL이 그대로이고, 뒤로가기나 새로고침 때 탭이 되돌아간다.
- `AssetsPage`처럼 `useSearchParams` 기반으로 바꾼다. `atab=시장 신호 알림`은 섹션 펼침용 특수값으로 그대로 처리한다.

---

## Phase B — 구조 정리 (동작 변화 없음, 계좌관리 기본 탭만 예외)

**B1. 계좌관리 기본 탭 → 증권계좌 (사용자 결정)**

- `frontend/src/constants/tabs.ts:1`의 순서를 `["증권계좌", "은행계좌", "부동산", "내역"]`으로 바꾼다.
- `AssetManagementPage.tsx`에서 기본값이 `[0]`인지, 아니면 하드코딩된 "은행계좌"인지 확인하고 맞춘다.
- 옛 링크(`atab=은행계좌`)는 명시값이라 그대로 동작한다.
- `pages.assets*`, `AssetManagementPage` 관련 테스트의 기본 탭 기대값을 갱신한다.

**B2. 탭 이름 단일 정의**

- 다음 인라인 정의를 `constants/tabs.ts`로 옮긴다.
  - `InvestPlanPage.tsx:44` `TABS` → `INVEST_PLAN_TABS`
  - `TaxTabContainer` `TAX_TABS`
  - `NotificationSettingsPage.tsx:128` `ALERT_TABS`
  - `AccountHistoryTab` `HISTORY_SEGMENTS`
- 백엔드는 다음 문자열을 링크에 하드코딩한다.
  - `action_items_service` 링크: 적립 계획, 챌린지, 절세, 세금 추정
  - `tax_action_service` 링크
  - `usePushNotifications.resolvePushDeepLink` 링크
- 그래서 `tabs.ts` 상단에 "백엔드 링크 문자열과 같아야 함" 주석을 단다. `rebalancingUrl.ts`의 관례와 같다.
- 컴포넌트 안에서 쓰는 소규모 segment(`DIV_SUBTABS`, `AnalysisPanel` 뷰)는 URL에 실리지 않으므로 그대로 둔다.

**B3. 폴더 위치 정합 — 홈에 나오지 않는 카드가 `components/dashboard/`에 있다**

| 컴포넌트 | 실제 사용처 | 옮길 곳 |
|---|---|---|
| `RebalancingStatusCard` | 리밸런싱 › 진단 | `components/rebalancing/` |
| `HorizonSummaryCard` | 자산 › 투자현황 | `components/portfolio/` (기존 폴더명 확인) |
| `IsaMaturityCard`, `PensionContributionCard`, `HealthInsuranceRiskCard` | 계획 › 절세 | `TaxLimitsSection`과 같은 폴더(`portfolio-analysis/` 또는 `tax/`) |

- import 경로와 `vi.mock` 경로를 함께 갱신한다. `__tests__`가 경로로 mock하므로 grep해서 전부 고친다.
- 이번 계획의 다른 변경과 섞이지 않도록 **기계적 이동만 단독 커밋**으로 한다.

**B4. 탭 계층 규칙 문서화**

- 계획 50 X1 규칙("페이지 1단 = pill, 2단 = underline, 3단 = segmented, 4단 금지")이 계획서에만 있다. `frontend/CLAUDE.md` 라우트 섹션에 1줄로 추가한다.
- 함께 확인할 것: 계획 53에서 남은 "자산 › 종목 현황 › 비중 › 지역 4단" 중첩이 `AllocationCard` segmented 도입으로 이미 3단인지 코드로 확인한다. 4단이면 정리하고, 3단이면 완료로 기록한다.

**B5. `frontend/CLAUDE.md` 갱신**

- 계좌관리 기본 탭, 옮긴 컴포넌트 목록, `tabs.ts`에 새로 들어간 상수를 반영한다.

---

## Phase C — 중복 진입점 정리 (화면 변화, 중위험)

**C1. 계획 페이지 안 추천 중복 (계획 64에서 이관)**

같은 "전체 목표 역산 추천"이 `/invest-plan` 안 여러 곳에서 계산·표시된다.
- `GoalTimelineCard` "더 빨리 달성하려면?" — 기대수익률·종목 수·달성 판정 + 링크
- `DividendPlanSection:290-337` — 추천 비중의 배당수익률 + `SuggestedCandidatesBlock`(후보 추가 UI까지) + 링크
- 위저드 6단계 — 추천으로 포트폴리오 생성. 흐름상 필요하므로 유지한다.

방향은 다음과 같다.
- 계획 페이지에서는 **요약 수치 1줄 + "목표 조정 › 추천" 링크**만 남긴다.
- 후보 추가 같은 편집 행동은 목표 조정 › 추천(`RecommendationCard`) 한 곳으로 모은다.
- 구체적으로는 `DividendPlanSection`에서 `SuggestedCandidatesBlock`을 빼고 배당 기대수익률 요약 + 링크만 둔다.
- `GoalTimelineCard`는 지금처럼 유지한다. 이미 요약 + 링크 형태다.
- 확인할 점: `SuggestedCandidatesBlock`이 배당 목표 전용 후보(고배당)를 제안하는지 본다. 그렇다면 링크를 `rebalancingUrl({tab:"목표 조정", mode:"추천"})`로 걸었을 때 같은 제안이 그쪽에도 나오는지 먼저 확인한다. 안 나오면 블록을 옮기는 대신 유지하고 이 항목은 보류한다.

**C2. 달러 환전 계획 ↔ 환율 알림 연결**

- `FxPlanCard`가 환율 알림을 만들지만, 관리 화면(설정 › 알림 설정 › 환율 알림)으로 가는 링크가 없다.
- 알림을 만든 뒤와 카드 하단에 "환율 알림 관리 →" `/settings/notifications?atab=환율 알림` 링크를 추가한다. A4가 먼저 되어 있어야 한다.

**C3. 일일 자동매수 한도 범위 표기**

- `alertModal/AutoDailyCapEditor`는 유저 단위 설정인데 포트폴리오별 모달 안에 있다.
- 라벨이나 힌트에 "모든 포트폴리오 공통"을 명시한다. 위치는 바꾸지 않는다.

**유지(변경 없음) — 검토 결과 의도된 중복**

- 사이드바와 설정의 테마·로그아웃: 데스크톱 편의 기능이다.
- 자산 › 배당(실적) ↔ 계획 › 배당 계획(목표): 서로 링크돼 있고 역할이 분리돼 있다.
- 리밸런싱 이력 ↔ 알림 발송 이력: 서로 링크가 있다.
- 자동화 모달 진입점 7곳: 호스트가 `PortfolioManageTab` 하나로 단일화돼 있다(계획 64).
- 동기화 버튼 여러 곳: 각 화면 맥락에 필요하다.

---

## 수정 파일 요약

- Backend:
  - `services/tax/tax_action_service.py`
  - `services/notifications/email_templates/{market_signal,rebalancing}.py`
  - 관련 테스트
- Frontend:
  - `constants/tabs.ts`
  - `pages/{SettingsPage,NotificationSettingsPage,InvestPlanPage,AssetManagementPage}.tsx`
  - `components/portfolio-analysis/TaxTabContainer.tsx`
  - `components/assets/AccountHistoryTab.tsx`
  - `components/invest/{DividendPlanSection,FxPlanCard}.tsx`
  - `alertModal/AutoDailyCapEditor.tsx`
  - `components/dashboard/*` 5개 이동
  - 관련 `__tests__`
- Docs:
  - `frontend/CLAUDE.md`
  - `docs/plans/106-*.md`
  - `docs/plans/README.md`

## 커밋 단위

1. 계획서 106
2. Phase A (백엔드 + 프론트)
3. B1 + B2
4. B3 기계적 이동만
5. B4·B5 문서
6. C1
7. C2 + C3
8. 결과·이관 기록

## 검증

- `make lint`, `make typecheck`, `make test-backend`(최종 확인은 `make test-backend-cov`), `make test-frontend`
- 링크 회귀 grep
  - `rg "tab=계좌관리\"" backend frontend/src`: 남은 `atab` 없는 링크가 의도된 것인지 확인한다.
  - `rg "components/dashboard/(RebalancingStatusCard|HorizonSummaryCard|IsaMaturityCard|PensionContributionCard|HealthInsuranceRiskCard)"`: 결과가 0건이어야 한다.
- `make dev`로 띄워 다음을 수동 확인한다.
  - 홈 "지금 할 일"의 절세 CTA 이동 위치
  - 설정의 목표 2행
  - 진단 › 시장 상황 "설정 →"
  - 알림 설정 탭 전환 후 새로고침 시 탭 유지
  - 계좌관리 진입 시 증권계좌가 기본으로 열림
  - 배당 계획의 추천 요약과 링크
  - 환전 계획 → 환율 알림 관리 링크
