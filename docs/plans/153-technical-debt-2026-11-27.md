# 153. 기술부채 — 152 첫 감사 + 잔여 정리 (2026-11-27)

상태: 배치 A·B·C 구현(B3는 의도된 차이로 주석만, C의 `mark_completed` 실 DB 동시성 테스트는 이관).

## Context
- 152(#324→#325→#326)는 main에 머지됨. `fix/152-batch-c`의 문서 커밋(A10 종결)만 main에 없어 이번 브랜치에 cherry-pick.
- 시작 시점 상태: ruff·ruff format·mypy·tsc(앱+테스트)·eslint 통과, pip-audit·npm audit 0건, TODO 0건, 열린 PR 없음. npm outdated는 패치/마이너뿐(Dependabot 범위). React 19·TS 7·plugin-react 6 메이저는 "의도적으로 남긴 것" 유지.
- 범위: 152 신규 코드(diff 3개) 첫 감사, 150 남은 D·E4(사용자 결정 2026-11-27: 포함), `docs/remaining-tasks.md` 동기화(11-20 기준이라 143~152 누락).

## 배치 A — 낙폭 추매

**A1 첫 구간이 3% 미만이면 매일 같은 알림 반복 (152 A1 회귀)**
- `validate_tiers`는 낙폭 1%부터 허용하는데 리셋 조건은 `drawdown_pct > -3`만 봤다. 첫 구간 2%·QQQ −2.5%면 08:10 job이 알림 → 다음 조회가 리셋 → 다음 날 또 알림. `completed`도 같아 "추매했어요"가 다음 조회 때 지워져 다시 매수를 권했다(152 이전부터).
- 수정: `should_reset(..., tiers)` — −3% 이내 **그리고** 첫 구간에 닿지 않을 때만 리셋. 검증 범위는 그대로(기존 저장값과 충돌 방지).

**A2 구간 추가·삭제 시 안 바뀐 구간의 기록까지 지워짐**
- 순번 비교(`_unchanged_tier_indexes`)라 [10,20,30]→[5,10,20]이면 산 10% 구간이 다시 DUE, `cycle_spent` 0 → 이미 쓴 여윳돈으로 다시 사라고 권함.
- 수정: `_tier_index_map` — 낙폭 값으로 짝지어 `completed`·`notified_tiers`의 순번을 새 위치로 옮기고, 짝 없는 구간 기록만 버린다.

## 배치 B — 시세 미스 표식 (151 A2 / 152 B1 후속)

**B1 혼자 조회된 상장폐지 종목은 미스로 기록되지 않음** — "같은 묶음의 다른 종목 성공" 규칙이라 단일 종목 호출, 다른 종목이 15분 현재가 캐시로 빠진 경우(흔함)엔 공개 소스 체인을 요청마다 다시 돌았다.

**B2 일부 성공해도 조회 중 서킷이 열려 실패한 종목은 10분 미스로 기록될 수 있음.**

수정(`resolve_misses`·`classify_misses`):
- 조회 뒤 그 묶음의 소스 서킷(국내 Naver+Yahoo, 해외 Yahoo, 기간 수익률은 Yahoo)이 열려 있으면 기록하지 않는다.
- 묶음에 성공 종목이 있으면 바로 기록(기존).
- 묶음 전체 실패면 의심 표식(`price_miss_suspect_key`, 15분 — 성공 종목은 현재가 캐시로 그동안 재조회되지 않는 길이)만 남기고, 그 안에 또 실패하면 기록.
- Yahoo는 빈 응답과 오류를 구분하지 않아(`_run_guarded`) "묶음 크기 1이면 기록"은 일시 장애 한 번을 10분 공백으로 만든다 — 그래서 두 번 연속 실패로 판정.

**B3 내비 배지 폴백 개수** — `_rebalance_items`의 `skip_portfolio_ids`는 전술 행이 뜬 포트폴리오(홈 목록 중복 방지)라 의도된 제외. `useNavBadges`에 주석만.

## 배치 C — 문서·잔여

- 150 D: 홈 "데이터 갱신" → "새로고침", 자산 "전체 갱신" → "증권사에서 전체 갱신"(모바일 짧은 라벨 "갱신" 유지, 설정 "계좌 데이터 갱신"은 의미가 분명해 유지).
- 150 E4: `MonthlyOptimizationCard`를 `components/portfolio/` → `components/invest/`로 이동(동작 변경 없음).
- `docs/remaining-tasks.md` 2026-11-27 기준 갱신.

## 이관
- `mark_completed` 두 요청 직렬화 실 DB 테스트: 두 커넥션이 실제 commit해야 해서 기존 `pg` 픽스처(바깥 트랜잭션 롤백)로는 못 쓴다. 정리 로직이 있는 별도 픽스처가 필요하고 로컬 Docker가 없어 검증 불가 → 다음 감사.
- 151 배치 C·D: 운영 기준선 실측 후.

## 검증
- backend: ruff·ruff format·mypy 통과, `pytest --cov` 4293 passed·93.86%(게이트 91%).
- frontend(`D:\project\growlio\frontend`): eslint·prettier·tsc 통과, vitest 215 files / 2301 passed.
- 신규 테스트: 얕은 첫 구간 리셋(계산·summarize_user), 구간 삽입·가운데 삭제 기록 이동, 미스 분류(묶음·서킷 열림), 단일 종목 두 번째 실패 기록, 서킷 열림 시 무기록, 기간 수익률 두 번째 실패 기록.
- 마이그레이션 없음.
