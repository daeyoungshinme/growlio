# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> 백엔드 전용 규칙/명령: `backend/CLAUDE.md`
> 프론트엔드 전용 규칙/명령: `frontend/CLAUDE.md`

## Project Overview

**Growlio** — 한국투자증권(KIS)/LS증권 API, 금융결제원 오픈뱅킹을 연동하는 자산관리 웹앱. React SPA + FastAPI 백엔드 구조.

## Prerequisites

Docker가 실행 중이어야 함 (PostgreSQL 5432, Redis 6379).

## First-time Setup (순서 중요)

```bash
# 1. 인프라 시작
docker compose up -d db redis

# 2. 의존성 설치
cd backend && uv venv  # 최초 1회: 가상환경 생성
make install-backend   # pip install
make install-frontend  # npm install

# 3. 환경 변수 설정
cp backend/.env.example backend/.env  # 값 채우기 (backend/CLAUDE.md Environment 섹션 참고)

# 4. DB 마이그레이션
make migrate

# 5. 개발 서버 실행
bash dev.sh   # 백엔드 + 프론트엔드 동시 실행 (Ctrl+C로 종료)
```

## Makefile 단축 명령

```bash
make up               # docker compose up -d db redis
make down             # docker compose down
make migrate          # cd backend && alembic upgrade head
make install-backend  # cd backend && pip install uv && uv pip install -e ".[dev]"
make install-frontend # cd frontend && npm install
make dev              # 백엔드 + 프론트엔드 동시 실행 (bash dev.sh)
make dev-backend      # 백엔드만 (localhost:8000)
make dev-frontend     # 프론트엔드만 (localhost:5173)
make test-backend     # cd backend && pytest
make test-frontend    # cd frontend && npm run test
make lint             # ruff (backend) + eslint (frontend)
make typecheck        # mypy (backend) + tsc build (frontend)
```

## Development Servers (요약)

```bash
# 통합 실행 (권장 — Mac/Windows Git Bash 동일)
bash dev.sh    # 백엔드 + 프론트엔드 동시 실행, Ctrl+C로 함께 종료
make dev       # 동일

# 개별 실행
make dev-backend   # 백엔드만 (localhost:8000)
make dev-frontend  # 프론트엔드만 (localhost:5173)
```

---

## Architecture

### Monorepo Structure
```
growlio/
├── backend/          # FastAPI (Python 3.11+)
├── frontend/         # React 18 + Vite (TypeScript)
├── nginx/            # nginx 리버스 프록시 (포트 80 → frontend 정적파일 + /api/* → backend:8000)
├── docker-compose.yml
└── Makefile
```

### 핵심 흐름

**계좌 동기화 → 스냅샷 저장 → 대시보드/포트폴리오 집계**

**스냅샷 패턴:** 계좌 sync 시 `_upsert_snapshot()` 호출 → 오늘 날짜 스냅샷 upsert. 월말 저장 개념 없음.
- 대시보드/포트폴리오: `MAX(snapshot_date)` subquery로 최신 스냅샷만 집계
- 월별 추이(`_get_monthly_trend`): CTE + ROW_NUMBER()로 계좌별 월 최신 스냅샷 1개만 선택. 반드시 `asset_accounts.is_active = TRUE` JOIN 필요 — 미적용 시 비활성 계좌 스냅샷이 합산에 포함됨

### 데이터 모델 핵심

- `AssetAccount` — 계좌 마스터. `asset_type`(BANK_ACCOUNT/DEPOSIT/STOCK_KIS/STOCK_LS/STOCK_OTHER/CASH_OTHER/OTHER)과 `data_source`(MANUAL/KIS_API/LS_SEC/OPEN_BANKING) 조합으로 동작 결정
- `AssetSnapshot` — 일별 계좌 스냅샷. `positions` JSONB에 종목 배열 저장. `(account_id, snapshot_date)` unique constraint
- `Transaction` — 입출금/배당 내역. `transaction_type` = DEPOSIT/WITHDRAWAL/DIVIDEND
- `UserSettings` — KIS/LS 자격증명(AES-256 암호화 저장), 투자 목표, 연간 입금 목표

---

## Key Constraints (공통)

- `avg_price` 및 모든 금액 컬럼은 **항상 KRW** — 해외 종목은 프론트에서 USD × 환율 변환 후 전송
- `asset_type_allocation`은 전체 자산 유형 반환. 포트폴리오 페이지에서 STOCK 타입만 프론트엔드 필터링으로 표시
- `APP_ENV=development`일 때만 `/docs` Swagger UI 활성화
