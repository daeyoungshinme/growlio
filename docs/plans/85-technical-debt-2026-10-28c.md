# 85. 기술부채 재점검 (2026-10-28c, 계획 84 직후)

> 상태: **A·B 완료**. C(로컬 브랜치 2개 삭제)는 사용자가 직접 실행한다.

## Context

계획 84(PR #171)는 코드 수준 부채 0건으로 끝났고, 그 뒤 새 코드는 없다. 이번에는 84 이관표에 빠져 있던 항목을 찾았다. **pyproject 상한에 막혀 있던 백엔드 메이저**다. `.github/dependabot.yml`이 상한과 같은 major를 ignore하기 때문에, 상한을 넓히지 않으면 알림조차 생기지 않아 계속 정체된다. 테스트 경고(`-W default`)도 같이 정리했다.

| 항목 | 결과 |
|---|---|
| ruff check/format, mypy(263파일), tsc, `eslint . --max-warnings 0` | 0건 |
| pip-audit, npm audit --omit=dev | 0건 |
| 84 A 저장소 위생 | 원격 브랜치·worktree는 정리됨. 머지된 로컬 브랜치 2개가 남음 |
| 열린 PR / Dependabot | 0건, lock과 설치본 일치 |
| APK Variables | 여전히 비어 있음 → `untracked_holdings` 이관 유지 |
| pytest `-W default` | 3052 passed, 경고 10건 → 3건(모두 외부 요인) |

## A. 상한에 막힌 백엔드 메이저 (완료)

| 패키지 | 전 → 후 | 상한 | 비고 |
|---|---|---|---|
| firebase-admin | 6.9.0 → 7.7.0 | `<8` | 전이 의존 google-api-python-client·httplib2 등 4개가 빠짐. `Message.token`이 폐기 예고됨(아래 이관) |
| tenacity | 8.5.0 → 9.2.1 | `<10` | 5개 모듈의 재시도 테스트 그대로 통과 |
| structlog | 25.5.0 → 26.1.0 | `<27` | redact·포맷 테스트 통과 |
| ruff (dev) | 0.15.22 → 0.17.3 | `<0.18` | 신규 lint 위반 0건 |

- ruff 0.17부터 Markdown 코드블록도 포맷한다. 그래서 `backend/CLAUDE.md`의 한 줄 압축 예시(`db.add(obj); await db.commit(); ...`)가 쪼개질 뻔했다 → `[tool.ruff] extend-exclude = ["*.md"]`로 막았다.
- `.pre-commit-config.yaml`: rev를 v0.17.3으로 올리고, 훅 id를 `ruff`(이제 legacy alias)에서 `ruff-check`로 바꿨다.
- `.github/dependabot.yml`의 상한 근거 주석을 새 상한(ruff 0.17.x, tenacity `<10`)에 맞췄다.

## B. 테스트 경고 (완료, 운영 코드 변경 없음)

1. **버려진 코루틴**: `test_green_level_uses_fallback_reason`이 세션을 직접 `AsyncMock()`으로 만들어, 동기 메서드 `db.add`가 코루틴을 반환하고 버려졌다. 같은 파일의 `_per_user_session()` 헬퍼(`add = MagicMock()`)를 쓰도록 고쳤다.
2. **짧은 HMAC 키**: `tests/test_security.py`의 테스트 키를 33바이트로 늘렸다 → PyJWT `InsecureKeyLengthWarning` 4건 제거.
3. **회귀 게이트**: `[tool.pytest.ini_options] filterwarnings`에 `error:coroutine .* was never awaited:RuntimeWarning`과 `error::pytest.PytestUnraisableExceptionWarning`을 추가했다. 이 경고는 GC(`__del__`) 시점에 나기 때문에 앞의 것만으로는 unraisable로 삼켜진다. 두 번째 필터까지 있어야 실패로 잡힌다. 수정 전 테스트로 FAILED가 나는 것을 확인했고, 전체 스위트를 2회 돌려 모두 통과했다.

남은 경고 3건: Starlette TestClient httpx 폐기 예고, pykrx `resources.path`, firebase `Message.token`.

## C. 로컬 브랜치 정리 (사용자 실행)
`git branch -d chore/tech-debt-2026-10-28b docs/claude-md-slim` — 둘 다 origin/main에 머지됨.

## 이관
| 항목 | 차단 요인 | 해제 조건 |
|---|---|---|
| `untracked_holdings` 제거 | APK 미배포, 저장소 Variables 3개 비어 있음 | Variables 설정 → `build-android.yml` 성공 → 재배포 |
| pandas 3 | pykrx가 `pandas<3` 요구 | pykrx 업스트림 |
| React 19 / recharts 3 / tailwind 4 / TS 7 / plugin-react 6 / yfinance 1.x / SQLAlchemy 2.1 | 브레이킹 메이저 | 건별 별도 계획 |
| 65 B4·66 P3 실측, 대형 함수 분해 | 운영 로그 없음(Render 슬립) | 상시 기동 후 |
| **신규** FCM `Message.token` → `fid` | `fid`는 Firebase 설치 ID라 앱이 등록하는 FCM 토큰과 다른 값이다. 클라이언트(Capacitor)도 함께 바꿔야 한다 | firebase-admin이 `token`을 실제로 제거하는 릴리스가 나오기 전에 별도 계획 |
| **신규** Starlette TestClient의 httpx 지원 폐기 예고 | API 테스트 다수가 `TestClient` 사용 | Starlette가 실제로 제거할 때 httpx2 또는 `AsyncClient`+`ASGITransport`로 전환 |
| **신규** Python 3.11 런타임(`Dockerfile`) | google api_core가 2027-10-24 이후 3.11 지원 중단 예고 | 3.12+ 전환 별도 계획 |

## 검증
- `ruff check`, `ruff format --check`, `mypy app`, `pip-audit` → 0건
- `pytest --cov=app --cov-fail-under=80` → 3052 passed, 91.79%
- `pre-commit run --all-files` → 전 훅 Passed(새 ruff rev 환경 설치 포함)
