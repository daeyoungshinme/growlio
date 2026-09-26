# 38. 고도화 E2 — 절세 액션 플랜 (세션 인수인계용, 자기완결)

> 출처: [37-full-review-2026-09-25.md](37-full-review-2026-09-25.md) Part 4 E2. 이 문서만 읽고 착수할 수 있도록 썼다.
> 착수 전 `git status`/`git log`로 동시 세션 변경을 확인하고, 이 문서의 파일:라인은 **작성 시점(2026-09-26) 스냅샷**이므로
> 코드와 다르면 코드를 우선한다. 세법 수치(한도·공제율)는 **착수 시점 최신 세법으로 재확인** 후 상수로 둘 것.

## 1. 왜 하는가

요구사항 "계좌별 세금에 대한 절세 계획을 세워주고" 대비 현재는 **계산·표시 위주**다 — 한도 잔여·예상 세금은 보여주지만
"언제·얼마를·어느 계좌에 하면 얼마 아낀다"는 **실행 가능한 액션**이 없다. 손실수확만 예외적으로 구체적 추천이 있다.

## 2. 현재 코드 상태 (2026-09-26)

| 영역 | 위치 | 하는 일 | 갭 |
|---|---|---|---|
| 연금저축/IRP 납입 | `backend/app/services/pension_contribution_service.py`(74줄) `calc_pension_contribution_status` → `GET /tax/pension-contribution` | 연간 DEPOSIT 합계 vs 한도(연금저축 600만 / 합산 900만) 진행률·잔여 | **세액공제액 미계산**(총급여 구간 정보 없음 — `_PENSION_CONTRIBUTION_NOTE`에 명시), 월 분할·마감 안내 없음. 납입액은 **수기 입력 Transaction만** 집계 |
| ISA | `backend/app/services/isa_service.py`(202줄) `get_isa_status_summary` → `GET /tax/isa-status` | 만기일(`maturity_date`), 비과세 한도(일반 200만/서민형 400만), 초과분 9.9%, 일반계좌 대비 절세액 | 만기 후 **연금계좌 이전(추가 공제)** 안내 없음, **연 2,000만 납입한도** 미추적 |
| 양도세·배당세 | `backend/app/services/tax_service.py`(457줄) `get_tax_summary` → `GET /tax/summary`, `_build_harvesting_recommendations`(해외 손실 종목 전량 매도 제안) | 해외 미실현 기준 250만 공제 후 22%, 금융소득 2,000만 경고(2026-09-25에 해외차익 합산 오류 수정됨), 금투세 시뮬 | 250만 공제 **이익실현(gain harvesting)** 제안 없음, 손실수확 **국내 미지원**·주문 미연결, 해외 실현손익은 프론트 수기 입력(`TaxPlannerSection`) |
| 연말 리마인더 | `backend/app/services/alerts/tax_reminder_service.py`(174줄) + `jobs/year_end_tax_reminder.py`(11~12월 매주 월 09:00, 옵트인) | 손실수확 top3·연금 잔여한도·ISA 만기 요약 이메일/푸시 | 금액 효과(공제액) 없음 |
| 세율 상수 | `tax_service.py` `_TAX_RATES`(2025/2026 하드코딩), `_get_rates(year)` | | 연도 추가 시 갱신 필요 |
| 프론트 | 자산 › 투자현황 › 세금 탭: `components/portfolio-analysis/TaxTabContainer.tsx`(한도 현황 `TaxLimitsSection`: `IsaMaturityCard`/`PensionContributionCard`/`HealthInsuranceRiskCard` / 세금 추정 `TaxOptimizationCard`), `components/tax/*`(`TaxPlannerSection`·`TaxRecommendationList`·`GeumtSimulationSection`). 홈 요약: `components/dashboard/TaxLimitsBanner.tsx` + `hooks/useTaxLimitsSummary.ts` | | 액션 리스트 UI 없음 |

사용자 입력 필드: `UserSettings`(`backend/app/models/user.py`)에 **소득(총급여) 정보 없음**.

## 3. 목표 설계

### 3-1. 백엔드 — `tax_action_service.py` + `GET /tax/action-plan?year=`
액션 1건 = `{id, category, title, detail, amount_krw(권장 금액), benefit_krw(예상 절세액, 불확실하면 null), deadline(date|null), priority(HIGH/MEDIUM/LOW), cta: {label, link}}`. 기존 서비스 결과를 **조합만** 하고 계산 로직을 복제하지 않는다.

| # | 카테고리 | 조건 | 액션 예 | 계산 |
|---|---|---|---|---|
| A1 | 연금 세액공제 | 연금저축/IRP 계좌 보유 & 잔여한도 > 0 | "12/31까지 IRP에 N원 추가 납입 시 세액공제 약 M원" + 남은 개월 수로 월 분할액 | 잔여 = `calc_pension_contribution_status`; 공제율 = 총급여 구간(아래 3-2) 16.5%/13.2%, 미입력이면 benefit=13.2% 하한값 + "소득 구간을 입력하면 정확해져요" |
| A2 | ISA 만기 이전 | ISA 만기 D-90 이내 또는 만기 후 60일 이내 | "만기 자금을 연금계좌로 이전하면 이전액 10%(최대 300만) 추가 공제" | `get_isa_status_summary`의 `maturity_date` |
| A3 | ISA 납입한도 | ISA 보유 | "올해 ISA 납입 가능 잔여 N원" (연 2,000만, 미납분 이월 — **이월 규칙은 세법 재확인**) | ISA 계좌 DEPOSIT 합계(연금과 같은 Transaction 집계 패턴) |
| A4 | 해외 250만 공제 이익실현 | 해외 미실현 이익 > 0 & 올해 실현 < 250만 | "연내 N원 이익실현(매도 후 재매수) 시 양도세 0원으로 취득가 상향" | `get_tax_summary`/`get_overseas_positions_detail`, 실현액은 우선 0 가정(E6에서 자동화) + 안내 |
| A5 | 손실수확 | 기존 `_build_harvesting_recommendations` 결과 | 그대로 액션화(top3) | 기존 |
| A6 | 금융소득 2,000만 | 배당(과세계좌) 1,500만 이상 | "연내 배당 추가 수령 시 종합과세 — 고배당은 ISA/연금 계좌로" | `get_tax_summary.comprehensive_tax_remaining_krw` |

- 우선순위: 마감(12/31·ISA 만기) 임박 + benefit 큰 순.
- `deadline`은 KST 기준(`app/utils/kst.today_kst` — `date.today()` 금지, 루트 CLAUDE.md 규칙).

### 3-2. 소득 구간 입력(최소 스키마)
- `UserSettings.income_bracket`: `"UNDER_55M" | "OVER_55M" | NULL`(총급여 5,500만 = 종합소득 4,500만 기준 — 공제율 16.5/13.2 분기). 금액 자체는 저장하지 않는다(민감정보 최소화).
- alembic revision 추가 → `alembic/env.py`에 모델 import 확인, **버전 테이블은 `growlio_alembic_version`**(루트 CLAUDE.md "자주 막히는 문제" 참고). `PUT /settings/...` 기존 설정 엔드포인트 패턴에 필드 추가.
- 입력 UI: 액션 카드 안 인라인 토글(“총급여 5,500만원 이하예요”) — 별도 설정 화면 만들지 말 것.

### 3-3. 프론트
- 자산 › 투자현황 › 세금 › **한도 현황 최상단**에 `TaxActionPlanCard`(액션 리스트, 각 행 CTA). 기존 카드(`IsaMaturityCard` 등)는 상세로 유지.
- 홈 `TaxLimitsBanner`/`useTaxLimitsSummary`: 가장 우선순위 높은 액션 1줄로 요약 교체 검토(홈 카드 높이 늘리지 말 것 — 계획 37 U1/U2 방향).
- 연말 리마인더(`tax_reminder_service`)가 같은 액션 리스트를 재사용하도록 전환(내용 중복 제거).
- 모바일 규칙: 터치 타겟 44px, 초소형 폰트 금지, `fmtKrw` 사용(frontend/CLAUDE.md).

## 4. 작업 순서 (권장 PR 단위)

1. 백엔드 `tax_action_service.py` + 엔드포인트 + 스키마(A1·A2·A5·A6 — 기존 데이터만으로 가능) + 테스트
2. `income_bracket` 마이그레이션 + 설정 API + A1 benefit 정밀화
3. A3(ISA 납입한도)·A4(250만 이익실현) — 세법 재확인 필요
4. 프론트 `TaxActionPlanCard` + 소득 구간 인라인 입력 + 홈 요약 연결
5. 연말 리마인더 재사용 전환

## 5. 검증
- `cd backend && pytest` — 서비스 단위 테스트는 기존 `tests/test_tax_service.py`의 `patch("app.services.tax_service._calc_*")` 패턴 참고. 케이스: 연금 잔여 0/일부, 소득구간 미입력/입력, ISA 만기 D-100/D-30/만기후, 해외 이익/손실, 배당 1,500만 이상.
- `make lint && make typecheck`, `cd frontend && npm run test`.
- 실브라우저 모바일(390px) 확인 시 테스트 계정 시딩→검증→삭제 절차(메모리 `project_fifth_round_real_device_2026-07-22`).

## 6. 리스크·주의
- **세법 수치 정확성**: 한도·공제율·ISA 이월 규칙은 매년 바뀐다 — 연도별 상수 테이블(`_TAX_RATES` 방식)로 두고 출처·기준연도를 주석에.
- 연금 납입액은 수기 입력 Transaction 의존(자동 동기화 계좌도 입금 내역은 자동 생성 안 됨) — 액션 문구에 "입금 내역 기준" 명시.
- "매도 후 재매수" 이익실현 제안은 실제 매매 권유 — 문구는 정보 제공형으로, 자동 주문 연결 금지(AUTO 파이프라인과 분리).

## 7. E2 이후 남은 고도화 (계획 37 Part 4 참고)

| # | 항목 | 비고 |
|---|---|---|
| E3 | 계좌 간 자산 배치(asset location) 최적화 | E1(연금 규정 필터, 완료) 위에 2단계 최적화 |
| E4 | 기간별(단기/중기/장기) 목표 금액 + by-horizon 목표 역산 | 스키마 추가 |
| E6 | 해외 실현손익 자동 집계(브로커 체결내역) | A4 정확도 향상 |
| E7 | 이자소득 추적 → 금융소득 2,000만 판정 완성 | A6 정확도 향상 |
| E8~E10 | 시장신호 국내지표·점수 게이트 / ETF 총보수 / 토스 주문 | 리서치·외부 API 의존 |
| (E1 후속) | IRP 파생형 ETF 40% 규정, 연금계좌 주문 사전검증, 후보 관리 "연금 불가" 배지 | 계획 37 E1 결과 참고 |
| (E5 후속) | KRX 공휴일 캘린더(AUTO 이월·주문 거부 방지) | `alerts/calculator.is_auto_schedule_day`는 주말만 이월 |
