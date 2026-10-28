# 86. 기술부채 재점검 (2026-10-28d, 계획 85 직후)

> 상태: **A·B·C·D 완료**. E(머지된 로컬·원격 브랜치 삭제)는 사용자가 직접 실행한다.

## Context

계획 85(PR #172) 머지 직후 재점검이다. 정적 검사·취약점은 이번에도 0건이었다. 대신 **의존성이 자동으로 따라오지 않는 사각지대** 2개를 Dependabot(uv) 실행 로그에서 찾았다.

| 점검 | 결과 |
|---|---|
| ruff check/format, mypy(263), tsc, `eslint . --max-warnings 0` | 0건 |
| npm audit --omit=dev | 0건 |
| npm Dependabot | 정상(미반영 minor는 기본 cooldown 때문) |
| **uv Dependabot 로그** | `uvicorn[standard]`·`sqlalchemy[asyncio]`·`sentry-sdk[fastapi]`·`pydantic[email]`, numpy·scipy → `No update possible` |

스크래치 복사본에서 `uv lock --upgrade-package`를 돌려 보니 4개 모두 uv로는 정상 해석됐다. 막힌 패키지가 **정확히 extras 표기를 쓴 의존성 전부**여서, 원인은 이 표기다. numpy 2.5·scipy 1.18은 Python 3.12 이상을 요구해 3.11용 구버전 포크에 묶여 있었다. 85에서 "2027-10까지 여유"라며 이관했던 Python 3.11 런타임이 실제로는 이미 업데이트를 막고 있었던 것이다.

## A. Python 3.11 → 3.13 (완료)
- `requires-python`, ruff `target-version`, mypy `python_version`, `Dockerfile` 2스테이지, `ci.yml`, 루트 `CLAUDE.md`를 모두 3.13으로 바꿨다.
- 새 target에서 나온 UP043(`AsyncGenerator[X, None]`)·UP047(PEP 695 제네릭 함수 5곳)·UP040(`type` 별칭 1곳)을 정리했다. ruff `--unsafe-fixes`는 TypeVar 이름이 본문과 어긋나게 바꿀 수 있어서, 규칙별로 적용한 뒤 diff를 확인했다.
- **pre-commit이 어디에도 선언돼 있지 않았다.** 옛 .venv에 수동으로 설치돼 있었을 뿐이라 venv를 재생성하자 커밋 훅이 깨졌다 → dev 의존성에 추가하고, Makefile은 `uv run --project backend pre-commit install`로 바꿨다.
- CI가 이미지를 빌드하지 않는다(로컬에도 Docker 없음). 그래서 `uv pip compile --python-platform x86_64-manylinux_2_28 --python-version 3.13 --only-binary :all:`로 prod 102개 패키지 전부 wheel이 있음을 확인했다.

## B. extras 표기 제거 (완료)
extra가 끌어오던 패키지를 각 패키지 METADATA의 `Requires-Dist`(marker 포함)대로 풀어 썼다. `uv export --no-dev` 결과는 전후 동일하다. `backend/CLAUDE.md`·`dependabot.yml`에 "extras 표기 금지" 한 줄을 추가했다.

## C. 막혀 있던 업데이트 반영 (완료)
`uv lock --upgrade`로 반영했다(pyproject 상한 안). uvicorn 0.54, sentry-sdk 2.73, pydantic 2.14, **SQLAlchemy 2.1.6**, numpy 2.5, scipy 1.18, protobuf 7 등이다.
- SQLAlchemy 2.1: `Select[tuple[X]]` → `Select[X]`(`_account_queries.py`). 다중 컬럼 결과 행에 nullable 컬럼 타입(`UUID | None`)이 드러나 mypy 6건이 생겼는데, 모두 SQL 필터(`in_()`/`isnot(None)`)로 None이 오지 않는 자리라 타입만 좁혔다.

## D. TestClient → httpx2 (완료)
dev 의존성에 `httpx2`(pydantic/httpx2, httpx 원작자)를 추가했다. Starlette 1.8+ testclient가 우선 import하는 패키지라서, 넣으면 폐기 경고가 사라진다.

## E. 저장소 위생 (사용자 실행)
`git branch -d chore/tech-debt-2026-10-28c && git push origin --delete chore/tech-debt-2026-10-28c` — #172로 머지됨.

## 남은 테스트 경고 (모두 외부 요인)
| 경고 | 출처 | 비고 |
|---|---|---|
| FCM `Message.token` 폐기 예고 | firebase-admin 7 | 이관 유지 |
| NumPy generic timedelta 폐기 예고 | pandas 2.3 내부(numpy 2.5 조합) — **87에서 정정**: 절반은 테스트의 `pd.Timedelta(days=)`가 출처였음 | pandas 3는 pykrx가 막고 있음. numpy가 오류로 바꾸는 릴리스는 Dependabot PR의 CI에서 잡힌다 |
| sqlite `ResourceWarning: unclosed database` | yfinance 내부 캐시(Python 3.13부터 경고) | 결과 영향 없음 |

## 이관
| 항목 | 차단 요인 | 해제 조건 |
|---|---|---|
| `untracked_holdings` 제거 | APK 저장소 Variables 3개 비어 있음 | Variables 설정 → `build-android.yml` 성공 → 재배포 |
| pandas 3 | pykrx `pandas<3` | pykrx 업스트림 |
| React 19 / recharts 3 / tailwind 4 / TS 7 / plugin-react 6 / yfinance 1.x | 브레이킹 메이저 | 건별 별도 계획 |
| FCM `Message.token` → `fid` | FID ≠ FCM 토큰, 클라이언트 동반 변경 | `token` 제거 릴리스 전 별도 계획 |
| 65 B4·66 P3 실측 | 운영 로그 없음(Render 슬립) | 상시 기동 후 |

## 검증
- `ruff check`, `ruff format --check`, `mypy app`(263) → 0건, `pre-commit run --all-files` → 전 훅 Passed
- `pytest --cov=app --cov-fail-under=80` → 3052 passed, 91.77% (Python 3.13.13)
- 배포 후: Render 빌드 성공 + `/health` 확인. 다음 주 Dependabot uv 로그에서 위 4개 패키지가 `No update possible`에서 빠졌는지 확인
