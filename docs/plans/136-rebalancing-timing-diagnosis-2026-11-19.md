# 136. 리밸런싱 진단 탭을 "언제 할지" 판단 화면으로 (2026-11-19)

## Context

리밸런싱 › 진단 탭은 지금 **상태만** 보여준다(포트폴리오별 최대 이탈 %, 시장 상황, 내 위험 지표). 사용자가 원하는 건 진단으로 **리밸런싱 시점**을 판단하는 것인데, 판단에 필요한 정보가 비어 있거나 흩어져 있다.

조사 결과(코드 기준):
- **판정이 절대 %p 하나뿐** — `filter_drifting_items`(`backend/app/services/rebalancing/service.py:426`)는 `|weight_diff_pct| > threshold`만 본다. 목표 5% 종목은 0%가 돼도(전량 이탈) 기본 5%p 임계치를 넘지 못해 알림이 안 울린다.
- **시점 정보 없음** — 마지막 리밸런싱 날짜·경과일, 다음 예정일(스케줄 알림), 지금 하면 드는 비용(수수료·세금) 모두 진단 탭에 없다. 백엔드엔 재료가 있다: `RebalancingExecution.executed_at`(인덱스 있음), `alerts/calculator.next_auto_schedule_date`·`_is_schedule_day`, `diagnosis_service._build_tax_preview`(순수 함수), 해외 양도세 공제 여유(`tax_action_builders.py:342-387`).
- **"지금 해도 되나"가 한 줄로 안 나옴** — 이탈(카드 위)과 시장 등급(배너)·자동실행 게이트(확정 등급, CAUTIOUS/STRICT/TACTICAL)가 따로 놀고, 진단 배너는 즉시(raw) 등급, 자동 실행은 확정 등급을 쓴다.
- **중복** — 시장 등급이 배너 헤더·확정 줄·`buildCombinedStatusNote`에 3번, 유저 단위 `composite_reason`이 모든 포트폴리오 행 아래 똑같이 반복된다.

사용자 결정: 상대 이탈(5/25 규칙)은 **판정 옵션으로 추가**(알림·자동실행·진단 공통, 기본 끔). 이탈 추이(일별 기록)는 **이번엔 제외**.

목표: 진단 탭의 포트폴리오 행 하나만 봐도 "지금 실행 / 분할 실행 / 보류 / 지켜보기 / 불필요"와 그 이유·비용·마지막/다음 시점을 알 수 있게 한다. 판정 기준은 기존처럼 단일 소스 유지.

---

## 배치 A — 상대 이탈 밴드 옵션 (판정 단일 소스 확장)

- **A1 모델·마이그레이션**: `RebalancingAlert.relative_threshold_pct: Numeric | None`(null=끔, 허용 10~100) — `backend/app/models/alert.py`. alembic 리비전 1개(`rb1` 류). 운영은 수동 적용(루트 CLAUDE.md 절차). 스키마 `schemas/alert.py` 생성·수정·응답에 필드, 범위 검증.
- **A2 판정**: `filter_drifting_items(items, threshold_pct, relative_pct=None)` — `abs(diff) > threshold` **또는** (`relative_pct` 있고 `target_weight_pct > 0`이고 `abs(diff)/target*100 > relative_pct`). 목표 0(목표 밖 보유·암묵 예수금 등)은 절대 기준만. docstring에 규칙 명시.
- **A3 전파**: `get_active_alert_thresholds`(`portfolio/_portfolio_queries.py:38`)가 포트폴리오별 (min abs, min rel)을 반환하도록 — 호출부 `drift_summary_service`, `alert_check`, `plan_generation`, `portfolio_analysis_service`(분석 응답에 쓰는 임계치) 전부 같은 값을 넘긴다. `PortfolioDriftSummary`·분석 응답에 `relative_threshold_pct` 추가.
- **A4 프론트 판정 미러**: `utils/portfolio.ts`에 `isDriftingItem(item, threshold, relative)` 추가하고 인라인 비교(`RebalancingDiagnosisCard.tsx:68`, 비중 표 강조 등 `Math.abs(i.weight_diff_pct) > threshold` 검색)를 교체. `getDriftStatus`의 "주의"(절반 이상) 단계도 상대 기준 절반을 반영.
- **A5 알림 폼**: `useRebalancingAlertFormState`·알림 모달에 "상대 이탈(목표 대비 %)" 숫자 입력 + `InfoTip`(예: 목표 10% 종목이 7.5% 미만/12.5% 초과면 이탈 — 25% 설정 시). `rebalancingAlertDescription` 문구에 반영. 입력 스타일 상수·`htmlFor` 규칙 준수.

## 배치 B — drift-summary에 "시점" 필드 추가 (백엔드)

`compute_portfolio_drift_summary`/`get_drift_summaries`(`drift_summary_service.py`)가 이미 갖고 있는 analysis·overview·알림 행을 재사용해 **외부 API 추가 호출 없이** 계산. 필드는 모두 optional로 추가(persist 캐시 호환 — `PERSIST_CACHE_BUSTER` 불필요, 홈 action-items 공유 응답도 무해).

- **B1 마지막 리밸런싱**: `last_rebalanced_at` — `RebalancingExecution`에서 `portfolio_id`별 `max(executed_at)` where `total_success > 0`, 유저당 1쿼리(`plan_gates.py:150-172`의 max-per-account 쿼리 패턴 참고). 새 헬퍼는 `portfolio/_portfolio_queries.py` 또는 `rebalancing/_alert_queries.py`.
- **B2 다음 예정일**: `next_scheduled_date`·`schedule_label` — 포트폴리오의 활성 알림 중 `trigger_condition`이 SCHEDULE_ONLY/BOTH인 것의 다음 날짜(최소값). AUTO는 `calculator.next_auto_schedule_date`, NOTIFY는 `_is_schedule_day`로 같은 탐색(필요하면 `next_notify_schedule_date` 순수 함수 추가, `calculator.py`에 테스트). DRIFT_ONLY면 null + "이탈 시" 표기.
- **B3 비용 추정**: `estimated_trade_krw`(매도 합, 그룹 행은 `iter_trade_items`로 펼침), `estimated_cost_krw`(수수료+해외 양도세 추정), `estimated_overseas_gain_krw` — `diagnosis_service._build_tax_preview(analysis, overview)` 재사용(이미 순수). `compute_portfolio_drift_summary`가 analysis를 반환하거나 내부에서 계산하도록 시그니처 정리.
- **B4 시점 판정(순수 함수)**: `rebalancing/timing_verdict.py` 신설 — 입력(이탈 판정, 최대 이탈/임계치 비율, **확정** 시장 등급, 알림 `market_condition_mode`, TACTICAL이면 `tactical_regime_for_gate()` 결과, 비용 비율) → `timing: NOW | SPLIT | HOLD | WATCH | OK` + `timing_reason`(한국어 1문장).
  - HOLD: 그 포트폴리오의 자동 실행 게이트가 지금 막는 상태(`is_market_signal_blocking_auto_mode` 그대로 호출 — 게이트와 문구가 어긋나지 않게), 게이트 없으면 확정 RED.
  - SPLIT: 이탈 + 확정 YELLOW. NOW: 이탈 + 그 외. WATCH: 임계치 절반 이상(기존 "주의"). OK: 그 미만.
  - 비용 비율(추정 비용 / 매매금액)이 크면(예: 해외 양도세 발생) reason에 "세금 약 N원" 덧붙임 — 판정 자체는 바꾸지 않음.
  - 확정 등급은 `market_signal_service.get_confirmed_composite_level()`을 루프 밖에서 1회. 배너의 raw 등급과 다를 수 있음을 reason에 쓰지 않고, 배너의 기존 "자동 실행·전술 판단 기준(확정)" 줄이 설명.
- **B5 테스트**: `tests/`에 timing_verdict 표 기반 테스트, drift-summary 새 필드(실행 이력 있음/없음/전부 실패, 스케줄 종류별, 그룹 행 비용), `filter_drifting_items` 상대 밴드 경계(`>` 엄격, 목표 0).

## 배치 C — 진단 카드 재구성 (프론트, 중복 삭제)

- **C1 행 개편** `RebalancingStatusCard.PortfolioDriftRow`: 상태점 + 이름 + **시점 칩**(지금 실행/분할 실행/보류/지켜보기/안정) + 최대 이탈. 둘째 줄에 `timing_reason`, 셋째 줄 보조 텍스트 "마지막 N일 전 · 다음 MM.DD(월간) · 예상 비용 N원"(`relativeTime`·`fmtKrw` 사용, 값 없는 조각은 생략). 기존 "리밸런싱 필요"/"점검 권장" 배지는 시점 칩으로 대체.
- **C2 중복 제거**:
  - 행마다 반복되던 `composite_reason` → 카드 상단 한 줄로 1회만(복합신호 켜진 경우).
  - `buildCombinedStatusNote`(`utils/diagnosisInsights.ts:50-60`)와 그 렌더 삭제 — 시점 칩이 이탈×시장 결합을 대신한다. 테스트도 정리.
  - 헤더 배지 "N개 필요" → "지금 N · 보류 M"처럼 시점 기준 집계.
- **C3 세금 타이밍 힌트**(카드 하단 1줄, 조건부): 어떤 포트폴리오든 `estimated_overseas_gain_krw > 0`이면 기존 `taxSummaryQuery(올해)`로 공제 여유(공제 − 실현) 계산해 "올해 해외 양도세 공제 여유 N원 — 이 안의 매도는 세금 없음"과 12월 마지막 주 마감 안내. 실현손익 조회 실패면 숨김(추정 금지). 백엔드 추가 없음 — 단 tax summary에 room 필드가 없으면 프론트 계산을 `utils/`에 함수로(인라인 금지).
- **C4 이 포트폴리오 진단 카드**(`RebalancingDiagnosisCard`): 판정은 A4 유틸로, 시점 칩·마지막/다음은 drift-summary 캐시(`driftSummaryQuery`)에서 해당 포트폴리오 행을 찾아 같은 표시(새 요청 없음).
- **C5 자동화 미설정 행**: 기존 "자동화 설정" 버튼 유지, 다음 예정일 자리에 "알림 없음"으로.

## 하지 않는 것 / 후속

- 일별 이탈 기록·추이 스파크라인(사용자 결정으로 제외 — 목표 비중 이력도 없어 과거 재구성 불가).
- 홈 "지금 할 일" REBALANCE 행에 시점 판정 반영 — 같은 응답이라 쉽지만 문구 정책은 후속.
- 인사이트 `REBALANCING_OPPORTUNITY`의 고정 5/10 기준(알림 임계치·상대 밴드 무시) — 사용처 확인 후 후속 계획에서 정리 여부 판단.

## 문서

- `docs/plans/136-rebalancing-timing-diagnosis-2026-11-19.md` 작성 + `docs/plans/README.md` 인덱스 행.
- `backend/CLAUDE.md`: 서비스 목록에 `timing_verdict.py` 한 줄(게이트 함수 재사용 함정), `filter_drifting_items` 상대 기준 한 줄. `frontend/CLAUDE.md`: 유틸 목록에 `isDriftingItem`(백엔드 판정과 동일 — 함께 수정).

## 수정 대상 핵심 파일

- 백엔드: `services/rebalancing/service.py`, `services/rebalancing/drift_summary_service.py`, `services/rebalancing/timing_verdict.py`(신규), `services/portfolio/_portfolio_queries.py`, `services/rebalancing/alert_check.py`, `services/rebalancing/plan_generation.py`, `services/rebalancing/portfolio_analysis_service.py`, `services/alerts/calculator.py`, `models/alert.py`, `schemas/alert.py`, `schemas/rebalancing/drift.py`, `alembic/versions/` 1개
- 프론트: `components/rebalancing/RebalancingStatusCard.tsx`, `components/rebalancing/RebalancingDiagnosisCard.tsx`, `utils/portfolio.ts`, `utils/diagnosisInsights.ts`, `api/rebalancing.ts`(타입), 알림 폼(`hooks/useRebalancingAlertFormState` 및 모달), `utils/rebalancingAlertDescription.ts`

## 검증

- 백엔드: `cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pytest` → 최종 `make test-backend-cov`(91%). 모델 변경이라 로컬 DB로 `uv run alembic upgrade head && uv run alembic check`.
- 프론트(`D:\project\growlio\frontend` 대문자 경로): `npm run lint -- --max-warnings 0 && npm run format:check && npm run typecheck && npm run test`. 새 유틸 테스트 `utils/__tests__/portfolio*.test.ts`, 카드 테스트 `components.rebalancingDiagnosisCard`·`pages.rebalancing` 갱신.
- 수동: `bash dev.sh` 후 `/rebalancing?rtab=진단` — 실행 이력 있는/없는 포트폴리오, 스케줄 알림·이탈 알림·알림 없음 포트폴리오에서 칩·마지막/다음·비용 표시, 알림 모달에서 상대 이탈 25% 설정 후 목표 5% 종목이 이탈로 바뀌는지, 모바일 폭(375px)에서 행 줄바꿈 확인.
- 운영: 마이그레이션은 코드 배포 **전** 수동 적용 필요(PR 본문에 명시).

---

## 결과 (2026-11-19)

- **A** 마이그레이션 `rb1_rebalancing_relative_threshold`(nullable 컬럼 — 옛 코드와 호환, **코드 배포 전 운영 수동 적용**). 판정 본체는 `services/rebalancing/drift_rule.py`(`filter_drifting_items`는 상대 기준이 없으면 예전 그대로 `|diff| > threshold`만 본다 — 목표 비중 필드가 없는 테스트 가짜 항목 호환). 알림 이메일 문구·행 강조도 상대 기준 반영. 알림 폼은 자유 입력 대신 `끔/20/25/50%` 선택(`RELATIVE_THRESHOLD_OPTIONS`), 스케줄만이면 저장하지 않는다.
- **B** `get_active_alert_thresholds` → `get_active_alerts_by_portfolio` + `alert_drift_thresholds`(최솟값), `get_last_rebalanced_at`(성공 1건 이상), `calculator.upcoming_schedule_date`(AUTO는 거래일 이월, 오늘이 스케줄일이고 아직 안 돌았으면 오늘). 매도 비용은 `diagnosis_service.estimate_sell_costs`로 분리해 `_build_tax_preview`·진단 요약이 공유. 확정 등급은 `get_last_composite_level`로 읽기만(`get_confirmed_composite_level`은 쓰기 경로).
- **C** 진단 행: 시점 칩 + 사유(안정이면 생략) + "마지막 · 다음 · 예상 비용". `buildCombinedStatusNote` 삭제, 복합신호 사유는 카드 위 1회, 헤더 배지 "지금 N · 보류 M". 해외 공제 여유 안내는 실현손익을 모르면(null) 숨김. 포트폴리오 탭 진단 카드는 기본 접힘이라 시점 라벨을 접힘 힌트 앞에도 붙였다. 포트폴리오 카드의 "주의"는 서버 `timing=WATCH`를 따른다.
- 검증: 백엔드 ruff·mypy·pytest 전체, 프론트 lint·format·typecheck·vitest 전체 통과. **미수행**: `alembic check`(로컬 `.env`가 공유 Supabase를 가리켜 실행하지 않음), 실기기·브라우저 화면 확인.
