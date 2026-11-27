# 154. 기술부채 — 153 첫 감사 (2026-11-27)

상태: 배치 A·B·C 구현. 마이그레이션 없음.

## Context
- 153(PR #327)은 감사 없이 main에 머지됐다 → 이번이 첫 감사.
- 시작 시점: main clean, 열린 PR 없음. ruff·ruff format·mypy·tsc 통과, `npm audit --omit=dev` 0건, backend TODO 0건. `npm outdated`는 패치·마이너(Dependabot 범위)와 이미 "의도적으로 남긴" React 19·TS 7·plugin-react 6 메이저뿐.

## 배치 A — 낙폭 추매 리셋 간격 (153 A1 보강)

**A1 첫 구간이 3% 이하면 기준선 근처 작은 반등에도 기록이 지워짐 (실버그)**
- 153 이후 리셋 조건은 `낙폭 > −3` 그리고 첫 구간 미도달(`낙폭 > −첫 구간`). 첫 구간이 3% 이하면 리셋 기준과 도달 기준이 같은 값이라 간격이 없다.
- 예: 첫 구간 2%, QQQ 종가 낙폭 −2.1%(도달, "추매했어요") → 다음 날 −1.9%(리셋: 완료·알림 기록과 `cycle_base_krw` 삭제) → 그다음 날 −2.1%(다시 DUE, ON_REACH 재알림, 이미 쓴 여윳돈으로 다시 매수 권유). 첫 구간이 정확히 3%면 147부터 같은 문제가 있었다.
- 수정: `dip_buy_calculator.reset_threshold_pct(tiers)` = `min(RESET_DRAWDOWN_PCT, 첫 구간 / 2)`. `should_reset`은 `낙폭 > −reset_threshold_pct(tiers)`일 때만 리셋한다. 첫 구간이 6% 이상이면 동작은 그대로다. 취소 알림 판정 `recovered_above_tiers`("첫 구간 위로 회복")는 그대로 둔다.

**A2 카드 문구가 실제 리셋 기준과 다름**
- `DipBuyCard`의 "고점 대비 −N% 이내로 회복하면…"은 전역 `reset_drawdown_pct`(3)를 썼다. 그래서 첫 구간이 얕은 규칙에서는 틀린 안내였다.
- 수정: 규칙 응답(`DipBuyRuleStatus`)에 규칙별 `reset_drawdown_pct`를 넣고, 카드는 `rule.reset_drawdown_pct ?? 전역 값`을 쓴다. 전역 필드는 호환용으로 유지한다. 필드가 optional 추가라 persist buster는 올리지 않았다.

## 배치 B — 153 이관 P3-G
- `tests/test_real_db_upserts.py::test_dip_buy_mark_completed_serializes_double_submit`: 두 세션이 동시에 `mark_completed`를 호출하면 하나는 성공하고 하나는 `BadRequestError`가 된다. 여윳돈은 한 번(1천만 → 8백만)만 빠지고, `completed`에는 한 건만 남는다.
- 두 커넥션이 실제로 commit해야 해서 롤백 픽스처 `pg` 대신 직접 만들고, 사용자를 삭제해 CASCADE로 지운다. 로컬(Docker 없음)은 skip, CI 서비스 컨테이너에서 돈다.

## 배치 C — 문서
- `backend/CLAUDE.md` 낙폭 추매 리셋 기준 문구, `docs/remaining-tasks.md` P3-G 완료, README 154 행.

## 확인했으나 문제없음 (재감사 때 다시 올리지 않기)
- `_tier_index_map`: `validate_tiers`가 낙폭 고유·오름차순을 강제하고 `_clean_tiers`는 반올림하지 않아 키 충돌·불일치가 없다.
- `resolve_misses`는 성공해도 의심 표식을 지우지 않는다. 하지만 성공 종목은 현재가 캐시(15분)·수익률 캐시가 의심 TTL(15분) 이상 유지하고, 현재가 캐시를 무효화하는 경로도 없어 창 안에서 다시 조회되지 않는다.
- `cache.set(..., ex=)`는 `CacheStore.set`이 지원하고, 서킷 `is_available()`은 프로브 슬롯을 쓰지 않는다.

## 검증
- backend: ruff·ruff format·mypy 통과, `pytest --cov` 4299 passed·10 skipped(실 DB, 로컬)·93.86%(게이트 91%).
- frontend(`D:\project\growlio\frontend`): eslint·prettier·tsc(앱+테스트) 통과, vitest 215 files / 2302 passed.
- 신규 테스트: `reset_threshold_pct` 경계, 얕은 첫 구간(2%·3%) 리셋 간격, `summarize_user` −2.5/−1.9에서 기록 유지, 라우트 규칙별 `reset_drawdown_pct`, 카드 규칙별 문구, 실 DB 이중 제출.
