# 계획 13: 시장신호 매일 요약 알림 (일 1회 정기 발송)

**리스크: 낮음~중간 (신규 UserSettings 컬럼 + 마이그레이션, 기존 알림 파이프라인/스케줄러 패턴 재사용)**

## 배경 (Why)

2026-07-20 사용자가 "시장신호 알림을 하루에 한 번은 주기적으로 받고 싶다"고 요청했다. 조사 결과, 시장신호 알림 인프라(스케줄러·이메일·푸시·알림이력)는 이미 갖춰져 있지만 현재 발송 조건이 전부 "이벤트성"이라 이 요청을 충족하지 못한다:

- `backend/app/jobs/market_signal_alert.py`(1시간 간격) → `market_signal_alert_service.check_market_signal_level_change()` — GREEN/YELLOW/RED **등급이 실제로 바뀔 때만** 발송. 등급이 며칠간 GREEN으로 유지되면 그 기간엔 알림이 전혀 안 감(`MarketSignalAlertSection.tsx`도 이 동작을 "며칠간 안 올 수도 있다"고 이미 안내 중).
- `backend/app/services/rebalancing/alert_check.py`(10분 간격) — 리밸런싱 드리프트 알림에 "얹혀서" 나가는 복합신호 알림. `check_composite_signal()`이 위험하다고 판단할 때만, 그것도 활성 리밸런싱 알림이 있는 유저에 한해 하루 최대 1회 발송.

즉 "등급 전환 시" 또는 "위험 신호 감지 시"만 존재하고, "매일 무조건 한 번 현재 상태를 알려주는" 정기 다이제스트 경로가 없다.

**사용자 확인 결과** (AskUserQuestion):
- 기존 "시장 신호 알림" 토글(`composite_signal_alerts_enabled`)과 별개로 **새 토글**을 추가한다 — 기존 "등급 전환 시 즉시" 동작은 그대로 유지.
- 발송 시각: **매일 08:30 KST** (장 시작 전, 리밸런싱 알림 기본 `notify_time`과 동일).
- 채널: **이메일 + 푸시 둘 다**.
- 기본값: 옵트인(기본 OFF) — 새 기능이므로 사용자가 명시적으로 켜야 발송.

## 현재 코드 상태 (2026-07-20 기준 — 실행 전 재확인 필수)

- `backend/app/scheduler.py:48-55` — 시장신호 job 등록부. 같은 파일의 `goal_achievement_check_daily`(106-111행, `CronTrigger(hour=18, minute=45, ...)`)가 "일 1회 정기 job" 등록 패턴의 참고 예시.
- `backend/app/jobs/market_signal_alert.py` — 기존 시장신호 job 파일 (등급 전환 전용, 건드리지 않음).
- `backend/app/services/alerts/market_signal_alert_service.py` — 등급 전환 감지 로직(`check_market_signal_level_change`, `_get_composite_subscribers`). 새 다이제스트 함수를 이 파일에 추가하거나 신규 파일로 분리 — 기존 함수와 로직이 다르므로(구독 조건도 다름: 다이제스트는 활성 리밸런싱 알림 불필요) 별도 함수로 분리 권장.
- `backend/app/models/user.py:61` — `composite_signal_alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)`. 새 컬럼을 바로 아래 추가.
- `backend/app/api/v1/settings.py:121-122`(`CompositeSignalAlertsUpdate`), `137`(`SettingsResponse.composite_signal_alerts_enabled`), `178`(응답 매핑), `307-319`(`PUT /settings/composite-signal-alerts` 엔드포인트) — 새 엔드포인트가 그대로 따라 할 패턴.
- `backend/app/services/email_templates.py:625-648`(`market_signal_change_template`) — 새 다이제스트 템플릿의 참고 구조. `_SIGNAL_LEVEL_LABEL`/`_SIGNAL_LEVEL_COLOR`(621-622행) 재사용.
- `backend/app/services/rebalancing/diagnosis_service.py:38-42`(`_MARKET_NOTES`) — GREEN/YELLOW/RED별 코멘트 문구, 다이제스트 본문에 재사용 가능.
- `backend/app/jobs/goal_achievement.py:25-38`(`_already_notified_this_month`) — "오늘/이번 달 이미 발송했는지" DB 조회 dedup 패턴. 다이제스트는 이 패턴을 "오늘"(day) 단위로 응용.
- `frontend/src/components/settings/MarketSignalAlertSection.tsx` — 기존 토글 UI. 같은 카드에 두 번째 토글을 추가.
- `frontend/src/hooks/useCompositeSignalToggle.ts` — 새 훅(`useMarketSignalDigestToggle.ts`)의 구조적 참고.
- `frontend/src/api/settings.ts:36`(타입), `49-50`(`updateCompositeSignalAlerts`) — 새 API 함수 패턴.
- `frontend/src/pages/SettingsPage.tsx:77-85`(`ALERT_TYPE_LABELS`) — 새 alert_type 레이블 추가 위치.

## 구현 단계

### 1. 백엔드 — 모델/마이그레이션
- `UserSettings`에 `market_signal_daily_digest_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)` 추가 (`models/user.py`).
- `cd backend && uv run alembic revision --autogenerate -m "add market signal daily digest toggle"` → 마이그레이션 검토 후 `alembic upgrade head`.

### 2. 백엔드 — 다이제스트 발송 로직
- `services/alerts/market_signal_alert_service.py`에 `send_market_signal_daily_digest(db, redis)` 신규 함수 추가:
  - 대상 유저: `UserSettings.market_signal_daily_digest_enabled == True` AND `User.is_active == True` — **활성 리밸런싱 알림 보유 여부는 조건에 넣지 않음**(기존 등급전환 알림과 달리, 이 다이제스트는 리밸런싱 알림 설정과 무관하게 독립적으로 신청 가능해야 사용자가 "그냥 매일 시장 상황만 보고 싶다"는 니즈를 충족함).
  - `get_market_signal(redis)`로 현재 `composite_level` 1회 조회(전체 루프 공용) — 이미 캐시된 값이라 추가 API 호출 없음.
  - `_MARKET_NOTES` 기반 reason 재사용, 다이제스트는 GREEN이어도 "오늘도 안정적입니다" 류의 짧은 문구로 대체(빈 메시지 방지).
  - 이메일: `send_market_signal_daily_digest_alert(to_email, level, reason)` 신규 함수(`email_service.py`) + `market_signal_daily_digest_template(level, reason)` 신규 템플릿(`email_templates.py`, `market_signal_change_template` 구조 재사용하되 "전환" 문구 대신 "오늘의 시장 신호" 프레이밍).
  - 푸시: `send_push_to_user(..., data={"type": "MARKET_SIGNAL_DIGEST"})`.
  - dedup: 오늘 이미 발송했는지 `AlertHistory`에서 `alert_type="MARKET_SIGNAL_DIGEST"` + 오늘 날짜(KST) 조회(`_already_notified_this_month` 패턴을 day 단위로 응용) — 스케줄러 재시작/misfire로 인한 중복 발송 방지.
  - 발송 성공 시 `save_alert_history(db, user.id, "MARKET_SIGNAL_DIGEST", f"오늘의 시장 신호: {level}")`.
  - 개별 유저 실패가 전체를 막지 않도록 `goal_achievement.py`의 `asyncio.Semaphore` + `asyncio.gather` 동시성 패턴 재사용.

### 3. 백엔드 — job 등록
- `backend/app/jobs/market_signal_daily_digest.py` 신규 파일 — `run_alert_job` 헬퍼(`_job_helpers.py`, 기존 job들과 동일 패턴) 또는 `goal_achievement.py` 스타일의 자체 세션 관리 중 기존 컨벤션에 맞는 쪽으로 작성.
- `scheduler.py`에 등록:
  ```python
  scheduler.add_job(
      run_market_signal_daily_digest,
      CronTrigger(hour=8, minute=30, timezone="Asia/Seoul"),
      id="market_signal_daily_digest",
      replace_existing=True,
  )
  ```

### 4. 백엔드 — 설정 API
- `CompositeSignalAlertsUpdate` 옆에 `MarketSignalDigestUpdate(BaseModel)` 스키마 추가.
- `SettingsResponse`에 `market_signal_daily_digest_enabled: bool = False` 필드 추가, `get_settings` 응답 매핑에도 반영.
- `PUT /settings/market-signal-digest` 엔드포인트 추가(`update_composite_signal_alerts`와 동일 구조, `@limiter.limit("10/minute")`).

### 5. 프론트엔드
- `api/settings.ts`: 타입에 `market_signal_daily_digest_enabled: boolean` 추가, `updateMarketSignalDigest(enabled: boolean)` 함수 추가.
- `hooks/useMarketSignalDigestToggle.ts` 신규 — `useCompositeSignalToggle.ts`와 동일 구조(단, 상태 조회는 `["settings"]` 쿼리의 `market_signal_daily_digest_enabled` 필드를 직접 읽거나 별도 캐시 무효화 유틸 추가 — `queryInvalidation.ts`에 `invalidateMarketSignalDigestData` 필요 여부는 구현 시 판단, 단순 `["settings"]` 무효화로 충분할 가능성 높음).
- `components/settings/MarketSignalAlertSection.tsx`에 두 번째 토글 행 추가: "매일 아침 시장신호 요약" — 설명 문구 "매일 08:30 현재 시장 위험 신호를 등급 변화와 무관하게 요약해 보내드립니다." 기존 토글과 시각적으로 구분(예: 구분선 또는 별도 sub-label)해 "즉시 알림"과 "매일 요약"이 다른 설정임을 명확히 표시.
- `pages/SettingsPage.tsx:77-85` `ALERT_TYPE_LABELS`에 `MARKET_SIGNAL_DIGEST: "시장신호 매일 요약"` 추가.
- 테스트: `hooks.usePushNotifications.test.ts` 인접 위치에 신규 훅 테스트, `components.settings2.test.tsx`에 새 토글 렌더/토글 케이스 추가.

### 6. 문서
- `backend/CLAUDE.md`의 `jobs/` 목록에 `market_signal_daily_digest.py` 항목 추가. 겸사겸사 기존 `market_signal_alert.py` 설명이 "10분 간격"으로 잘못 적혀 있는 것도 "1시간 간격"으로 수정(코드 `scheduler.py`의 `IntervalTrigger(hours=1)`이 정답, 조사 중 발견된 기존 문서 오류).
- `frontend/CLAUDE.md` hooks 목록에 `useMarketSignalDigestToggle.ts` 추가.

## 검증

- `cd backend && uv run pytest -k market_signal` — 신규 테스트(다이제스트 발송 조건, dedup, 유저 필터링) + 기존 테스트 회귀 확인.
- `cd backend && uv run ruff check . && uv run mypy app/`
- `cd frontend && npm run test && npm run typecheck && npm run lint`
- 수동 확인: 로컬에서 `market_signal_daily_digest_enabled=True`로 설정 후 job 함수를 직접 호출(또는 스케줄러 시각을 임시로 앞당겨)해 이메일(Resend 테스트 키 또는 로그)·푸시·`AlertHistory` 기록이 정상 생성되는지 확인. 등급 전환 알림((A) 기존 job)이 여전히 정상 동작하는지 회귀 확인(같은 서비스 파일을 건드리므로).

## 확장 아이디어 (범위 밖)

- 다이제스트에 "어제 대비 변화"(예: 어제 GREEN → 오늘도 GREEN이지만 세부 점수는 상승) 같은 트렌드 정보를 포함하면 정보 밀도가 높아지지만, 이번엔 "일단 하루 한 번 오게 하는 것"이 목표이므로 범위 밖.
- 다이제스트 발송 시각을 유저별로 커스터마이징(리밸런싱 알림의 `notify_time`처럼)하는 것도 가능하나, 이번 요청은 "하루 한 번"이 핵심이라 고정 시각(08:30)으로 시작하고 피드백 보고 판단.
