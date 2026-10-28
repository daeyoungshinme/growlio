# 87. 기술부채 재점검 (2026-10-28e, 계획 86 직후)

> 상태: **A·B·C 완료**. D(머지된 브랜치 삭제)는 사용자가 직접 실행한다.

## Context

계획 86(PR #173) 머지 직후 재점검이다. 정적 검사·취약점·Dependabot은 이번에도 깨끗했다. 남은 부채는 **테스트 인프라**에 있었다.

| 점검 | 결과 |
|---|---|
| ruff check/format, mypy(263), tsc, `eslint . --max-warnings 0` | 0건 |
| npm audit --omit=dev | 0건 |
| uv Dependabot 로그(머지 후 첫 실행) | `No update possible` 0건 → 86 B 효과 확인 |
| npm Dependabot 로그 | `@types/react 18.3.28` 1건(18.3.31 존재, cooldown 추정) |
| pytest | 3052 passed, 경고 21건, `--durations` 상위 6개가 약 12s |
| vitest --coverage | 1858 passed, 79.38 / 67.33 / 67.75 / 77.97 — 게이트(66/52/52/64)보다 12~15%p 높음 |

## A. 커버리지 게이트 래칫 (완료)
- 프론트 `vite.config.ts` thresholds는 09-13 실측 기준이었다. 이번 실측에서 약 3%p를 빼 76/64/64/75로 올렸다.
- 백엔드는 80 → 89(실측 91.77)로 올렸다. `Makefile`, `ci.yml`, `pyproject.toml`(`fail_under`), 루트·backend `CLAUDE.md`를 함께 바꿨다.

## B. NumPy generic timedelta 경고 (완료)
- 원인을 정정한다. pandas 2.3 + numpy 2.5에서는 **`pd.Timedelta(days=N)` 키워드 형식 자체가** 경고를 낸다(`pd.Timedelta(N, unit="D")`는 경고 없음). 86이 "pandas 내부"로 분류한 경고 중 10건은 `test_dividend_sync_sources.py`의 헬퍼가 출처였다 → 단위를 명시하도록 바꿨다. 앱 코드에는 `Timedelta(` 사용처가 없다.
- 나머지 10건은 `etf_overlap_service.py`의 `resample("W-FRI")`가 pandas 내부(`resample.py`의 `Timedelta(days=1, ...)`)를 거치면서 난다. 앱 코드 경로이므로, numpy가 이 경고를 오류로 바꾸면 ETF 중복 점검이 깨진다. 그런 릴리스는 Dependabot PR의 CI가 잡는다. 근본 해소는 pandas 3에서 이뤄진다.

## C. 테스트 실대기·네트워크 호출 제거 (완료)
- `tests/conftest.py`: `NAVER_RETRY`의 `wait`을 `wait_none()`으로 바꾸는 autouse fixture를 추가했다. `@retry(**NAVER_RETRY)`는 호출마다 데코레이트되므로 함수가 아니라 dict를 패치한다. stop과 retry 설정은 그대로라 재시도 검증은 유지된다.
- `test_kis_client.py` 일시 오류 재시도의 1초 대기, `test_yahoo_price.py` 예외 경로의 `time.sleep`을 패치했다.
- **`test_price_service.py`의 `patch("asyncio.get_event_loop")`는 무효였다.** 코드는 `get_running_loop`를 쓴다. 그래서 `all_providers_fail` 테스트가 실제 yfinance로 `UNKNOWN`을 조회하고 있었다(3s, 오프라인이면 결과가 달라질 수 있음). 죽은 패치를 지우고 `_sync_yahoo_price`를 직접 막았다.
- 결과: 1s 이상 걸리는 테스트가 사라졌다(상위 항목은 커버리지 오버헤드 포함 약 1s). 경고는 21건에서 13건으로 줄었다(resample 10, FCM 1, yfinance sqlite ResourceWarning 2).

## D. 저장소 위생 (사용자 실행)
`git branch -d chore/tech-debt-2026-10-28d && git push origin --delete chore/tech-debt-2026-10-28c chore/tech-debt-2026-10-28d` — #172, #173으로 머지됨.

## 이관
86 이관 표(untracked_holdings / pandas 3 / React 19 등 메이저 / FCM `fid` / 65 B4·66 P3 실측)는 변동 없다.
- **관찰**: 다음 주 npm Dependabot 로그에서 `@types/react`의 `No update possible`이 계속되면, `react-types` 그룹과 major ignore 사이의 상호작용을 조사한다.

## 검증
- `pytest --cov=app --cov-fail-under=89` → 3052 passed, 91.77%, 경고 13건
- `vitest run --coverage` → 1858 passed, 새 thresholds 통과
- ruff·pre-commit 통과
