# 26. 기술부채 정리 (2026-08-13)

## 배경

2026-08-13, "기술 부채 있는지 검토해서 수정 계획 세워달라"는 요청으로 마지막 감사
(`docs/plans/24-technical-debt-2026-07-29.md`, 2026-07-29) 이후 2주간의 변경분에 초점을 맞춰
재조사했다. 대부분의 죽은 코드·중복·구조적 문제는 이전 25라운드에서 이미 정리된 상태라 전면
재조사 대신 direct 조사(라인수 재측정, `pip-audit`/`npm audit` 재실행, 신규 파일 diff)로 신규
발생분만 추렸다.

## 발견 및 구현 (전부 같은 세션에 완료)

### 1. `sharp` devDependency 신규 취약점 패치
2026-08-13 아이콘 리디자인 세션(`^0.34.2` 추가)에서 이후 libvips 취약점(high severity,
CVE-2026-33327 등)이 보고됨 — `docs/plans/25` 보안 감사 이후 처음 발견되는 신규 항목.
`^0.35.3`로 상향(`frontend/package.json`), `npm run generate:icons`로 빌드 스크립트 정상 동작
확인(재생성된 PNG는 바이트 크기 동일해 실질 변경 없음 — 커밋 대상에서 제외). `npm audit`
9건→3건(react-router-dom만 잔존, 아래 "재확인 후 유지" 참고).

### 2. `goal_recommendation_service.py` 재분리 (1622→1332줄)
2026-07-20에 1113→720줄로 분리됐던 것이 이후 기능 추가(연령대별 추천·배당목표 후보제안 등,
커밋 `a67812c`/`6d45305`/`bc5bd06`)로 다시 최대 파일이 됨. 연령대별 추천 블록
(`age_group_from_birth_year`/`_AGE_GROUP_PROFILE`/`get_age_based_recommendation`/
`_compute_age_based_recommendation`)을 신규 `goal_age_recommendation_service.py`(346줄)로
순수 extract-move — 공유 헬퍼(`_fetch_dividend_yields`/`_suggest_for_dividend_goal`/
`_fetch_market_signal_level`/`_equity_class_bounds`/`_cash_equivalent_daily_returns` 등)는
여전히 `goal_recommendation_service.py`에 남아 새 모듈이 import(역방향 의존 없음). 호출부
(`rebalancing.py`/`settings.py`)는 새 모듈에서 직접 import하도록 갱신, 재export shim 없음.

**배당 후보제안 블록은 계획과 달리 분리하지 않음** — `_suggest_for_dividend_goal()`이 전체/기간별/
연령대별 3개 경로 전부가 공유하는 cross-cutting 헬퍼임을 코드 확인 후 파악, 특정 모듈로 옮겨도
결합도가 줄지 않아 `goal_recommendation_service.py`에 유지하기로 판단 변경.

**테스트 수정 시 발견한 버그 패턴**: `tests/test_goal_recommendation.py`의 autouse fixture
`_mock_dividend_yields`가 `app.services.goal_recommendation_service._fetch_dividend_yields`
경로만 patch하고 있었는데, 새 모듈이 이 심볼을 import해 자기 네임스페이스에 별도로 바인딩하므로
patch가 새 모듈 호출 경로에는 적용되지 않아 age 관련 테스트 3개가 실제 Naver/Yahoo API를
호출하며 실패했다 — fixture와 개별 테스트의 patch를 양쪽 모듈 경로 모두로 확장해 해결. **서브모듈
분리 시 일반화 가능한 교훈**: 이동한 함수가 호출하는 이름을 원본 모듈에서 그대로 import해오면,
그 이름을 patch하는 기존 테스트는 원본 모듈 경로만으로는 더 이상 충분하지 않다 — 이동 후에는
호출부가 실제로 위치한 모듈 경로로 patch 대상을 갱신해야 한다(mock의 근본 원리: patch 대상은
정의 위치가 아니라 룩업이 일어나는 네임스페이스).

### 3. `email_templates.py` → `email_templates/` 패키지 분리 (847줄)
`docs/plans/24` 3번에서 "다음 세션 우선순위"로 이관됐던 항목. 알림 종류별로 분리:
`_shared.py`(`_kv_table`/`_email_div`/`_SIGNAL_LEVEL_LABEL`/`_SIGNAL_LEVEL_COLOR` 공용),
`alerts.py`(환율/주가 단순 알림 3종), `rebalancing.py`(드리프트·자동실행·AUTO 플랜 대기/보류
게이트 — 가장 큰 그룹, 세금영향·시장신호·일일한도 게이트 알림 포함), `market_signal.py`(등급전환·
매일요약), `reports.py`(월간리포트·목표달성·연말절세·추천비중변화·회원탈퇴). `__init__.py`가
17개 공개 템플릿 함수 전체를 재노출해 `email_service.py`/`tests/test_email_templates.py`의
`from app.services.email_templates import X` 호출부는 변경 없이 그대로 동작.

### 4. 저장소 위생
루트에 미추적 `.coverage` 파일(`.gitignore`가 `backend/.coverage`만 커버해 누락) 삭제 +
`.gitignore`에 경로 무관 `.coverage`/`.coverage.*` 패턴 추가(기존 `backend/.coverage*` 패턴은
중복이라 제거).

## 재확인 후 그대로 유지 (조치 없음, 근거만 재확인)

- **`plan_service.py`(999줄)/`market_signal_service.py`(835줄)/`hooks/rebalancingExecution/index.ts`(528줄)** — 전부 실거래·AUTO 게이트 경로. `docs/plans/24` 1·2번 사유 그대로 유효, 이번에도 미착수.
- **`portfolio_optimizer.py:170`의 `noqa: C901`** — 기록만 유지.
- **프론트 500줄대 워치리스트 6개** — 07-29 이후 크기 변화 없음(재측정 확인). 조치 불필요.
- **`react-router-dom` v6→v7, 프론트 localStorage 토큰 평문 저장** — `docs/plans/25`에서 이미 브레이킹/아키텍처 변경 사유로 이관, 상황 변화 없음.
- **백엔드 `pip-audit`(pillow/starlette/pyasn1 등)** — 전부 `pyproject.toml`에 직접 핀 없는 전이 의존성. `docs/plans/24`의 "Dependabot 주간 PR로 점진 해소" 결정 유지 — npm 쪽이 9건→3건으로 실제 감소해 같은 전략이 유효함을 재확인.
- **Kiwoom 해외주식 API-ID 실계좌 검증** — 여전히 실계좌 필요, 사용자 트리거 대기.

## 검증

백엔드 2043 tests 88.04%, ruff/mypy 클린. 프론트 1447 tests, `npm run build`(tsc 포함)/eslint 클린.
