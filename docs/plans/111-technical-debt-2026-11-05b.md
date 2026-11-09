# 계획 111: 기술부채 — 계획 110 배치 E 정리 (2026-11-05)

> **진행 상태**: E2·E3·E4 완료(결과는 문서 끝). E1은 여기선 보류했고, 계획 114의 마이그레이션 `fk1`로 완료됐다.

## Context

110의 A~D는 PR #219~#222로 머지됐다. 이 문서는 남은 배치 E를 맡는다. 돈·세금 판단에 직결되는 항목은 없다.

브랜치는 `chore/tech-debt-2026-11-05e`다.

## 범위

### E1. FK 인덱스 3개 — 보류

| 컬럼 | 필요한 이유 |
|---|---|
| `rebalancing_plans.portfolio_id` | 포트폴리오 삭제, `cancel_pending_buy_legs` |
| `rebalancing_executions.portfolio_id` | 포트폴리오 삭제 시 SET NULL |
| `rebalancing_plan_legs.execution_id` | 사용자 삭제 시 실행 건마다 legs 전체 스캔 |

- `models/rebalancing_plan.py`, `models/asset.py`의 `__table_args__`에 `Index` 추가 + alembic 마이그레이션(작성 시점 head `dc2_drop_dead_columns`).
- **함정**: (작성 당시) `render.yaml`의 `preDeployCommand`가 `alembic upgrade head`를 돌린다고 봤다. 이후 Render 무료 플랜은 pre-deploy가 돌지 않아 112에서 지웠고, 마이그레이션은 배포 전 수동 실행이다(루트 CLAUDE.md 배포 절). 로컬 `.env`도 공유 Supabase를 가리킬 수 있으니 `alembic upgrade`를 로컬에서 돌리지 않는다.
- 테이블이 작아 우선순위가 낮다. 2026-11-05 사용자가 미루기로 결정했다. 착수 전 다시 확인받는다.
- 나머지 FK 8개는 판단을 마쳤다. 소형 테이블이거나 탈퇴 때만 발동해 추가하지 않는다.

### E2. 차트 대체 텍스트

대상: `BacktestResultChart`(3), `DividendPlanSection`(2), `AllocationHistoryChart`, `DCAProjectionChart`, `SavingsSimulatorCard`, `MonthlyDividendChart`, `TreemapChart`, `PortfolioWeightChart`.

### E3. 문서·주석 드리프트

`backend/CLAUDE.md`의 누락 파일·잡·라우터, `frontend/CLAUDE.md`의 `api/fetchAllPages.ts`, 틀린 주석 4곳.

### E4. 낮은 순위 버그 묶음

| # | 문제 | 위치 |
|---|---|---|
| a | pv 900만, 목표 1,000만, 월 500만, 12개월이면 "필요 수익률 -90%" | `goal/goal_return_solver.py` |
| b | 세제 선호 후보 보강 전 등록 수로 잔여 슬롯을 계산해 "후보에 추가"가 20개 상한을 넘을 수 있음 | `goal/goal_recommendation_service.py` |
| c | 호출마다 세마포어를 새로 만들어 조합 15개면 동시 120건, `run_yf_bounded`도 안 씀 | `goal/_goal_recommendation_common.py` |
| d | SPY UP + QQQ UNKNOWN이 정상 NEUTRAL 관측으로 2일 확정에 쓰임 | `tactical/tactical_regime.py` |
| e | 비중표 33.333×3이 ±0.01 검증을 통과하지만 `Numeric(6,2)`로 99.99 저장 | `tactical/tactical_regime.py`, `models/portfolio.py` |

---

## 결과

### E4 — 다섯 건 모두 수정 전 코드에서 재현

| # | 재현 | 수정 |
|---|---|---|
| a | -90.0 반환 | 적립만으로 달성되면 0.0을 반환한다. 미리보기는 "현재 적립액만으로도 목표 금액에 도달합니다"를 표시한다. 옵티마이저에는 0%를 하한으로 넘기지 않는다 — 후보 CAGR이 전부 음수일 때 빈 추천이 되기 때문이다 |
| b | 등록 5개인데 잔여 슬롯 19 | 전체 자산 경로에서 잔여 슬롯 계산에 보강 수를 뺀다. `candidate_dicts`에 직접 합치면(horizon 방식) 설정 행의 리스트까지 바뀌어 저장 후보가 달라진다 — 스냅샷이 잡았다. age 경로는 보강이 없고 horizon은 이미 누적하므로 고치지 않았다 |
| c | 조합 15개에서 동시 호출 peak 120 | 프로세스 공용 `_dividend_fetch_sem`. Yahoo 호출은 `run_yf_bounded`를 거친다 |
| d | NEUTRAL 반환 | RISK_OFF 판정 뒤에 한쪽이라도 UNKNOWN이면 None(기존 확정 국면 유지) |
| e | Decimal 합계 99.99 | 소수 둘째 자리로 맞추고 차이는 가장 큰 자산에 얹는다 |

**d의 수정 전후 동작** (전술 자동 변경에 영향)

| 매크로 | SPY | QQQ | 전 | 후 |
|---|---|---|---|---|
| GREEN | UP | UNKNOWN | NEUTRAL | 판정 보류 |
| YELLOW(직전 RISK_ON) | UP | UNKNOWN | NEUTRAL — 이틀이면 공격 국면이 풀림 | 판정 보류 — 공격 국면 유지 |
| GREEN | NEUTRAL | UNKNOWN | NEUTRAL | 판정 보류 |
| GREEN | UNKNOWN | UP·NEUTRAL·DOWN | NEUTRAL | 판정 보류 |
| GREEN | DOWN | UNKNOWN | RISK_OFF | RISK_OFF |
| RED | UP 또는 UNKNOWN | 한쪽 UNKNOWN | RISK_OFF | RISK_OFF |

SPY NEUTRAL + QQQ UNKNOWN은 QQQ 값과 무관하게 NEUTRAL이지만, "한쪽 시세가 없으면 판정하지 않는다"로 규칙을 단순하게 두려고 함께 보류한다. 백테스트도 같은 `classify_regime`을 쓴다. 기존 백테스트 테스트는 그대로 통과했다.

**e를 거부가 아니라 정규화로 한 이유**: 저장값도 `resolve_weights`에서 이 검증을 거친다. 거부로 바꾸면 이미 저장된 표가 조용히 기본 비중으로 바뀐다. 33.33×3(합계 99.99)은 부동소수 오차로 이미 ±0.01 검증에서 거부되므로 동작이 그대로다.

### E2

차트 11개에 `role="img"` + 요약 `aria-label`을 붙였다. 요약 문장은 `utils/chartSummary.ts`에 모았다. 계획은 "차트 옆 순수 함수"였지만, 컴포넌트 파일에서 함수를 export하면 `react-refresh/only-export-components` 경고가 `--max-warnings 0`에 걸린다. 이 8개 차트의 화면에는 금액 숨김 설정이 없다.

### E3

- `backend/CLAUDE.md`: `kis/domestic_quote.py`·`overseas_quote.py`, `schemas/_validators.py`, 잡 `kosdaq_tickers_refresh`, 라우터 등록 경로, `auth`·`rebalancing`·`stocks`의 누락 엔드포인트.
- `frontend/CLAUDE.md`: `api/fetchAllPages.ts`, `utils/chartSummary.ts`.
- 주석: `scheduler.py`의 keep-alive 설명, `execution_service.py`의 키움 주문가능금액, `models/alert.py`·`models/asset.py`의 `TWO_PHASE`.

### 검증

- 백엔드: ruff·ruff format·mypy 통과, pytest 3,683건 통과, 커버리지 92.9%(게이트 89%). 스냅샷 파일은 바꾸지 않았다.
- 프론트: tsc(앱·테스트)·eslint `--max-warnings 0`·prettier 통과, vitest 2,021건 통과(`--coverage`), `npm run build` 성공.
- E4 회귀 테스트는 수정 전 코드에서 실패함을 확인했다. c는 수정 전 peak 120을 별도 스크립트로 쟀다.

**미검증**
- 스크린리더 실기기 읽기는 확인하지 못했다. 렌더 테스트로 접근 가능한 이름만 고정했다.
- `AllocationHistoryChart`·`DCAProjectionChart`·`SavingsSimulatorCard`·`DividendPlanSection`의 라벨은 요약 함수 단위 테스트만 있고, 라벨이 붙었는지 보는 렌더 테스트는 없다.
- `MonthlyDividendChart`의 막대 클릭은 원래 키보드로 조작할 수 없다. 이번 범위가 아니다.

---

## 범위 밖 (이관)

- **보류**: E1.
- **스키마 판단**: ISA 계약 기간, 연금 입금 유형, 배당 세전·세후, 실제 원화 취득가(현재 문구만 수정, 양도세 추정액엔 환차익이 빠져 있음).
- **큰 작업**: 데이터 보존 잡(테이블 크기 먼저), 암호화 키 회전, 공분산 날짜 키 정렬, KIS present-balance TR(실계좌 확인 후).
- **판단 필요**: 미리보기·추천의 기대수익률 척도 차이, 전체 자산 경로의 IRP 30% 하한, 시각 미지정 `/execute` 경로의 신선도 게이트.
- **낮은 순위 보고 건**: DCA 초기값 일부 계좌(#20), 곡선 이번 달 누락(#21), 잔액 0(#23), 달성 불가 계획의 전망(#24), 혼합 포트폴리오 달러 예수금(#25), 캐시 경합 잔여(#16), QLD 이중 저장(#27), 연령 구간 갱신(#29). 프론트 메이저 업그레이드는 그대로 둔다.

## 사용자 확인 필요 (코드 밖, 110에서 이어짐)

1. **DB 비밀번호 교체** — 세션 로그에 평문 노출. `.env`의 다른 비밀값도 공유 범위에 따라 판단.
2. **Render 로그**: `preDeployCommand` 실행 여부, `periodic_catchup` 실제 실행, 시장 신호 변경 알림 발송.
3. **KIS 실계좌 읽기 전용 확인**: NASD 이중 집계, `frcr_dncl_amt_2` 유무, 실현손익 `output2` 형태.
4. **APK CI**: 마지막 실행 2026-05-25 실패. Variables 설정 또는 워크플로우 정리.
5. **세법**: 대주주 50억·2026 건보료율 공식 고시, 2026 세제개편안의 ISA 변경 입법 여부.

## 작업 시 함정

- docs 커밋은 end-of-file 훅에 자주 걸린다. 출력을 `grep`으로 거르면 실패를 놓치니 커밋 뒤 `git status`를 확인한다.
- 테스트의 가짜 함수에 새 kwarg가 없으면 AUTO 잡 재조회 루프가 mock 때문에 무한 반복해 pytest timeout으로 끝난다.
- 추천 스냅샷(`tests/snapshots/goal_recommendation.json`)은 일괄 갱신하지 말고 시나리오별로 본다.
- `is_mock_mode`는 기본값이 True다. 판정은 `is_paper_account`를 쓴다.
- 모듈 공용 `asyncio.Semaphore`는 대기가 생기는 순간 이벤트 루프에 묶인다. 테스트에서 경합시키려면 `patch.object`로 새 세마포어로 바꾼다.
