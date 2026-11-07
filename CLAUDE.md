# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 백엔드 전용 규칙/명령: `backend/CLAUDE.md`
> 프론트엔드 전용 규칙/명령: `frontend/CLAUDE.md`

## Project Overview

**Growlio** — 한국투자증권(KIS)/키움증권(Kiwoom)/토스증권(Toss) API를 연동하는 자산관리 웹앱. React SPA + FastAPI 백엔드 구조.

## Prerequisites

Docker가 실행 중이어야 함 (PostgreSQL 5432). Python 3.13+, Node 24(CI·이미지 기준 LTS, 22+에서도 동작), [uv](https://docs.astral.sh/uv/) 필수.

> Android 빌드 시 추가 필요: JDK 21+, Android Studio (SDK 포함).

> **pre-commit hooks**: `make install-backend`가 `pre-commit install`까지 실행함. commit 시 ruff/ruff-format(backend), mypy(backend, venv 있을 때), eslint/prettier(frontend, node_modules 있을 때), trailing-whitespace·end-of-file·merge-conflict·yaml/json 검사. 실패 시 commit 블록. 설정: `.pre-commit-config.yaml`.

## First-time Setup (순서 중요)

```bash
# 1. 인프라 시작
docker compose up -d db

# 2. 의존성 설치
make install-backend   # backend uv sync(uv.lock 기준, CI와 동일) + pre-commit install (최초 1회)
make install-frontend  # npm ci (package-lock.json 기준, CI와 동일)

# 3. 환경 변수 설정
cp backend/.env.example backend/.env    # 값 채우기 (backend/CLAUDE.md Environment 섹션 참고)
cp frontend/.env.example frontend/.env  # 값 채우기 (frontend/CLAUDE.md Environment 섹션 참고)

# 4. DB 마이그레이션
make migrate

# 5. 개발 서버 실행
# macOS / Linux — 터미널 2개:
make dev-backend    # 터미널 1 → localhost:8000
make dev-frontend   # 터미널 2 → localhost:5173
# Windows Git Bash — 터미널 1개:
bash dev.sh         # (또는 make dev)
```

## Makefile 단축 명령

전체 목록은 `Makefile`(`make up`/`down`/`migrate`/`install-*`/`dev`/`test-*`/`lint`/`typecheck`/`format`/`clean`). 주의점만:

- `make migrate-down` — 1단계 롤백
- `make db-reset` — **데이터 전체 삭제**(개발 환경 전용)
- `make dev`·`make build-android-*` — Windows 전용(`bash dev.sh`, `gradlew.bat`). macOS/Linux는 `make dev-backend` + `make dev-frontend`
- `make test-backend`는 커버리지 없이 빠르게, `make test-backend-cov`가 CI와 같은 91% 게이트
- `make lint`·`make typecheck`는 CI와 같은 기준

---

## Architecture

### Monorepo Structure
```
growlio/
├── backend/          # FastAPI (Python 3.13+)
├── frontend/         # React 18 + Vite (TypeScript)
│   └── android/      # Capacitor Android 프로젝트
├── .github/          # GitHub Actions (CI: lint/test/build, Android APK)
├── render.yaml       # Render 백엔드 배포 설정
├── docker-compose.yml
└── Makefile
```

### 핵심 흐름

**계좌 동기화 → 스냅샷 저장 → 대시보드/포트폴리오 집계**

스냅샷 패턴, 데이터 모델 상세 → `backend/CLAUDE.md` 참고.

---

## 배포 & CI

- **실제 운영 배포**: 백엔드는 `render.yaml`(Render, Docker runtime) — 프론트엔드는 `frontend/vercel.json`(Vercel)이 실제 배포 경로. `vercel.json`이 `/api/*` → Render 백엔드로 rewrite하고, CSP를 포함한 보안 헤더도 여기서 설정됨(보안 헤더 수정은 반드시 `vercel.json`에). 새 API prefix 추가 시 `frontend/vercel.json`의 `rewrites`도 함께 확인.
- Render는 `autoDeployTrigger: checksPass` — main의 CI가 통과해야 배포된다(대시보드가 Blueprint 동기화 상태여야 반영).
- **마이그레이션은 자동 실행되지 않는다**(Render 무료 플랜은 pre-deploy 미지원). 스키마 변경이 있으면 **코드 배포 전에** `backend/.env`의 `MIGRATION_DATABASE_URL`을 운영 DB로 지정하고 `cd backend && uv run python scripts/bootstrap_alembic.py && uv run alembic upgrade head`. `/metrics`는 `METRICS_TOKEN`으로 보호된 채 유지되지만 저장소에 수집 구성은 없다.
- `.github/` — 3개 워크플로우: `ci.yml` (lint/test/build + 이미지 빌드 스모크 `docker-build` + 보안 스캔(TruffleHog·bandit·pip-audit·npm audit), push·PR마다), `build-android.yml` (APK 빌드, tag push 또는 workflow_dispatch 수동 실행 — 웹 빌드·`cap sync`·Gradle을 한 잡에서 실행, 저장소 Variables `VITE_API_DOMAIN`/`VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY`/`VITE_REDIRECT_URL` 필수, release는 키스토어 Secrets 필요), `keep-alive.yml` (cron 10분이지만 GitHub 스로틀로 실측 2~9시간 간격 — 슬립은 못 막고 잠든 서버를 가끔 깨워 `periodic_catchup`을 돌리는 정도. 외부 핑 등록 후 제거 예정).
- **Render 무료 플랜은 15분 무요청 시 잠들고 스케줄러도 함께 멈춘다** — `backend/CLAUDE.md` "스케줄러 실행 제약".

---

## 계획 문서 (`docs/plans/`)

대규모 개선 작업은 세션 단위로 독립 실행 가능한 계획서로 쪼개 `docs/plans/`에 저장 — 각 파일은 자기완결적(self-contained)이며 `docs/plans/README.md`가 전체 인덱스(상태/영역/의존성/리스크 표) 역할. 새 로드맵 작업을 시작하기 전 `docs/plans/README.md`에서 관련 항목이 이미 완료/보류 처리됐는지 먼저 확인 — 계획서는 작성 시점의 스냅샷일 뿐이므로, 계획서 내용과 실제 코드가 다르면 코드를 우선.

---

## Key Constraints (공통)

- `avg_price` 및 모든 금액 컬럼은 **항상 KRW** — 해외 종목은 프론트에서 USD × 환율 변환 후 전송
- **월별 추이 쿼리(`get_monthly_trend`)**: `asset_accounts` JOIN + `is_active = TRUE` 필수 — 누락 시 비활성 계좌 스냅샷이 합산되어 금액 수배 부풀림
- **스냅샷 기준**: 월말 스냅샷 개념 없음 — 해당 월 마지막 sync일 값이 월별 대표값으로 사용됨

---

## 작업 마무리 전 검증

CI(`ci.yml`)와 같은 기준 — 커밋/PR 전에 변경 영역에 맞춰 실행:

```bash
make lint            # ruff + eslint --max-warnings 0
make typecheck       # mypy + tsc --noEmit (앱·테스트 tsconfig 둘 다)
make test-backend    # 빠른 반복용 — 최종 확인은 make test-backend-cov (91% 게이트)
make test-frontend   # CI는 --coverage로 실행, 임계값은 frontend/vite.config.ts
```

- Windows pytest 종료 코드 `-1073741819`는 실패가 아님 (`backend/CLAUDE.md` Tests).
- 파일 추가·삭제·이동 시 `backend/CLAUDE.md`·`frontend/CLAUDE.md`의 해당 목록(라우터·서비스·훅·유틸 등)도 함께 갱신 — 각 목록이 "추가/삭제 시 갱신"을 전제로 유지됨.
- CLAUDE.md 항목은 **한 줄 요약 + 코드만 봐선 모르는 함정**까지만. 구현 세부·설계 경위·`plans/NN` 이력은 계획서와 커밋 메시지에 남기고 여기엔 쓰지 않는다(하위 CLAUDE.md는 해당 디렉토리 작업 때마다 통째로 컨텍스트에 로드됨).

---

## 자주 막히는 문제

- `make up` 후 DB 연결 실패: PostgreSQL 준비 대기 필요 — `docker compose logs db` 로 상태 확인 후 재시도
- `EMAXCONNSESSION`/`max clients reached` 오류: `backend/.env`의 `DATABASE_URL`이 Supabase Session Pooler를 가리키는지 확인 — `backend/CLAUDE.md` Environment
- `make migrate`가 Supabase(nestlio와 `public` 스키마 공유) DB에서 버전 충돌/실패: `backend/CLAUDE.md` "Alembic 주의"의 `growlio_alembic_version`
- `dev.sh`는 기본적으로 8000/5173 포트를 점유한 이전(좀비) 프로세스를 강제 종료 후 재기동함. 다른 세션에서 의도적으로 띄워둔 백엔드까지 종료되는 게 문제라면 `bash dev.sh --keep-port`(또는 `make dev-keep-port`) 사용 — 8000이 사용 중이면 종료하지 않고 다음 빈 포트로 대신 구동, 프론트엔드 Vite 프록시도 자동으로 그 포트를 따라감
- 백엔드(8000)만 뜨고 `localhost:5173` 연결 불가: dev.sh를 `Git\usr\bin\bash.exe`로 직접 실행하면 `/usr/bin`이 PATH에 없어 npm이 실패함 — dev.sh가 PATH를 자동 보정하므로, 재발 시 dev.sh 상단의 PATH 보정 블록을 먼저 확인
- pre-commit hook 실패: `make lint` 로 로컬 점검 후 커밋 — mypy 타입 오류가 가장 흔한 원인
- **동시 세션 작업**: 이 저장소는 여러 창/세션에서 병행 작업되는 경우가 잦음 — 계획 수립·구현 도중 `git status`가 대화 시작 시점과 달라져 있다면 다른 세션의 진행 중 작업일 가능성이 높음. 무시하거나 되돌리지 말고 먼저 `git diff`로 변경 내용을 확인할 것
