# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 백엔드 전용 규칙/명령: `backend/CLAUDE.md`
> 프론트엔드 전용 규칙/명령: `frontend/CLAUDE.md`

## Project Overview

**Growlio** — 한국투자증권(KIS)/키움증권(Kiwoom) API, 금융결제원 오픈뱅킹을 연동하는 자산관리 웹앱. React SPA + FastAPI 백엔드 구조.

## Prerequisites

Docker가 실행 중이어야 함 (PostgreSQL 5432, Redis 6379). Python 3.11+, Node 18+, [uv](https://docs.astral.sh/uv/) 필수.

> **pre-commit hooks** 설정됨 — commit 시 ruff, mypy, eslint, trailing-whitespace 자동 실행. 실패 시 commit 블록.

## First-time Setup (순서 중요)

```bash
# 1. 인프라 시작
docker compose up -d db redis

# 2. 의존성 설치
cd backend && uv venv  # 최초 1회: 가상환경 생성
make install-backend   # pip install
make install-frontend  # npm install

# 3. 환경 변수 설정
cp backend/.env.example backend/.env    # 값 채우기 (backend/CLAUDE.md Environment 섹션 참고)
cp frontend/.env.example frontend/.env  # 값 채우기 (frontend/CLAUDE.md Environment 섹션 참고)

# 4. DB 마이그레이션
make migrate

# 5. 개발 서버 실행
# Windows (Git Bash)
bash dev.sh         # 또는: make dev (백엔드 + 프론트엔드 동시 실행)
# macOS / Linux — 터미널 2개에서 각각 실행:
make dev-backend    # 터미널 1 (localhost:8000)
make dev-frontend   # 터미널 2 (localhost:5173)
```

## Makefile 단축 명령

```bash
make up               # docker compose up -d db redis
make down             # docker compose down
make migrate          # cd backend && alembic upgrade head
make install-backend  # cd backend && uv venv && uv pip install -e ".[dev]"
make install-frontend # cd frontend && npm install
make dev              # 백엔드 + 프론트엔드 동시 실행 (bash dev.sh) — Windows Git Bash 전용
make dev-backend      # 백엔드만 (localhost:8000)
make dev-frontend     # 프론트엔드만 (localhost:5173)
make test-backend     # cd backend && pytest
make test-frontend    # cd frontend && npm run test
make lint             # ruff (backend) + eslint (frontend)
make typecheck        # mypy (backend) + tsc --noEmit (frontend)
make clean            # frontend/dist, pytest_cache, ruff_cache 삭제
make format           # ruff --fix (backend) + prettier --write (frontend)
make db-reset         # docker compose down -v + up + migrate (데이터 초기화)
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
├── nginx/            # nginx 리버스 프록시 (포트 80 → frontend 정적파일 + /api/* → backend:8000)
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
- `nginx/` — 포트 80 리버스 프록시. `/api/*` → backend:8000, 그 외 → frontend 정적파일. 새 API prefix 추가 시 수정 필요.
- `.github/` — CI: lint/test/build (push/PR마다 실행). Android APK 빌드 workflow 포함.

---

## Key Constraints (공통)

- `avg_price` 및 모든 금액 컬럼은 **항상 KRW** — 해외 종목은 프론트에서 USD × 환율 변환 후 전송
- **월별 추이 쿼리**: `is_active = TRUE` 필터 필수 — 누락 시 비활성 계좌 스냅샷이 합산되어 금액 수배 부풀림
- **스냅샷 기준**: 월말 스냅샷 개념 없음 — 해당 월 마지막 sync일 값이 월별 대표값으로 사용됨
