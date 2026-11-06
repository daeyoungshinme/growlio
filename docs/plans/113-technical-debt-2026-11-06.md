# 113. 기술부채 재감사 (2026-11-06)

> **진행 상태**: A~E 완료, 브랜치 `chore/tech-debt-2026-11-06`. 이관 항목은 문서 끝.

## 배경

"남아 있는 기술부채 확인해서 수정 계획" 요청. 112 머지(#234·#235·#236) 직후 main 기준으로 백엔드·프론트·인프라/테스트 3축을 감사했다.

정적 검사는 깨끗했다: ruff·mypy·tsc(앱·테스트)·eslint·pip-audit 0건, CI 그린, 열린 PR 없음. 이번에 나온 것은 아래와 같다.

- 사용자에게 틀린 숫자·문구가 보이는 실버그 5건
- 캐시 무효화 누락
- 주문 실패 관측성 공백
- 정리 항목

실버그와 캐시 누락은 소스로 대조한 뒤 반영했다.

사용자 결정: 목표 달성 메일은 **목표별 1회**로 바꾼다. 매달 재발송은 하지 않는다.

---

## 배치 A — 실버그 (백엔드)

| # | 문제 | 수정 |
|---|---|---|
| A1 | 리밸런싱 계좌 그룹 실행 중 예상 밖 예외가 `logger.error`로만 가서 Sentry에 닿지 않았다. 주석은 옛 경로(`_job_helpers.report_job_failure`)를 가리켰다 | 예상 밖 예외는 `report_handled_failure`로 보낸다(스택 없이, 자격증명 지역변수 보호). 예상한 실패(`AppError`·`SyncError`)는 warning 그대로 |
| A2 | 목표 달성 메일의 현재 금액이 부동산을 포함한 `total_assets_krw`였다. 진행률은 부동산 제외라 "100.5% — 15억 / 5억"처럼 보였다 | `investable_assets_krw`(112 A1과 같은 기준) |
| A3 | "이번 달 미발송"만 확인해 한 번 달성한 목표 메일이 매달 다시 갔다 | `app_state` 발송 키 `goal_achieved_sent_key(user, alert_type, 목표금액[, 연도])`. 자산 목표는 금액별로 영구, 연간 입금·배당은 연도별(TTL 400일). 목표 금액을 바꾸면 다시 보낸다. 키 도입 전 이번 달 발송분은 다시 보내지 않고 키만 남긴다 |
| A4 | 1월 1~3일에 보내는 12월 리포트의 연간 배당·입금 달성률이 새해 값(≈0)이었다. 대시보드 요약이 올해 기준이라서다 | 리포트 대상 연도가 올해가 아니면 `get_annual_dividends_received`·`get_net_deposits_for_year`로 그 연도를 다시 집계한다(대시보드와 같은 SQL). `periodic_catchup`도 같은 함수를 쓴다 |
| A5 | 홈 손실수확 인사이트의 "최대 X원 절세"가 미실현 이익까지 다 판다는 가정의 `tax_saved_krw` 합이라 절세 탭 금액과 달랐다 | 실현손익(`get_overseas_realized_summary`, 캐시됨)을 넘겨 절세 탭과 같은 `build_loss_harvest_actions` 합을 쓴다. 실현손익 미확인·공제 안쪽이면 알리지 않는다 |
| A6 | ISA 안내 문구 "구성요소가분리되지" | 공백 |

## 배치 B — 캐시 무효화 누락·숨은 실패 (프론트)

| # | 문제 | 수정 |
|---|---|---|
| B1·B2 | `account-positions`(거래 입력 종목 목록)와 `monthly-optimization`(보유 배당 기반 1시간 캐시)을 아무도 무효화하지 않았다 | 아래 공용 목록에 추가 |
| B3 | `invalidateSyncData`·`invalidateAccountData`가 거의 같은 25줄 목록을 따로 들고 있어 이미 어긋나 있었다 | `HOLDINGS_QUERY_KEYS` 하나로 묶었다. 계좌 CUD는 거래·연금 납입만 더한다. 테스트로 "계좌 CUD ⊇ sync"를 고정 |
| B4 | `YearlyDividendChart`가 조회 실패를 "배당 없음"(카드 숨김)으로 보였다. `dividendPlan` 쿼리 정의가 두 곳에 있었다 | `dividendPlanQuery`(queryOptions)로 공용화하고, 실패 시 다시 시도 카드를 띄운다 |
| B5 | 계획 탭 "다시 시도"가 `invalidateDcaData`(8계열)를 지웠다 | 적립 분석 `refetch` + `PageLoadError` |
| B6 | 백테스트 1/3/5년 프리셋이 2월 29일에 없는 날짜를 만들었다. 종료일·거래내역 연도가 모듈 로드 시점에 고정됐다 | `yearsAgoLocal`(말일 보정), 기본값은 호출 시점 함수, 연도 목록은 마운트 시점 |
| B7 | 리밸런싱 배당 증감이 증가=초록·감소=빨강으로, 앱 규칙(빨강=상승)과 반대였다 | `pnlColor`·`fmtSigned`·`fmtPct` |

## 배치 C — 백엔드 정리

- **C1** `/tax/summary`: 어디서도 읽지 않는 7개 필드를 서비스에서 계산하지 않는다. 수수료 합계 쿼리(`_calc_total_fees`)는 요약·인사이트·절세 플랜·지금 할 일마다 돌았는데 함께 지웠다. 라우터 필터는 내부 전용 2개(`financial_income_krw`, `harvesting_recommendations`)만 남겼다.
- **C2** `conftest.py`에 autouse `app.dependency_overrides.clear()`를 넣었다. `setup_app`만 쓰고 정리하지 않던 6개 파일의 순서 의존이 사라진다. 기존 파일별 정리 코드는 그대로 두었다.
- **C3** ISA 절세액 세율을 `tax_service.get_tax_rates(year)`(연도별 표)에서 받는다. 이 함수는 `_get_rates`에서 공개 이름으로 바꿨다.
- **C4** 적립 미래가치 공식 3벌을 `goal_return_solver.future_value_monthly`로 모았다. 추천 스냅샷은 변화 없음.
- **C5** stocks 라우터를 정리했다.
  - 인라인 스키마를 `schemas/stock.py`로 옮겼다.
  - private 함수 import(`_search_*`, `_price_via_kis`)를 없앴다. 대신 `search_stocks_by_query`, `price_via_kis`를 쓴다.
  - 해외 시장 판정에서 대소문자를 무시한다. 소문자 `nasdaq`이면 USD 값이 원화로 반환되던 문제를 회귀 테스트로 막았다.
- **C6** `UserSettings` 인라인 조회 4곳을 `get_settings_row`로 바꿨다.
- **C7** ISA 손익 직접 입력 시 계좌 캐시 전체 무효화를 제거했다. 이 무효화는 목표 추천 세대 교체(콜드 MVO)까지 일으켰다. 이 값은 캐시 없는 ISA 현황·절세 액션만 읽는다.
- **C8** 자잘한 정리:
  - KIS 배당 파싱의 `type: ignore` 제거, 로그에 실제로 읽은 필드명을 남긴다.
  - 고아 주석 제거.
  - 추천 변화 알림 dedup 함수 이름을 `_already_sent_today`로 바꿨다.
  - 챌린지 요약은 계좌당 1회만 조회한다.

## 배치 D — 프론트 정리

- `fmtKrw`·`fmtKrwPrice`·`fmtKrwShort`의 음수를 0 방향으로 절사한다. `-0.3`이 "-1원"으로, `-0`이 "-0원"으로 보이던 문제다.
- 투자현황 손익 표시를 `fmtSigned`·`fmtPct`로 바꿨다. `> 0` 판정 화면(변화량 0이면 부호 없음)은 의도대로 둔다.
- 112 배치 4 잔재를 정리했다: 고아 `flat` JSDoc, `FxPlanCard` `wrap`, 홈 히어로 옛 카드 주석, ISO 왕복 변환. `relativeTime`은 이제 epoch ms도 받는다.
- 그 밖의 정리:
  - `TaxSummary` 대주주 필드를 필수로 바꿨다.
  - `MiniDonut`는 선택한 조각을 이름으로 기억한다.
  - 주문 멱등 키는 지연 생성한다.
  - `useAnalysisState`의 렌더 중 ref 쓰기를 `useLatestRef`로 바꿨다.

## 배치 E — 인프라·문서

- **compose**: 문서화된 명령은 전부 `db`만 쓰므로, 사용처 없는 `backend` 서비스와 `docker-compose.override.yml`을 지웠다. root `.env` 없는 새 클론에서 `env_file` 누락으로 compose가 실패하던 문제도 함께 사라진다. 루트 `.env.example`은 선택(`POSTGRES_PASSWORD`)으로 남겼다.
- **pre-commit ruff**: `ruff-pre-commit` rev 핀(Dependabot 미추적)을 local system 훅으로 바꿨다. `backend/.venv`의 ruff(uv.lock)를 쓰고, mypy 훅과 같은 패턴이다.
- **CI**: `setup-uv`의 `version`을 Dockerfile uv 태그(0.13.7)와 같게 고정했다. Dependabot docker 주석에 "uv 이미지를 올리면 CI도 맞춘다"를 적었다.
- **커버리지**:
  - 백엔드는 `app/main.py`를 측정에 포함하고(88%) 게이트를 89 → 91로 올렸다(실측 93.01%).
  - 프론트는 `src/lib/**` 전체 제외를 SDK 초기화 3개로 좁혀 `storedSession`을 측정한다.
- `make clean`이 실제 산출물을 지우도록 고쳤다: root 캐시, `.coverage`, `coverage.xml`, `tsbuildinfo`, `tsc_output.txt`.
- **문서**:
  - 루트 CLAUDE.md의 keep-alive 설명을 실측과 맞추고, 커버리지 게이트를 91%로 고쳤다.
  - backend/CLAUDE.md에 `already_sent_alert_today`·`challenge_reminder_recipients`·목표 알림 1회 규칙을 적었다.
  - 111 E1 함정 문구의 `preDeployCommand`를 바로잡았다.

---

## 검증

- 백엔드: ruff·ruff format·mypy 0건, pytest 3676 통과, 커버리지 93.01%(게이트 91).
- 프론트: tsc(앱·테스트)·eslint `--max-warnings 0` 0건, vitest 187파일 2023건 통과, 커버리지 임계값 통과.
- 새 pre-commit ruff 훅이 미사용 import를 잡아 고치는 것을 확인했다.
- **확인 못 한 것**:
  - 이 환경에 Docker·make가 없어 `docker compose config`와 `make clean`은 돌리지 못했다. PR CI가 첫 판정이다.
  - 브라우저 확인(리밸런싱 배당 증감 색, 투자현황 손익, 계획 탭 다시 시도, 자산 › 배당 연도별 차트)은 하지 않았다.

## 작업 시 함정

- worktree에서 `uv sync`만 하면 dev extras(ruff·mypy)가 빠진다. 그러면 pre-commit의 mypy·ruff 훅이 SKIP을 출력하고 "Passed"로 보인다. `uv sync --extra dev`(= `make install-backend`)를 쓴다.
- Bash 도구에서 `cat > 파일`처럼 stdin을 기다리는 명령은 타임아웃까지 멈춘다.
- `Math.trunc(-0.3)`은 `-0`이고, `toLocaleString()`은 "-0"을 낸다. `|| 0`으로 정규화한다.
- `useLatestRef`가 돌려주는 ref도 eslint `exhaustive-deps`는 안정 값으로 모른다. deps에 넣는다(값은 안 바뀐다).

## 이관 / 보류

- **stocks 시세 파이프라인 통합**(C5 나머지): 라우터는 Yahoo → 국내 → 계좌 지정 KIS, `price_service.fetch_prices_batch`는 국내 → Yahoo → 임의 KIS 계좌 순서다. 합치면 동작이 바뀌어 별도 판단이 필요하다. 배치 응답은 계약상 ticker 키라 같은 티커·다른 시장 충돌도 그대로다.
- `goal_start_date`의 Date 컬럼 전환: `external.py`(nestlio 전송)와 마이그레이션을 수반한다.
- FK 인덱스(111 E1 보류 유지, 공유 Supabase 마이그레이션).
- yfinance 1.x, React 19·recharts 3·TS 7 메이저: 기존 결정대로 유지. (tailwind 4는 #240에서 완료 — 114)
- CI 이미지 스모크(`/app/scripts`)와 Dockerfile `PYTHONPATH`: 운영 이미지에서 bootstrap을 돌릴 일이 다시 생길 수 있어 유지 여부를 따로 판단한다.
- 그 밖:
  - `websockets`·`watchfiles` 운영 의존성 분리
  - 600줄대 파일 분할
  - private 이름 교차 import 4곳(`_RECOMMENDATION_DRIFT_THRESHOLD_PCT`, `_MARKET_NOTES`, `_cagr_lookback_years_from_settings`, `_upsert_snapshot`)
  - 테스트 폴더 배치 규칙, `ToggleSwitch.tsx` 파일명, CI pytest `-x`
  - `_stock_unrealized_from_rows`는 이제 첫 값만 쓰인다(테스트가 4튜플을 고정해 그대로 둠)
- **사용자 실행**: 병합된 로컬 브랜치 31개 삭제(`git branch --merged main`). 109·111의 사용자 확인 항목(KIS 실계좌, Render 로그, APK CI, 세법 고시)은 그대로다.
