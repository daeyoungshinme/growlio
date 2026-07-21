# 계획 15: 3차 재감사 — 페르소나 기반(신규 사용자 / 파워유저) 독립 조사 (2026-07-21)

## 배경 (Why)

2026-07-20까지 같은 취지("불필요 기능 제거·병합 + 탭 UX 개선 + 고도화 로드맵")의 전체 감사가 이미 두 차례 수행되어 `docs/plans/01~14`가 대부분 완료 처리됐다(README 상태표 참고). 2026-07-21, 사용자가 동일 요청을 세 번째로 해, 이번엔 "코드 존재 여부"나 "요구사항 완결성" 축이 아니라 **구체적 사용자 페르소나의 실제 여정**으로 완전히 새 관점을 잡았다. 서브에이전트 2개(신규 사용자 온보딩 / 파워유저 장기운용)를 과거 산출물(`docs/plans/`, 메모리) 미참조 지시로 병렬 투입했다.

## A. 신규 사용자 온보딩 여정 감사

| # | 발견 | 근거 | 영향도 |
|---|---|---|---|
| A1 | 진단 탭 첫 방문 시(포트폴리오 0개) `DiagnosisSummaryHeader`가 "지금은 조치가 필요하지 않습니다"라는 **오해성 안전 메시지**를 내보내고, `RebalancingStatusCard`는 `null` 렌더로 사라져 "포트폴리오 만들기" CTA가 아예 없음 | `RebalancingPage.tsx:167-211`, `DiagnosisSummaryHeader.tsx:66-70`, `RebalancingStatusCard.tsx:230` | 높음 |
| A2 | `RecommendationCard`의 목표 미설정 안내가 텍스트만 있고 `/invest-plan` 딥링크 없음 (동일 파일군의 `SetupTargetPortfolioBanner`/`RebalancingAlertSummaryCard`는 딥링크 패턴을 이미 정확히 구현) | `RecommendationCard.tsx:303-307` vs `SetupTargetPortfolioBanner.tsx:40-45` | 높음 |
| A3 | 온보딩 체크리스트 2단계("포트폴리오 구성")가 `<span>`이라 클릭 불가, 계좌 1개 등록 즉시 체크리스트 전체가 사라져 정작 필요한 시점에 안내가 없음 | `DashboardPage.tsx:54-65, 134` | 중간 |
| A4 | 계좌관리 딥링크(`/assets?tab=계좌관리`) 클릭해도 기본 서브탭이 "은행계좌"라 핵심 동작(증권사 계좌 등록)까지 탭 1번 더 필요 | `AssetManagementPage.tsx:38`, `constants/tabs.ts:1` | 중간 |
| A5 | 첫 증권계좌 등록 모달에 최대 13개 필드(투자기간·세제유형 등 아직 안 써본 기능 설명 포함)가 한 화면에 노출 | `StockAccountModal.tsx:296-304` | 중간 |
| A6 | 계좌 등록 직후 대시보드 카드 5개(세제 현황·자산추이 포함)가 한번에 전면 노출 — 목표 미설정 신규 사용자에게 과부하 | `DashboardPage.tsx:149-203` | 낮음~중간 |
| A7 | 첫 포트폴리오 편집기에 "투자기간·세제유형(목표 역산 추천 매칭용)" 셀렉트가 기본(비접힘) 노출 | `UnifiedPortfolioEditor.tsx:189-224` | 낮음 |

## B. 파워유저 장기운용 여정 감사

| # | 발견 | 근거 | 영향도 |
|---|---|---|---|
| B1 | 월간 리포트(`monthly_report_enabled`, 기본 True)를 끄는 프론트 토글이 어디에도 없음 — 사실상 옵트아웃 불가 | `models/user.py:59`, `jobs/monthly_report.py:51`, 프론트 검색 0건 | 중간 |
| B2 | 발송이력 라벨 매핑에 `MONTHLY_REPORT` 누락 — 이력 탭에 원문 문자열로 노출 | `SettingsPage.tsx:79-88` vs `jobs/monthly_report.py:92` | 낮음 |
| B3 | AUTO가 시장신호 게이트로 `NOTIFY`로 조용히 강등될 때, 발송 이메일/이력에 "원래 AUTO였는데 이번엔 건너뛰었다"는 사유가 전달되지 않음(서버 로그에만 남음) — 세금 게이트는 동시 세션이 `notify_tax_gate_blocked`로 이미 같은 패턴을 처리 중이라 확장 여지 확인 | `alert_check.py:140-150`, `email_service.py:82-94` | 중간 |
| B4 | 시장신호 등급전환 알림이 "활성 리밸런싱 알림 보유"를 구독 조건으로 재사용 — 수동 리밸런싱만 쓰는 유저는 토글을 켜도 알림을 못 받음(경고 배너로 안내는 됨) | `market_signal_alert_service.py:40-53`, `MarketSignalAlertSection.tsx:56-66` | 낮음 |
| B5 | 절세 여력(손실수확 추천)이 자산탭 → 세금 서브탭 → 접이식 펼치기까지 3클릭 뒤에 숨어있음 | `TaxOptimizationCard.tsx:16,29` | 낮음 |

**확인 결과 문제 없음(참고용)**: `RebalancingStatusCard` 대시보드/진단탭 중복 렌더는 요약/드릴다운 의도된 설계, 알림 설정 분산(설정탭 요약 vs 리밸런싱탭 편집)도 의도 명시됨, AUTO 실행 이력의 성공/실패/스킵 투명성 양호, `tax_type`/`investment_horizon`은 매도 우선순위·추천 그룹핑에 실제로 반영되어 계좌 특성이 뭉뚱그려지지 않음.

**동시 세션 관찰**: 조사 시점 `rebalancing_auto_execution.py`/`plan_service.py`/`rebalancing_execution.py`가 미커밋 상태로 수정 중이었고, 세금영향 게이트(`TaxGateBlocked`)가 실행 경로에서 언패킹 오류를 일으키는 버그를 다른 세션이 바로 고치는 중이었음(`notify_tax_gate_blocked` 추가). 이 문서가 다루는 파일들과 직접 겹치지 않아 충돌 없음 — 별도 조치 불요.

## 권장 우선순위

| 순위 | 항목 | 영향도 | 난이도 |
|---|---|---|---|
| 1 | A1 — 진단탭 0포트폴리오 시 CTA 추가(오해성 메시지 제거) | 높음 | 낮음 |
| 2 | A2 — 추천카드 목표설정 딥링크 추가 | 높음 | 낮음 |
| 3 | A4 — 계좌관리 딥링크 기본 서브탭을 증권계좌로 | 중간 | 낮음 |
| 4 | A3 — 온보딩 체크리스트 2단계 링크화 + 계좌 등록 후에도 목표/포트폴리오 미완료 시 유지 | 중간 | 낮음 |
| 5 | B1 — 월간 리포트 옵트아웃 토글 추가 | 중간 | 낮음 |
| 6 | B2 — MONTHLY_REPORT 라벨 매핑 추가 | 낮음 | 낮음(1줄) |
| 7 | B3 — 시장신호 게이트 강등 사유 사용자 노출 | 중간 | 중간 |
| 8 | A5 — 계좌 등록 모달 필드 단계 분리/고급설정 접힘 | 중간 | 중간 |
| 9 | A7 — 포트폴리오 편집기 투자기간/세제유형 고급설정 접힘 | 낮음 | 낮음 |
| 10 | A6 — 신규 사용자 대시보드 카드 단계적 노출 | 낮음 | 중간 |
| 11 | B4 — 시장신호 알림 구독 선결조건 완화 | 낮음 | 중간 |
| 12 | B5 — 세금탭 손실수확 추천 노출 단계 단축 | 낮음 | 낮음 |

1~4번은 전부 딥링크/CTA 추가 수준(신규 컴포넌트 불필요)이라 한 세션에서 같이 처리 가능. 5~6번은 설정 페이지 기존 토글 옆에 1개 추가하는 수준. 7번부터는 게이트 로직을 만지므로 동시 세션이 진행 중인 세금 게이트 수정이 먼저 커밋된 뒤 착수 권장.

## 구현 결과 (2026-07-21, 1~4번 완료)

- **A1**: `DiagnosisSummaryHeader`에 `portfolioCount`/`onCreatePortfolio` prop 추가 — 0개면 "지금은 조치 불필요" 문구 대신 "아직 등록된 포트폴리오가 없습니다" 안내 + "포트폴리오 만들기 →" CTA로 대체. `RebalancingPage.tsx`가 `["portfolios"]` 쿼리(진단탭에서만 enabled, 다른 컴포넌트와 캐시 공유)를 발화해 개수를 넘기고, CTA 클릭 시 `handleTabChange("포트폴리오")` 호출.
- **A2**: `RecommendationCard.tsx`의 목표 미설정 안내 텍스트 옆에 `/invest-plan`으로 가는 "목표 설정하러 가기 →" 링크 추가. 테스트 파일이 Router 컨텍스트 없이 렌더링하던 문제를 로컬 `renderWithProviders` 래퍼(`MemoryRouter` 감싸기)로 수정 — 기존 30여 개 호출부는 변경 없이 그대로 유효.
- **A4**: `AssetManagementPage.tsx`의 서브탭 상태를 로컬 `useState`에서 URL 쿼리(`atab`, `PortfolioPage`의 `portfolioTab` 패턴과 동일)로 전환. 온보딩 체크리스트의 "등록하기" 링크를 `/assets?tab=계좌관리&atab=증권계좌`로 변경해 클릭 즉시 증권계좌 서브탭으로 착지.
- **A3**: 온보딩 체크리스트 2단계("포트폴리오 구성")의 비활성 `<span>`을 `/rebalancing?rtab=포트폴리오`로 가는 실제 링크로 교체. 단, 조사 중 "계좌 등록 즉시 체크리스트 전체가 사라져 안내가 끊긴다"는 우려는 재확인 결과 이미 완화되어 있었음 — 계좌 등록 후 전체 대시보드에서는 `SetupTargetPortfolioBanner`(포트폴리오 0개 시 노출)와 `InvestmentGoalCard`의 "목표 설정" CTA(목표 미설정 시 노출)가 각각 2·3단계의 후속 안내를 이미 담당하고 있어 별도 조치 불필요로 결론.

검증: 프론트 `npm run typecheck`/`eslint` 클린, 관련 테스트 스위트(rebalancing/dashboard/recommendationCard/pages 등 8개 파일 147개 + recommendationCard 35개 + 기타 60개) 전부 통과.

## 구현 결과 (2026-07-21, 7번 완료)

동시 세션의 세금영향 게이트 작업(`TaxGateBlocked`/`notify_tax_gate_blocked` 패턴, `plan_service.py`/`email_service.py`/`email_templates.py`/`cache_keys.py`)이 아직 커밋 전이지만 워킹트리에 완성된 형태로 존재함을 확인 — 이를 그대로 본떠 시장신호 게이트에도 대칭 적용했다.

- **핵심(구 완전 침묵 경로)**: `jobs/rebalancing_auto_execution.py`의 5분 간격 AUTO 플랜 생성 job이 `is_market_signal_blocking_auto_mode()`에 걸리면 로그만 남기고 `continue`하던 것을, `plan_service.py`에 신설한 `MarketSignalGateBlocked` sentinel + `notify_market_signal_gate_blocked()`(세금 게이트와 동일 구조 — 전용 이메일/푸시/AlertHistory 저장, 알림당 1일 1회 dedup)를 호출하도록 배선. 신규 이메일 템플릿 `market_signal_gate_blocked_template()`(`email_templates.py`), 발송 함수 `send_market_signal_gate_blocked_email()`(`email_service.py`), dedup 키 `market_signal_gate_alert_sent_key()`+`TTL_MARKET_SIGNAL_GATE_ALERT_SENT`(`cache_keys.py`) 추가.
- **2차(구 애매한 침묵 경로)**: `rebalancing/alert_check.py`의 10분 간격 드리프트 job은 AUTO→NOTIFY 강등 후에도 이메일 자체는 나가고 있었지만 사유가 없었다 — 별도 이메일을 새로 보내는 대신(5분 job이 이미 전용 이메일을 보내므로 중복 방지), 강등이 감지되면 `automation_note` 문자열(`"시장 위험 신호(RED)로 이번엔 자동 실행 대신 알림만 발송됐습니다."`)을 계산해 `_process_rebalancing_alert` → `send_rebalancing_alert` → `rebalancing_alert_template`까지 관통시켜 이메일 본문에 노란 배너로 노출하고, `save_alert_history` 메시지에도 `", 자동실행→알림 전환(RED)"` 접미사로 남긴다.
- DB 마이그레이션·프론트엔드 변경 없음(기존 `market_condition_mode` 컬럼만 읽고, 알림 이력은 자유 텍스트라 그대로 렌더링됨).

검증: 신규/수정 테스트 포함 백엔드 전체 `uv run pytest` 1782 tests 통과(커버리지 86.66%), `ruff check .`/`mypy app/` 클린. 기존 시장신호 게이트 차단 테스트(`test_rebalancing_auto_execution.py`의 CAUTIOUS/STRICT/STALE/예외 4건)에 `notify_market_signal_gate_blocked` 호출 검증 추가, `test_rebalancing_alert_service.py`에 AUTO→NOTIFY 강등 시 이메일/이력에 사유가 실리는지 검증하는 신규 테스트 1건 추가.
