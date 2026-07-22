# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 백엔드 전용 규칙/명령: `backend/CLAUDE.md`
> 프론트엔드 전용 규칙/명령: `frontend/CLAUDE.md`

## Project Overview

**Growlio** — 한국투자증권(KIS)/키움증권(Kiwoom) API를 연동하는 자산관리 웹앱. React SPA + FastAPI 백엔드 구조.

## Prerequisites

Docker가 실행 중이어야 함 (PostgreSQL 5432, Redis 6379). Python 3.11+, Node 22+, [uv](https://docs.astral.sh/uv/) 필수.

> Android 빌드 시 추가 필요: JDK 17+, Android Studio (SDK 포함).

> **pre-commit hooks** 설정됨 — commit 시 ruff, mypy, eslint, trailing-whitespace 자동 실행. 실패 시 commit 블록.

## First-time Setup (순서 중요)

```bash
# 1. 인프라 시작
docker compose up -d db redis

# 2. 의존성 설치
make install-backend   # backend uv venv + pip install (최초 1회)
make install-frontend  # npm install

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

```bash
make up               # docker compose up -d db redis
make down             # docker compose down
make migrate          # cd backend && alembic upgrade head
make migrate-down     # cd backend && alembic downgrade -1 (1단계 롤백)
make install-backend  # cd backend && uv venv && uv pip install -e ".[dev]"
make install-frontend # cd frontend && npm install
make dev              # 백엔드 + 프론트엔드 동시 실행 (bash dev.sh) — Windows Git Bash 전용
make dev-backend      # 백엔드만 (localhost:8000)
make dev-frontend     # 프론트엔드만 (localhost:5173)
make test-backend     # cd backend && pytest
make test-frontend    # cd frontend && npm run test
# E2E (Makefile 없음): cd frontend && npx playwright test   # dev 서버(5173) 실행 중 필요
make lint             # ruff (backend) + eslint (frontend)
make typecheck        # mypy (backend) + tsc --noEmit (frontend)
make clean            # frontend/dist, pytest_cache, ruff_cache 삭제
make format           # ruff format + ruff --fix (backend) + prettier --write (frontend)
make format-backend   # ruff format + ruff --fix (backend만)
make db-reset         # docker compose down -v + up + migrate (**데이터 전체 삭제** — 개발 환경 전용)
make build-android-debug    # npm build + cap sync + gradlew assembleDebug
make build-android-release  # npm build + cap sync + gradlew assembleRelease
# Android 빌드 전제: JDK 17+, Android Studio (SDK 설치 포함) 필요
```

---

## Architecture

### Monorepo Structure
```
growlio/
├── backend/          # FastAPI (Python 3.11+)
├── frontend/         # React 18 + Vite (TypeScript)
│   └── android/      # Capacitor Android 프로젝트
├── nginx/            # nginx 리버스 프록시 (프로덕션/Docker 전용 — 로컬 개발에서는 미사용; Vite dev server가 /api/* 프록시 처리)
├── monitoring/       # Prometheus 설정(prometheus.yml) + Grafana 대시보드
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

- `render.yaml` — 백엔드 Render 배포 설정. 프론트엔드는 별도 호스팅.
- `nginx/` — 포트 80 리버스 프록시. `/api/*` → backend:8000, 그 외 → frontend 정적파일. 새 API prefix 추가 시 `nginx/nginx.conf`의 `location` 블록 수정 필요.
- `monitoring/` — Prometheus 설정(`prometheus.yml`) + Grafana 대시보드. `docker compose --profile monitoring up -d` 로 실행 (Prometheus `:9090`, Grafana `:3000`).
- `.github/` — 3개 워크플로우: `ci.yml` (lint/test/build, push·PR마다), `build-android.yml` (APK 빌드, tag push 또는 workflow_dispatch 수동 실행), `e2e.yml` (Playwright E2E, PR 전용).

---

## 계획 문서 (`docs/plans/`)

대규모 개선 작업은 세션 단위로 독립 실행 가능한 계획서로 쪼개 `docs/plans/`에 저장 — 각 파일은 자기완결적(self-contained)이며 `docs/plans/README.md`가 전체 인덱스(상태/영역/의존성/리스크 표) 역할. 새 로드맵 작업을 시작하기 전 `docs/plans/README.md`에서 관련 항목이 이미 완료/보류 처리됐는지 먼저 확인 — 계획서는 작성 시점의 스냅샷일 뿐이므로, 계획서 내용과 실제 코드가 다르면 코드를 우선.

---

## Key Constraints (공통)

- `avg_price` 및 모든 금액 컬럼은 **항상 KRW** — 해외 종목은 프론트에서 USD × 환율 변환 후 전송
- **월별 추이 쿼리**: `is_active = TRUE` 필터 필수 — 누락 시 비활성 계좌 스냅샷이 합산되어 금액 수배 부풀림
- **스냅샷 기준**: 월말 스냅샷 개념 없음 — 해당 월 마지막 sync일 값이 월별 대표값으로 사용됨

---

## 자주 막히는 문제

- `make up` 후 DB 연결 실패: PostgreSQL 준비 대기 필요 — `docker compose logs db` 로 상태 확인 후 재시도
- alembic revision 생성 후 반드시 `alembic/env.py`에 새 모델 import 추가 (누락 시 autogenerate에서 모델 인식 못함)
- pre-commit hook 실패: `make lint` 로 로컬 점검 후 커밋 — mypy 타입 오류가 가장 흔한 원인
- **동시 세션 작업**: 이 저장소는 여러 창/세션에서 병행 작업되는 경우가 잦음 — 계획 수립·구현 도중 `git status`가 대화 시작 시점과 달라져 있다면 다른 세션의 진행 중 작업일 가능성이 높음. 무시하거나 되돌리지 말고 먼저 `git diff`로 변경 내용을 확인할 것
