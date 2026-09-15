# 지속 투자 동기부여 검토 (2026-09-15)

## 배경

"자산증식을 위해 투자를 지속하고 동기부여할 수 있도록 프로젝트 전체를 검토해달라"는 요청으로 진행한 감사. Explore 에이전트 3개(챌린지·게임화 / 알림 시스템 / 홈 대시보드+`docs/plans` 백로그)를 병렬로 돌려 현재 코드 상태를 조사했다.

결론: 이 프로젝트는 이미 "동기부여/리텐션" 기반이 두텁게 갖춰져 있다 — 적립 챌린지(`InvestmentChallenge`, DEPOSIT/RETURN_PCT/TARGET_VALUE 3종, 스트릭 계산, 월별 캘린더, 마일스톤 3/6/12/24/36/60개월 축하 알림), 목표 달성 알림 3종(자산/입금/배당), 월간 리포트, 추천비중 변화 알림, 리밸런싱 AUTO 실행+시장신호 게이트, 네비게이션 배지 넛지까지 전부 구현되어 있다. 신규 기능을 쌓기보다 **이미 만든 동기부여 장치가 실제로 사용자에게 도달하는지**를 점검하는 쪽에서 실제 갭을 발견했다.

## 구현 완료 (이번 세션)

### 1. 챌린지 알림 이중 게이트 버그 수정

`ChallengeFormModal.tsx`의 챌린지별 "독려·결산 알림 받기" 토글은 기본 ON이지만, 실제 발송 잡(`challenge_deposit_reminder.py`/`challenge_monthly_wrap.py`)은 그보다 먼저 전역 `UserSettings.challenge_reminders_enabled`(기본 **OFF**)로 유저를 걸러버려, 사용자가 챌린지를 만들어도(토글이 기본 ON이라 아무것도 안 건드려도) 설정 › 알림 설정을 따로 찾아가지 않는 한 독려/결산/마일스톤 알림이 영원히 오지 않는 상태였다. 이전 라운드들의 세금게이트/시장신호게이트 이중 게이트 버그와 같은 패턴.

**수정**: `challenge_service.create_challenge()`에서 `payload.reminder_enabled=True`이고 유저의 전역 플래그가 꺼져 있으면 같은 트랜잭션에서 자동으로 켠다. 사용자가 챌린지별 토글을 ON으로 둔 채 챌린지를 만든 행동 자체를 알림 수신 의사로 간주.

- `backend/app/services/challenge_service.py` — `create_challenge()`에 `get_or_create_settings()` 호출 추가
- `backend/tests/test_challenge_service.py` — 신규 테스트 2건(opt-in 자동 전환 / reminder_enabled=False 시 전역 플래그 불변)
- `backend/CLAUDE.md` — `challenge_reminders_enabled` 설명에 자동 opt-in 동작 보강

### 2. 홈 대시보드 챌린지 empty-state CTA 카드

`ChallengeProgressCard`는 ACTIVE 챌린지가 없으면 완전히 렌더를 생략해, 계좌를 연결하고도 챌린지를 만든 적 없는 사용자는 이 기능의 존재를 계속 모를 수 있었다(계획 탭 하위 서브탭까지 직접 들어가야 발견됨).

**수정**: `SetupTargetPortfolioBanner`와 동일한 패턴(`useCollapsible` + localStorage 영속 dismiss)으로 신규 `ChallengeEmptyStateCard.tsx`를 만들어, `DashboardPage.tsx`가 ACTIVE 챌린지 유무에 따라 `ChallengeProgressCard`(있음) 또는 `ChallengeEmptyStateCard`(없음, "적립 습관을 챌린지로 만들어보세요" + 닫기 가능)를 선택 렌더하도록 변경. `ChallengeProgressCard` 자체는 건드리지 않아 기존 "no active challenges → null" 테스트/동작 그대로 유지.

- `frontend/src/components/dashboard/ChallengeEmptyStateCard.tsx` 신규
- `frontend/src/pages/DashboardPage.tsx` — 챌린지 카드 렌더 분기 추가
- `frontend/src/__tests__/components.challengeEmptyStateCard.test.tsx` 신규(CTA 링크, 닫기+영속 dismiss)

검증: 백엔드 `test_challenge_service.py`/`test_challenges_api.py`/`test_challenge_jobs.py` 전체 통과 + ruff/mypy clean, 프론트 관련 3개 테스트 파일 통과 + tsc/eslint clean.

## 백로그 (이번 세션 범위 밖)

- **마일스톤/독려 알림 이력을 챌린지 섹션 안에서 조회**: 현재는 설정 › 알림 설정 › 발송 이력 탭에서 다른 모든 알림 타입과 섞여서만 보인다(`fetchAlertHistory`가 `alert_type` 서버측 필터 미지원, `frontend/src/api/alerts.ts:183`). 계획 탭 챌린지 섹션 안에서 바로 보이게 하려면 필터 파라미터 추가(백엔드 선행)가 필요.
- **게임화 확장(뱃지 컬렉션, 연간 리뷰 등)**: 포인트/레벨/뱃지함 시스템은 없음. 스트릭+마일스톤 알림으로 핵심은 충족되고 있어 이번엔 제안만 기록, 구현 안 함.

## 정기 자동매수(DCA, "주식 모으기"류) — 설계 검토만, 구현 없음

2026-07-22부터 `README.md`가 "경쟁앱 대비 기능격차"로 기록해온 항목. 실자금이 매월 자동 이동하는 신규 기능이라 사용자가 이번엔 설계 검토까지만 범위로 확정했다.

코드를 다시 확인한 결과, 기존 리밸런싱 인프라가 이 요구사항의 상당 부분을 이미 커버한다:

- **옵션 A — 기존 인프라 재사용**: `RebalancingAlert.trigger_condition = SCHEDULE_ONLY` + `mode = AUTO`(`backend/app/models/alert.py:65`, `backend/app/services/rebalancing/alert_check.py:82`)를 조합하면 드리프트 여부와 무관하게 스케줄일마다 목표 비중으로 자동 매수가 실행된다 — "포트폴리오를 세워두고 매달 그 비중대로 자동 매수"는 **이미 구현되어 있다.** 진입장벽은 (a) 목표 포트폴리오를 먼저 설계해야 함, (b) 리밸런싱 개념으로만 노출돼 발견성이 낮음. 이 옵션이라면 신규 백엔드보다 **UX 재포지셔닝**(온보딩/계획 탭에 "매달 자동으로 모으기" 진입로 노출)이 핵심이라 리스크가 크게 낮다.
- **옵션 B — 단일 종목 정액 매수(토스 "주식 모으기"류)**: 목표 포트폴리오 없이 "매달 X원씩 종목 Y" 방식. 매수 주문 실행 경로(`plan_execution.py`/`order_builder.py`)는 재사용 가능하나 트리거 모델이 다름(종목+고정금액+주기). `InvestmentChallenge`(DEPOSIT)와 개념적으로 가깝지만 챌린지는 추적/알림만 하고 실제 매수는 안 함 — 신규 모델(`RecurringOrder` 등) + 신규 잡 + 브로커 주문 API 필요(토스는 주문 API가 없어 KIS/키움 한정).

두 옵션 모두 최소한 거래한도, 실패 알림, 멱등성, 주문 가능 시간대 체크가 필요 — AUTO 리밸런싱 실행의 기존 안전장치(`_order_quantity_guard.py`, 주문 접수 `retry_on_request_error=False` 등)를 재사용 가능.

**다음 세션에서 결정 필요**: 옵션 A(재포지셔닝, 저위험) vs 옵션 B(신규 기능, 고위험이지만 더 직관적인 "적립" UX) 중 방향 선택. 착수 계획 없음.
