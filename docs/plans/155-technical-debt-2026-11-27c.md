# 155. 기술부채 — 154 첫 감사 (2026-11-27)

상태: 완료(코드 변경 없음). 마이그레이션 없음. Dependabot alerts 켜기는 사용자 조치.

## Context
- 154(PR #328)는 감사 없이 main에 머지됐다 → 이번이 첫 감사. 147~153은 152·153·154에서 차례로 감사했다.
- 시작 시점: main clean, 열린 PR 없음, main CI(#328 머지) success.

## 결과 — 코드 부채 0건

**운영 확인 1건 해소 (remaining-tasks P1 운영, 109)**
- `gh api repos/.../dependabot/alerts` → "Dependabot alerts are disabled for this repository"(403). 확인 결과 꺼져 있으므로 켠다.
- 조치(사용자): 저장소 Settings → Code security → Dependabot alerts **Enable**. 확인: `gh api repos/<owner>/growlio/dependabot/alerts --jq 'length'`가 숫자를 반환하면 된다. 첫 알림 목록은 다음 감사 때 본다.

**154 B 확인**
- PR #328 CI backend 잡에서 `test_dip_buy_mark_completed_serializes_double_submit`이 PASSED였다(skip 아님). 4309 passed.

## 확인했으나 문제없음 (재감사 때 다시 올리지 않기)
- `reset_threshold_pct`의 `tiers[0]`: `validate_tiers`가 낙폭 1~60·오름차순을 강제하므로 tiers[0]이 가장 얕은 구간이고, 기준은 0.5% 이상이다. 첫 구간이 6% 이상이면 기준은 그대로 3%다.
- 낙폭이 −첫 구간과 −리셋 기준 사이에 있을 때: `recovered_above_tiers`가 참이라 MONTHLY 취소 안내는 나갈 수 있고, 리셋은 아직 일어나지 않는다. ON_REACH는 `notified_tiers`가 남아 있어 재알림이 없다. 의도한 히스테리시스다.
- 카드 문구는 규칙별 `reset_drawdown_pct ?? 전역 값`을 쓰고, 이메일 템플릿에는 3%가 하드코딩되어 있지 않다.
- 전역 `DipBuyStatusResponse.reset_drawdown_pct`는 이제 폴백으로만 쓰인다. 하지만 persist 캐시의 옛 응답과 호환해야 해서 유지한다 → remaining-tasks "의도적으로 남긴 것".
- 정적 점검: ruff·ruff format·mypy 통과, backend TODO 0건, `npm audit --omit=dev` 0건. `npm outdated`에는 패치·마이너(Dependabot 범위)와 이미 남기기로 한 React 19·TS 7·plugin-react 6 메이저만 있다.
