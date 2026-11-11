# 123 — 달러 환전 계획에 추가 환전(여행 등) 항목 (2026-11-11)

## 배경

계획 › 적립 계획 › **달러 환전 계획**(`FxPlanCard`, plans/96·121)은 해외 적립에 필요한 달러만 계산한다(포트폴리오 해외 몫 × 기간 − 증권 계좌 보유 달러 → "지금" + 목표 환율 2구간, 구간 알림 `source=FX_PLAN`). 여행·유학비·해외 결제처럼 **적립과 별개로 특정 날짜까지 필요한 달러**는 넣을 곳이 없다.

사용자 결정(2026-11-11):
- 추가 환전은 적립 계획과 **별도 구간**으로 표시한다. 증권 계좌 보유 달러로 상쇄하지 않는다(여행 달러는 은행·트래블카드로 따로 환전). 해외 포트폴리오가 없어도 쓸 수 있다.
- 항목마다 **목표 환율 알림**을 걸 수 있다(발동 메일·푸시에 금액, 홈 "지금 할 일").

범위 밖: USD 외 통화(JPY·EUR — 환율 소스·알림이 USD/KRW 전용), 실제 환전 실행(3사 모두 API 없음), 환전 예측.

## 설계

### 데이터 (마이그레이션 `fx2_fx_extra_needs`, down=`fx1_exchange_rate_alert_plan_source`)
- 새 모델 `FxExtraNeed`(`app/models/fx_extra_need.py`, `models/__init__.py` import): `id`, `user_id`(CASCADE), `name` String(40), `amount_usd` Numeric(18,2), `exchanged_usd` Numeric(18,2) default 0(이미 바꾼 금액 — 진행 기록), `due_date` Date, `created_at`/`updated_at`. 인덱스 `user_id`는 `__table_args__`에도 선언.
- `ExchangeRateAlert.fx_need_id` UUID FK → `fx_extra_needs.id` **ondelete=CASCADE**(항목 삭제 시 그 알림도 삭제) + 인덱스. 출처는 기존 `FX_PLAN` 그대로, `portfolio_id`는 NULL.
- 상한: 사용자당 10개(`MAX_FX_EXTRA_NEEDS_PER_USER`, `constants.py`). 알림 상한 50은 기존 공유.
- **운영 DB에 수동 적용 필요**(루트 CLAUDE.md 절차) — 배포 전에.

### 백엔드
- `fx_plan_service.py`
  - 구간 계산 재사용: 남은 금액 `amount − exchanged`에 대해, 필요일까지 `FX_EXTRA_URGENT_DAYS`(14일) 이하면 전액 "지금" 1구간, 아니면 기존 `compute_fx_plan(position, remaining, live_rate)`. 지난 항목은 `status=PAST_DUE`(구간 없음), 다 바꾼 항목은 `DONE`.
  - 환율·위치는 `get_fx_plan`과 같은 경로(`get_live_or_cached_usd_krw` + `fetch_usd_krw_closes`) — 공용 헬퍼 `_rate_and_position(cache)`로 추출해 양쪽이 쓴다. 실값·종가 둘 다 없으면 `NO_RATE`(달러→원 계산 안 함, plans/99 A6 규칙).
  - `sync_fx_plan_alerts`를 **범위(scope)** 인자로 일반화: `portfolio_id` 또는 `fx_need_id` 중 하나. 기존 루프의 "다른 포트폴리오면 건너뜀"을 "같은 scope가 아니면 건너뜀"으로 바꾸고, 포트폴리오 계획 sync가 항목 알림을, 항목 sync가 포트폴리오 알림을 건드리지 않음을 테스트로 고정. 락 키·MANUAL 건너뛰기·발동 후 `FX_PLAN_ACTION_DAYS` 보존 규칙은 그대로. 지난 항목에는 새 알림 생성 거부(BadRequest).
- 새 서비스 함수(같은 파일, 너무 커지면 `fx_extra_need_service.py`로 분리): `list_fx_extra_needs`(구간 포함) · `create` · `update` · `delete`(소유 확인은 `get_owned_or_404` 패턴, 타 유저 404).
- 라우터 `api/v1/invest.py`(prefix 동일 → vercel rewrite 변경 없음):
  - `GET /invest/fx-extra-needs` → `{ position_rate, rate_is_live, needs: [{id, name, amount_usd, exchanged_usd, remaining_usd, due_date, days_left, status, tranches}] }`
  - `POST /invest/fx-extra-needs`, `PATCH /invest/fx-extra-needs/{id}`(보낸 키만), `DELETE /invest/fx-extra-needs/{id}`
  - `PUT /invest/fx-extra-needs/{id}/alerts` — 본문은 기존 `FxPlanAlertSyncRequest`의 targets 형식 재사용, 응답 `FxPlanAlertSyncResponse`.
  - 스키마는 `schemas/invest.py`(금액은 `_validators.py` 공용 검증 — NaN·음수 거부, `exchanged ≤ amount`, `due_date ≥ 오늘 KST` 생성 시).
- 알림 발송 `alerts/exchange_rate_service.py`: 대상 쿼리에서 **필요일 지난 항목의 알림은 건너뛴다**(join `FxExtraNeed.due_date >= today_kst()`). 발동 문구에 항목 이름: `"도쿄 여행 환전 구간 $500(약 70만원)"`, 메일 `send_exchange_rate_alert`에 `plan_label` 인자 추가. 푸시 type·링크는 기존 `FX_PLAN`/`#fx-plan` 그대로.
- `action_items_service.py` FX_PLAN 행: 발동 알림에 `fx_need_id`가 있으면 제목에 항목 이름(한 행 유지, 여러 건이면 "외 N건").
- 지난 항목 정리: 별도 잡 없이 — 목록 조회 시 `PAST_DUE`로 표시하고 사용자가 삭제(알림은 CASCADE). 발송은 위 필터로 막힌다.

### 프론트엔드
- `api/invest.ts`: 타입 `FxExtraNeed`·`FxExtraNeedsData` + CRUD·`syncFxExtraNeedAlerts`. `QUERY_KEYS.fxExtraNeeds`.
- `utils/queryInvalidation.ts`: `invalidateFxExtraNeedData(qc)` — fxExtraNeeds + 환율 알림 + 대시보드 action-items. 알림 sync 후엔 이것만 호출.
- 새 컴포넌트 `components/invest/FxExtraNeedsSection.tsx` — `FxPlanCard` 맨 아래(상태 분기 **밖**, `NO_PORTFOLIO`여도 보이게) 구분선 + 소제목 "추가 환전 (여행 등)":
  - 항목 행: 이름 · 필요일(D-N) · `exchanged/amount` 진행 바(`clampPct`) · 남은 금액의 구간 목록(기존 카드의 구간 행 마크업을 `FxTrancheList`로 추출해 공유) · "목표 환율 알림 등록/바꾸기" 버튼(기존 `planAlertState`를 scope 인자 받게 일반화해 `fx_need_id` 기준으로 재사용) · ⋯ 메뉴(`AccountActionsMenu`: 수정 / 환전 완료 처리 / 삭제 → `ConfirmModal`, "등록한 알림도 함께 삭제됩니다").
  - 빈 상태: "여행처럼 날짜가 정해진 달러가 필요하면 추가하세요" + 추가 버튼.
  - `PAST_DUE`: 회색 + "필요일이 지났습니다 · 삭제" 안내, 알림 버튼 숨김.
- `FxExtraNeedModal.tsx` — `Modal`+`ModalBody`+`ModalFooter`(`<form id>`), 필드: 이름, 금액(USD, `useCurrencyInput`), 필요일(`localToday()` 최소값), 이미 환전한 금액. Zod `src/schemas/fxExtraNeed.ts`.
- `isFxPlanAlert` 사용처(`ExchangeRateAlertSection`, 알림 이력)에서 항목 알림은 "추가 환전: {이름}" 라벨 — 알림 응답 스키마에 `fx_need_id`, `fx_need_name` 추가.
- 섹션은 무겁지 않으므로 lazy 분리 불필요(모달만 `React.lazy`).

### 문서
- `docs/plans/123-fx-extra-needs-2026-11-11.md`(이 계획 자기완결본) + `docs/plans/README.md` 인덱스 행.
- `backend/CLAUDE.md` `fx_plan_service` 줄·invest 라우터 줄, `frontend/CLAUDE.md` `invest/FxPlanCard` 줄·무효화 표에 한 줄씩(함정만: 증권 달러로 상쇄 안 함, 알림 CASCADE, 지난 항목 알림 발송 필터).

## 작업 순서(배치)
- **A 백엔드 모델·CRUD·구간**: 모델·마이그레이션·스키마·서비스·라우터·테스트(`tests/test_fx_plan_service.py`에 구간 규칙 — 14일 이하 전액 지금, DONE/PAST_DUE, NO_RATE; 새 `tests/test_fx_extra_needs_api.py`에 CRUD·소유권 404·상한·검증).
- **B 알림 연결**: `sync_fx_plan_alerts` scope 일반화 + 상호 불간섭 테스트, 발송 필터·문구(`test_exchange_rate_alert_service.py`), action-items 제목(`test_action_items_service.py`), 알림 스키마 필드.
- **C 프론트**: API·키·무효화·섹션·모달·Zod·알림 라벨 + 테스트(`components.fxPlanCard.test.tsx` 확장 또는 `components.fxExtraNeedsSection.test.tsx`: 빈 상태·추가·D-N·지난 항목·알림 버튼 상태).
- **D 문서**.

## 검증
```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app/ && uv run pytest --cov=app   # 91% 게이트
cd frontend && npm run lint -- --max-warnings 0 && npm run format:check && npm run typecheck && npm run test
```
- 로컬 DB `uv run alembic upgrade head` → `downgrade -1` → `upgrade head` 왕복.
- `bash dev.sh`로 계획 › 적립 계획 › 달러 환전 계획: 항목 추가(D-30, $1,000) → 구간 3개·알림 등록 → 설정 › 환율 알림에 "추가 환전" 라벨 확인 → 항목 삭제 시 알림도 사라짐 → 해외 포트폴리오 없는 계정에서도 섹션 표시. 모바일 폭(375px)에서 모달 저장 버튼이 키보드에 안 가리는지.
- 배포 전 운영 DB에 `fx2` 수동 적용.

## 결과 (2026-11-11)

배치 A~D를 구현했다(브랜치 `feat/fx-extra-needs`).

- 계획과 다르게 한 점
  - 서비스를 `fx_plan_service.py`에 넣지 않고 `fx_extra_need_service.py`로 분리했다. 환율·위치 조회는 `fx_plan_service.load_fx_rate_context`로 묶어 두 서비스가 함께 쓴다.
  - 계획 알림 비교 로직(`planAlertState`·`syncToastMessage`·버튼 문구)을 `FxPlanCard`에서 `utils/fxPlanAlerts.ts`로 옮겼다. 범위 인자(`portfolioId`/`fxNeedId`)를 받는다.
  - 금액 입력은 `useCurrencyInput` 대신 `inputMode="decimal"` 입력을 쓴다(USD 소수점, 쉼표 허용).
- 함정
  - 항목 알림은 `portfolio_id`가 null이다. 포트폴리오 범위 비교에 `fx_need_id is None`을 함께 넣지 않으면, 해외 포트폴리오가 없는 상태(`portfolio_id=null`)에서 항목 알림을 적립 계획 알림으로 잘못 센다.
  - 알림 발송 행이 5칸(`…, FxExtraNeed.name`)이 됐다. 환율 알림 잡을 모킹하는 테스트는 5칸 튜플을 줘야 한다.
- 남은 것
  - 운영 DB에 `fx2_fx_extra_needs`를 수동 적용(배포 전)
  - 실기기·브라우저 화면 확인
