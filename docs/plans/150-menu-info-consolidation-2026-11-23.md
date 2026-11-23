# 150 — 전체 메뉴·정보 구성 재점검: 불필요·중복 정리와 통합 (2026-11-23)

## 배경

50(전체 검토)·106(메뉴 IA)·112(불필요·중복 정리) 이후 143~149에서 낙폭 추매·환전 탭·전술 웅덩이·시장 종합 판단·리밸런싱 시점 판정·적립 시나리오·배당 달성 시점이 짧은 기간에 붙었다. 그 결과 같은 개념이 여러 화면에 다른 말로 반복된다.

- 시장 상황: 9곳
- 목표 진행률: 3곳
- 배당 통계: 2곳
- 환율·환전 대기: 6곳

알림 설정도 여러 곳에 흩어졌다. 낙폭 추매 알림은 설정 › 알림에도, 발송 이력 라벨에도 없다.

이 계획은 **개념마다 "주인 화면"을 정한다**. 주인 화면만 전체 정보를 보여주고, 나머지 화면은 한 줄 요약 + 링크로 줄인다. 메뉴 구조(탭 이름·깊이)는 바꾸지 않는다.

## 현재 메뉴 트리

```
홈 /dashboard → Hero · 지금 할 일 · 목표 카드 · 챌린지 · 자산 추이
자산 /assets ?tab=
 ├ 투자현황 ?portfolioTab= → 종목 현황(비중 분석 국내/해외|종목|지수) | 배당(?divTab= 종목별|월별)
 └ 계좌관리 ?atab= → 증권계좌 | 은행계좌 | 부동산 | 내역(?history= 현금 흐름|매수 내역)
리밸런싱 /rebalancing ?rtab= → 진단 | 포트폴리오 | 목표 조정(?gmode= 추천|전술) | 이력
계획 /invest-plan ?tab= → 적립 계획(#dip-buy) | 환전 | 배당 계획 | 절세(?taxTab= 한도 현황(#isa-status)|세금 추정) | 챌린지
설정 /settings → 계정 · 다른 설정(링크) · 알림 · DART · 앱
 └ /settings/notifications ?atab= → 환율 알림 | 주가 알림 | 발송 이력 (+ 시장 모니터링 카드)
```

- 최대 깊이는 3단이다. "4단 금지" 규칙을 지키고 있으므로 구조는 손대지 않는다.
- 3단의 segmented는 대부분 보기 전환(기간·정렬)이지 이동 메뉴가 아니다.

## 재제안하지 않는 항목(이전 결정)

| 항목 | 출처 | 이번 계획에서의 처리 |
|---|---|---|
| 자산 배당 탭 / 계획 배당 계획 분리 | 106·112 | 탭은 그대로 두고, 같은 통계 3개가 반복되는 것만 B2에서 다룬다 |
| 사이드바 테마·로그아웃, 자동화 진입점 7곳, 동기화 버튼 여러 개, 리밸런싱 이력 vs 발송 이력 | 106 | 의도적 유지 |
| 계좌관리 순자산 구성 카드 | 50 M3 | 만들지 않는다 |
| 푸시 토글 이동, 카드별 `AutomationStatusBar` | 67 | 유지 |
| 위저드 6단계 | 106 | 유지 |
| 챌린지 금액 실시간 연동 | 50 | 채택 안 함 |
| 레거시 탭 리다이렉트 5종(`portfolioTab=세금`, `atab=입출금·배당`·`기간별 매수`, `#fx-plan`, `rtab=추천`·`전술`, `atab=시장 신호 알림`) | `frontend/CLAUDE.md` "지우지 말 것" | 유지 |

## 정보 주인 원칙

| 개념 | 주인(전체 표시) | 나머지 화면 |
|---|---|---|
| 주식 손익·보유 | 자산 › 투자현황 | 홈: Hero 한 줄 |
| 목표 진행·달성 전망 | 계획 › 적립 계획 `GoalTimelineCard` | 홈: 진행률·남은 금액 한 줄 + 가장 뒤처진 칩 |
| 배당 목표 | 계획 › 배당 계획 | 자산 › 배당: 받은 실적·예상 실적만 |
| 시장 상황 | 리밸런싱 › 진단 `MarketSignalBanner` | 레벨 배지 1개 + 진단 링크(설명 반복 없음) |
| 이탈·리밸런싱 시점 | 진단 `RebalancingStatusCard` | 포트폴리오 카드: 배지만 |
| 환율·환전 | 계획 › 환전 | 홈: Hero 환율. 환전 대기 안내는 링크 한 줄 |
| 알림 설정 | 설정 › 알림(모든 알림의 켜짐 상태·목록) | 각 기능 화면에서 생성하되, 설정에서 전부 보이게 한다 |

## 배치 A — 실버그·누락 (PR 1, 작음) — 구현 완료

> 결과: A2는 백엔드 `save_alert_history`·`dispatch_dual_channel_alert` 호출부를 전수 대조한 결과 이력에 남는 값 중 빠진 것은 `DCA_DIP_BUY` 하나였다(`DCA_FX_*`·`FX_PLAN`·`PLAN_GENERATED`는 이력이 아니라 푸시 type·지금 할 일 종류). A3은 조회 없이 위치 안내 카드("적립 관련 알림")로 — 낙폭 추매 상태 조회는 52주 시세를 불러 설정 화면에 무겁다. A4는 배지 판정을 `hooks/useNavBadges.ts`로 추출해 두 내비가 공유.

**A1. 홈 챌린지 카드가 사라짐**
- 증상: ACTIVE 챌린지가 모두 기한 종료(`progress.is_expired`)면 `ChallengeProgressCard`가 null을 반환한다. 그런데 `DashboardPage`는 `status === "ACTIVE"`만 보고 빈 상태 카드(`ChallengeEmptyStateCard`)를 고르지 않는다. 결과적으로 챌린지 카드가 통째로 사라진다.
- 수정: `pages/DashboardPage.tsx` 챌린지 분기 조건을 `c.status === "ACTIVE" && !c.progress.is_expired`로 바꾼다. plans/146 B1과 같은 기준이다.
- 테스트: 기한 종료 챌린지만 있을 때 빈 상태 카드가 나오는지 확인한다.

**A2. 발송 이력 라벨 누락**
- 증상: `pages/NotificationSettingsPage.tsx`의 `ALERT_TYPE_LABELS`에 `DCA_DIP_BUY`(`backend/app/jobs/dca_dip_buy_notice.py`)가 없다. 낙폭 추매 알림이 이력에 코드 문자열 그대로 보인다.
- 수정: 백엔드가 `AlertHistory.alert_type`에 기록하는 값 전체와 대조한다. 후보는 `DCA_FX_REQUIRED`·`DCA_FX_WAITING`·`FX_PLAN`·`PLAN_GENERATED`이며, 실제로 이력에 기록되는지 확인한 뒤 누락분을 추가한다.
- 테스트: 백엔드 상수 목록과 라벨 키를 대조하는 회귀 테스트. 백엔드 쪽 단일 목록이 없으면 프론트 테스트에 기대 목록을 고정한다.

**A3. 설정 › 알림에 없는 알림**
- 낙폭 추매 알림 행을 추가한다. 켜짐 상태(`notify_mode`)를 보여주고 "적립 계획 › 낙폭 추매에서 설정" 링크(`#dip-buy`)를 단다.
- 같은 방식으로 정기 적립 예수금 부족 알림(`DCA_CASH_SHORTFALL`)의 출처도 한 줄로 안내한다.
- 시장 모니터링 카드의 "전술 국면 알림" 안내 행과 같은 패턴을 재사용한다.

**A4. 데스크톱 사이드바 배지**
- `components/layout/Sidebar.tsx`에 `BottomNav.tsx`와 같은 리밸런싱(이탈)·계획(챌린지) 빨간 점을 단다.
- 배지 계산 로직이 BottomNav 안에 있으면 훅으로 추출해 둘 다 쓴다.

## 배치 B — 중복 정보 축소 (PR 2: B1·B2·B5·B6·B7 / PR 3: B3·B4·B8)

> 결과(구현 시 코드 재확인 — 조사 시점 정보 일부가 이미 정리돼 있었다):
> - **B1 완료** — 홈 목표 카드의 접힘 상세(예상일 배지·앞섬/지연·막대) 제거, "목표까지 N 남음 · YYYY.MM 달성 예상" 한 줄. 자산 목표 없을 때 링크 대신 안내 문구(헤더 링크 하나로).
> - **B2 완료** — 자산 › 배당 통계 3칸 → 2칸(월평균 제거), 계획 › 배당 계획에서 "올해 실수령" 제거(모바일 3→2열·데스크톱 4→3열·목표 미설정 3→2열).
> - **B3 축소 완료** — 공용 `MarketSignalLevelBadge`는 이미 추천 노트·자동화 모달·전술 판정 근거에서 쓰이고 있었고, 배너 확정 설명 중복은 145 PR2에서 처리됨. 남은 중복인 라벨·색 정의 두 벌을 `utils/marketSignalBadge.ts` 하나로 통합.
> - **B4 유지** — `RebalancingDiagnosisCard`의 시점 판정은 실행 버튼 위에서 보류·분할 이유(`timing_reason`)를 보여주는 유일한 곳(포트폴리오 카드 배지는 이유 없음).
> - **B5 변경 없음** — 적립 계획 배너는 이미 한 줄 + 이력 링크이고, "다시 매수" 버튼이 이력에 있어 목적지도 맞다.
> - **B6 축소 완료** — 배당 쪽은 이미 한 줄 비교(67 P1-13). 적립 `GoalTimelineCard`의 2칸 상자·"추천 종목 N개"를 같은 한 줄 비교로. 내용이 달라(앞당기기 시나리오 vs 후보 ETF) 공용 컴포넌트는 만들지 않음.
> - **B7 변경 없음** — 세금 추정 쪽은 67 P1-16에서 이미 경고 한 줄 + 한도 현황 링크.
> - **B8 변경 없음** — 라벨에 기준이 이미 적혀 있다(자산 유형 집중도·종목 집중도(HHI)·쏠림 {이름}).

**B1. 홈 목표 카드**
- 문제: `components/dashboard/DcaOutlook.tsx`의 펼침 영역(달성 예상일·개월 앞서/지연·진행 막대)이 `components/invest/GoalTimelineCard.tsx`(현재 진행률·달성 예상·계획 대비·막대)를 거의 그대로 반복한다.
- 수정: 홈은 진행률 + 남은 금액 한 줄과 칩만 남기고, 펼침 영역은 계획 › 적립 계획 링크로 바꾼다.
- 데이터가 없을 때 나오는 "DCA 투자 계획 설정하기"와 헤더의 "목표 설정" 링크가 겹친다. 헤더 링크 하나만 남긴다.

**B2. 배당 통계 3종**
- 문제: 예상 연간·월평균·올해 수령이 `components/portfolio/DividendTab.tsx`(≈L253-291)와 `components/invest/DividendPlanSection.tsx`(≈L280-300)에 같은 형태로 있다.
- 수정:
  - 자산 › 배당은 실적 중심으로 "올해 수령·예상 연간·배당수익률"을 보여준다.
  - 계획 › 배당 계획은 목표 대비 중심으로 "달성률·필요 수익률·달성 시점"을 보여준다.
  - 월평균(= 연간 ÷ 12)은 계획 쪽에만 둔다.

**B3. 시장 상황 표기 통일**
- 다음 곳마다 등급 배지·문구가 제각각이다.
  - 추천 결과 노트 배지(`RecommendationResultPanel`)
  - 자동화 모달 "현재" 배지(`AlertAutoModeSection`)
  - 낙폭 추매 "방어 국면 보류" 안내(`DipBuyCard`)
  - 전술 판정 근거 매크로 배지(`TacticalStatusParts`)
  - 홈 `MarketSignalPill`
- 수정: 공용 배지 컴포넌트 하나(레벨 + 확정/즉시 구분 + 진단 링크)로 통일하고, 설명 문구는 주인 화면(`MarketSignalBanner`)에만 둔다.
- 배너 안의 확정 등급 설명 중복은 145 PR2에서 이미 접힘 조건으로 처리했으므로 대상이 아니다.

**B4. 리밸런싱 포트폴리오 탭의 겹친 진단**
- `RebalancingDiagnosisCard`(분석 › 이 포트폴리오 진단)가 진단 탭 행과 포트폴리오 카드 배지의 시점 판정(`TIMING_LABEL`)을 다시 보여준다. 분석 화면에만 있는 정보(예상 비용·세금 영향)만 남기고 시점 배지는 뺀다.
- `AutomationStatusBar`는 카드(compact)·분석 패널(full) 각 1회씩이라 의도된 구성이다(63 P2-2, 67). 이번 대상이 아니다.

**B5. 환전 대기 안내 2곳**
- 문제: 같은 안내가 `invest/AutoInvestStatusBanner.tsx`(WAITING_FX 개수)와 `invest/FxPlanCard.tsx` ≈L410-423(`waiting_fx_usd`)에 있다.
- 수정: 환전 탭이 주인이다. 적립 계획 배너는 "환전 대기 N건 · 환전 탭에서 보기" 한 줄로 줄인다.

**B6. "더 빨리 달성하려면?" 2곳**
- 문제: `GoalTimelineCard`와 `DividendPlanSection`의 접힘 섹션이 같은 추천 쿼리로 필요 수익률·기대수익률을 보여준다. 둘 다 리밸런싱 › 목표 조정 › 추천 탭의 수치를 반복한다.
- 수정: 공용 컴포넌트 하나로 합치고, 내용은 "필요 수익률 X% vs 추천 기대 Y%" 한 줄 + 추천 링크로 줄인다.

**B7. 건보 피부양자 경고 2곳**
- 문제: `tax/TaxOptimizationCard.tsx`(세금 추정, ≈L218-276)와 `HealthInsuranceRiskCard`(한도 현황)가 겹친다.
- 수정: 세금 추정 쪽은 경고 한 줄 + 한도 현황 링크로 줄인다.

**B8. 같은 이름, 다른 집중도 숫자**
- 문제: "집중도·쏠림"이라는 이름으로 4가지가 있고 정의가 서로 다르다.
  - 자산 유형 게이지 `DiagnosticGauge`
  - 위험 카드 쏠림 `RiskMetricsCard`
  - 진단 요약 칩
  - 분석 상세 집중도 `RebalancingDetailMetrics`
- 수정: 라벨에 기준을 붙인다(자산 유형 / 종목 / 지수). 같은 이름에 다른 숫자가 나오지 않게 한다. 계산은 바꾸지 않는다.

## 배치 C — 긴 설명·겹친 인트로 축소 (PR 3)

**C1. 겹친 인트로**
- 리밸런싱 `TabIntro` 위에 `GoalAdjustTab`의 `MODE_INTRO` + `ORDER_NOTICE`가 다시 쌓인다(67 보류 항목). 목표 조정은 모드 인트로 한 줄만 남긴다.
- 환전 섹션 부제(`InvestPlanPage.tsx` 환전 탭)는 카드 첫 블록과 겹치므로 뺀다.

**C2. 긴 설명문**
- 첫 문장만 보이게 하고, 나머지는 기존 접힘 패턴("자세히")으로 옮긴다. 대상:
  - `DipBuyCard` 인트로 4문장
  - `DcaTacticalNotice`
  - `MarketSignalBanner` 종합 판단 각주
  - `FxPlanCard` 각주 3곳
  - `FxExtraNeedsSection` 안내
  - `TaxOptimizationCard` 대주주 문단
  - 전술 면책(`TacticalAllocationTab`)

**C3. 낙폭 추매 ↔ 전술 웅덩이 역할 구분 문구**
- 문제: 두 화면(`DipBuyCard`, `TacticalStatusParts` 웅덩이 요약)이 서로를 설명하는 문구를 각자 다르게 쓴다.
- 수정: 상수 하나("여윳돈 추가 매수 = 낙폭 추매 / 비중 이동 = 웅덩이")로 통일한다.

## 배치 D — "갱신" 용어 (PR 3)

- 홈 "데이터 갱신"(캐시 재조회)과 자산 "전체 갱신"(증권사 동기화)은 라벨이 같지만 하는 일이 다르다.
- 홈은 "새로고침", 자산은 "증권사에서 갱신"으로 라벨을 구분한다. 버튼 수는 106 결정대로 유지한다.

## 배치 E — 사용자 결정 필요 (기본값: 유지)

| # | 항목 | 겹치는 곳 | 제안 |
|---|---|---|---|
| E1 | 종목 현황 › 비중 분석 "종목" 뷰(상위 5 + 기타) | 보유 표 비중 열·비중순 정렬 | 제거 검토 |
| E2 | 보유 표의 배당 열(투자배당율·배당월, 모바일 펼침 예상 연배당) | 배당 탭 종목별 표 | 보유 표에서 빼고 배당 탭 링크 |
| E3 | 저사용 도구: 절약 복리 시뮬레이터, 적립 설정 편집 2갈래(위저드 + 평면 폼), `HorizonSummaryCard` | — | 사용자 판단 |
| E4 | `components/portfolio/MonthlyOptimizationCard.tsx`는 `invest/DividendPlanSection`에서만 쓴다 | — | `components/invest/`로 이동(동작 변경 없음, `frontend/CLAUDE.md` 목록 갱신) |

## 백엔드 영향

- 탭 이름, 앵커(`#dip-buy`·`#isa-status`), "시장 모니터링" 카드명은 바꾸지 않는다. 다음 코드가 이 이름들을 링크 문자열로 쓰기 때문이다.
  - `services/action_items_service.py`
  - `services/tax/tax_action_builders.py`
  - `services/insight_service.py`
  - `services/email_service.py`
  - 이메일 푸터(`email_templates/market_signal.py`·`rebalancing.py`·`reports.py`)
- B·C·D는 프론트만 바꾼다.
- A2는 백엔드 alert_type을 읽어 대조만 한다.
- 마이그레이션은 없다.

## 순서

A(PR 1) → B1·B2·B5·B6·B7(PR 2: 목표·배당·환전·세금) → B3·B4·B8·C·D(PR 3: 리밸런싱·문구) → E(결정 반영 후).

## 검증

- 프론트(대문자 드라이브에서 실행): `cd D:/project/growlio/frontend && npm run lint -- --max-warnings 0 && npm run format:check && npm run typecheck && npm run test`
- 백엔드를 건드리면: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pytest`
- A1·A2는 회귀 테스트로 고정한다.
- B·C는 홈·자산·계획·리밸런싱·설정 화면을 390px 뷰포트에서 실화면으로 확인한다. 특히 링크 목적지와 접힘 상태를 본다.
- 파일 이동(E4)·컴포넌트 추가(B3·B6) 시 `frontend/CLAUDE.md` 목록도 갱신한다.
