# 84. 기술부채 재점검 (2026-10-28, 계획 83 직후)

> 상태: **B·C 완료**. A(원격 브랜치·worktree·로컬 브랜치 삭제)는 사용자가 직접 실행한다. 이관 항목은 계획 80·83과 같다.

## Context

계획 83(PR #169)이 머지된 직후 다시 점검했다. 그 사이 새 코드가 없어서 코드 재감사 대신 세 가지를 봤다. 정적 검사를 다시 돌렸고, 저장소·로컬 환경 위생을 확인했고, 이관 항목의 차단 요인이 아직 유효한지 재확인했다.

| 항목 | 결과 |
|---|---|
| ruff check/format, mypy(263파일), tsc, `eslint src` | 0건 |
| pip-audit, npm audit --omit=dev | 취약점 0건 |
| TODO/FIXME | 0건 |
| skip 테스트 | 2건, 둘 다 의도된 조건부 skip |
| 최대 파일 | 백엔드 675줄(tactical_allocation_service), 프론트 705줄(StockHoldingsTable) |

코드 수준의 기술부채는 남아 있지 않다.

## A. 저장소 위생 (사용자 실행)
- 원격 `feat/market-status-tactical-picker-2026-10-27`(#167 CLOSED, 버려진 변형) 삭제: `git push origin --delete feat/market-status-tactical-picker-2026-10-27`
- worktree `D:/project/growlio-pr82`(#165 머지됨, status clean) 제거: `git worktree remove D:/project/growlio-pr82`
- origin/main에 머지된 로컬 브랜치 약 75개 삭제: `git branch --merged origin/main | grep -vE '^\*|main$' | xargs git branch -d`. `-d`(안전 삭제)만 쓴다.
- 이미 삭제된 원격 브랜치를 가리키던 원격 추적 ref 19개는 `git fetch --prune`으로 정리했다.
- 삭제하지 말 것: `docs/claude-md-slim`은 같은 시각 다른 세션이 올린 진행 중 브랜치다.

## B. 로컬 환경 동기화 (완료)
- 로컬 node_modules가 lockfile보다 뒤처져 있었다. 대표적으로 `@sentry/vite-plugin`은 lock이 11.9.0인데 설치본은 5.4.1이었다.
- `npm ci`는 실행 중인 Vite dev 서버가 rolldown 네이티브 바이너리를 잠그고 있어 EPERM으로 실패했다. `npm install`로 lock에 맞췄다(package-lock 변경 없음).
- CI는 `npm ci`를 쓰므로 영향이 없었다. 로컬 빌드만 구버전 플러그인으로 돌고 있었다.

## C. eslint 설정 보강 (완료, `frontend/eslint.config.js`)
- `npx eslint .`를 돌리면 2633건이 나왔다. `make lint`와 pre-commit은 `eslint src`라 문제가 없었다.
  - `android/app/src/main/assets/public`(cap sync 산출물)에서 2632건
  - `scripts/generate-icons.mjs`의 Node 전역 no-undef 3건
- 수정: `ignores`에 `android`와 `coverage`를 추가하고, `scripts/**/*.mjs`에 `globals.node`를 준다. 이제 `npx eslint . --max-warnings 0`이 0건이다.

## 이관
| 항목 | 차단 요인 | 해제 조건 |
|---|---|---|
| `untracked_holdings` 제거 | APK 미배포. 마지막 빌드는 2026-05-25 실패이고, 저장소 Variables(`VITE_API_DOMAIN` 등 3개)가 비어 있음 | 사용자가 Variables를 설정하고 `build-android.yml` 수동 실행 성공 후 재배포 |
| pandas 3 | pykrx가 `pandas<3`을 요구 | pykrx 업스트림 지원 |
| React 19 / recharts 3 / tailwind 4 / TS 7 / @vitejs/plugin-react 6 / yfinance 1.x / SQLAlchemy 2.1 | 브레이킹 메이저 | 건별 별도 계획 |
| minor/patch 범프(axios 1.21, vite 8.3.5, tanstack 5.105 등) | 없음 | Dependabot 주간 그룹 PR |
| 65 B4·66 P3 실측, 대형 함수 분해 | 운영 로그 없음(Render 슬립) | 상시 기동 후 측정 |

## 검증
- `make lint`, `make typecheck`, `make test-frontend`, `npm run build`
- `npx eslint . --max-warnings 0` → 0건
- `npm ls @sentry/vite-plugin` → 11.9.0
