# 프로젝트 군더더기 정리 계획 (plans/112)

## Context

문서·설정·백엔드·프론트에서 불필요하거나 중복된 정보를 조사했다.

- **가장 큰 낭비:** 작업 전 읽는 문서다. `docs/plans/README.md`가 138KB, 하위 CLAUDE.md 2종이 합쳐 79KB다.
- **코드:** 죽은 파일과 미사용 의존성은 거의 없다. 효과가 큰 곳은 테스트 헬퍼 복붙(`_make_user` 29개 파일, `_make_mock_db` 29개, `_setup_app` 21개)과 모바일·데스크톱 마크업 두 벌이다.
- **조사 중 발견한 잘못된 표시·문서:** 목표 수치 표시 오류 2건, 실제와 다른 배포 문서 1건.

**사용자 결정**
- 화면: 데스크톱 목표 전망 접기, 홈 주식 현황 카드 통합, 계획 탭 배당 차트 정리. 자산 배당 월평균 칸은 유지한다.
- 인프라: nginx 자체호스팅, keep-alive, monitoring 제거.
- 계획서: README만 압축하고 파일은 이동하지 않는다.
- Render: 무료 플랜, 수동 마이그레이션.

**실행 방식:** 배치별로 독립 PR을 만든다. 착수 전에 이 내용을 `docs/plans/112-*.md`로 저장하고 인덱스에 추가한다. 번호는 착수 시점의 최신 번호로 재확인한다.

---

## 배치 0 — 표시 오류 수정 (우선)

**A1. 진행률과 "남은 금액"의 기준 불일치**
- 문제: `InvestmentGoalCard.tsx:52`는 부동산을 포함한 `total_assets_krw`로 남은 금액을 계산한다. 진행률은 부동산을 뺀 값이다(`asset_aggregator.py:233`). 부동산이 크면 "60%"인데 "목표 달성"으로 보인다.
- 수정: 대시보드 응답에 `investable_assets_krw`를 추가하고(`schemas/dashboard.py`, `api/dashboard.ts`) 이 값으로 계산한다. persist 캐시의 옛 응답에는 필드가 없으므로 없을 때 남은 금액 문구를 숨긴다.

**A2. "약 N개월 후"가 남은 기간이 아님**
- 문제: `months_to_goal`은 `start_date`부터 센 총 기간이다(`dca_service.py:312`). 함수 docstring의 "남은 개월 수"도 틀렸다.
- 수정: `GoalTimelineCard.tsx:115-119`와 `DcaOutlook.tsx:162-166`의 문구를 제거한다. 예상 연월이 바로 위에 있어 정보 손실이 작다. docstring도 고친다.
- 라벨은 "계획 기준 / 실제 기준"으로 통일하고, `GoalTimelineCard:113`에 `fmtMonth`를 적용한다.

**검증:** 부동산 포함 케이스와 시작일이 과거인 케이스의 회귀 테스트를 추가한다.

---

## 배치 1 — 문서 압축 (코드 변경 없음)

**`docs/plans/README.md` 138KB → 약 20KB**
- 계획 목록을 행당 한 줄(번호·파일·요약·상태)로 줄인다.
- 낡은 "상태 (2026-07-20)" 절 38KB를 삭제한다.
- 실행 전 필수 확인사항과 경쟁앱 로드맵 절은 유지한다.
- **결번 17·23은 파일이 없으므로 README에 내용을 남긴다.**
- 낡은 상태 표기(52·59·60행)는 코드와 대조해 고치고, 메모리 링크 `[[...]]`를 제거한다.

**CLAUDE.md 3종 합계 약 90KB → 약 60KB** (함정은 보존, 중복·경위만 삭제)
- 패딩: `frontend/CLAUDE.md` 표 패딩을 제거한다(약 7KB).
- 표 축소: queryKey 표는 `constants/queryKeys.ts` 포인터와 함정(`Base` 키 규칙)만 남긴다.
- 단일화: 루트와 하위에 겹치는 금액 KRW·`is_active`·Render 슬립·Windows pytest·Pooler·alembic 버전 테이블·새 모델 import는 한 곳에만 둔다.
- 삭제: 루트 Makefile 설명 표는 주의점(`db-reset` 등)만 남긴다. 환경변수 목록도 함정만 남긴다.
- 경위 문구 삭제: "토스 연동 때 7곳 누락", "덮던 경합", "막던 문제" 등.
- 사실 오류 수정
  - `get_dividend_data` → 실제 함수 `get_ticker_dividend_summary`(`dividend/orchestrator.py:302`)
  - `RebalancingStatusCard` "항상 펼침"(실제는 접기 가능)
  - 타입 위치 `src/types/index.ts`(대부분 `src/api/*`)
  - 목록 누락: `RefreshContext`, `providers/base.py`, `kis/order.py`, `kiwoom/order.py`
  - "주문 접수 4곳"과 "호출부 5곳"은 재집계 후 수정하거나 수치를 삭제한다.

---

## 배치 2 — 미사용 인프라 제거 + Render 문서 현실화

**Render (실제 절차에 맞춤)**
- `render.yaml`의 `preDeployCommand`를 제거한다.
- `backend/scripts/bootstrap_alembic.py`는 수동 절차에 필요하므로 **유지**한다.
- 수동 절차(코드 배포 **전**에 마이그레이션)를 루트 CLAUDE.md "배포"에 적는다.
- preDeploy를 언급하는 곳을 함께 고친다: 루트·`backend/CLAUDE.md`, `backend/Dockerfile:17`, `ci.yml:203`, `bootstrap_alembic.py:14`.
- `ENV PYTHONPATH=/app`과 CI의 scripts import 검사는 영향이 있는지 확인한 뒤 판단한다.

**nginx 자체호스팅 제거**
- 삭제: `nginx/`, `frontend/Dockerfile`, `frontend/Dockerfile.dockerignore`, compose의 `nginx` 서비스, 루트 `.env.example`의 VITE 빌드 인자, `ci.yml:221` 프론트 이미지 빌드 스텝.
- 수정: `ci.yml:156`과 `build-android.yml:43`의 "frontend/Dockerfile과 같은 major" 주석, dependabot의 해당 docker 항목, CLAUDE.md 설명.
- 유지: `frontend/vercel.json`을 보안 헤더의 단일 출처로 둔다. `backend/Dockerfile`과 CI 백엔드 이미지 빌드도 유지한다.

**monitoring 제거**
- 삭제: `monitoring/`, compose의 `prometheus`·`grafana`·볼륨, `.env.example`의 `GRAFANA_PASSWORD`.
- 수정: `dependabot.yml:147` 주석.
- 유지: 앱의 `/metrics`, `METRICS_TOKEN`, `prometheus_client`.

**keep-alive 제거** (별도 커밋)
- 삭제: `.github/workflows/keep-alive.yml`. 문서 설명은 "외부 핑 또는 유료 플랜 필요"로 줄인다.
- ⚠️ **부작용:** 슬립을 막지는 못하지만, 실측 약 4~8시간마다(`gh run list`) 잠든 서버를 **깨우는 역할**은 한다. `periodic_catchup`은 기동 2분 뒤 놓친 월간 잡을 보충한다. 앱을 열지 않는 기간에는 제거 후 월간 리포트·알림이 지금보다 더 늦어지거나 빠질 수 있다.
- **외부 핑(UptimeRobot 등)을 먼저 등록한 뒤 제거한다.**

**작은 설정 정리**
- `.gitignore`: 중복 4줄 삭제, 경로 무관 캐시 패턴 추가, `google-services.json` 차단.
- `.pre-commit-config.yaml`: 낡은 설치 안내 수정.
- `.vscode/settings.json`: 없는 black 설정과 경로를 고치거나 추적 해제.
- `make clean`: 캐시 경로 보강.

---

## 배치 3 — 화면 정보 축소

**홈 주식 현황 카드 → Hero 통합** (`InvestmentSnapshotCard.tsx` 삭제, `DashboardPage.tsx:212-216`)
- `HeroSummaryCard`에 "주식 평가손익 (매입원가 대비)" 한 줄을 넣는다.
- **금액 숨김 규칙을 그대로 따른다:** 손익 금액은 `amountVisible`일 때만 보이고, 숨김 상태에서는 `••••••`로 표시한다. 수익률은 현재 누적 수익률처럼 항상 보인다.
- 주식이 없으면 줄을 숨긴다. 자산 탭 링크(`portfolioUrl()`)는 유지한다. 투자원금은 자산 탭에서 본다.

**데스크톱 목표 전망 접기** (`investmentGoal/DcaOutlook.tsx`)
- 데스크톱도 모바일처럼 진행률 헤드라인과 접기로 맞춘다. 기존 `growlio:goalCard:dcaDetailOpen` 키를 재사용한다.
- `Desktop/MobileDcaOutlook` 두 벌을 하나로 합친다.

**계획 탭 배당 차트** (`invest/DividendPlanSection.tsx:343-470`)
- 월별 분포 차트를 제거하고 약한 달 표시만 남긴다.
- 연도별 실수령 추이는 자산 › 배당 › 월별로 **옮긴다**. 삭제하지 않으며 증감률 목록도 유지한다(계획 67 결정).
- 배당 탭 분리(계획 106)는 유지한다.

**같은 화면의 명백한 반복 제거**
- `DividendTab:402-407` 합계 행(상단 "예상 연간 배당금"과 같은 값)
- `GoalTimelineCard:104-108` 목표 금액
- `InvestPlanPage:187-189` 부제와 `:432,460,468` 힌트
- `GoalAdjustTab`·`TacticalAllocationTab`·`RecommendationResultPanel` 안내문(공통 문구 1개, 면책 문구는 적용 버튼 근처 1곳)

---

## 배치 4 — 프론트 코드 군더더기

**삭제**
- `ToggleSwitch` export(프로덕션은 `ToggleRow`만 사용)
- `CurrencyType`, `ChallengeFormData`, `api/dividends.ts`의 미사용 `DividendSummary`
- 프로덕션에서 항상 flat인 `flat` prop 6곳
- `RebalancingStatusCard`의 죽은 null 분기와 낡은 주석
- 백엔드 응답 중 프론트가 쓰지 않는 필드의 타입 선언

**통합**
- `DividendPlanSection`·`DividendTab`의 모바일/데스크톱 중복 마크업(`useIsSmUp`)
- `RealEstateAccountModal`·`RealEstateEditModal`(은행·증권 모달의 `initialAccount` 방식 재사용)
- 오류+"다시 시도" 블록 → 공용 컴포넌트(54건/47파일)
- 부호 처리 `fmtSigned`를 `utils/format.ts`에 추가(44건)
- `HeroSummaryCard`·`OfflineBanner` → 기존 `relativeTime` 재사용
- `DashboardPage:38-93` 온보딩 → 배열 순회

---

## 배치 5 — 백엔드 죽은 코드와 페이로드

**삭제**
- 호출처 0건: `get_latest_snapshot`, `ROLE_MEMBER`, `TILTS`, `KiwoomBalanceResponse`, 소비자 없는 재노출(`tactical_allocation_service.__all__` 5개, `COMPOSITE_SCORE_MAX`)
- 테스트 전용: `fetch_current_price`(`cache_keys.py:127` 주석 포함), `is_dca_auto_buy`, `pnl_pct`
- 항상 빈 필드: `manual_positions`, `untracked_holdings`, `CurrentHolding`

**응답 축소** (각 필드는 착수 시 프론트·이메일·nestlio `growlio_client.py` 사용 여부를 재확인)
- `top_drifted_items`와 생성 코드(`rebalancing/service.py`)
- 대시보드 `monthly_trend`, `annual_dividends_received`, `dividend_monthly_breakdown`, `xirr_is_estimated`. 월간 리포트가 내부 dict를 쓰므로 **스키마에서만** 뺀다.
- `/tax/summary` 미사용 필드. 내부 서비스가 쓰는 값은 **라우터 응답에서만** 뺀다.

**저위험 중복 통합**
- `_already_sent_*` 3벌
- challenge 잡 수신자 조회 2벌
- `kis/domestic_quote.py` 2벌
- `dividend/fetcher.py` 2벌
- 자격증명 삭제 라우트 3벌(경로는 유지)

---

## 배치 6 — 테스트 헬퍼 통합 (약 600~900줄)

- `tests/conftest.py`에 사용자 팩토리와 API 클라이언트 fixture를 추가하고, 헬퍼를 파일 묶음 단위로 옮긴다. **단언은 바꾸지 않는다.**
- `test_api_routes.py`의 401 테스트 4개(AST 동일)를 제거한다.
- `test_goal_recommendation.py:551,602` ceiling/floor 테스트는 입력과 단언이 같다. **한쪽이 잘못 작성됐을 수 있어 삭제 전에 의도부터 확인한다.**
- `test_tax_api.py`의 `_MOCK_TAX_SUMMARY`를 실제 응답 형태로 고친다(없는 키 4개 사용 중).

---

## 이번 범위에서 제외

| 항목 | 이유 |
|---|---|
| 주문 경로 통합(`_kis/_kiwoom_order_executor`, `kis/order.py`) | 실주문 위험 대비 이득이 작음 |
| 키움·토스 토큰 통합, 시장 신호 표 방식, `useTabParam` | 중간 위험, 별도 판단 |
| `manual_currency` 드롭, 쓰기 전용 감사 컬럼, alembic squash | 마이그레이션 수반, nestlio와 DB 공유 |
| `/external/net-worth-history` | 배포된 nestlio의 호출 여부 확인 필요 |
| `dart_circuit` | 적용과 삭제 중 결정 필요 |
| 사용 빈도가 낮을 수 있는 기능(시뮬레이터 등), Hero 환율, 진단 이탈 목록, 절세 각주 | 사용 데이터 없음 또는 미선택 |
| `Button` 전면 도입/삭제, 코드 주석의 `plans/NN` 225건 | 별도 결정 필요 |
| 계획서 아카이브, 자산 배당 월평균 칸 | 사용자가 유지 선택 |
| `startCommand` 제거 | Render Docker 동작 미확인 |

---

## 검증

배치마다 아래를 실행한다. CI와 같은 기준이다.

```bash
make lint && make typecheck
make test-backend-cov   # 89% 게이트
make test-frontend      # 임계값은 vite.config.ts
```

Windows의 `N passed` 후 종료 코드 `-1073741819`는 실패가 아니다.

- **배치 0·3:** `make dev`로 실행해 브라우저에서 확인한다. 모바일과 데스크톱 폭, 금액 숨김/표시 전환, 부동산 보유 계정의 남은 금액, 주식 없는 계정을 본다.
- **배치 1:** 삭제한 식별자와 경로를 grep해 깨진 참조를 확인한다. 줄인 함정이 없는지 diff를 검토한다.
- **배치 2:** 아래를 확인한다.
  - `docker compose config`, `docker compose up -d db`
  - `backend` 이미지 빌드
  - `grep -rE "nginx|monitoring|prometheus|grafana|keep-alive|frontend/Dockerfile|preDeploy"` 잔존 참조
  - 머지 후 CI 그린, Render 배포 `/health`
- **배치 5:** `alembic check`로 모델 드리프트를 확인한다. 응답 필드 삭제 전에 `backend/`·`frontend/src`·nestlio를 grep한다.
- **완료 시:** 줄어든 양을 계획서에 기록하고, 파일 목록이 바뀐 CLAUDE.md 항목을 갱신한다.
