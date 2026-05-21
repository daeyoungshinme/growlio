.PHONY: up down migrate install-backend install-frontend dev-backend dev-frontend \
        test-backend test-frontend lint typecheck

up:
	docker compose up -d db redis

down:
	docker compose down

migrate:
	cd backend && alembic upgrade head

install-backend:
	cd backend && pip install uv && uv pip install -e ".[dev]"

install-frontend:
	cd frontend && npm install

dev-backend:
	cd backend && uvicorn app.main:app --reload

dev-frontend:
	cd frontend && npm run dev

test-backend:
	cd backend && .venv/bin/pytest

test-frontend:
	cd frontend && npm run test

lint:
	cd backend && .venv/bin/ruff check .
	cd frontend && npm run lint

typecheck:
	cd backend && .venv/bin/mypy app/
	cd frontend && npm run build
